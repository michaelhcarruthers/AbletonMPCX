"""Spectrum analyser tools — MCPSpectrum telemetry, band diagnostics, arrangement automation, and device parameter helpers."""
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
# Spectrum Telemetry
# ---------------------------------------------------------------------------

@mcp.tool()
def find_spectrum_analyzers(
    device_name_patterns: list | None = None,
    min_band_count: int = 4,
) -> dict:
    """
    Auto-discover spectrum analyzer devices across all tracks (including master and returns).

    Detection works in two ways:
    1. If device_name_patterns is provided, matches devices whose name contains any of the
       given substrings (case-insensitive).
    2. If device_name_patterns is None or empty, falls back to heuristic detection:
       any device with min_band_count or more parameters whose names contain 'Hz' or 'hz'
       is treated as a spectrum analyzer.

    This is the permanent, generic discovery path — it works regardless of plugin name
    changes. Add MCPSpectrum, Spectrum, or any third-party analyzer and it will be found.

    Args:
        device_name_patterns: Optional list of device name substrings to match,
                               e.g. ["MCPSpectrum", "Spectrum Analyzer", "SPAN"].
                               Pass None to use heuristic auto-detection.
        min_band_count: Minimum number of frequency-named parameters a device must have
                        to qualify under heuristic detection (default 4).

    Returns:
        analyzer_count: number of analyzer devices found
        analyzers: list of {
            track_index, track_name, track_type ("normal"|"master"|"return"),
            device_index, device_name, class_name,
            band_count,
            bands: {band_name: {value, value_string, parameter_index, min, max}}
        }
    """
    # Gather all tracks: normal + master + returns
    all_tracks = []
    try:
        normal = _send("get_track_names", {"include_returns": False, "include_master": False})
        for t in normal:
            t["_track_type"] = "normal"
            all_tracks.append(t)
    except Exception:
        pass
    try:
        master_tracks = _send("get_track_names", {"include_returns": False, "include_master": True})
        for t in master_tracks:
            if t.get("is_master"):
                t["_track_type"] = "master"
                all_tracks.append(t)
    except Exception:
        pass
    try:
        return_tracks = _send("get_track_names", {"include_returns": True, "include_master": False})
        for t in return_tracks:
            if t.get("is_return"):
                t["_track_type"] = "return"
                all_tracks.append(t)
    except Exception:
        pass

    use_name_match = bool(device_name_patterns)
    patterns_lower = [p.lower() for p in (device_name_patterns or [])]

    results = []
    for track in all_tracks:
        track_index = track["index"]
        try:
            devices = _send("get_devices", {"track_index": track_index})
        except Exception:
            continue

        for device in devices:
            device_name_lower = device["name"].lower()

            # Name-based matching
            if use_name_match:
                if not any(p in device_name_lower for p in patterns_lower):
                    continue

            # Fetch parameters
            try:
                params_result = _send("get_device_parameters", {
                    "track_index": track_index,
                    "device_index": device["index"],
                })
            except Exception:
                continue

            parameters = params_result.get("parameters", [])

            # Heuristic: count parameters with frequency ranges in their names
            freq_params = [
                p for p in parameters
                if "hz" in p["name"].lower() or "Hz" in p["name"]
            ]

            if not use_name_match and len(freq_params) < min_band_count:
                continue  # Skip — not a spectrum analyzer

            # Build bands dict
            band_params = freq_params if not use_name_match else parameters
            bands: dict = {}
            for param in band_params:
                bands[param["name"]] = {
                    "value": param["value"],
                    "value_string": param.get("value_string", ""),
                    "parameter_index": param["index"],
                    "min": param.get("min", None),
                    "max": param.get("max", None),
                }

            results.append({
                "track_index": track_index,
                "track_name": track["name"],
                "track_type": track.get("_track_type", "normal"),
                "device_index": device["index"],
                "device_name": device["name"],
                "class_name": device.get("class_name", ""),
                "band_count": len(bands),
                "bands": bands,
            })

    return {
        "analyzer_count": len(results),
        "analyzers": results,
    }


