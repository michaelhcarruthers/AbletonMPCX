"""Arrangement automation tools — write volume and dynamic automation
via the Remote Script (port 9877). No M4L bridge device required.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

from helpers import mcp, _send

# ---------------------------------------------------------------------------
# Helper constants and time-conversion utilities
# (moved from tools.session so arrangement tools can use them locally)
# ---------------------------------------------------------------------------

_STYLE_PRESETS: dict[str, dict] = {
    "snoop":    {"bpm": 90,  "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "hip_hop":  {"bpm": 90,  "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "boom_bap": {"bpm": 85,  "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Sample", "audio"), ("Lead", "midi")]},
    "trap":     {"bpm": 140, "tracks": [("808", "midi"), ("HiHat", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "lofi":     {"bpm": 75,  "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Piano", "midi"), ("Texture", "audio")]},
}
_STYLE_FREE: dict = {"bpm": 120, "tracks": [("MIDI 1", "midi"), ("MIDI 2", "midi"), ("MIDI 3", "midi"), ("Audio 1", "audio")]}

_SCENE_SECTION_COLORS = {
    "intro":   70,  # grey
    "verse":   41,  # blue
    "chorus":   5,  # red
    "hook":     5,  # red
    "drop":     5,  # red
    "pre":     28,  # cyan
    "build":   28,  # cyan
    "bridge":  49,  # purple
    "break":   49,  # purple
    "outro":   70,  # grey
    "default":  0,
}

_SCAFFOLD_TEMPLATES = {
    "default": {
        "structure": ["Intro", "Verse", "Chorus", "Verse", "Chorus", "Outro"],
        "bars":      {"Intro": 8, "Verse": 16, "Chorus": 8, "Outro": 8},
    },
    "hiphop": {
        "structure": ["Intro", "Verse", "Hook", "Verse", "Hook", "Bridge", "Hook", "Outro"],
        "bars":      {"Intro": 4, "Verse": 16, "Hook": 8, "Bridge": 8, "Outro": 4},
    },
    "edm": {
        "structure": ["Intro", "Build", "Drop", "Break", "Build", "Drop", "Outro"],
        "bars":      {"Intro": 8, "Build": 8, "Drop": 16, "Break": 8, "Outro": 8},
    },
    "pop": {
        "structure": ["Intro", "Verse", "Pre", "Chorus", "Verse", "Pre", "Chorus", "Bridge", "Chorus", "Outro"],
        "bars":      {"Intro": 8, "Verse": 16, "Pre": 4, "Chorus": 8, "Bridge": 8, "Outro": 4},
    },
    "minimal": {
        "structure": ["Intro", "Part A", "Part B", "Part A", "Outro"],
        "bars":      {"Intro": 8, "Part A": 16, "Part B": 16, "Outro": 8},
    },
}


def _get_time_sig_numerator(override: int | None = None) -> int:
    """Return the song's current time signature numerator, with optional caller override."""
    if override is not None:
        return override
    try:
        info = _send("get_song_info")
        return int(info.get("time_signature_numerator", 4))
    except Exception:
        return 4


def _bars_beats_to_song_time(start_bar: int, start_beat: float, time_sig_numerator: int) -> float:
    """Convert 1-indexed bar + beat position to absolute song time in beats."""
    return (start_bar - 1) * time_sig_numerator + (start_beat - 1)


