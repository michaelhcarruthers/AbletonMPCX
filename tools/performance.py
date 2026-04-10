"""Performance tools — performance FX (reverb throw, filter sweep, stutter), DJ blend/transition macros, and the macro execution engine."""
from __future__ import annotations

import logging

import helpers
from helpers import mcp, _send

logger = logging.getLogger(__name__)


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


def _find_or_add_device(track_index: int, device_name: str) -> int:
    """Find a device by name on a track, or add it if not present. Returns device index."""
    try:
        devices = _send("get_devices", {"track_index": track_index, "is_return_track": False}, _log=False)
    except Exception:
        devices = []
    name_lower = device_name.lower()
    for d in devices:
        if name_lower in d.get("name", "").lower():
            return d["index"]
    # Not found — add it
    result = _send("add_native_device", {
        "track_index": track_index,
        "device_name": device_name,
        "is_return_track": False,
    })
    # Re-fetch to get the new index
    devices = _send("get_devices", {"track_index": track_index, "is_return_track": False}, _log=False)
    for d in devices:
        if name_lower in d.get("name", "").lower():
            return d["index"]
    raise RuntimeError(f"Could not find or add device '{device_name}' on track {track_index}")


def _find_device_parameter_by_name(
    track_index: int, device_index: int, param_name: str
) -> tuple[int, dict]:
    """Find a device parameter by name. Returns (parameter_index, parameter_info)."""
    result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
        "is_return_track": False,
    })
    params = result.get("parameters", []) if isinstance(result, dict) else result if isinstance(result, list) else []
    name_lower = param_name.lower()
    for p in params:
        if name_lower in p.get("name", "").lower():
            return p["index"], p
    raise RuntimeError(
        f"Parameter '{param_name}' not found on device {device_index} of track {track_index}"
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
    time_signature_numerator: int | None = None,
) -> dict:
    """Add a reverb throw automation: Dry/Wet ramps from 0 → peak_wet → 0 over length_beats."""
    tsn = _get_time_sig_numerator(time_signature_numerator)
    _send("begin_undo_step", {"name": "reverb_throw"})
    try:
        if device_index is None:
            device_index = _find_or_add_device(track_index, "Reverb")

        devices = _send("get_devices", {"track_index": track_index, "is_return_track": False}, _log=False)
        device_name = next(
            (d["name"] for d in devices if d["index"] == device_index),
            "Reverb",
        )

        param_idx, param_info = _find_device_parameter_by_name(
            track_index, device_index, "Dry/Wet"
        )

        start_time = _bars_beats_to_song_time(start_bar, start_beat, tsn)
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
    time_signature_numerator: int | None = None,
) -> dict:
    """Add a filter sweep: automates Auto Filter cutoff frequency from start_freq to end_freq."""
    tsn = _get_time_sig_numerator(time_signature_numerator)
    _send("begin_undo_step", {"name": "filter_sweep"})
    try:
        if device_index is None:
            device_index = _find_or_add_device(track_index, "Auto Filter")

        param_idx, param_info = _find_device_parameter_by_name(
            track_index, device_index, "Frequency"
        )

        start_time = _bars_beats_to_song_time(start_bar, start_beat, tsn)
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
    time_signature_numerator: int | None = None,
) -> dict:
    """Add a delay echo-out: ramps Feedback up then cuts Dry/Wet to 0 at the end."""
    tsn = _get_time_sig_numerator(time_signature_numerator)
    _send("begin_undo_step", {"name": "delay_echo_out"})
    try:
        if device_index is None:
            # Try to find an existing delay or echo device
            devices = _send("get_devices", {"track_index": track_index, "is_return_track": False}, _log=False)
            device_index = None
            for d in devices:
                name_lower = d["name"].lower()
                if "delay" in name_lower or "echo" in name_lower:
                    device_index = d["index"]
                    break
            if device_index is None:
                device_index = _find_or_add_device(track_index, "Delay")

        devices = _send("get_devices", {"track_index": track_index, "is_return_track": False}, _log=False)
        device_name = next(
            (d["name"] for d in devices if d["index"] == device_index),
            "Delay",
        )

        start_time = _bars_beats_to_song_time(start_bar, start_beat, tsn)
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
    time_signature_numerator: int | None = None,
) -> dict:
    """Create a volume stutter effect by automating track volume on/off at chop_size_beats intervals."""
    tsn = _get_time_sig_numerator(time_signature_numerator)
    _send("begin_undo_step", {"name": "stutter_clip"})
    try:
        start_time = _bars_beats_to_song_time(start_bar, start_beat, tsn)
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
            "parameter_type": "volume",
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
    time_signature_numerator: int | None = None,
    **kwargs,
) -> dict:
    """Add a performance effect to a track at a musical position."""
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
# Rack macro helpers
# ---------------------------------------------------------------------------