@mcp.tool()
def get_spectrum_telemetry_instances(
    device_name_patterns: list | None = None,
) -> dict:
    """
    Scan all tracks for MCP Spectrum Telemetry (or compatible) analyzer devices
    and return their current band values with full track/device context.

    This is a convenience wrapper around find_spectrum_analyzers() that defaults
    to searching for devices matching common MCPSpectrum name patterns.

    The plugin exposes 8 bands with explicit frequency ranges in parameter names
    (e.g. "Punch (120–250 Hz)") — no additional mapping needed.

    Args:
        device_name_patterns: List of device name substrings to match.
                               Defaults to ["MCPSpectrum", "MCP Spectrum", "MCPSpectrumTelemetry"].
                               Pass an empty list [] to use heuristic auto-detection instead.

    Returns:
        instance_count: number of analyzer instances found
        instances: list of {
            track_index, track_name, track_type,
            device_index, device_name, class_name,
            band_count,
            bands: {band_name: {value, value_string, parameter_index, min, max}}
        }
    """
    if device_name_patterns is None:
        device_name_patterns = ["MCPSpectrum", "MCP Spectrum", "MCPSpectrumTelemetry"]

    result = find_spectrum_analyzers(
        device_name_patterns=device_name_patterns,
        min_band_count=4,
    )
    return {
        "instance_count": result["analyzer_count"],
        "instances": result["analyzers"],
    }


@mcp.tool()
def diagnose_spectrum_issue(
    target_band: str,
    reference_track_index: int = -1,
    device_name_patterns: list | None = None,
) -> dict:
    """
    Diagnose a spectrum issue by comparing a target frequency band across all
    discovered analyzer instances, ranking sources by level vs. the reference track.

    Call get_spectrum_telemetry_instances() or find_spectrum_analyzers() first to
    see available band names and which tracks have analyzers loaded.

    Example usage:
        diagnose_spectrum_issue("Punch (120–250 Hz)")
        diagnose_spectrum_issue("Body (250–500 Hz)", reference_track_index=-1)
        diagnose_spectrum_issue("Bass (60–120 Hz)", device_name_patterns=["SPAN"])

    Args:
        target_band: Exact band parameter name as exposed by the plugin,
                     e.g. "Punch (120–250 Hz)". Use get_spectrum_telemetry_instances()
                     to see available names.
        reference_track_index: Track index of the reference analyzer (default: -1 = master).
        device_name_patterns: Passed to get_spectrum_telemetry_instances(). Leave None
                               for default MCPSpectrum detection.

    Returns:
        target_band: the band queried
        reference_track_name: name of the reference track used
        master_value: band value on the reference track (None if not found)
        ranked_sources: list sorted descending by value: {
            track_index, track_name, track_type,
            device_index, device_name,
            band, value,
            delta_vs_master (positive = louder than reference in this band)
        }
        band_names_available: list of band names found on the reference instance
                               (useful if target_band is not found)
        warning: optional message if reference instance was not found
    """
    data = get_spectrum_telemetry_instances(device_name_patterns=device_name_patterns)
    instances = data["instances"]

    reference_inst = None
    sources = []

    for inst in instances:
        if inst["track_index"] == reference_track_index:
            reference_inst = inst
        else:
            sources.append(inst)

    warning = None
    master_value = None
    reference_track_name = None
    band_names_available: list = []

    if reference_inst is None:
        warning = (
            "No analyzer instance found on reference track (index {}). "
            "Place an MCPSpectrum analyzer on the master track (index -1) for full diagnosis. "
            "Ranking sources against each other without a master reference."
        ).format(reference_track_index)
        # Fall back: treat all instances as sources
        sources = instances
    else:
        reference_track_name = reference_inst["track_name"]
        band_names_available = list(reference_inst["bands"].keys())
        band_data = reference_inst["bands"].get(target_band)
        if band_data is not None:
            master_value = band_data["value"]
        else:
            warning = (
                "Band '{}' not found on reference track '{}'. "
                "Available bands: {}".format(
                    target_band,
                    reference_inst["track_name"],
                    list(reference_inst["bands"].keys()),
                )
            )

    ranked = []
    for inst in sources:
        band_data = inst["bands"].get(target_band)
        if band_data is None:
            continue
        value = band_data["value"]
        ranked.append({
            "track_index": inst["track_index"],
            "track_name": inst["track_name"],
            "track_type": inst.get("track_type", "normal"),
            "device_index": inst["device_index"],
            "device_name": inst["device_name"],
            "band": target_band,
            "value": value,
            "delta_vs_master": round(value - master_value, 4) if master_value is not None else None,
        })

    ranked.sort(key=lambda x: x["value"], reverse=True)

    result: dict = {
        "target_band": target_band,
        "reference_track_name": reference_track_name,
        "master_value": master_value,
        "ranked_sources": ranked,
        "band_names_available": band_names_available,
    }
    if warning:
        result["warning"] = warning
    return result