@mcp.tool()
def write_dynamic_automation(
    track_name: str,
    direction: str,
    bar_start: int,
    bar_end: int,
    curve: str = "linear",
) -> dict:
    """Ramp track volume and filter cutoff up (louder) or down (softer) across a bar range in arrangement view."""
    from helpers.preflight import get_session_state, get_track_index_by_name, get_device_index_by_name
    from helpers.timing import bar_range_to_seconds

    # --- validate curve ---
    VALID_CURVES = ("ease_in", "ease_out", "linear")
    if curve not in VALID_CURVES:
        raise ValueError(f"Invalid curve '{curve}'. Must be one of: {VALID_CURVES}")

    # --- resolve track ---
    track_index = get_track_index_by_name(track_name)
    if track_index is None:
        return {"error": f"Track '{track_name}' not found.", "applied": False}

    # --- resolve timing (all Python, no AI reasoning) ---
    session = get_session_state()
    tempo = session["tempo"]
    time_sig_num = session["time_sig_numerator"]
    start_secs, end_secs = bar_range_to_seconds(bar_start, bar_end, tempo, time_sig_num)

    # --- direction config ---
    direction_lower = direction.strip().lower()
    if direction_lower not in ("louder", "softer"):
        return {"error": f"direction must be 'louder' or 'softer', got '{direction}'", "applied": False}

    going_up = direction_lower == "louder"

    # Volume: louder = 0.5 → 0.85 range shift, softer = 0.85 → 0.5
    # These are normalised Live mixer values (0.0–1.0 maps to -inf to +6dB)
    # 0.85 ≈ 0dB, 0.5 ≈ -12dB
    volume_start = 0.5 if going_up else 0.85
    volume_end   = 0.85 if going_up else 0.5

    # Filter cutoff: louder = open up, softer = close down
    filter_start = 0.4 if going_up else 0.8
    filter_end   = 0.8 if going_up else 0.4

    # --- build automation points ---
    def make_envelope(val_start: float, val_end: float) -> list[dict]:
        """Build envelope points for a 2-point ramp with optional curve shaping."""
        if curve == "ease_in":
            mid_secs = start_secs + (end_secs - start_secs) * 0.7
            mid_val = val_start + (val_end - val_start) * 0.2
            return [
                {"time": start_secs, "value": val_start},
                {"time": mid_secs,   "value": mid_val},
                {"time": end_secs,   "value": val_end},
            ]
        elif curve == "ease_out":
            mid_secs = start_secs + (end_secs - start_secs) * 0.3
            mid_val = val_start + (val_end - val_start) * 0.8
            return [
                {"time": start_secs, "value": val_start},
                {"time": mid_secs,   "value": mid_val},
                {"time": end_secs,   "value": val_end},
            ]
        else:
            return [
                {"time": start_secs, "value": val_start},
                {"time": end_secs,   "value": val_end},
            ]

    applied_automations = []

    # --- write volume automation ---
    try:
        vol_result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "parameter_type": "volume",
            "points": make_envelope(volume_start, volume_end),
        })
        applied_automations.append("volume")
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "automations_written": [],
        }

    # --- attempt filter cutoff automation (graceful skip if no filter device) ---
    filter_result = None
    filter_device_index = get_device_index_by_name(track_index, "eq")
    if filter_device_index is None:
        filter_device_index = get_device_index_by_name(track_index, "filter")
    if filter_device_index is None:
        filter_device_index = get_device_index_by_name(track_index, "auto filter")

    if filter_device_index is not None:
        try:
            filter_result = _send("write_arrangement_automation", {
                "track_index": track_index,
                "parameter_type": "device_parameter",
                "device_index": filter_device_index,
                "parameter_index": 0,
                "points": make_envelope(filter_start, filter_end),
            })
            applied_automations.append("filter_cutoff")
        except Exception as e:
            filter_result = {"error": str(e)}

    return {
        "status": "ok",
        "direction": direction_lower,
        "automations_written": applied_automations,
    }


@mcp.tool()
def write_arrangement_volume_automation(
    track_index: int,
    start_beat: float,
    end_beat: float,
    start_value: float,
    end_value: float,
    curve: str = "linear",
) -> dict:
    """Write volume automation to a track in arrangement view.

    Uses the Remote Script (port 9877) — does NOT require the M4L bridge device.

    track_index: zero-based track index
    start_beat: song position in beats where ramp starts (beat 0 = bar 1)
    end_beat: song position in beats where ramp ends
    start_value: normalised volume at start (0.0 = silence, 0.85 ≈ 0dB, 1.0 = +6dB)
    end_value: normalised volume at end
    curve: 'linear' (default), 'ease_in', or 'ease_out'
    """
    VALID_CURVES = ("linear", "ease_in", "ease_out")
    if curve not in VALID_CURVES:
        return {"error": f"curve must be one of {VALID_CURVES}", "applied": False}

    duration = end_beat - start_beat
    if duration <= 0:
        return {"error": "end_beat must be greater than start_beat", "applied": False}

    if curve == "ease_in":
        mid_beat = start_beat + duration * 0.7
        mid_val = start_value + (end_value - start_value) * 0.2
        points = [
            {"time": start_beat, "value": start_value},
            {"time": mid_beat, "value": mid_val},
            {"time": end_beat, "value": end_value},
        ]
    elif curve == "ease_out":
        mid_beat = start_beat + duration * 0.3
        mid_val = start_value + (end_value - start_value) * 0.8
        points = [
            {"time": start_beat, "value": start_value},
            {"time": mid_beat, "value": mid_val},
            {"time": end_beat, "value": end_value},
        ]
    else:
        points = [
            {"time": start_beat, "value": start_value},
            {"time": end_beat, "value": end_value},
        ]

    try:
        result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "parameter_type": "volume",
            "points": points,
        })
    except RuntimeError as e:
        return {"error": str(e), "applied": False}
    return {
        "status": "ok",
        "track_index": track_index,
        "start_beat": start_beat,
        "end_beat": end_beat,
        "start_value": start_value,
        "end_value": end_value,
        "curve": curve,
        "points_written": len(points),
        "result": result,
    }


