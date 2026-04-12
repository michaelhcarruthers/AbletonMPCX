"""Clip arrangement tools — arrangement view clips and automation."""
from __future__ import annotations
import logging
import math
from typing import Any
from helpers import mcp, _send, _send_silent
from tools.session import _get_time_sig_numerator, _bars_beats_to_song_time
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Arrangement clip tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_detail_clip(include_notes: bool = True) -> dict:
    """Return info and MIDI notes for the clip currently open in Live's Detail View."""
    result = _send_silent("get_detail_clip", {"include_notes": include_notes})
    return result


@mcp.tool()
def list_arrangement_clips(
    track_index: int | None = None,
    start_bar: int | None = None,
    end_bar: int | None = None,
    slim: bool = True,
) -> dict:
    """List all clips in the arrangement view, optionally filtered by track or time range. slim=True (default) returns only clip_index, start_time, length, name per clip — use this when you don't need full clip details. Pass slim=False for full clip data including loop, color and mute info. Note: when slim=True, track_index filter is applied server-side; start_bar/end_bar filters are not applied in slim mode."""
    if track_index is not None:
        tracks = _send("get_tracks", {"slim": True})
        if isinstance(tracks, list) and (track_index < 0 or track_index >= len(tracks)):
            return {"clips": [], "total_clips": 0, "error": f"track_index {track_index} out of range — song has {len(tracks)} tracks"}
    server_params: dict[str, Any] = {"slim": slim}
    if slim and track_index is not None:
        # In slim mode the server applies the track filter since track_index is
        # not included in the per-clip slim response
        server_params["track_index"] = track_index
    try:
        raw = _send("get_arrangement_clips", server_params)
        all_clips = raw if isinstance(raw, list) else raw.get("clips", [])
    except Exception as e:
        return {
            "clips": [],
            "total_clips": 0,
            "filtered_by": {},
            "error": str(e),
            "prompt": (
                "Could not read arrangement clips directly (Live API limitation). "
                "To read a specific arrangement clip: click it in Live's Arrangement View "
                "to open it in the Detail View, then call get_detail_clip()."
            ),
        }

    if slim:
        return {"clips": all_clips, "total_clips": len(all_clips)}

    clips = []
    try:
        _tsn = int(_send("get_song_info", {}).get("time_signature_numerator", 4))
    except Exception:
        _tsn = 4
    for clip in all_clips:
        t_idx = clip.get("track_index", clip.get("track_idx", 0))
        t_name = clip.get("track_name", "")
        c_idx = clip.get("clip_index", clip.get("clip_idx", 0))
        c_name = clip.get("name", clip.get("clip_name", ""))
        start_time = float(clip.get("start_time", clip.get("start", 0.0)))
        end_time = float(clip.get("end_time", clip.get("end", start_time)))
        # Convert beat times to bars using the actual time signature numerator
        clip_start_bar = int(start_time // _tsn) + 1
        length_beats = max(0.0, end_time - start_time)
        length_bars = length_beats / float(_tsn)
        is_midi = bool(clip.get("is_midi_clip", clip.get("is_midi", False)))
        is_audio = not is_midi
        color = clip.get("color", 0)
        muted = bool(clip.get("muted", clip.get("mute", False)))

        # Apply filters
        if track_index is not None and t_idx != track_index:
            continue
        if start_bar is not None and clip_start_bar < start_bar:
            continue
        if end_bar is not None and clip_start_bar >= end_bar:
            continue

        clips.append({
            "track_index": t_idx,
            "track_name": t_name,
            "clip_index": c_idx,
            "clip_name": c_name,
            "start_time": start_time,
            "end_time": end_time,
            "start_bar": clip_start_bar,
            "length_bars": length_bars,
            "is_audio": is_audio,
            "is_midi": is_midi,
            "color": color,
            "muted": muted,
        })

    filtered_by: dict[str, Any] = {}
    if track_index is not None:
        filtered_by["track_index"] = track_index
    if start_bar is not None:
        filtered_by["start_bar"] = start_bar
    if end_bar is not None:
        filtered_by["end_bar"] = end_bar

    return {
        "clips": clips,
        "total_clips": len(clips),
        "filtered_by": filtered_by,
    }


@mcp.tool()
def get_arrangement_clip_notes(
    track_index: int,
    clip_index: int,
) -> dict:
    """Read the MIDI notes from a specific arrangement clip."""
    tracks = _send("get_tracks", {"slim": True})
    if isinstance(tracks, list) and (track_index < 0 or track_index >= len(tracks)):
        return {"error": f"track_index {track_index} out of range — song has {len(tracks)} tracks"}
    result = _send_silent("get_arrangement_clip_notes", {
        "track_index": track_index,
        "clip_index": clip_index,
    })
    if isinstance(result, dict):
        result["note_count"] = len(result.get("notes", []))
    return result


@mcp.tool()
def delete_arrangement_clip(track_index: int, clip_index: int) -> dict:
    """Delete a clip from the Arrangement View by track index and clip index."""
    return _send("delete_arrangement_clip", {
        "track_index": track_index,
        "clip_index": clip_index,
    })


@mcp.tool()
def delete_arrangement_clip_batch(clips: list[dict]) -> dict:
    """Delete multiple arrangement clips in a single call.

    Each entry in clips must be a dict with:
      - track_index (int)
      - clip_index (int)

    Returns a summary of deleted and failed clips.
    """
    deleted = []
    failed = []
    for clip in clips:
        track_index = clip["track_index"]
        clip_index = clip["clip_index"]
        try:
            _send("delete_arrangement_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
            })
            deleted.append({"track_index": track_index, "clip_index": clip_index})
        except RuntimeError as e:
            failed.append({"track_index": track_index, "clip_index": clip_index, "error": str(e)})
    return {
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }


