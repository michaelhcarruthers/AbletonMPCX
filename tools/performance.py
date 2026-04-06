"""Performance tools — performance FX (reverb throw, filter sweep, stutter), DJ blend/transition macros, and the macro execution engine."""
from __future__ import annotations

import collections
import copy
import datetime
import json
import math
import os
import pathlib
import plistlib
import re
import shutil
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any

import helpers
from helpers import (
    mcp,
    _send,
    _send_logged,
    _append_operation,
    _operation_log,
    _MAX_LOG_ENTRIES,
    _snapshots,
    _reference_profiles,
    _audio_analysis_cache,
    _get_memory,
    _save_memory,
    _load_memory,
    _memory_path,
    _save_reference_profile,
    _load_reference_profiles_from_project,
)

# ---------------------------------------------------------------------------
# Performance FX MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def reverb_throw(
    track_index: int,
    start_bar: int,
    start_beat: float,
    length_beats: float = 1.0,
    device_index: int | None = None,
    peak_wet: float = 0.9,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Add a reverb throw automation: Dry/Wet ramps from 0 → peak_wet → 0 over length_beats.

    Finds the first Reverb device on the track (or use device_index to specify one).
    If no Reverb is found, adds one first.
    Writes automation to the Dry/Wet parameter in the Arrangement View.

    The shape is: 0 at start, peak_wet at midpoint, 0 at end.

    Args:
        track_index: Track to add the effect to.
        start_bar: 1-based bar number where the throw starts.
        start_beat: 1-based beat within the bar.
        length_beats: Duration of the throw in beats (default 1.0 = one beat).
        device_index: Specific device index. If None, finds first Reverb on track.
        peak_wet: Peak Dry/Wet value (0.0-1.0, default 0.9).
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        track_index, device_index, device_name, parameter_name,
        start_time_beats, end_time_beats, peak_wet, points_written
    """
    _send("begin_undo_step", {"name": "reverb_throw"})
    try:
        if device_index is None:
            device_index = _find_or_add_device(track_index, "Reverb")

        devices = _send("get_devices", {"track_index": track_index}, _log=False)
        device_name = next(
            (d["name"] for d in devices if d["index"] == device_index),
            "Reverb",
        )

        param_idx, param_info = _find_device_parameter_by_name(
            track_index, device_index, "Dry/Wet"
        )

        start_time = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)
        mid_time = start_time + length_beats / 2.0
        end_time = start_time + length_beats

        points = [
            {"time": start_time, "value": 0.0},
            {"time": mid_time, "value": peak_wet},
            {"time": end_time, "value": 0.0},
        ]

        result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": param_idx,
            "points": points,
            "clear_range": True,
        })
    finally:
        _send("end_undo_step", {})

    return {
        "track_index": track_index,
        "device_index": device_index,
        "device_name": device_name,
        "parameter_name": param_info["name"],
        "start_time_beats": start_time,
        "end_time_beats": end_time,
        "peak_wet": peak_wet,
        "points_written": result.get("points_written", len(points)),
    }


@mcp.tool()
def filter_sweep(
    track_index: int,
    start_bar: int,
    start_beat: float,
    length_beats: float = 4.0,
    start_freq_hz: float = 200.0,
    end_freq_hz: float = 18000.0,
    device_index: int | None = None,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Add a filter sweep: automates Auto Filter cutoff frequency from start_freq to end_freq.

    Finds the first Auto Filter on the track (or use device_index).
    If no Auto Filter is found, adds one.
    Writes a linear ramp on the frequency parameter in the Arrangement View.

    Args:
        track_index: Track to sweep.
        start_bar: 1-based bar number where the sweep starts.
        start_beat: 1-based beat within the bar.
        length_beats: Duration of the sweep in beats.
        start_freq_hz: Starting cutoff frequency in Hz.
        end_freq_hz: Ending cutoff frequency in Hz.
        device_index: Specific Auto Filter device index. If None, auto-detect.
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        track_index, device_index, start_freq_hz, end_freq_hz,
        start_time_beats, end_time_beats, points_written
    """
    _send("begin_undo_step", {"name": "filter_sweep"})
    try:
        if device_index is None:
            device_index = _find_or_add_device(track_index, "Auto Filter")

        param_idx, param_info = _find_device_parameter_by_name(
            track_index, device_index, "Frequency"
        )

        start_time = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)
        end_time = start_time + length_beats

        points = [
            {"time": start_time, "value": start_freq_hz},
            {"time": end_time, "value": end_freq_hz},
        ]

        result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": param_idx,
            "points": points,
            "clear_range": True,
        })
    finally:
        _send("end_undo_step", {})

    return {
        "track_index": track_index,
        "device_index": device_index,
        "start_freq_hz": start_freq_hz,
        "end_freq_hz": end_freq_hz,
        "start_time_beats": start_time,
        "end_time_beats": end_time,
        "points_written": result.get("points_written", len(points)),
    }