@mcp.tool()
def mix_section(
    bar_start: int,
    bar_end: int,
    tracks: list[dict],
    curve: str = "ease_in_out",
    transition_bars: float = 0.5,
    time_signature_numerator: int | None = None,
) -> dict:
    """Write volume automation for multiple tracks across a bar range in one call.

    Use this to reshape the mix balance for a section — push drums back, bring pad
    forward, fade bass down — all in one tool call instead of one per track.

    bar_start: first bar of the section (1-indexed)
    bar_end: last bar of the section (exclusive — automation ends at the start of this bar)
    tracks: list of track mix specs, each dict with:
      - track_index (int): zero-based track index
      - volume (float): target normalised volume for the section body (0.0–1.0)
                        0.85 ≈ 0dB, 0.70 ≈ -3dB, 0.50 ≈ -12dB, 0.0 = silence
      - start_volume (float, optional): volume at bar_start (defaults to current fader value)
      - end_volume (float, optional): volume at bar_end (defaults to same as volume)
      - per_bar (list[dict], optional): fine-grained per-bar level map:
            [{"bar": 5, "volume": 0.6}, {"bar": 6, "volume": 0.4}, ...]
            When provided, overrides volume/start_volume/end_volume for this track
            and writes one automation point per listed bar instead of a simple ramp.

    curve: shape of the volume ramp — "linear", "ease_in", "ease_out", "ease_in_out" (default)
    transition_bars: how many bars to ramp in/out at section boundaries (default 0.5)
    time_signature_numerator: override the time signature numerator (default: read from song)

    Returns a summary of what was written and any errors per track.

    Volume reference:
      1.0  = +6 dB (boost)
      0.85 = 0 dB  (unity, default fader position)
      0.70 = -3 dB
      0.60 = -6 dB
      0.50 = -12 dB
      0.35 = -18 dB
      0.0  = silence
    """
    VALID_CURVES = ("linear", "ease_in", "ease_out", "ease_in_out")
    if curve not in VALID_CURVES:
        raise ValueError("curve must be one of {}".format(VALID_CURVES))

    tsn = _get_time_sig_numerator(time_signature_numerator)

    # Get current track volumes for defaults
    try:
        tracks_info = _send("get_tracks", {"slim": False})
        if isinstance(tracks_info, list):
            current_volumes = {t["index"]: t.get("volume", 0.85) for t in tracks_info}
        else:
            current_volumes = {}
    except Exception:
        current_volumes = {}

    # Build the batch writes list
    writes = []
    track_results = []

    for spec in tracks:
        track_index = int(spec["track_index"])
        current_vol = current_volumes.get(track_index, 0.85)

        per_bar = spec.get("per_bar")

        if per_bar:
            # Per-bar mode: write one automation point at the start of each specified bar
            points = []
            for entry in per_bar:
                bar = int(entry["bar"])
                vol = max(0.0, min(1.0, float(entry["volume"])))
                beat_time = _bars_beats_to_song_time(bar, 1.0, tsn)
                points.append({"time": beat_time, "value": vol})
            # Sort by time to be safe
            points.sort(key=lambda p: p["time"])
        else:
            # Simple ramp mode
            target_vol = max(0.0, min(1.0, float(spec["volume"])))
            start_vol = max(0.0, min(1.0, float(spec.get("start_volume", current_vol))))
            end_vol = max(0.0, min(1.0, float(spec.get("end_volume", target_vol))))

            # Convert bars to beats
            start_beat = _bars_beats_to_song_time(bar_start, 1.0, tsn)
            body_beat = _bars_beats_to_song_time(bar_start, 1.0 + transition_bars * tsn, tsn)
            end_beat = _bars_beats_to_song_time(bar_end, 1.0, tsn)
            fade_out_beat = max(body_beat, end_beat - transition_bars * tsn)

            if curve == "ease_in_out":
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": body_beat, "value": target_vol},
                    {"time": fade_out_beat, "value": target_vol},
                    {"time": end_beat, "value": end_vol},
                ]
            elif curve == "ease_in":
                mid_beat = start_beat + (end_beat - start_beat) * 0.7
                mid_val = start_vol + (target_vol - start_vol) * 0.2
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": mid_beat, "value": mid_val},
                    {"time": end_beat, "value": end_vol},
                ]
            elif curve == "ease_out":
                mid_beat = start_beat + (end_beat - start_beat) * 0.3
                mid_val = start_vol + (target_vol - start_vol) * 0.8
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": mid_beat, "value": mid_val},
                    {"time": end_beat, "value": end_vol},
                ]
            else:  # linear
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": end_beat, "value": end_vol},
                ]

            # Deduplicate consecutive identical points to keep automation tidy
            deduped = [points[0]]
            for pt in points[1:]:
                if pt["time"] != deduped[-1]["time"]:
                    deduped.append(pt)
            points = deduped

        writes.append({
            "track_index": track_index,
            "parameter_type": "volume",
            "points": points,
            "clear_range": True,
        })
        track_results.append({"track_index": track_index, "points": len(points)})

    # Send as batch
    try:
        result = _send("write_arrangement_automation_batch", {"writes": writes})
        writes_applied = result.get("writes_applied", len(writes))
        batch_errors = result.get("errors", [])
    except Exception as e:
        # Fallback: send individually if batch command not yet available
        writes_applied = 0
        batch_errors = []
        for write in writes:
            try:
                _send("write_arrangement_automation", write)
                writes_applied += 1
            except Exception as we:
                batch_errors.append({"track_index": write["track_index"], "error": str(we)})

    return {
        "status": "ok",
        "bar_start": bar_start,
        "bar_end": bar_end,
        "tracks_written": writes_applied,
        "tracks_requested": len(writes),
        "track_results": track_results,
        "errors": batch_errors,
        "curve": curve,
    }


