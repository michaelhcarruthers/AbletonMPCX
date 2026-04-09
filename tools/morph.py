"""Morph tools — scene volume morph, tempo morph, device parameter morph, and combined morph plan."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from helpers import (
    mcp,
    _send,
)


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
    """Linearly interpolate track volumes between two scene states."""
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
        except Exception as e:
            logger.debug("Could not get clip slots for track %s: %s", ti, e)

    relevant_tracks = from_clips | to_clips
    plan = []
    for t in tracks:
        ti = t.get("track_index")
        if ti not in relevant_tracks:
            continue
        vol = float(t.get("volume", 0.85))
        # Tracks only in from_scene fade out; tracks only in to_scene fade in;
        # tracks in both scenes stay at their current volume.
        if ti in from_clips and ti not in to_clips:
            from_vol = vol
            to_vol = 0.0
        elif ti in to_clips and ti not in from_clips:
            from_vol = 0.0
            to_vol = vol
        else:
            from_vol = vol
            to_vol = vol
        plan.append({
            "track_index": ti,
            "track_name": t.get("name", ""),
            "from_volume": from_vol,
            "to_volume": to_vol,
            "steps": steps,
        })

    stepped_morph = False
    if not dry_run and plan:
        _send("begin_undo_step", {"name": "morph_scene_volumes"})
        try:
            states = [{"track_index": item["track_index"], "volume": item["to_volume"]} for item in plan]
            _send("set_mixer_snapshot", {"states": states})
        finally:
            _send("end_undo_step")

    return {
        "steps_scheduled": 0 if dry_run else 1,
        "track_count": len(plan),
        "from_scene_index": from_scene_index,
        "to_scene_index": to_scene_index,
        "stepped_morph": stepped_morph,
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
    """Linearly interpolate the session tempo from ``from_bpm`` to ``to_bpm``."""
    stepped_morph = False
    if not dry_run:
        _send("set_tempo", {"tempo": to_bpm})

    return {
        "steps_scheduled": 0 if dry_run else 1,
        "from_bpm": from_bpm,
        "to_bpm": to_bpm,
        "steps": steps,
        "stepped_morph": stepped_morph,
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
    """Animate a single device parameter from ``from_value`` to ``to_value``."""
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
    except Exception as e:
        logger.debug("Could not get device parameters for morph validation: %s", e)
    clamped_from = max(p_min, min(p_max, from_value))
    clamped_to = max(p_min, min(p_max, to_value))

    duration_ms = steps * interval_ms
    moves = [
        {
            "parameter_index": parameter_index,
            "target": clamped_to,
            "duration_ms": duration_ms,
            "curve": "linear",
        }
    ]

    if not dry_run:
        # Snap the parameter to the starting value before scheduling the animation
        _send("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
            "value": clamped_from,
        })
        _send("perform_device_parameter_moves", {
            "track_index": track_index,
            "device_index": device_index,
            "moves": moves,
        })

    return {
        "steps_scheduled": 0 if dry_run else steps,
        "parameter_name": param_name,
        "from_value": clamped_from,
        "to_value": clamped_to,
        "steps": steps,
        "moves": moves,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Combined morph plan
# ---------------------------------------------------------------------------

@mcp.tool()
def morph_plan(transitions: list[dict], dry_run: bool = True) -> dict:
    """Execute a sequence of morph transitions."""
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
        "transitions_scheduled": len(results),
        "results": results,
        "dry_run": dry_run,
    }
