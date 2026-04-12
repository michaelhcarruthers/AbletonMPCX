"""Clip core tools — clip slots, clip properties, and clip gain."""
from __future__ import annotations
import logging
import math
from typing import Any
from helpers import mcp, _send, _send_silent
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ClipSlot
# ---------------------------------------------------------------------------

@mcp.tool()
def get_clip_slots(track_index: int) -> list:
    """Return all clip slots for the track at track_index."""
    return _send("get_clip_slots", {"track_index": track_index})


@mcp.tool()
def get_session_clips(slim: bool = True) -> dict:
    """Return all clip slots across all tracks in the Session View. slim=True (default) returns only slots that have clips, with track_index, slot_index, name, has_clip, length. Pass slim=False for full clip data on every slot."""
    return _send("get_session_clips", {"slim": slim})

@mcp.tool()
def fire_clip_slot(track_index: int, slot_index: int, record_length: float | None = None, launch_quantization: int | None = None) -> dict:
    """Fire the clip slot at (track_index, slot_index)."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if record_length is not None:
        params["record_length"] = record_length
    if launch_quantization is not None:
        params["launch_quantization"] = launch_quantization
    return _send("fire_clip_slot", params)

@mcp.tool()
def stop_clip_slot(track_index: int, slot_index: int) -> dict:
    """Stop the clip slot at (track_index, slot_index)."""
    return _send("stop_clip_slot", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def create_clip(track_index: int, slot_index: int, length: float = 4.0) -> dict:
    """Create an empty MIDI clip in the slot at (track_index, slot_index) with the given length in beats."""
    return _send("create_clip", {"track_index": track_index, "slot_index": slot_index, "length": length})

@mcp.tool()
def delete_clip(track_index: int, slot_index: int) -> dict:
    """Delete the clip in the slot at (track_index, slot_index)."""
    return _send("delete_clip", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def delete_clip_batch(clips: list[dict]) -> dict:
    """Delete multiple clips in a single call.

    Each entry in clips must be a dict with:
      - track_index (int)
      - slot_index (int)

    Returns a summary of deleted and failed slots.
    """
    deleted = []
    failed = []
    for clip in clips:
        track_index = clip["track_index"]
        slot_index = clip["slot_index"]
        try:
            _send("delete_clip", {"track_index": track_index, "slot_index": slot_index})
            deleted.append({"track_index": track_index, "slot_index": slot_index})
        except RuntimeError as e:
            failed.append({"track_index": track_index, "slot_index": slot_index, "error": str(e)})
    return {
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }

@mcp.tool()
def duplicate_clip_slot(track_index: int, slot_index: int) -> dict:
    """Duplicate the clip slot at (track_index, slot_index) to the next empty slot below."""
    return _send("duplicate_clip_slot", {"track_index": track_index, "slot_index": slot_index})

# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------

@mcp.tool()
def get_clip_playing_state(track_index: int, slot_index: int) -> dict:
    """Return the playing state of a clip slot."""
    return _send("get_clip_playing_state", {"track_index": track_index, "slot_index": slot_index})


@mcp.tool()
def get_clip_info(track_index: int, slot_index: int) -> dict:
    """Return full details for the clip at (track_index, slot_index)."""
    return _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def get_clip_playing_position(track_index: int, slot_index: int) -> dict:
    """Return the current playhead position within the clip (in beats). Only meaningful while the clip is playing."""
    return _send("get_clip_playing_position", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def set_clip_name(track_index: int, slot_index: int, name: str) -> dict:
    """Rename the clip at (track_index, slot_index)."""
    return _send("set_clip_name", {"track_index": track_index, "slot_index": slot_index, "name": name})

@mcp.tool()
def set_clip_color(track_index: int, slot_index: int, color: int) -> dict:
    """Set the clip color as an RGB integer (0x00rrggbb)."""
    return _send("set_clip_color", {"track_index": track_index, "slot_index": slot_index, "color": color})


@mcp.tool()
def set_clip_color_batch(updates: list) -> dict:
    """Set the color of multiple clips in a single round trip."""
    return _send("set_clip_color_batch", {"updates": updates})

@mcp.tool()
def set_clip_loop(track_index: int, slot_index: int, looping: bool | None = None, loop_start: float | None = None, loop_end: float | None = None) -> dict:
    """Set loop state and/or loop start/end (in beats) for the clip."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if looping is not None:
        params["looping"] = looping
    if loop_start is not None:
        params["loop_start"] = loop_start
    if loop_end is not None:
        params["loop_end"] = loop_end
    return _send("set_clip_loop", params)