@mcp.tool()
def analyze_section_levels(
    bar: int,
    track_indices: list[int] | None = None,
    time_signature_numerator: int | None = None,
) -> dict:
    """Read the current volume (fader or automation) for all tracks at a specific bar.

    Returns per-track volume levels at the given bar position so Claude can assess
    the current mix balance before deciding what to change.

    bar: 1-indexed bar number to sample levels at
    track_indices: optional list of track indices to check (default: all tracks)
    time_signature_numerator: override time sig numerator (default: read from song)

    Returns per-track volumes with dB equivalents and a balance summary.

    Volume → dB reference (Live's mixer scale):
      1.0  → +6 dB
      0.85 → 0 dB  (unity)
      0.70 → -3 dB
      0.50 → -12 dB
      0.35 → -18 dB
    """
    import math

    tsn = _get_time_sig_numerator(time_signature_numerator)
    beat_position = _bars_beats_to_song_time(bar, 1.0, tsn)

    # Get all tracks
    try:
        all_tracks = _send("get_tracks", {"slim": False})
        if not isinstance(all_tracks, list):
            return {"error": "Could not get tracks"}
    except Exception as e:
        return {"error": str(e)}

    if track_indices is not None:
        track_filter = set(track_indices)
        all_tracks = [t for t in all_tracks if (t.get("index") if "index" in t else t.get("track_index")) in track_filter]

    def _track_idx(t: dict) -> int:
        """Return a consistent track index from a track dict (handles both key names)."""
        return t.get("index") if "index" in t else t.get("track_index", 0)

    def vol_to_db(v: float) -> float:
        """Approximate dB from Live's normalised mixer value."""
        if v <= 0.0:
            return -float("inf")
        # Live uses a roughly piecewise curve; approximate:
        # 0.85 ≈ 0dB, linear above, logarithmic below
        if v >= 0.85:
            return round((v - 0.85) / 0.15 * 6.0, 1)
        else:
            return round(20.0 * math.log10(v / 0.85), 1)

    # Try to read automation value at beat_position; fall back to fader value
    levels = []
    for t in all_tracks:
        t_idx = _track_idx(t)
        t_name = t.get("name", "Track {}".format(t_idx))
        fader_vol = float(t.get("volume", 0.85))

        # Attempt to read automation at this beat position
        auto_vol = None
        try:
            auto_result = _send("get_automation_value_at", {
                "track_index": t_idx,
                "parameter_type": "volume",
                "beat_position": beat_position,
            })
            if isinstance(auto_result, dict) and "value" in auto_result:
                auto_vol = float(auto_result["value"])
        except Exception:
            pass  # command may not exist — fall back to fader

        effective_vol = auto_vol if auto_vol is not None else fader_vol
        source = "automation" if auto_vol is not None else "fader"

        levels.append({
            "track_index": t_idx,
            "track_name": t_name,
            "volume": round(effective_vol, 4),
            "volume_db": vol_to_db(effective_vol),
            "source": source,
            "muted": bool(t.get("mute", False)),
        })

    # Sort by volume descending (loudest first)
    levels.sort(key=lambda x: x["volume"], reverse=True)

    # Build a quick balance summary
    active = [l for l in levels if not l["muted"] and l["volume"] > 0.01]
    if active:
        loudest = active[0]
        quietest = active[-1]
        dynamic_range_db = loudest["volume_db"] - quietest["volume_db"]
        summary = "Loudest: {} ({} dB). Quietest: {} ({} dB). Range: {:.1f} dB.".format(
            loudest["track_name"], loudest["volume_db"],
            quietest["track_name"], quietest["volume_db"],
            dynamic_range_db,
        )
    else:
        summary = "No active tracks at bar {}.".format(bar)

    return {
        "bar": bar,
        "beat_position": beat_position,
        "levels": levels,
        "track_count": len(levels),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Scene scaffolding (moved from tools.session)
# ---------------------------------------------------------------------------

@mcp.tool()
def build_scene_scaffold(
    structure: list[str] | None = None,
    bars_each: dict[str, int] | None = None,
    color_code: bool = True,
    template: str | None = None,
) -> dict:
    """Create a set of named, color-coded scenes for a song structure in one command."""
    template_used = None
    if template is not None:
        tpl = _SCAFFOLD_TEMPLATES.get(template, _SCAFFOLD_TEMPLATES["default"])
        structure = tpl["structure"]
        bars_each = tpl["bars"]
        template_used = template
    elif structure is None:
        tpl = _SCAFFOLD_TEMPLATES["default"]
        structure = tpl["structure"]
        bars_each = tpl["bars"]
        template_used = "default"

    if bars_each is None:
        bars_each = {}

    # Handle repeated section names by numbering them
    counts: dict[str, int] = {}
    named_structure = []
    for section in structure:
        base = section
        counts[base] = counts.get(base, 0) + 1
    # Track occurrence index
    occurrence: dict[str, int] = {}
    total_occurrences: dict[str, int] = counts
    for section in structure:
        occurrence[section] = occurrence.get(section, 0) + 1
        if total_occurrences[section] > 1:
            named_structure.append("{} {}".format(section, occurrence[section]))
        else:
            named_structure.append(section)

    try:
        existing_scenes = _send("get_scenes")
        start_index = len(existing_scenes)
    except RuntimeError as e:
        return {"error": "Could not get scenes: {}".format(e)}

    scene_list = []
    for i, name in enumerate(named_structure):
        scene_index = start_index + i
        # Determine bars (use the base section name for lookup)
        base_name = re.sub(r"\s+\d+$", "", name)
        bars = bars_each.get(base_name, bars_each.get(name, 8))

        # Determine color
        color = _SCENE_SECTION_COLORS["default"]
        if color_code:
            for keyword, c in _SCENE_SECTION_COLORS.items():
                if keyword == "default":
                    continue
                if keyword in name.lower():
                    color = c
                    break

        try:
            _send("create_scene", {"index": -1})
        except RuntimeError as e:
            scene_list.append({"scene_index": scene_index, "name": name, "bars": bars, "color": color, "error": str(e)})
            continue

        try:
            _send("set_scene_name", {"scene_index": scene_index, "name": name})
        except RuntimeError as e:
            logger.debug("Could not set scene name for scene %s: %s", scene_index, e)

        if color_code:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": color})
            except RuntimeError as e:
                logger.debug("Could not set scene color for scene %s: %s", scene_index, e)

        scene_list.append({"scene_index": scene_index, "name": name, "bars": bars, "color": color})

    return {
        "scenes_created": len(scene_list),
        "scene_list": scene_list,
        "template_used": template_used,
    }


@mcp.tool()
def list_scaffold_templates() -> dict:
    """List all available scene scaffold templates with their structures."""
    results = []
    for name, tpl in _SCAFFOLD_TEMPLATES.items():
        structure = tpl["structure"]
        bars_map = tpl["bars"]
        total_bars = sum(bars_map.get(re.sub(r"\s+\d+$", "", s), 8) for s in structure)
        results.append({
            "name": name,
            "structure": structure,
            "total_bars": total_bars,
            "section_count": len(structure),
        })
    return {"templates": results}


@mcp.tool()
def place_clip_in_arrangement(
    track_index: int,
    clip_index: int,
    start_bar: int,
    start_beat: float = 1.0,
    time_signature_numerator: int | None = None,
) -> dict:
    """Place (duplicate) a Session View clip into the Arrangement View at a specific position."""
    tsn = _get_time_sig_numerator(time_signature_numerator)
    start_time_beats = _bars_beats_to_song_time(start_bar, start_beat, tsn)

    clip_name = ""
    clip_length_beats = 0.0
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
        clip_name = clip_info.get("name", "")
        clip_length_beats = float(clip_info.get("length", 0.0))
    except RuntimeError as e:
        logger.debug("Could not get clip info for track %s slot %s: %s", track_index, clip_index, e)

    try:
        _send("duplicate_clip_to_arrangement", {
            "track_index": track_index,
            "clip_index": clip_index,
            "time": start_time_beats,
        })
    except RuntimeError:
        try:
            _send("copy_clip_to_arrangement", {
                "track_index": track_index,
                "clip_index": clip_index,
                "time": start_time_beats,
            })
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "start_time_beats": start_time_beats,
                "clip_name": clip_name,
                "clip_length_beats": clip_length_beats,
                "error": "Neither duplicate_clip_to_arrangement nor copy_clip_to_arrangement is supported: {}".format(e),
            }

    return {
        "track_index": track_index,
        "start_time_beats": start_time_beats,
        "clip_name": clip_name,
        "clip_length_beats": clip_length_beats,
    }