@mcp.tool()
def set_device_parameter_by_name(
    track_index: int,
    device_index: int,
    param_name: str,
    value: float,
    match_original_name: bool = True,
) -> dict:
    """
    Set a device parameter by name instead of index.

    This is the permanent agent-friendly write path. Instead of requiring the agent
    to enumerate parameters, find the index, and then write — this tool resolves
    the parameter by display name (or original_name) and writes in a single call.

    Matching is case-insensitive and uses substring matching as a fallback when
    exact match fails.

    Use track_index=-1 for the master track.

    Args:
        track_index: Track index (-1 for master).
        device_index: Device index on the track.
        param_name: Parameter display name to match, e.g. "Punch (120–250 Hz)",
                    "Filter Freq", "Attack". Case-insensitive.
        value: Value to set. Clamped to parameter min/max automatically.
        match_original_name: If True (default), also attempts to match against
                              the parameter's original_name field.

    Returns:
        parameter_index: the index that was written
        matched_name: exact parameter name that was matched
        value_set: the value passed to the setter
        track_index, device_index
    """
    params_result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    })
    parameters = params_result.get("parameters", [])

    param_name_lower = param_name.lower().strip()
    matched_param = None

    # 1. Exact match on display name
    for p in parameters:
        if p["name"].lower().strip() == param_name_lower:
            matched_param = p
            break

    # 2. Exact match on original_name
    if matched_param is None and match_original_name:
        for p in parameters:
            orig = p.get("original_name", "")
            if orig and orig.lower().strip() == param_name_lower:
                matched_param = p
                break

    # 3. Substring match on display name
    if matched_param is None:
        for p in parameters:
            if param_name_lower in p["name"].lower():
                matched_param = p
                break

    # 4. Substring match on original_name
    if matched_param is None and match_original_name:
        for p in parameters:
            orig = p.get("original_name", "")
            if orig and param_name_lower in orig.lower():
                matched_param = p
                break

    if matched_param is None:
        available = [p["name"] for p in parameters]
        raise ValueError(
            "Parameter '{}' not found on device at track={}, device={}. "
            "Available parameters: {}".format(param_name, track_index, device_index, available)
        )

    _send("set_device_parameter", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": matched_param["index"],
        "value": value,
    })

    return {
        "parameter_index": matched_param["index"],
        "matched_name": matched_param["name"],
        "value_set": value,
        "track_index": track_index,
        "device_index": device_index,
    }