@mcp.tool()
def set_clip_loop_batch(updates: list[dict]) -> dict:
    """Set loop properties on multiple clips in a single call.

    Each entry in updates must be a dict with:
      - track_index (int)
      - slot_index (int)
      - looping (bool, optional)
      - loop_start (float, optional): loop start in beats
      - loop_end (float, optional): loop end in beats

    Returns a summary of updated and failed clips.
    """
    updated = []
    failed = []
    for u in updates:
        track_index = u["track_index"]
        slot_index = u["slot_index"]
        params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
        if "looping" in u:
            params["looping"] = u["looping"]
        if "loop_start" in u:
            params["loop_start"] = u["loop_start"]
        if "loop_end" in u:
            params["loop_end"] = u["loop_end"]
        try:
            _send("set_clip_loop", params)
            updated.append({"track_index": track_index, "slot_index": slot_index})
        except RuntimeError as e:
            failed.append({"track_index": track_index, "slot_index": slot_index, "error": str(e)})
    return {
        "updated_count": len(updated),
        "failed_count": len(failed),
        "updated": updated,
        "failed": failed,
    }

@mcp.tool()
def set_clip_markers(track_index: int, slot_index: int, start_marker: float | None = None, end_marker: float | None = None) -> dict:
    """Set the start and/or end marker of the clip (in beats)."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if start_marker is not None:
        params["start_marker"] = start_marker
    if end_marker is not None:
        params["end_marker"] = end_marker
    return _send("set_clip_markers", params)

@mcp.tool()
def set_clip_mute(track_index: int, slot_index: int, mute: bool) -> dict:
    """Mute or unmute the clip at (track_index, slot_index)."""
    return _send("set_clip_mute", {"track_index": track_index, "slot_index": slot_index, "mute": mute})

@mcp.tool()
def set_clip_pitch(track_index: int, slot_index: int, pitch_coarse: int | None = None, pitch_fine: float | None = None) -> dict:
    """Set transpose (semitones) and/or detune (cents) for an audio clip."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if pitch_coarse is not None:
        params["pitch_coarse"] = pitch_coarse
    if pitch_fine is not None:
        params["pitch_fine"] = pitch_fine
    return _send("set_clip_pitch", params)