@mcp.tool()
def delay_echo_out(
    track_index: int,
    start_bar: int,
    start_beat: float,
    length_beats: float = 2.0,
    device_index: int | None = None,
    peak_feedback: float = 0.85,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Add a delay echo-out: ramps Feedback up then cuts Dry/Wet to 0 at the end.

    Finds the first Delay or Echo device on the track (or use device_index).
    If no delay device is found, adds a Simple Delay.

    Shape:
    - Feedback: ramps from current value to peak_feedback over length_beats
    - Dry/Wet: stays at current value, then snaps to 0 at the end

    Args:
        track_index: Track to apply the echo-out to.
        start_bar: 1-based bar number.
        start_beat: 1-based beat.
        length_beats: Duration in beats.
        device_index: Specific delay device. If None, auto-detect.
        peak_feedback: Maximum feedback value (0.0-1.0).
        time_signature_numerator: Beats per bar.

    Returns:
        track_index, device_index, device_name, start_time_beats, end_time_beats, points_written
    """
    _send("begin_undo_step", {"name": "delay_echo_out"})
    try:
        if device_index is None:
            # Try to find an existing delay or echo device
            devices = _send("get_devices", {"track_index": track_index}, _log=False)
            device_index = None
            for d in devices:
                name_lower = d["name"].lower()
                if "delay" in name_lower or "echo" in name_lower:
                    device_index = d["index"]
                    break
            if device_index is None:
                device_index = _find_or_add_device(track_index, "Delay")

        devices = _send("get_devices", {"track_index": track_index}, _log=False)
        device_name = next(
            (d["name"] for d in devices if d["index"] == device_index),
            "Delay",
        )

        start_time = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)
        end_time = start_time + length_beats

        total_points = 0

        # Feedback: ramp from current to peak_feedback
        try:
            fb_idx, fb_info = _find_device_parameter_by_name(
                track_index, device_index, "Feedback"
            )
            current_feedback = fb_info.get("value", 0.5)
            fb_points = [
                {"time": start_time, "value": current_feedback},
                {"time": end_time, "value": peak_feedback},
            ]
            fb_result = _send("write_arrangement_automation", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": fb_idx,
                "points": fb_points,
                "clear_range": True,
            })
            total_points += fb_result.get("points_written", len(fb_points))
        except (RuntimeError, Exception):
            pass

        # Dry/Wet: snap to 0 at the end
        try:
            dw_idx, dw_info = _find_device_parameter_by_name(
                track_index, device_index, "Dry/Wet"
            )
            current_wet = dw_info.get("value", 1.0)
            dw_points = [
                {"time": start_time, "value": current_wet},
                {"time": end_time - 0.001, "value": current_wet},
                {"time": end_time, "value": 0.0},
            ]
            dw_result = _send("write_arrangement_automation", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": dw_idx,
                "points": dw_points,
                "clear_range": True,
            })
            total_points += dw_result.get("points_written", len(dw_points))
        except (RuntimeError, Exception):
            pass

    finally:
        _send("end_undo_step", {})

    return {
        "track_index": track_index,
        "device_index": device_index,
        "device_name": device_name,
        "start_time_beats": start_time,
        "end_time_beats": end_time,
        "points_written": total_points,
    }


@mcp.tool()
def stutter_clip(
    track_index: int,
    start_bar: int,
    start_beat: float,
    length_beats: float = 1.0,
    chop_size_beats: float = 0.125,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Create a volume stutter effect by automating track volume on/off at chop_size_beats intervals.

    Writes alternating 0.0/1.0 volume automation points to create a gate/chop effect.
    Uses the track's mixer volume parameter in the Arrangement View.

    Args:
        track_index: Track to stutter.
        start_bar: 1-based bar number.
        start_beat: 1-based beat.
        length_beats: Total duration of the stutter in beats.
        chop_size_beats: Size of each chop in beats (default 0.125 = 1/32 note at 1 beat = quarter).
        time_signature_numerator: Beats per bar.

    Returns:
        track_index, start_time_beats, end_time_beats, chop_count, points_written
    """
    _send("begin_undo_step", {"name": "stutter_clip"})
    try:
        # Get the volume parameter index from the mixer
        mixer_params = _send("get_arrangement_automation_targets", {
            "track_index": track_index,
        }, _log=False)
        params_list = mixer_params.get("parameters", [])
        vol_idx = None
        for p in params_list:
            if "volume" in p["name"].lower() or "vol" in p["name"].lower():
                vol_idx = p["parameter_index"]
                break
        if vol_idx is None:
            # Fallback: use index 0 (typically volume for mixer)
            vol_idx = 0

        start_time = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)
        end_time = start_time + length_beats

        points = []
        t = start_time
        on = True
        chop_count = 0
        while t < end_time:
            points.append({"time": t, "value": 1.0 if on else 0.0})
            t += chop_size_beats
            on = not on
            chop_count += 1
        # Restore volume at the end
        points.append({"time": end_time, "value": 1.0})

        result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "device_index": None,
            "parameter_index": vol_idx,
            "points": points,
            "clear_range": True,
        })
    finally:
        _send("end_undo_step", {})

    return {
        "track_index": track_index,
        "start_time_beats": start_time,
        "end_time_beats": end_time,
        "chop_count": chop_count,
        "points_written": result.get("points_written", len(points)),
    }