@mcp.tool()
def set_spectrum_band_on_track(
    track_index: int,
    band_name: str,
    value: float,
    device_name_patterns: list | None = None,
) -> dict:
    """
    Set a spectrum analyzer band value on a specific track by band name.

    Finds the first matching analyzer device on the track and sets the named
    band parameter — no need to know device index or parameter index.

    Args:
        track_index: Track to target (-1 for master).
        band_name: Band parameter name, e.g. "Punch (120–250 Hz)".
                   Use get_spectrum_telemetry_instances() to list available names.
        value: Value to set (clamped to parameter range automatically).
        device_name_patterns: Optional device name filter. Defaults to MCPSpectrum patterns.

    Returns:
        track_index, device_index, device_name,
        band_name, parameter_index, value_set
    """
    if device_name_patterns is None:
        device_name_patterns = ["MCPSpectrum", "MCP Spectrum", "MCPSpectrumTelemetry"]

    try:
        devices = _send("get_devices", {"track_index": track_index})
    except Exception as e:
        raise RuntimeError("Could not get devices for track {}: {}".format(track_index, e))

    patterns_lower = [p.lower() for p in device_name_patterns]
    target_device = None
    for device in devices:
        if any(p in device["name"].lower() for p in patterns_lower):
            target_device = device
            break

    if target_device is None:
        device_names = [d["name"] for d in devices]
        raise ValueError(
            "No spectrum analyzer device found on track {} matching patterns {}. "
            "Devices on track: {}".format(track_index, device_name_patterns, device_names)
        )

    result = set_device_parameter_by_name(
        track_index=track_index,
        device_index=target_device["index"],
        param_name=band_name,
        value=value,
    )

    return {
        "track_index": track_index,
        "device_index": target_device["index"],
        "device_name": target_device["name"],
        "band_name": band_name,
        "parameter_index": result["parameter_index"],
        "value_set": value,
    }


# ---------------------------------------------------------------------------
# Arrangement automation helpers (module-level, not MCP tools)
# ---------------------------------------------------------------------------

def _bars_beats_to_song_time(bar: int, beat: float, time_signature_numerator: int = 4) -> float:
    """
    Convert a bar/beat position to absolute song time in beats.

    bar is 1-based (bar 1 = beat 0.0 of the song).
    beat is 1-based (beat 1 = start of bar, beat 2 = second beat, etc).
    beat can be fractional (e.g. beat 2.5 = halfway through beat 2).
    time_signature_numerator: beats per bar (4 for 4/4, 3 for 3/4, etc).

    Examples:
        _bars_beats_to_song_time(1, 1) -> 0.0
        _bars_beats_to_song_time(1, 2) -> 1.0
        _bars_beats_to_song_time(2, 1) -> 4.0
        _bars_beats_to_song_time(50, 3) -> 197.0  (in 4/4)
        _bars_beats_to_song_time(50, 3, numerator=3) -> 149.0  (in 3/4)
    """
    return float((bar - 1) * time_signature_numerator + (beat - 1))


def _find_device_parameter_by_name(
    track_index: int,
    device_index: int,
    param_name: str,
) -> tuple:
    """
    Find a device parameter by name (case-insensitive substring match).

    Returns:
        (parameter_index, parameter_info_dict)

    Raises:
        RuntimeError if not found, with a helpful message listing available params.
    """
    result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    }, _log=False)
    parameters = result.get("parameters", [])
    name_lower = param_name.lower().strip()

    # 1. Exact match on name
    for p in parameters:
        if p["name"].lower().strip() == name_lower:
            return p["index"], p

    # 2. Exact match on original_name
    for p in parameters:
        orig = p.get("original_name", "")
        if orig and orig.lower().strip() == name_lower:
            return p["index"], p

    # 3. Substring match on name
    for p in parameters:
        if name_lower in p["name"].lower():
            return p["index"], p

    # 4. Substring match on original_name
    for p in parameters:
        orig = p.get("original_name", "")
        if orig and name_lower in orig.lower():
            return p["index"], p

    available = [p["name"] for p in parameters]
    raise RuntimeError(
        "Parameter '{}' not found on device at track={}, device={}. "
        "Available parameters: {}".format(param_name, track_index, device_index, available)
    )


def _find_or_add_device(track_index: int, device_name: str) -> int:
    """
    Find or add a device on a track by name.

    1. Calls get_devices(track_index)
    2. Searches for a device whose name contains device_name (case-insensitive)
    3. If not found, calls add_native_device(track_index, device_name)
    4. Returns the device index.
    """
    devices = _send("get_devices", {"track_index": track_index}, _log=False)
    name_lower = device_name.lower()
    for d in devices:
        if name_lower in d["name"].lower():
            return d["index"]
    # Not found — add it
    _send("add_native_device", {"track_index": track_index, "device_name": device_name})
    # Re-fetch to get the new index
    devices = _send("get_devices", {"track_index": track_index}, _log=False)
    for d in devices:
        if name_lower in d["name"].lower():
            return d["index"]
    raise RuntimeError(
        "Device '{}' could not be added to track {}.".format(device_name, track_index)
    )