@mcp.tool()
def duplicate_clip_to_scenes(
    operations: list[dict],
) -> dict:
    """Duplicate clips into multiple scene slots across one or more tracks in a single call.

    Each operation must be a dict with:
      - track_index (int): the track to operate on
      - source_clip_index (int): the source session slot index
      - target_scene_indices (list[int]): destination slot indices

    Supports both MIDI and audio clips. MIDI clips are recreated with notes;
    audio clips are duplicated using duplicate_clip_slot then moved with move_clip_slot.
    """
    results = []

    for op in operations:
        track_index = op["track_index"]
        source_clip_index = op["source_clip_index"]
        target_scene_indices = op["target_scene_indices"]
        copies_made = 0
        skipped = []

        try:
            clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": source_clip_index})
        except RuntimeError as e:
            results.append({
                "track_index": track_index,
                "source_clip_index": source_clip_index,
                "copies_made": 0,
                "skipped": target_scene_indices,
                "error": str(e),
            })
            continue

        length = clip_info.get("length", 4.0)
        clip_name = clip_info.get("name", "")
        clip_color = clip_info.get("color")
        is_midi = bool(clip_info.get("is_midi_clip", False))

        if is_midi:
            try:
                notes_result = _send("get_notes", {"track_index": track_index, "slot_index": source_clip_index})
                notes = notes_result.get("notes", []) if isinstance(notes_result, dict) else notes_result
            except RuntimeError:
                notes = []

            for target_idx in target_scene_indices:
                try:
                    _send("create_clip", {"track_index": track_index, "slot_index": target_idx, "length": length})
                    if clip_name:
                        _send("set_clip_name", {"track_index": track_index, "slot_index": target_idx, "name": clip_name})
                    if clip_color is not None:
                        _send("set_clip_color", {"track_index": track_index, "slot_index": target_idx, "color": clip_color})
                    if notes:
                        _send("replace_all_notes", {"track_index": track_index, "slot_index": target_idx, "notes": notes})
                    copies_made += 1
                except RuntimeError:
                    skipped.append(target_idx)
        else:
            for target_idx in target_scene_indices:
                try:
                    _send("duplicate_clip_slot", {
                        "track_index": track_index,
                        "slot_index": source_clip_index,
                    })
                    try:
                        _send("move_clip_slot", {
                            "track_index": track_index,
                            "from_slot_index": source_clip_index + 1,
                            "to_slot_index": target_idx,
                        })
                    except RuntimeError as move_err:
                        skipped.append({"slot": target_idx, "reason": str(move_err)})
                        continue
                    if clip_name:
                        try:
                            _send("set_clip_name", {"track_index": track_index, "slot_index": target_idx, "name": clip_name})
                        except RuntimeError:
                            pass
                    if clip_color is not None:
                        try:
                            _send("set_clip_color", {"track_index": track_index, "slot_index": target_idx, "color": clip_color})
                        except RuntimeError:
                            pass
                    copies_made += 1
                except RuntimeError as e:
                    skipped.append({"slot": target_idx, "reason": str(e)})

        skipped_slots = {s if isinstance(s, int) else s["slot"] for s in skipped}
        results.append({
            "track_index": track_index,
            "source_clip_index": source_clip_index,
            "clip_type": "midi" if is_midi else "audio",
            "copies_made": copies_made,
            "target_scenes": [i for i in target_scene_indices if i not in skipped_slots],
            "skipped": skipped,
        })

    return {
        "results": results,
        "total_copies": sum(r["copies_made"] for r in results),
        "operations_count": len(operations),
    }