@mcp.tool()
def set_clip_gain(
    gain_db: float,
    track_index: int | None = None,
    clip_index: int | None = None,
    bus_index: int | None = None,
    all_tracks: bool = False,
    target_db: float = -14.0,
) -> dict:
    """Set clip gain for one clip, all clips on a track, all clips in a group/bus, or all clips
    in the session with proportional LUFS-aware scaling.

    Modes:
      - Single clip:      track_index + clip_index + gain_db
      - All clips on track: track_index + gain_db (clip_index omitted)
      - All clips in bus: bus_index + gain_db (applies to all child tracks of the group)
      - Proportional all: all_tracks=True — reads current LUFS from the analyzer,
                          calculates the uniform dB offset needed to hit target_db,
                          and applies the same offset to every clip in the session.

    clip.gain is linear 0.0–1.0. This tool converts gain_db using 10 ** (db / 20).
    Faders are never touched. Automation is left in place.

    Args:
        gain_db: Gain value in dB. In all_tracks mode this is ignored; the offset is
                 calculated automatically from the current LUFS reading.
        track_index: Zero-based track index. Required for single-clip and all-clips-on-track modes.
        clip_index: Zero-based slot index. If omitted with track_index, applies to all clips on track.
        bus_index: Zero-based group track index. Applies to all child tracks of that group.
        all_tracks: If True, applies proportional gain staging across the entire session.
        target_db: Target LUFS for proportional mode (default -14.0).
    """
    def _db_to_gain(db: float) -> float:
        return 10.0 ** (db / 20.0)

    def _gain_to_db(gain: float) -> float:
        if gain <= 0.0:
            return -float("inf")
        return 20.0 * math.log10(gain)

    def _clamp_gain(g: float) -> float:
        return max(0.0, min(1.0, g))

    # -----------------------------------------------------------------------
    # Mode 1: Single clip
    # -----------------------------------------------------------------------
    if track_index is not None and clip_index is not None and not all_tracks and bus_index is None:
        gain_linear = _clamp_gain(_db_to_gain(gain_db))
        _send("set_clip_gain", {
            "track_index": track_index,
            "slot_index": clip_index,
            "gain": gain_linear,
        })
        return {
            "mode": "single_clip",
            "track_index": track_index,
            "clip_index": clip_index,
            "gain_db": gain_db,
            "gain_linear": gain_linear,
        }

    # -----------------------------------------------------------------------
    # Mode 2: All clips on a single track
    # -----------------------------------------------------------------------
    if track_index is not None and clip_index is None and not all_tracks and bus_index is None:
        clips_raw = _send("get_session_clips", {"slim": True})
        all_clips = clips_raw if isinstance(clips_raw, list) else clips_raw.get("clips", [])
        track_clips = [c for c in all_clips if c.get("track_index") == track_index]
        gain_linear = _clamp_gain(_db_to_gain(gain_db))
        updated = []
        failed = []
        for clip in track_clips:
            si = clip.get("slot_index")
            try:
                _send("set_clip_gain", {
                    "track_index": track_index,
                    "slot_index": si,
                    "gain": gain_linear,
                })
                updated.append(si)
            except RuntimeError as e:
                failed.append({"slot_index": si, "error": str(e)})
        return {
            "mode": "all_clips_on_track",
            "track_index": track_index,
            "gain_db": gain_db,
            "gain_linear": gain_linear,
            "updated_count": len(updated),
            "failed_count": len(failed),
            "updated_slots": updated,
            "failed": failed,
        }

    # -----------------------------------------------------------------------
    # Mode 3: All clips in a group/bus (children of a group track)
    # -----------------------------------------------------------------------
    if bus_index is not None and not all_tracks:
        tracks_raw = _send("get_tracks", {"slim": True})
        all_track_list = tracks_raw if isinstance(tracks_raw, list) else []

        # Find child tracks by group_track_index == bus_index. If not available,
        # fall back to the get_group_children command.
        child_track_indices = []
        for t in all_track_list:
            ti = t.get("track_index")
            if ti is None:
                continue
            if t.get("group_track_index") == bus_index:
                child_track_indices.append(ti)

        # Fallback: get_tracks slim may not return group_track_index — use the
        # dedicated get_group_children command if available, else skip
        if not child_track_indices:
            try:
                group_result = _send("get_group_children", {"track_index": bus_index})
                child_track_indices = group_result if isinstance(group_result, list) else group_result.get("child_indices", [])
            except RuntimeError:
                # Last resort: not supported, return an error
                return {
                    "mode": "bus",
                    "bus_index": bus_index,
                    "error": f"Could not resolve child tracks for group at bus_index={bus_index}. "
                             "Try targeting tracks individually with track_index.",
                }

        clips_raw = _send("get_session_clips", {"slim": True})
        all_clips = clips_raw if isinstance(clips_raw, list) else clips_raw.get("clips", [])
        bus_clips = [c for c in all_clips if c.get("track_index") in child_track_indices]

        gain_linear = _clamp_gain(_db_to_gain(gain_db))
        updated = []
        failed = []
        for clip in bus_clips:
            ti = clip.get("track_index")
            si = clip.get("slot_index")
            try:
                _send("set_clip_gain", {
                    "track_index": ti,
                    "slot_index": si,
                    "gain": gain_linear,
                })
                updated.append({"track_index": ti, "slot_index": si})
            except RuntimeError as e:
                failed.append({"track_index": ti, "slot_index": si, "error": str(e)})
        return {
            "mode": "bus",
            "bus_index": bus_index,
            "child_tracks": child_track_indices,
            "gain_db": gain_db,
            "gain_linear": gain_linear,
            "updated_count": len(updated),
            "failed_count": len(failed),
            "updated": updated,
            "failed": failed,
        }

    # -----------------------------------------------------------------------
    # Mode 4: Proportional all-tracks LUFS-aware gain staging
    # -----------------------------------------------------------------------
    if all_tracks:
        from tools.realtime_analyzer import _send_analyzer

        # Step 1: Read current LUFS from the analyzer
        try:
            levels = _send_analyzer("get_levels")
            current_lufs = levels.get("lufs") or levels.get("lufs_integrated")
        except RuntimeError as e:
            return {
                "mode": "all_tracks",
                "error": f"Analyzer offline: {e}. Load AMCPX_Analyzer.amxd and try again.",
            }

        if current_lufs is None:
            return {
                "mode": "all_tracks",
                "error": "Analyzer returned no LUFS reading. Play audio through Live first so the "
                         "analyzer has data, then retry.",
            }

        # Step 2: Calculate the uniform dB offset
        offset_db = target_db - float(current_lufs)

        # Step 3: Collect all clips
        clips_raw = _send("get_session_clips", {"slim": True})
        all_clips = clips_raw if isinstance(clips_raw, list) else clips_raw.get("clips", [])

        if not all_clips:
            return {
                "mode": "all_tracks",
                "current_lufs": current_lufs,
                "target_db": target_db,
                "offset_db": offset_db,
                "updated_count": 0,
                "note": "No clips found in session.",
            }

        # Step 4: Read current gain for each clip, apply uniform offset
        # get_session_clips slim returns: track_index, slot_index, name, has_clip, length
        # We need to read current gain per clip (get_clip_info) — do this in bulk
        updated = []
        failed = []
        skipped = []

        for clip in all_clips:
            ti = clip.get("track_index")
            si = clip.get("slot_index")
            try:
                info = _send("get_clip_info", {"track_index": ti, "slot_index": si})
                current_gain_linear = float(info.get("gain", 1.0))
                # MIDI clips don't have gain
                if info.get("is_midi_clip", False):
                    skipped.append({"track_index": ti, "slot_index": si, "reason": "midi_clip"})
                    continue
                current_gain_db = _gain_to_db(current_gain_linear)
                new_gain_db = current_gain_db + offset_db
                new_gain_linear = _clamp_gain(_db_to_gain(new_gain_db))
                _send("set_clip_gain", {
                    "track_index": ti,
                    "slot_index": si,
                    "gain": new_gain_linear,
                })
                updated.append({
                    "track_index": ti,
                    "slot_index": si,
                    "previous_gain_db": round(current_gain_db, 2),
                    "new_gain_db": round(new_gain_db, 2),
                    "new_gain_linear": round(new_gain_linear, 4),
                })
            except RuntimeError as e:
                failed.append({"track_index": ti, "slot_index": si, "error": str(e)})

        return {
            "mode": "all_tracks",
            "current_lufs": round(float(current_lufs), 2),
            "target_db": target_db,
            "offset_db": round(offset_db, 2),
            "updated_count": len(updated),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
        }

    # -----------------------------------------------------------------------
    # Fallback: no valid mode
    # -----------------------------------------------------------------------
    return {
        "error": "Invalid parameter combination. Provide one of: "
                 "(track_index + clip_index), (track_index), (bus_index), or (all_tracks=True).",
        "gain_db": gain_db,
    }