# ---------------------------------------------------------------------------
# Arrangement automation MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def bars_beats_to_song_time(
    bar: int,
    beat: float,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Convert a musical bar/beat position to absolute song time in beats.

    bar is 1-based (bar 1 = the very start of the song).
    beat is 1-based (beat 1 = start of bar, beat 2 = second beat, etc).
    beat can be fractional (e.g. beat 2.5 = halfway through beat 2).
    time_signature_numerator: beats per bar (4 for 4/4, 3 for 3/4, etc).

    Returns:
        song_time_beats (float): absolute song time as used by Live's API
        bar, beat, time_signature_numerator (echo of inputs)
    """
    song_time_beats = _bars_beats_to_song_time(bar, beat, time_signature_numerator)
    return {
        "song_time_beats": song_time_beats,
        "bar": bar,
        "beat": beat,
        "time_signature_numerator": time_signature_numerator,
    }


@mcp.tool()
def get_arrangement_automation_targets(track_index: int, device_index: int) -> dict:
    """
    Return all automatable parameters for a track/device, for use with write_arrangement_automation.

    Args:
        track_index: Track index (-1 for master).
        device_index: Device index.

    Returns:
        parameters: list of {parameter_index, name, value, min, max}
        device_name: name of the device
    """
    return _send("get_arrangement_automation_targets", {
        "track_index": track_index,
        "device_index": device_index,
    })


@mcp.tool()
def write_arrangement_automation(
    track_index: int,
    device_index: int,
    parameter_index: int,
    points: list,
    clear_range: bool = False,
) -> dict:
    """
    Write automation points to an arrangement lane for a device parameter.

    Each point dict: {"time": float_beats, "value": float}

    If clear_range=True, clears existing automation in the time range
    covered by the provided points before writing.

    Use get_device_parameters() to find parameter_index values.
    Use bars_beats_to_song_time() to convert bar/beat positions to beat times.

    Args:
        track_index: Track index (-1 for master).
        device_index: Device index on the track.
        parameter_index: Parameter index within the device.
        points: List of {time: float, value: float} dicts.
        clear_range: If True, clear existing automation in the covered range first.

    Returns:
        points_written, parameter_name, track_index, device_index, parameter_index
    """
    result = _send("write_arrangement_automation", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "points": points,
        "clear_range": clear_range,
    })
    result["parameter_index"] = parameter_index
    return result


# ---------------------------------------------------------------------------
# Mix levels overview and clipping watch
# ---------------------------------------------------------------------------

@mcp.tool()
def get_mix_levels_overview() -> dict:
    """
    Return current output levels for all tracks in a single call.

    Returns:
        tracks: list of {track_index, track_name, output_meter_left, output_meter_right,
                         peak_left, peak_right, is_clipping, muted, soloed}
        master: {output_meter_left, output_meter_right, peak_left, peak_right, is_clipping}
        clipping_tracks: list of {track_index, track_name}
        total_tracks: int
        any_clipping: bool
        timestamp: float
    """
    tracks_raw = _send("get_tracks", {})
    master_raw = _send("get_master_track", {})

    tracks = []
    clipping_tracks = []

    for t in tracks_raw:
        left = float(t.get("output_meter_left", 0.0))
        right = float(t.get("output_meter_right", 0.0))
        peak_l = float(t.get("peak_left", left))
        peak_r = float(t.get("peak_right", right))
        # Ableton meter values are 0.0–1.0; >=1.0 indicates clipping
        clipping = bool(t.get("is_clipping", False) or (peak_l >= 1.0 or peak_r >= 1.0))
        entry = {
            "track_index": t.get("index", t.get("track_index", 0)),
            "track_name": t.get("name", ""),
            "output_meter_left": left,
            "output_meter_right": right,
            "peak_left": peak_l,
            "peak_right": peak_r,
            "is_clipping": clipping,
            "muted": bool(t.get("mute", False)),
            "soloed": bool(t.get("solo", False)),
        }
        tracks.append(entry)
        if clipping:
            clipping_tracks.append({
                "track_index": entry["track_index"],
                "track_name": entry["track_name"],
            })

    m_left = float(master_raw.get("output_meter_left", 0.0))
    m_right = float(master_raw.get("output_meter_right", 0.0))
    m_peak_l = float(master_raw.get("peak_left", m_left))
    m_peak_r = float(master_raw.get("peak_right", m_right))
    m_clipping = bool(master_raw.get("is_clipping", False) or (m_peak_l >= 1.0 or m_peak_r >= 1.0))

    master = {
        "output_meter_left": m_left,
        "output_meter_right": m_right,
        "peak_left": m_peak_l,
        "peak_right": m_peak_r,
        "is_clipping": m_clipping,
    }

    return {
        "tracks": tracks,
        "master": master,
        "clipping_tracks": clipping_tracks,
        "total_tracks": len(tracks),
        "any_clipping": bool(clipping_tracks) or m_clipping,
        "timestamp": time.time(),
    }


@mcp.tool()
def watch_for_clipping(duration_seconds: float = 5.0, poll_interval: float = 0.5) -> dict:
    """
    Monitor all tracks for clipping over a specified duration.

    Polls meter levels at poll_interval and records any tracks that clip.

    Args:
        duration_seconds: How long to monitor (default 5s, max 30s)
        poll_interval: How often to sample in seconds (default 0.5s, min 0.1s)

    Returns:
        clipped_tracks: list of {track_index, track_name, clip_count, first_clip_at, last_clip_at}
        total_samples: int
        duration_monitored: float
        any_clipping: bool
        recommendation: str
    """
    duration_seconds = min(float(duration_seconds), 30.0)
    poll_interval = max(float(poll_interval), 0.1)

    # {track_index: {track_name, clip_count, first_clip_at, last_clip_at}}
    clip_data: dict = {}
    total_samples = 0
    start_time = time.time()
    deadline = start_time + duration_seconds

    while time.time() < deadline:
        try:
            snapshot = get_mix_levels_overview()
        except Exception:
            time.sleep(poll_interval)
            continue

        total_samples += 1
        now = time.time()

        # Check master
        if snapshot["master"]["is_clipping"]:
            key = "master"
            if key not in clip_data:
                clip_data[key] = {
                    "track_index": -1,
                    "track_name": "Master",
                    "clip_count": 0,
                    "first_clip_at": now - start_time,
                    "last_clip_at": now - start_time,
                }
            clip_data[key]["clip_count"] += 1
            clip_data[key]["last_clip_at"] = now - start_time

        for t in snapshot["tracks"]:
            if t["is_clipping"]:
                key = t["track_index"]
                if key not in clip_data:
                    clip_data[key] = {
                        "track_index": t["track_index"],
                        "track_name": t["track_name"],
                        "clip_count": 0,
                        "first_clip_at": now - start_time,
                        "last_clip_at": now - start_time,
                    }
                clip_data[key]["clip_count"] += 1
                clip_data[key]["last_clip_at"] = now - start_time

        remaining = deadline - time.time()
        time.sleep(min(poll_interval, max(0.0, remaining)))

    duration_monitored = time.time() - start_time
    clipped_tracks = list(clip_data.values())

    if clipped_tracks:
        names = ", ".join(e["track_name"] for e in clipped_tracks[:5])
        recommendation = (
            "Clipping detected on {} track(s) ({}). "
            "Reduce gain or add a limiter on the affected tracks.".format(
                len(clipped_tracks), names
            )
        )
    else:
        recommendation = "No clipping detected over {:.1f}s — levels look safe.".format(
            duration_monitored
        )

    return {
        "clipped_tracks": clipped_tracks,
        "total_samples": total_samples,
        "duration_monitored": round(duration_monitored, 2),
        "any_clipping": bool(clipped_tracks),
        "recommendation": recommendation,
    }