@mcp.tool()
def arrange_from_scene_scaffold(
    track_indices: list[int] | None = None,
    layout: dict[str, int] | None = None,
    time_signature_numerator: int | None = None,
) -> dict:
    """Build the Arrangement View from the current scene structure."""
    tsn = _get_time_sig_numerator(time_signature_numerator)
    try:
        scenes = _send("get_scenes")
    except RuntimeError as e:
        return {"error": "Could not get scenes: {}".format(e)}

    if track_indices is None:
        try:
            tracks = _send("get_tracks")
            track_indices = [t.get("index", t.get("track_index", i)) for i, t in enumerate(tracks)]
        except RuntimeError as e:
            return {"error": "Could not get tracks: {}".format(e)}

    if layout is None:
        layout = {}

    placements = []
    current_bar = 1
    total_bars = 0

    for scene_idx, scene in enumerate(scenes):
        scene_name = scene.get("name", "Scene {}".format(scene_idx + 1))

        base_name = re.sub(r"\s+\d+$", "", scene_name)
        if base_name in layout:
            length_bars = layout[base_name]
        elif scene_name in layout:
            length_bars = layout[scene_name]
        else:
            length_beats = 0.0
            for ti in track_indices:
                try:
                    clip_info = _send("get_clip_info", {"track_index": ti, "slot_index": scene_idx})
                    clip_len = float(clip_info.get("length", 0.0))
                    if clip_len > 0:
                        length_beats = clip_len
                        break
                except RuntimeError as e:
                    logger.debug("Could not get clip length for track %s scene %s: %s", ti, scene_idx, e)

            length_bars = max(1, round(length_beats / tsn)) if length_beats > 0 else 8

        tracks_placed = 0
        for ti in track_indices:
            try:
                start_time = _bars_beats_to_song_time(current_bar, 1.0, tsn)
                _send("duplicate_clip_to_arrangement", {
                    "track_index": ti,
                    "clip_index": scene_idx,
                    "time": start_time,
                })
                tracks_placed += 1
            except RuntimeError:
                try:
                    start_time = _bars_beats_to_song_time(current_bar, 1.0, tsn)
                    _send("copy_clip_to_arrangement", {
                        "track_index": ti,
                        "clip_index": scene_idx,
                        "time": start_time,
                    })
                    tracks_placed += 1
                except RuntimeError as e:
                    logger.debug("Could not place clip for track %s scene %s: %s", ti, scene_idx, e)

        placements.append({
            "scene_name": scene_name,
            "scene_index": scene_idx,
            "start_bar": current_bar,
            "length_bars": length_bars,
            "tracks_placed": tracks_placed,
        })
        current_bar += length_bars
        total_bars += length_bars

    arrangement_length_beats = float(total_bars * tsn)

    return {
        "scenes_placed": len(placements),
        "placements": placements,
        "total_bars": total_bars,
        "arrangement_length_beats": arrangement_length_beats,
    }