@mcp.tool()
def add_performance_fx(
    track_index: int,
    fx_type: str,
    start_bar: int,
    start_beat: float,
    length_beats: float = 1.0,
    time_signature_numerator: int = 4,
    **kwargs,
) -> dict:
    """
    Add a performance effect to a track at a musical position.

    This is the unified entry point — dispatches to the appropriate specific tool.

    fx_type options:
        'reverb_throw'   — reverb wet automation swell
        'filter_sweep'   — Auto Filter cutoff ramp
        'delay_echo_out' — delay feedback ramp + wet cutoff
        'stutter'        — volume chop gate

    Args:
        track_index: Track to apply the effect to.
        fx_type: Type of effect (see above).
        start_bar: 1-based bar number.
        start_beat: 1-based beat within the bar.
        length_beats: Duration in beats.
        time_signature_numerator: Beats per bar (default 4).
        **kwargs: Additional parameters passed to the specific effect tool.
                  e.g. peak_wet=0.8 for reverb_throw,
                       start_freq_hz=100, end_freq_hz=8000 for filter_sweep

    Returns:
        fx_type, track_index, start_bar, start_beat, length_beats,
        plus all fields returned by the specific effect tool.

    Examples:
        add_performance_fx(0, 'reverb_throw', 50, 3, 1.0)
        add_performance_fx(1, 'filter_sweep', 32, 1, 4.0, start_freq_hz=80, end_freq_hz=12000)
        add_performance_fx(2, 'stutter', 64, 1, 1.0, chop_size_beats=0.0625)
    """
    common_kwargs = dict(
        track_index=track_index,
        start_bar=start_bar,
        start_beat=start_beat,
        length_beats=length_beats,
        time_signature_numerator=time_signature_numerator,
    )
    common_kwargs.update(kwargs)

    fx_map = {
        "reverb_throw": reverb_throw,
        "filter_sweep": filter_sweep,
        "delay_echo_out": delay_echo_out,
        "stutter": stutter_clip,
    }

    if fx_type not in fx_map:
        raise ValueError(
            "Unknown fx_type '{}'. Valid options: {}".format(
                fx_type, list(fx_map.keys())
            )
        )

    specific_result = fx_map[fx_type](**common_kwargs)

    return {
        "fx_type": fx_type,
        "track_index": track_index,
        "start_bar": start_bar,
        "start_beat": start_beat,
        "length_beats": length_beats,
        **specific_result,
    }