@mcp.tool()
def duplicate_arrangement_clip(
    track_index: int,
    clip_index: int,
    target_time_beats: float,
) -> dict:
    """Copy an existing Arrangement clip to a new position on the same track.

    track_index: zero-based track index
    clip_index: zero-based index into track.arrangement_clips
    target_time_beats: absolute song position in beats where the copy should start

    Uses the Live API duplicate_clip_to_time — works for both audio and MIDI clips.
    """
    result = _send("duplicate_clip_to_time", {
        "track_index": track_index,
        "clip_index": clip_index,
        "target_time": target_time_beats,
    })
    return result


@mcp.tool()
def duplicate_arrangement_clip_batch(
    operations: list[dict],
) -> dict:
    """Copy multiple Arrangement clips to new timeline positions in a single call.

    Each operation must be a dict with:
      - track_index (int)
      - clip_index (int): source clip index in track.arrangement_clips
      - target_times (list[float]): list of absolute beat positions to copy to

    Returns a summary of successful copies and failures.
    """
    results = []
    total_copies = 0

    for op in operations:
        track_index = op["track_index"]
        clip_index = op["clip_index"]
        target_times = op["target_times"]
        copies = []
        failed = []

        for t in target_times:
            try:
                _send("duplicate_clip_to_time", {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "target_time": t,
                })
                copies.append(t)
                total_copies += 1
            except RuntimeError as e:
                failed.append({"target_time": t, "error": str(e)})

        results.append({
            "track_index": track_index,
            "clip_index": clip_index,
            "copies_made": len(copies),
            "target_times": copies,
            "failed": failed,
        })

    return {
        "results": results,
        "total_copies": total_copies,
        "operations_count": len(operations),
    }


@mcp.tool()
def place_clip_in_arrangement_batch(
    placements: list[dict],
    time_signature_numerator: int | None = None,
) -> dict:
    """Place multiple Session View clips into the Arrangement View in a single call.

    Each entry in placements must be a dict with:
      - track_index (int)
      - clip_index (int)
      - start_bar (int): 1-indexed bar number
      - start_beat (float, optional): beat within the bar, default 1.0

    time_signature_numerator: override the song time signature numerator (default: read from song).

    Returns a summary of placed and failed clips.
    """
    tsn = _get_time_sig_numerator(time_signature_numerator)

    placed = []
    failed = []

    for p in placements:
        track_index = p["track_index"]
        clip_index = p["clip_index"]
        start_bar = p["start_bar"]
        start_beat = float(p.get("start_beat", 1.0))
        start_time_beats = _bars_beats_to_song_time(start_bar, start_beat, tsn)

        clip_name = ""
        clip_length_beats = 0.0
        try:
            clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
            clip_name = clip_info.get("name", "")
            clip_length_beats = float(clip_info.get("length", 0.0))
        except RuntimeError:
            pass

        try:
            try:
                _send("duplicate_clip_to_arrangement", {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "time": start_time_beats,
                })
            except RuntimeError:
                _send("copy_clip_to_arrangement", {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "time": start_time_beats,
                })
            placed.append({
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip_name,
                "start_bar": start_bar,
                "start_beat": start_beat,
                "start_time_beats": start_time_beats,
                "clip_length_beats": clip_length_beats,
            })
        except RuntimeError as e:
            failed.append({
                "track_index": track_index,
                "clip_index": clip_index,
                "start_bar": start_bar,
                "error": str(e),
            })

    return {
        "placed_count": len(placed),
        "failed_count": len(failed),
        "placed": placed,
        "failed": failed,
        "time_signature_numerator": tsn,
    }