@mcp.tool()
def insert_tempo_section(
    position_bar: int,
    tempo: float,
    time_signature_numerator: int | None = None,
    duplicate_material_from_bar: int | None = None,
    duplicate_material_length_bars: int | None = None,
) -> dict:
    """Insert a new tempo section at a bar position in the Arrangement.

    position_bar: 1-indexed bar where the tempo change happens
    tempo: BPM for the new section
    time_signature_numerator: current time sig numerator for bar→beat conversion (default: read from song)
    duplicate_material_from_bar: if set, duplicate all arrangement clips from this bar range into the new section
    duplicate_material_length_bars: length of the source material to duplicate (required if duplicate_material_from_bar is set)

    Returns the beat position of the inserted tempo change and any duplicated clips.
    """
    tsn = _get_time_sig_numerator(time_signature_numerator)
    position_beats = _bars_beats_to_song_time(position_bar, 1.0, tsn)

    result = _send("insert_tempo_section", {
        "position_beats": position_beats,
        "tempo": tempo,
    })

    duplicated = []
    if duplicate_material_from_bar is not None and duplicate_material_length_bars is not None:
        source_start_beats = _bars_beats_to_song_time(duplicate_material_from_bar, 1.0, tsn)
        source_end_beats = source_start_beats + (duplicate_material_length_bars * tsn)
        offset_beats = position_beats - source_start_beats

        try:
            tracks_info = _send("get_tracks", {})
            tracks = tracks_info if isinstance(tracks_info, list) else tracks_info.get("tracks", [])
            for track in tracks:
                track_index = track.get("index", track.get("track_index"))
                if track_index is None:
                    continue
                try:
                    clips_result = _send("get_arrangement_clips", {"track_index": track_index})
                    clips = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])
                    for i, clip in enumerate(clips):
                        clip_start = float(clip.get("start_time", clip.get("position", 0.0)))
                        clip_end = clip_start + float(clip.get("length", 0.0))
                        if clip_start >= source_start_beats and clip_end <= source_end_beats:
                            target_time = clip_start + offset_beats
                            try:
                                _send("duplicate_clip_to_time", {
                                    "track_index": track_index,
                                    "clip_index": i,
                                    "target_time": target_time,
                                })
                                duplicated.append({
                                    "track_index": track_index,
                                    "clip_index": i,
                                    "target_time": target_time,
                                })
                            except RuntimeError:
                                pass
                except RuntimeError:
                    pass
        except RuntimeError:
            pass

    return {
        "position_bar": position_bar,
        "position_beats": position_beats,
        "tempo": tempo,
        "tempo_insert_result": result,
        "duplicated_clips": duplicated,
        "duplicated_count": len(duplicated),
    }