# ---------------------------------------------------------------------------
# Performance macro definitions
# Each entry is a list of parameter targets. The execution engine in
# perform_macro() reads these — adding a new macro never requires code changes.
#
# curve: list of (position_ratio, value) tuples
#   position_ratio: 0.0 = start of range, 1.0 = end of range
#   value: raw parameter value (0.0–1.0 normalized unless otherwise noted)
#
# device: substring to match against device name (case-insensitive)
# param: substring to match against parameter name (case-insensitive)
# required: if True, device is required; missing required steps are flagged in check_macro_readiness()
# ---------------------------------------------------------------------------

_MACRO_DEFINITIONS: dict[str, list[dict]] = {
    "build": [
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.1), (1.0, 0.85)], "required": False},
        {"device": "Auto Filter", "param": "Resonance",  "curve": [(0.0, 0.2), (1.0, 0.55)], "required": False},
        {"device": "Saturator",   "param": "Drive",       "curve": [(0.0, 0.0), (1.0, 0.65)], "required": False},
        {"device": "Utility",     "param": "Width",       "curve": [(0.0, 0.8), (1.0, 1.0)],  "required": False},
        {"device": "Reverb",      "param": "Dry/Wet",     "curve": [(0.0, 0.0), (1.0, 0.35)], "required": False},
    ],
    "break": [
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.85), (1.0, 0.05)], "required": False},
        {"device": "Auto Filter", "param": "Resonance",  "curve": [(0.0, 0.2),  (1.0, 0.6)],  "required": False},
        {"device": "Simple Delay", "param": "Feedback",  "curve": [(0.0, 0.3),  (0.7, 0.85), (1.0, 0.0)], "required": False},
        {"device": "Utility",     "param": "Width",      "curve": [(0.0, 1.0),  (1.0, 0.6)],  "required": False},
    ],
    "throw": [
        {"device": "Reverb",      "param": "Dry/Wet",    "curve": [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)], "required": False},
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.4), (0.5, 0.85), (1.0, 0.4)], "required": False},
    ],
    "drop": [
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.9),  (1.0, 0.04)], "required": False},
        {"device": "Simple Delay", "param": "Dry/Wet",   "curve": [(0.0, 0.0),  (0.6, 0.8),  (1.0, 0.0)], "required": False},
        {"device": "Simple Delay", "param": "Feedback",  "curve": [(0.0, 0.3),  (0.8, 0.85), (1.0, 0.0)], "required": False},
    ],
    "heat": [
        {"device": "Saturator",   "param": "Drive",      "curve": [(0.0, 0.0), (1.0, 0.8)],  "required": False},
        {"device": "Auto Filter", "param": "Resonance",  "curve": [(0.0, 0.2), (1.0, 0.7)],  "required": False},
        {"device": "Compressor",  "param": "Threshold",  "curve": [(0.0, 0.7), (1.0, 0.3)],  "required": False},
    ],
    "space": [
        {"device": "Reverb",       "param": "Dry/Wet",   "curve": [(0.0, 0.05), (1.0, 0.7)],  "required": False},
        {"device": "Simple Delay", "param": "Dry/Wet",   "curve": [(0.0, 0.0),  (1.0, 0.5)],  "required": False},
        {"device": "Utility",     "param": "Width",      "curve": [(0.0, 0.7), (1.0, 1.0)],  "required": False},
    ],
    "tension": [
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.7), (1.0, 0.12)], "required": False},
        {"device": "Auto Filter", "param": "Resonance",  "curve": [(0.0, 0.3), (1.0, 0.75)], "required": False},
        {"device": "Saturator",   "param": "Drive",      "curve": [(0.0, 0.1), (1.0, 0.55)], "required": False},
    ],
    "release": [
        {"device": "Reverb",      "param": "Dry/Wet",    "curve": [(0.0, 0.0), (0.3, 0.9), (1.0, 0.3)], "required": False},
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.1), (1.0, 0.95)], "required": False},
        {"device": "Saturator",   "param": "Drive",      "curve": [(0.0, 0.6), (1.0, 0.0)],  "required": False},
        {"device": "Utility",     "param": "Width",      "curve": [(0.0, 0.5), (1.0, 1.0)],  "required": False},
    ],
    "filter_drive": [
        # The classic combo: filter sweep + drive rise together
        {"device": "Auto Filter", "param": "Frequency",  "curve": [(0.0, 0.1), (1.0, 0.9)],  "required": True},
        {"device": "Auto Filter", "param": "Resonance",  "curve": [(0.0, 0.2), (0.7, 0.65), (1.0, 0.3)], "required": False},
        {"device": "Saturator",   "param": "Drive",      "curve": [(0.0, 0.1), (0.6, 0.75), (1.0, 0.2)], "required": False},
    ],
}