def _find_rack_on_track(track_index: int) -> tuple[int, dict] | None:
    """Find the first Audio Effect Rack or Instrument Rack on a track.
    Returns (device_index, device_info) or None if not found.
    """
    try:
        devices = _send("get_devices", {"track_index": track_index, "is_return_track": False})
    except Exception:
        return None
    for d in devices:
        # class_name for racks: "AudioEffectGroupDevice", "InstrumentGroupDevice", "MidiEffectGroupDevice"
        class_name = d.get("class_name", "")
        name = d.get("name", "").lower()
        if "group" in class_name.lower() or "rack" in name:
            return d.get("index", d.get("device_index", 0)), d
    return None


def _get_rack_macros(track_index: int, device_index: int) -> list[dict]:
    """Return the macro knob parameters from a rack device.
    Macro knobs are the first 8 parameters (indices 0–7) of a rack.
    Returns list of {index, name, value, min, max}.
    """
    try:
        result = _send("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index,
            "is_return_track": False,
        })
    except Exception as e:
        raise RuntimeError("Could not read rack parameters on track {}: {}".format(track_index, e))
    params = result.get("parameters", []) if isinstance(result, dict) else []
    # Rack macro knobs are the first 8 parameters
    return params[:8]


@mcp.tool()
def get_rack_macros(track_index: int, device_index: int | None = None) -> dict:
    """Read the macro knob names and current values from a rack on a track.

    If device_index is not provided, the first rack found on the track is used.
    Returns the 8 macro knob names, values, and ranges so Claude can see what
    is mapped before performing a macro move.
    """
    if device_index is None:
        found = _find_rack_on_track(track_index)
        if found is None:
            return {
                "error": "No rack found on track {}. Add an Audio Effect Rack or Instrument Rack first.".format(track_index),
                "track_index": track_index,
            }
        device_index, device_info = found
    else:
        try:
            devices = _send("get_devices", {"track_index": track_index, "is_return_track": False})
            device_info = next((d for d in devices if d.get("index", d.get("device_index")) == device_index), {})
        except Exception as e:
            return {"error": str(e), "track_index": track_index}

    macros = _get_rack_macros(track_index, device_index)
    return {
        "track_index": track_index,
        "device_index": device_index,
        "rack_name": device_info.get("name", "Rack"),
        "macros": [
            {
                "index": m["index"],
                "name": m.get("name", "Macro {}".format(i + 1)),
                "value": m.get("value", 0.0),
                "min": m.get("min", 0.0),
                "max": m.get("max", 1.0),
            }
            for i, m in enumerate(macros)
        ],
        "macro_count": len(macros),
    }


@mcp.tool()
def perform_macro(
    track_index: int,
    knob_targets: dict,
    duration_ms: float = 2000.0,
    curve: str = "ease_in_out",
    device_index: int | None = None,
) -> dict:
    """Animate rack macro knobs to target values using gesture-wrapped parameter moves.

    knob_targets: dict mapping knob name substring (case-insensitive) OR "Macro N" to a
                  target value (0.0–1.0 normalised). Example:
                  {"Filter": 0.8, "Drive": 0.6, "Space": 0.3}
                  or {"Macro 1": 0.8, "Macro 2": 0.6}

    If device_index is not provided, the first rack on the track is used.

    Reads the rack's macro knob names at call time — no hard-coded definitions.
    Works with any devices inside the rack (native, VST, AU).
    """
    valid_curves = {"linear", "ease_in", "ease_out", "ease_in_out"}
    if curve not in valid_curves:
        raise ValueError("Invalid curve '{}'. Valid options: {}".format(curve, sorted(valid_curves)))

    if device_index is None:
        found = _find_rack_on_track(track_index)
        if found is None:
            raise RuntimeError(
                "No rack found on track {}. Add an Audio Effect Rack first, "
                "then map your device parameters to macro knobs.".format(track_index)
            )
        device_index, _ = found

    macros = _get_rack_macros(track_index, device_index)

    moves = []
    matched = []
    skipped = []

    for knob_target_name, target_value in knob_targets.items():
        search = knob_target_name.strip().lower()
        matched_macro = None
        for m in macros:
            macro_name = m.get("name", "").lower()
            if search in macro_name or macro_name in search:
                matched_macro = m
                break

        if matched_macro is None:
            skipped.append({
                "knob": knob_target_name,
                "reason": "No macro knob matching '{}' found. Available: {}".format(
                    knob_target_name, [m.get("name") for m in macros]
                ),
            })
            continue

        target = max(0.0, min(1.0, float(target_value)))
        moves.append({
            "parameter_index": matched_macro["index"],
            "target": target,
            "duration_ms": duration_ms,
            "curve": curve,
        })
        matched.append({
            "knob": knob_target_name,
            "macro_name": matched_macro.get("name"),
            "macro_index": matched_macro["index"],
            "target": target,
        })

    if not moves:
        raise RuntimeError(
            "perform_macro: no macro knobs matched on track {}. "
            "Call get_rack_macros({}) first to see available knob names.".format(track_index, track_index)
        )

    result = _send("perform_device_parameter_moves", {
        "track_index": track_index,
        "device_index": device_index,
        "moves": moves,
        "is_return_track": False,
    })

    return {
        "status": "ok",
        "track_index": track_index,
        "device_index": device_index,
        "duration_ms": duration_ms,
        "curve": curve,
        "moves_scheduled": result.get("moves_scheduled", len(moves)),
        "matched": matched,
        "skipped": skipped,
    }


