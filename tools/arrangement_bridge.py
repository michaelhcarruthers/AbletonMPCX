"""Arrangement automation tools — write volume and dynamic automation
via the Remote Script (port 9877). No M4L bridge device required.
"""
from __future__ import annotations

from typing import Any

from helpers import mcp, _send


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