_SETUP_CHAINS: dict[str, list[tuple[str, dict]]] = {
    "dj_throw_bus": [
        ("Reverb", {}),
        ("Simple Delay", {}),
        ("Auto Filter", {}),
        ("Utility", {}),
    ],
    "build_chain": [
        ("Auto Filter", {}),
        ("Saturator", {}),
        ("Utility", {}),
    ],
    "heat_chain": [
        ("Saturator", {}),
        ("Compressor", {}),
        ("Auto Filter", {}),
    ],
}



@mcp.tool()
def list_macro_definitions() -> dict:
    """
    List all available performance macro names and the devices/parameters each requires.

    Use this before calling perform_macro() or check_macro_readiness() to see
    what macros are available and what they target.

    Returns:
        macros: dict of {macro_name: {steps: [{device, param, required}], step_count}}
        available_macro_names: list of macro name strings
        setup_chains: list of available setup chain names (for setup_fx_chain())
    """
    macros = {}
    for name, steps in _MACRO_DEFINITIONS.items():
        macros[name] = {
            "steps": [
                {
                    "device": s["device"],
                    "param": s["param"],
                    "required": s.get("required", False),
                }
                for s in steps
            ],
            "step_count": len(steps),
        }
    return {
        "macros": macros,
        "available_macro_names": sorted(_MACRO_DEFINITIONS.keys()),
        "setup_chains": sorted(_SETUP_CHAINS.keys()),
    }