@mcp.tool()
def create_song_from_brief(
    style: str,
    key: str | None = None,
    bpm: float | None = None,
) -> dict:
    """Create a skeleton arrangement from a music style brief."""
    preset = _STYLE_PRESETS.get(style, _STYLE_FREE)
    bpm_used: float = bpm if bpm is not None else float(preset["bpm"])
    tracks: list[tuple[str, str]] = preset["tracks"]
    warnings: list[str] = []

    # 1. Set tempo
    _send("set_tempo", {"tempo": bpm_used})

    # 2. Create tracks and rename them
    track_names: list[str] = []
    for idx, (name, track_type) in enumerate(tracks):
        if track_type == "audio":
            _send("create_audio_track", {"index": idx})
        else:
            _send("create_midi_track", {"index": idx})
        _send("set_track_name", {"track_index": idx, "name": name})
        track_names.append(name)

    # 3. Warn if key was provided (no set_song_key command available)
    if key is not None:
        warnings.append(
            "Key '{}' noted but no set_song_key command is available; "
            "set the key manually in Ableton.".format(key)
        )

    return {
        "style": style,
        "bpm": bpm_used,
        "key": key,
        "tracks_created": len(track_names),
        "track_names": track_names,
        "warnings": warnings,
    }


@mcp.tool()
def auto_name_clip(track_index: int, clip_index: int, dry_run: bool = False) -> dict:
    """Auto-name a clip based on its MIDI content or audio file name."""
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
    except RuntimeError as e:
        return {"error": "Could not get clip info: {}".format(e)}

    inference_basis = "unknown"
    suggested_name = "Clip {}".format(clip_index + 1)

    clip_type = clip_info.get("type", clip_info.get("is_midi_clip"))
    is_midi = clip_type == "midi" or clip_type is True

    if not is_midi:
        file_path = clip_info.get("file_path", clip_info.get("sample_path", ""))
        if file_path:
            base = os.path.splitext(os.path.basename(file_path))[0]
            suggested_name = base
            inference_basis = "audio_filename"
        else:
            inference_basis = "default"
    else:
        notes = clip_info.get("notes", [])
        if notes:
            pitches = [n.get("pitch", n.get("note", 60)) for n in notes]
            avg_pitch = sum(pitches) / len(pitches)
            density = len(notes) / max(clip_info.get("length", 1.0), 0.001)

            if avg_pitch < 48:
                suggested_name = "Bass Line"
                inference_basis = "midi_low_register"
            elif avg_pitch > 72:
                if density < 2.0:
                    suggested_name = "Melody"
                    inference_basis = "midi_high_sparse"
                else:
                    suggested_name = "Lead"
                    inference_basis = "midi_high_dense"
            else:
                if density > 3.0:
                    suggested_name = "Chords"
                    inference_basis = "midi_mid_dense"
                else:
                    suggested_name = "Pad"
                    inference_basis = "midi_mid_sparse"
        else:
            inference_basis = "empty_midi"

    applied = False
    if not dry_run:
        try:
            _send("set_clip_name", {"track_index": track_index, "slot_index": clip_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "suggested_name": suggested_name,
                "inference_basis": inference_basis,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "clip_index": clip_index,
        "suggested_name": suggested_name,
        "inference_basis": inference_basis,
        "applied": applied,
    }


@mcp.tool()
def auto_name_scene(scene_index: int, dry_run: bool = False) -> dict:
    """Auto-name a scene based on the clip names in that scene row."""
    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    clip_names = []
    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        try:
            slots = _send("get_clip_slots", {"track_index": idx})
            if scene_index < len(slots):
                slot = slots[scene_index]
                clip_name = slot.get("clip_name", slot.get("name", ""))
                if clip_name:
                    clip_names.append(clip_name.lower())
        except RuntimeError as e:
            logger.debug("Could not get clip slots for track %s: %s", idx, e)

    combined = " ".join(clip_names)
    suggested_name = "Scene {}".format(scene_index + 1)
    inference_basis = "position"

    for keyword, color in _SCENE_SECTION_COLORS.items():
        if keyword == "default":
            continue
        if keyword in combined:
            suggested_name = keyword.capitalize()
            inference_basis = "clip_keyword"
            break

    applied = False
    if not dry_run:
        try:
            _send("set_scene_name", {"scene_index": scene_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "scene_index": scene_index,
                "suggested_name": suggested_name,
                "inference_basis": inference_basis,
                "applied": False,
                "error": str(e),
            }

    return {
        "scene_index": scene_index,
        "suggested_name": suggested_name,
        "inference_basis": inference_basis,
        "applied": applied,
    }