@mcp.tool()
def perform_macro_live(
    track_index: int,
    knob_targets: dict,
    duration_ms: float = 2000.0,
    curve: str = "ease_in_out",
    device_index: int | None = None,
) -> dict:
    """Alias for perform_macro — animate rack macro knobs in real time.

    knob_targets: dict mapping knob name substring to target value (0.0–1.0).
    Reads rack macro knob names at call time.
    """
    return perform_macro(
        track_index=track_index,
        knob_targets=knob_targets,
        duration_ms=duration_ms,
        curve=curve,
        device_index=device_index,
    )


@mcp.tool()
def perform_macro_to_arrangement(
    track_index: int,
    knob_targets: dict,
    start_bar: int,
    start_beat: float,
    length_beats: float,
    time_signature_numerator: int | None = None,
    device_index: int | None = None,
) -> dict:
    """Write rack macro knob moves as arrangement automation curves.

    knob_targets: dict mapping knob name substring to a tuple (start_value, end_value)
                  or a single float end_value (start = current value).
                  Example: {"Filter": (0.1, 0.9), "Drive": (0.0, 0.7)}

    Reads rack macro knob names at call time.
    Requires an arrangement clip to exist on the track covering the target time range
    and Live's automation arm to be enabled.
    """
    tsn = _get_time_sig_numerator(time_signature_numerator)
    start_time = _bars_beats_to_song_time(start_bar, start_beat, tsn)
    end_time = start_time + length_beats

    if device_index is None:
        found = _find_rack_on_track(track_index)
        if found is None:
            raise RuntimeError(
                "No rack found on track {}. Add an Audio Effect Rack first.".format(track_index)
            )
        device_index, _ = found

    macros = _get_rack_macros(track_index, device_index)

    applied = []
    skipped = []

    _send("begin_undo_step", {"name": "perform_macro_to_arrangement"})
    try:
        for knob_target_name, target_spec in knob_targets.items():
            search = knob_target_name.strip().lower()
            matched_macro = None
            for m in macros:
                macro_name = m.get("name", "").lower()
                if search in macro_name or macro_name in search:
                    matched_macro = m
                    break

            if matched_macro is None:
                skipped.append({
                    "knob": knob_target_name,
                    "reason": "No macro knob matching '{}' found. Available: {}".format(
                        knob_target_name, [m.get("name") for m in macros]
                    ),
                })
                continue

            # Resolve start/end values
            if isinstance(target_spec, (list, tuple)) and len(target_spec) == 2:
                start_val, end_val = float(target_spec[0]), float(target_spec[1])
            else:
                start_val = float(matched_macro.get("value", 0.0))
                end_val = float(target_spec)

            start_val = max(0.0, min(1.0, start_val))
            end_val = max(0.0, min(1.0, end_val))

            points = [
                {"time": start_time, "value": start_val},
                {"time": end_time, "value": end_val},
            ]

            try:
                write_result = _send("write_arrangement_automation", {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_index": matched_macro["index"],
                    "points": points,
                    "clear_range": True,
                })
                applied.append({
                    "knob": knob_target_name,
                    "macro_name": matched_macro.get("name"),
                    "start_value": start_val,
                    "end_value": end_val,
                    "points_written": write_result.get("points_written", len(points)),
                })
            except Exception as e:
                skipped.append({
                    "knob": knob_target_name,
                    "reason": "Automation write failed: {}. "
                              "Ensure an arrangement clip exists on track {} covering beats {:.1f}–{:.1f} "
                              "and that Live's automation arm is enabled.".format(
                                  str(e), track_index, start_time, end_time),
                })
    finally:
        _send("end_undo_step", {})

    return {
        "track_index": track_index,
        "device_index": device_index,
        "start_time_beats": start_time,
        "end_time_beats": end_time,
        "applied": applied,
        "skipped": skipped,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
    }