@mcp.tool()
def check_macro_readiness(track_index: int, macro_name: str) -> dict:
    """
    Check whether all required devices for a macro are present on the track.

    Call this before perform_macro() to get a pre-flight report without
    making any changes. Claude can use this to tell you what's missing
    and offer to run setup_fx_chain() to fix it.

    Args:
        track_index: Track to check (-1 for master).
        macro_name: Name of the macro to check (see list_macro_definitions()).

    Returns:
        macro_name, ready (bool),
        steps_ready: list of {device, param, device_index, device_name, parameter_index, status: "ready"}
        steps_missing: list of {device, param, required, status: "missing", reason}
        can_partially_apply (bool): True if at least one non-required step is ready
        suggestion: human-readable message about what to do next
    """
    if macro_name not in _MACRO_DEFINITIONS:
        raise ValueError(
            "Unknown macro '{}'. Available: {}".format(macro_name, sorted(_MACRO_DEFINITIONS.keys()))
        )

    steps = _MACRO_DEFINITIONS[macro_name]

    try:
        devices_result = _send("get_devices", {"track_index": track_index})
    except Exception as e:
        raise RuntimeError("Could not get devices for track {}: {}".format(track_index, e))

    steps_ready = []
    steps_missing = []

    for step in steps:
        device_name_pattern = step["device"].lower()
        param_name_pattern = step["param"].lower()

        # Find device
        matched_device = None
        for d in devices_result:
            if device_name_pattern in d["name"].lower():
                matched_device = d
                break

        if matched_device is None:
            steps_missing.append({
                "device": step["device"],
                "param": step["param"],
                "required": step.get("required", False),
                "status": "missing",
                "reason": "No device matching '{}' found on track {}".format(step["device"], track_index),
            })
            continue

        # Find parameter
        try:
            params_result = _send("get_device_parameters", {
                "track_index": track_index,
                "device_index": matched_device["index"],
            })
        except Exception:
            steps_missing.append({
                "device": step["device"],
                "param": step["param"],
                "required": step.get("required", False),
                "status": "missing",
                "reason": "Could not read parameters from '{}'".format(matched_device["name"]),
            })
            continue

        matched_param = None
        for p in params_result.get("parameters", []):
            if param_name_pattern in p["name"].lower():
                matched_param = p
                break

        if matched_param is None:
            steps_missing.append({
                "device": step["device"],
                "param": step["param"],
                "required": step.get("required", False),
                "status": "missing",
                "reason": "Parameter '{}' not found on device '{}'".format(
                    step["param"], matched_device["name"]),
            })
        else:
            steps_ready.append({
                "device": step["device"],
                "param": step["param"],
                "device_index": matched_device["index"],
                "device_name": matched_device["name"],
                "parameter_index": matched_param["index"],
                "parameter_name": matched_param["name"],
                "status": "ready",
            })

    all_ready = len(steps_missing) == 0
    can_partially_apply = len(steps_ready) > 0

    if all_ready:
        suggestion = "Macro '{}' is fully ready on track {}.".format(macro_name, track_index)
    elif can_partially_apply:
        missing_devices = list({s["device"] for s in steps_missing})
        suggestion = (
            "Macro '{}' will partially apply ({}/{} steps ready). "
            "Missing devices: {}. "
            "Run setup_fx_chain(track_index, 'build_chain') to add missing devices.".format(
                macro_name, len(steps_ready), len(steps), missing_devices)
        )
    else:
        suggestion = (
            "Macro '{}' cannot apply — no required devices found on track {}. "
            "Run setup_fx_chain() to create a suitable device chain first.".format(
                macro_name, track_index)
        )

    return {
        "macro_name": macro_name,
        "track_index": track_index,
        "ready": all_ready,
        "steps_ready": steps_ready,
        "steps_missing": steps_missing,
        "can_partially_apply": can_partially_apply,
        "suggestion": suggestion,
    }


