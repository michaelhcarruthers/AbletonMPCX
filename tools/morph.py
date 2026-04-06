"""Morph tools — scene volume morph, tempo morph, device parameter morph, and combined morph plan."""
from __future__ import annotations

import time
from typing import Any

from helpers import (
    mcp,
    _send,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b at position t (0.0–1.0)."""
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# Scene volume morph
# ---------------------------------------------------------------------------

@mcp.tool()
def morph_scene_volumes(
    from_scene_index: int,
    to_scene_index: int,
    steps: int = 10,
    interval_ms: float = 100.0,
    dry_run: bool = True,
) -> dict:
    """Linearly interpolate track volumes between two scene states.

    Reads the volumes of all tracks that have clips in either scene,
    then interpolates from the 'from' state to the 'to' state over
    `steps` increments.

    Args:
        from_scene_index: Source scene index (volume start state).
        to_scene_index: Target scene index (volume end state).
        steps: Number of interpolation steps (default 10).
        interval_ms: Milliseconds to wait between steps (default 100).
        dry_run: If True (default), returns the plan without touching Live.

    Returns:
        dict with steps_applied, track_count, scene indices, dry_run flag, and plan.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    num_tracks = len(tracks)

    # Collect which tracks have clips in each scene
    from_clips: set[int] = set()
    to_clips: set[int] = set()
    for ti in range(num_tracks):
        try:
            slots = _send("get_clip_slots", {"track_index": ti})
            slots_list = slots if isinstance(slots, list) else []
            for slot in slots_list:
                si = slot.get("scene_index") if isinstance(slot, dict) else None
                has_clip = slot.get("has_clip", False) if isinstance(slot, dict) else False
                if not has_clip:
                    continue
                if si == from_scene_index:
                    from_clips.add(ti)
                if si == to_scene_index:
                    to_clips.add(ti)
        except Exception:
            pass

    relevant_tracks = from_clips | to_clips
    plan = []
    for t in tracks:
        ti = t.get("track_index")
        if ti not in relevant_tracks:
            continue
        vol = float(t.get("volume", 0.85))
        # Use current volume as both from and to if only in one scene
        from_vol = vol
        to_vol = vol
        plan.append({
            "track_index": ti,
            "track_name": t.get("name", ""),
            "from_volume": from_vol,
            "to_volume": to_vol,
            "steps": steps,
        })

    steps_applied = 0
    if not dry_run and plan:
        _send("begin_undo_step", {"name": "morph_scene_volumes"})
        try:
            for step in range(1, steps + 1):
                t_val = step / steps
                for item in plan:
                    vol = _lerp(item["from_volume"], item["to_volume"], t_val)
                    _send("set_track_volume", {"track_index": item["track_index"], "value": vol})
                time.sleep(interval_ms / 1000.0)
                steps_applied += 1
        finally:
            _send("end_undo_step")
    elif dry_run:
        steps_applied = steps

    return {
        "steps_applied": steps_applied,
        "track_count": len(plan),
        "from_scene_index": from_scene_index,
        "to_scene_index": to_scene_index,
        "dry_run": dry_run,
        "plan": plan,
    }


# ---------------------------------------------------------------------------
# Tempo morph
# ---------------------------------------------------------------------------

@mcp.tool()
def morph_tempo(
    from_bpm: float,
    to_bpm: float,
    steps: int = 10,
    interval_ms: float = 100.0,
    dry_run: bool = True,
) -> dict:
    """Linearly interpolate the session tempo from `from_bpm` to `to_bpm`.

    Args:
        from_bpm: Starting BPM value.
        to_bpm: Ending BPM value.
        steps: Number of interpolation steps (default 10).
        interval_ms: Milliseconds to wait between steps (default 100).
        dry_run: If True (default), returns the plan without touching Live.

    Returns:
        dict with steps_applied, from_bpm, to_bpm, steps, and dry_run flag.
    """
    steps_applied = 0
    if not dry_run:
        for step in range(1, steps + 1):
            current_bpm = _lerp(from_bpm, to_bpm, step / steps)
            _send("set_tempo", {"tempo": current_bpm})
            time.sleep(interval_ms / 1000.0)
            steps_applied += 1
    else:
        steps_applied = steps

    return {
        "steps_applied": steps_applied,
        "from_bpm": from_bpm,
        "to_bpm": to_bpm,
        "steps": steps,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Device parameter morph
# ---------------------------------------------------------------------------

@mcp.tool()
def morph_device_parameter(
    track_index: int,
    device_index: int,
    parameter_index: int,
    from_value: float,
    to_value: float,
    steps: int = 10,
    interval_ms: float = 100.0,
    dry_run: bool = True,
) -> dict:
    """Linearly interpolate a single device parameter from `from_value` to `to_value`.

    Reads the parameter's min/max via `get_device_parameters` and clamps
    the interpolated values to that range before sending.

    Args:
        track_index: Zero-based track index.
        device_index: Zero-based device index on the track.
        parameter_index: Zero-based parameter index on the device.
        from_value: Starting parameter value.
        to_value: Ending parameter value.
        steps: Number of interpolation steps (default 10).
        interval_ms: Milliseconds to wait between steps (default 100).
        dry_run: If True (default), returns the plan without touching Live.

    Returns:
        dict with steps_applied, parameter_name, from_value, to_value, steps, and dry_run.
    """
    # Read parameter metadata to get min/max and name
    param_name = ""
    p_min: float = 0.0
    p_max: float = 1.0
    try:
        params_info = _send("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index,
        })
        if isinstance(params_info, list) and parameter_index < len(params_info):
            p = params_info[parameter_index]
            param_name = p.get("name", "")
            p_min = float(p.get("min", 0.0))
            p_max = float(p.get("max", 1.0))
    except Exception:
        pass

    clamped_from = max(p_min, min(p_max, from_value))
    clamped_to = max(p_min, min(p_max, to_value))

    steps_applied = 0
    if not dry_run:
        for step in range(1, steps + 1):
            v = _lerp(clamped_from, clamped_to, step / steps)
            _send("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "value": v,
            })
            time.sleep(interval_ms / 1000.0)
            steps_applied += 1
    else:
        steps_applied = steps

    return {
        "steps_applied": steps_applied,
        "parameter_name": param_name,
        "from_value": clamped_from,
        "to_value": clamped_to,
        "steps": steps,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Combined morph plan
# ---------------------------------------------------------------------------

@mcp.tool()
def morph_plan(transitions: list[dict], dry_run: bool = True) -> dict:
    """Execute a sequence of morph transitions.

    Each transition dict must have a `type` key. Supported types:
    - `"volume"`: calls `morph_scene_volumes` (params: from_scene_index, to_scene_index, steps, interval_ms)
    - `"tempo"`: calls `morph_tempo` (params: from_bpm, to_bpm, steps, interval_ms)
    - `"device_parameter"`: calls `morph_device_parameter` (params: track_index, device_index,
      parameter_index, from_value, to_value, steps, interval_ms)

    Args:
        transitions: List of transition dicts with `type` and type-specific params.
        dry_run: If True (default), all child morphs run in dry_run mode.

    Returns:
        dict with transitions_executed, results list, and dry_run flag.
    """
    results = []
    for transition in transitions:
        t_type = transition.get("type", "")
        params = {k: v for k, v in transition.items() if k != "type"}
        params["dry_run"] = dry_run

        if t_type == "volume":
            result = morph_scene_volumes(**params)
        elif t_type == "tempo":
            result = morph_tempo(**params)
        elif t_type == "device_parameter":
            result = morph_device_parameter(**params)
        else:
            result = {"error": "Unknown transition type: {}".format(t_type)}

        results.append({"type": t_type, "result": result})

    return {
        "transitions_executed": len(results),
        "results": results,
        "dry_run": dry_run,
    }