@mcp.tool()
def get_arrangement_automation(
    track_index: int,
    device_index: int | None,
    parameter_index: int,
    start_beat: float = 0.0,
    end_beat: float | None = None,
) -> dict:
    """Read automation points for a parameter in the Arrangement View."""
    params: dict = {
        "track_index": track_index,
        "parameter_index": parameter_index,
        "start_beat": start_beat,
    }
    if device_index is not None:
        params["device_index"] = device_index
    if end_beat is not None:
        params["end_beat"] = end_beat
    result = _send("get_arrangement_automation", params)
    if isinstance(result, dict):
        result["point_count"] = len(result.get("points", []))
    return result


@mcp.tool()
def clear_arrangement_automation(
    track_index: int,
    device_index: int | None,
    parameter_index: int,
    start_beat: float = 0.0,
    end_beat: float | None = None,
) -> dict:
    """Clear all automation points from a parameter in the Arrangement View within the given time range."""
    params: dict = {
        "track_index": track_index,
        "parameter_index": parameter_index,
        "start_beat": start_beat,
    }
    if device_index is not None:
        params["device_index"] = device_index
    if end_beat is not None:
        params["end_beat"] = end_beat
    return _send("clear_arrangement_automation", params)


@mcp.tool()
def get_arrangement_overview() -> dict:
    """Return a high-level structural overview of the arrangement."""
    # Fetch all arrangement clips (unfiltered)
    clips_result = list_arrangement_clips(slim=False)
    all_clips = clips_result["clips"]

    # Tempo
    try:
        song_info = _send("get_song_info", {})
        tempo = float(song_info.get("tempo", 0.0))
    except Exception:
        tempo = 0.0

    if not all_clips:
        return {
            "total_bars": 0,
            "tracks_with_clips": 0,
            "clips_per_track": [],
            "empty_regions": [],
            "total_clips": 0,
            "tempo": tempo,
        }

    # Build per-track summary
    track_map: dict[int, dict] = {}
    for clip in all_clips:
        t_idx = clip["track_index"]
        if t_idx not in track_map:
            track_map[t_idx] = {
                "track_index": t_idx,
                "track_name": clip["track_name"],
                "clip_count": 0,
                "first_bar": clip["start_bar"],
                "last_bar": clip["start_bar"],
            }
        entry = track_map[t_idx]
        entry["clip_count"] += 1
        if clip["start_bar"] < entry["first_bar"]:
            entry["first_bar"] = clip["start_bar"]
        clip_last_bar = int(clip["start_bar"] + clip["length_bars"])
        if clip_last_bar > entry["last_bar"]:
            entry["last_bar"] = clip_last_bar

    clips_per_track = sorted(track_map.values(), key=lambda x: x["track_index"])

    # Total bars = last bar across all clips
    total_bars = max(
        int(c["start_bar"] + c["length_bars"]) for c in all_clips
    )

    # Detect empty regions: bars where NO track has a clip
    # Build a set of all "occupied" bars; use math.ceil so sub-bar clips still
    # occupy at least 1 bar, consistent with how length_bars is displayed.
    occupied_bars: set[int] = set()
    for clip in all_clips:
        bar_start = clip["start_bar"]
        bar_end = bar_start + max(1, math.ceil(clip["length_bars"]))
        for b in range(bar_start, bar_end):
            occupied_bars.add(b)

    empty_regions = []
    in_gap = False
    gap_start = 1
    for bar in range(1, total_bars + 1):
        if bar not in occupied_bars:
            if not in_gap:
                in_gap = True
                gap_start = bar
        else:
            if in_gap:
                gap_end = bar
                empty_regions.append({
                    "start_bar": gap_start,
                    "end_bar": gap_end,
                    "length_bars": gap_end - gap_start,
                })
                in_gap = False
    if in_gap:
        empty_regions.append({
            "start_bar": gap_start,
            "end_bar": total_bars + 1,
            "length_bars": total_bars + 1 - gap_start,
        })

    return {
        "total_bars": total_bars,
        "tracks_with_clips": len(track_map),
        "clips_per_track": clips_per_track,
        "empty_regions": empty_regions,
        "total_clips": len(all_clips),
        "tempo": tempo,
    }