@mcp.tool()
def perform_macro(
    track_index: int,
    macro_name: str,
    start_bar: int,
    start_beat: float,
    length_beats: float,
    intensity: float = 1.0,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Trigger a named performance macro on a track at a musical position.

    A macro is a multi-parameter gesture — it targets multiple devices and
    parameters simultaneously to create a musical effect (build, throw, drop, etc).

    IMPORTANT: This tool NEVER adds devices. It only targets devices already
    present on the track. Use check_macro_readiness() first to see what's available,
    and setup_fx_chain() to add missing devices if needed.

    intensity (0.0–1.0) scales all parameter values proportionally.
    At intensity=1.0 the full curve values are used.
    At intensity=0.5 all values are halved relative to their mid-point.

    Available macros: build, break, throw, drop, heat, space, tension, release, filter_drive
    Use list_macro_definitions() to see all available macros and their targets.

    Args:
        track_index: Track to apply the macro to (-1 for master).
        macro_name: Name of the macro (e.g. 'build', 'throw', 'drop').
        start_bar: 1-based bar number where the macro starts.
        start_beat: 1-based beat within the bar.
        length_beats: Duration of the macro in beats.
        intensity: Scale factor for all parameter values (0.0–1.0, default 1.0).
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        macro_name, track_index, start_time_beats, end_time_beats, intensity,
        applied: list of {device_name, parameter_name, points_written}
        skipped: list of {device, param, reason}
        applied_count, skipped_count

    Example:
        perform_macro(1, 'build', 31, 1, 4.0)
        perform_macro(0, 'throw', 50, 3, 1.0, intensity=0.7)
        perform_macro(2, 'filter_drive', 64, 1, 2.0)
    """
    if macro_name not in _MACRO_DEFINITIONS:
        raise ValueError(
            "Unknown macro '{}'. Available: {}".format(macro_name, sorted(_MACRO_DEFINITIONS.keys()))
        )

    intensity = max(0.0, min(1.0, intensity))
    steps = _MACRO_DEFINITIONS[macro_name]

    # Convert musical time to beats
    start_time = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)
    end_time = start_time + length_beats

    try:
        devices_result = _send("get_devices", {"track_index": track_index})
    except Exception as e:
        raise RuntimeError("Could not get devices for track {}: {}".format(track_index, e))

    applied = []
    skipped = []

    _send("begin_undo_step", {"name": "perform_macro: {}".format(macro_name)})
    try:
        for step in steps:
            device_name_pattern = step["device"].lower()
            param_name_pattern = step["param"].lower()

            # Find device on track
            matched_device = None
            for d in devices_result:
                if device_name_pattern in d["name"].lower():
                    matched_device = d
                    break

            if matched_device is None:
                skipped.append({
                    "device": step["device"],
                    "param": step["param"],
                    "reason": "No device matching '{}' found on track {}".format(
                        step["device"], track_index),
                })
                continue

            # Find parameter
            try:
                params_result = _send("get_device_parameters", {
                    "track_index": track_index,
                    "device_index": matched_device["index"],
                })
            except Exception as e:
                skipped.append({
                    "device": step["device"],
                    "param": step["param"],
                    "reason": "Could not read parameters: {}".format(str(e)),
                })
                continue

            matched_param = None
            for p in params_result.get("parameters", []):
                if param_name_pattern in p["name"].lower():
                    matched_param = p
                    break

            if matched_param is None:
                skipped.append({
                    "device": step["device"],
                    "param": step["param"],
                    "reason": "Parameter '{}' not found on '{}'".format(
                        step["param"], matched_device["name"]),
                })
                continue

            # Build automation points from curve + intensity scaling
            curve = step["curve"]
            points = []
            for pos_ratio, value in curve:
                # Scale value by intensity around the midpoint (0.5)
                scaled_value = 0.5 + (value - 0.5) * intensity
                scaled_value = max(0.0, min(1.0, scaled_value))
                abs_time = start_time + pos_ratio * length_beats
                points.append({"time": abs_time, "value": scaled_value})

            # Write automation
            try:
                write_result = _send("write_arrangement_automation", {
                    "track_index": track_index,
                    "device_index": matched_device["index"],
                    "parameter_index": matched_param["index"],
                    "points": points,
                    "clear_range": True,
                })
                applied.append({
                    "device_name": matched_device["name"],
                    "parameter_name": matched_param["name"],
                    "points_written": write_result.get("points_written", len(points)),
                })
            except Exception as e:
                skipped.append({
                    "device": step["device"],
                    "param": step["param"],
                    "reason": "Automation write failed: {}".format(str(e)),
                })

    finally:
        _send("end_undo_step", {})

    return {
        "macro_name": macro_name,
        "track_index": track_index,
        "start_time_beats": start_time,
        "end_time_beats": end_time,
        "intensity": intensity,
        "applied": applied,
        "skipped": skipped,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
    }


@mcp.tool()
def setup_fx_chain(
    track_index: int,
    chain_type: str,
    track_name: str | None = None,
) -> dict:
    """
    Create a device chain on a track for use with performance macros.

    This is the ONLY tool that adds devices. It is intended for one-time
    setup — not for repeated use during performance.

    Best practice: run this on a dedicated return track or utility track,
    not on source tracks with existing processing chains.

    Available chain types:
        'dj_throw_bus'  — Reverb + Simple Delay + Auto Filter + Utility
        'build_chain'   — Auto Filter + Saturator + Utility
        'heat_chain'    — Saturator + Compressor + Auto Filter

    Use list_macro_definitions() to see which macros work best with each chain type.

    Args:
        track_index: Track to add the chain to (-1 for master).
        chain_type: Name of the chain preset (see above).
        track_name: Optional — rename the track after adding the chain.

    Returns:
        chain_type, track_index, devices_added: list of device names,
        device_count, track_name (if renamed)
    """
    if chain_type not in _SETUP_CHAINS:
        raise ValueError(
            "Unknown chain type '{}'. Available: {}".format(
                chain_type, sorted(_SETUP_CHAINS.keys()))
        )

    chain_steps = _SETUP_CHAINS[chain_type]
    devices_added = []

    _send("begin_undo_step", {"name": "setup_fx_chain: {}".format(chain_type)})
    try:
        for device_name, _ in chain_steps:
            try:
                _send("add_native_device", {
                    "track_index": track_index,
                    "device_name": device_name,
                })
                devices_added.append(device_name)
            except Exception as e:
                # Non-fatal: log and continue
                devices_added.append("{} (FAILED: {})".format(device_name, str(e)))

        if track_name:
            try:
                _send("set_track_name", {"track_index": track_index, "name": track_name})
            except Exception:
                pass
    finally:
        _send("end_undo_step", {})

    return {
        "chain_type": chain_type,
        "track_index": track_index,
        "devices_added": devices_added,
        "device_count": len([d for d in devices_added if "FAILED" not in d]),
        "track_name": track_name,
    }


@mcp.tool()
def set_macro_intensity(
    track_index: int,
    macro_name: str,
    intensity: float,
) -> dict:
    """
    Apply a macro's end-state parameter values at a fixed intensity — no automation.

    Unlike perform_macro() which writes time-based automation curves,
    this sets all macro parameters to their 'end' values scaled by intensity,
    immediately and statically. Useful for real-time level setting.

    intensity=0.0 sets all parameters to their curve start values.
    intensity=1.0 sets all parameters to their curve end values.
    intensity=0.5 sets all to the midpoint between start and end.

    Args:
        track_index: Track to apply to.
        macro_name: Macro name (see list_macro_definitions()).
        intensity: 0.0–1.0 blend between start and end curve values.

    Returns:
        macro_name, track_index, intensity,
        applied: list of {device_name, parameter_name, value_set}
        skipped: list of {device, param, reason}
    """
    if macro_name not in _MACRO_DEFINITIONS:
        raise ValueError(
            "Unknown macro '{}'. Available: {}".format(macro_name, sorted(_MACRO_DEFINITIONS.keys()))
        )

    intensity = max(0.0, min(1.0, intensity))
    steps = _MACRO_DEFINITIONS[macro_name]

    try:
        devices_result = _send("get_devices", {"track_index": track_index})
    except Exception as e:
        raise RuntimeError("Could not get devices for track {}: {}".format(track_index, e))

    applied = []
    skipped = []

    for step in steps:
        device_name_pattern = step["device"].lower()
        param_name_pattern = step["param"].lower()

        matched_device = None
        for d in devices_result:
            if device_name_pattern in d["name"].lower():
                matched_device = d
                break

        if matched_device is None:
            skipped.append({"device": step["device"], "param": step["param"],
                             "reason": "Device not found"})
            continue

        try:
            params_result = _send("get_device_parameters", {
                "track_index": track_index,
                "device_index": matched_device["index"],
            })
        except Exception:
            skipped.append({"device": step["device"], "param": step["param"],
                             "reason": "Could not read parameters"})
            continue

        matched_param = None
        for p in params_result.get("parameters", []):
            if param_name_pattern in p["name"].lower():
                matched_param = p
                break

        if matched_param is None:
            skipped.append({"device": step["device"], "param": step["param"],
                             "reason": "Parameter not found"})
            continue

        # Interpolate between first and last curve points
        curve = step["curve"]
        start_val = curve[0][1]
        end_val = curve[-1][1]
        value = start_val + (end_val - start_val) * intensity
        value = max(0.0, min(1.0, value))

        try:
            _send("set_device_parameter", {
                "track_index": track_index,
                "device_index": matched_device["index"],
                "parameter_index": matched_param["index"],
                "value": value,
            })
            applied.append({
                "device_name": matched_device["name"],
                "parameter_name": matched_param["name"],
                "value_set": round(value, 4),
            })
        except Exception as e:
            skipped.append({"device": step["device"], "param": step["param"],
                             "reason": "Set failed: {}".format(str(e))})

    return {
        "macro_name": macro_name,
        "track_index": track_index,
        "intensity": intensity,
        "applied": applied,
        "skipped": skipped,
    }