@mcp.tool()
def set_macro_intensity(
    track_index: int,
    knob_targets: dict,
    device_index: int | None = None,
) -> dict:
    """Set rack macro knob values instantly — no animation, no automation written.

    knob_targets: dict mapping knob name substring to a target value (0.0–1.0).
    Reads rack macro knob names at call time.
    """
    if device_index is None:
        found = _find_rack_on_track(track_index)
        if found is None:
            raise RuntimeError("No rack found on track {}.".format(track_index))
        device_index, _ = found

    macros = _get_rack_macros(track_index, device_index)

    applied = []
    skipped = []

    for knob_target_name, target_value in knob_targets.items():
        search = knob_target_name.strip().lower()
        matched_macro = None
        for m in macros:
            macro_name = m.get("name", "").lower()
            if search in macro_name or macro_name in search:
                matched_macro = m
                break

        if matched_macro is None:
            skipped.append({"knob": knob_target_name, "reason": "No matching macro knob found"})
            continue

        value = max(0.0, min(1.0, float(target_value)))
        try:
            _send("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": matched_macro["index"],
                "value": value,
                "is_return_track": False,
            })
            applied.append({
                "knob": knob_target_name,
                "macro_name": matched_macro.get("name"),
                "value_set": round(value, 4),
            })
        except Exception as e:
            skipped.append({"knob": knob_target_name, "reason": "Set failed: {}".format(str(e))})

    return {
        "track_index": track_index,
        "device_index": device_index,
        "applied": applied,
        "skipped": skipped,
    }


@mcp.tool()
def setup_performance_rack(
    track_index: int,
    macro_names: list[str] | None = None,
    track_name: str | None = None,
) -> dict:
    """Add an Audio Effect Rack to a track and optionally name its macro knobs.

    macro_names: list of up to 8 strings to assign to Macro 1–8.
                 Example: ["Filter", "Resonance", "Drive", "Space", "Width", "Crush", "Macro 7", "Macro 8"]
                 If fewer than 8 are provided, remaining knobs keep their default names.

    After this, add devices inside the rack and map parameters to the named macro knobs
    using Ableton's macro mapping UI. Then call perform_macro() to animate those knobs.
    """
    _send("begin_undo_step", {"name": "setup_performance_rack"})
    try:
        _send("add_native_device", {
            "track_index": track_index,
            "device_name": "Audio Effect Rack",
            "is_return_track": False,
        })
    except Exception as e:
        _send("end_undo_step", {})
        raise RuntimeError("Could not add Audio Effect Rack: {}".format(e))

    # Find the rack we just added
    try:
        devices = _send("get_devices", {"track_index": track_index, "is_return_track": False})
    except Exception as e:
        _send("end_undo_step", {})
        raise RuntimeError("Could not read devices after adding rack: {}".format(e))

    rack_index = None
    for d in reversed(devices):  # most recently added is last
        class_name = d.get("class_name", "")
        name = d.get("name", "").lower()
        if "group" in class_name.lower() or "rack" in name:
            rack_index = d.get("index", d.get("device_index", 0))
            break

    if rack_index is None:
        _send("end_undo_step", {})
        raise RuntimeError("Rack was added but could not be found on track {}.".format(track_index))

    # Rename macro knobs if requested
    macros_named = []
    if macro_names:
        macros = _get_rack_macros(track_index, rack_index)
        for i, name in enumerate(macro_names[:8]):
            if i < len(macros):
                try:
                    _send("set_device_parameter_name", {
                        "track_index": track_index,
                        "device_index": rack_index,
                        "parameter_index": macros[i]["index"],
                        "name": name,
                    })
                    macros_named.append({"index": i + 1, "name": name})
                except Exception:
                    # Naming macros may not be supported via API — note but don't fail
                    macros_named.append({"index": i + 1, "name": name, "note": "API rename not supported — rename manually in Live"})

    if track_name:
        try:
            _send("set_track_name", {"track_index": track_index, "name": track_name})
        except Exception as e:
            logger.debug("Could not set track name: %s", e)

    _send("end_undo_step", {})

    return {
        "track_index": track_index,
        "rack_device_index": rack_index,
        "macros_named": macros_named,
        "track_name": track_name,
        "next_steps": (
            "Rack added. Now: (1) open the rack in Live, (2) add devices inside it, "
            "(3) map device parameters to the named macro knobs using Ableton's macro mapping (CMD+M), "
            "(4) call get_rack_macros({}) to verify, then use perform_macro() to animate them.".format(track_index)
        ),
    }

