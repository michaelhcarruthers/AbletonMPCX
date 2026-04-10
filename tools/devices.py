"""Device tools — instruments, audio effects, MIDI effects, MixerDevice, RackDevice, GroovePool, and Browser."""
from __future__ import annotations

import helpers
from helpers import mcp, _send
from helpers.vocabulary import resolve_intensity, resolve_device_name, DEVICE_ALIASES

# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

def get_scenes() -> list:
    """Return all scenes with name, tempo, color, and state."""
    return _send("get_scenes")

def get_scene_info(scene_index: int) -> dict:
    """Return full details for the scene at scene_index."""
    return _send("get_scene_info", {"scene_index": scene_index})

def set_scene_name(scene_index: int, name: str) -> dict:
    """Rename the scene at scene_index."""
    return _send("set_scene_name", {"scene_index": scene_index, "name": name})

def set_scene_tempo(scene_index: int, tempo: float) -> dict:
    """Set the scene tempo at scene_index."""
    return _send("set_scene_tempo", {"scene_index": scene_index, "tempo": tempo})

def set_scene_color(scene_index: int, color: int) -> dict:
    """Set the scene color as an RGB integer (0x00rrggbb)."""
    return _send("set_scene_color", {"scene_index": scene_index, "color": color})

def fire_scene(scene_index: int) -> dict:
    """Launch the scene at scene_index."""
    return _send("fire_scene", {"scene_index": scene_index})

# ---------------------------------------------------------------------------
# MixerDevice
# ---------------------------------------------------------------------------

def get_mixer_device(track_index: int) -> dict:
    """Return the mixer device state (volume, pan, sends) for the track. Use track_index=-1 to target the master track."""
    return _send("get_mixer_device", {"track_index": track_index})

def set_crossfade_assign(track_index: int, value: int) -> dict:
    """Set crossfade assignment: 0=A, 1=none, 2=B."""
    return _send("set_crossfade_assign", {"track_index": track_index, "value": value})

# ---------------------------------------------------------------------------
# RackDevice
# ---------------------------------------------------------------------------

def get_rack_chains(track_index: int, device_index: int, is_return_track: bool = False) -> list:
    """Return the chains of a Rack device at (track_index, device_index). Set is_return_track=True to target a return track."""
    return _send("get_rack_chains", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

def get_rack_drum_pads(track_index: int, device_index: int, is_return_track: bool = False) -> list:
    """Return the drum pads of a Drum Rack device (use is_return_track=True for return tracks)."""
    return _send("get_rack_drum_pads", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

def randomize_rack_macros(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Randomize the macro controls of a Rack device. Set is_return_track=True to target a return track."""
    return _send("randomize_rack_macros", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

def store_rack_variation(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Store the current macro state as a new variation in a Rack device. Set is_return_track=True to target a return track."""
    return _send("store_rack_variation", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

# ---------------------------------------------------------------------------
# GroovePool
# ---------------------------------------------------------------------------

def get_grooves() -> list:
    """Return all grooves in the groove pool."""
    return _send("get_grooves")

def extract_groove_from_clip(
    track_index: int,
    slot_index: int,
    groove_name: str = "Extracted Groove",
) -> dict:
    """Extract the timing and velocity feel from a MIDI clip and add it to the groove pool."""
    return _send("extract_groove_from_clip", {
        "track_index": track_index,
        "slot_index": slot_index,
        "groove_name": groove_name,
    })

# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

def get_browser_tree(category_type: str = "all") -> dict:
    """Return the Ableton browser tree up to 2 levels deep for the given category type."""
    return _send("get_browser_tree", {"category_type": category_type})

def get_browser_items_at_path(path: str) -> dict:
    """Return browser items at the given path (e.g. 'instruments/Drum Rack')."""
    return _send("get_browser_items_at_path", {"path": path})

def load_browser_item(uri: str, track_index: int = 0, is_return_track: bool = False) -> dict:
    """Load a browser item by URI onto a track; use get_browser_items_at_path to discover valid URIs."""
    return _send("load_browser_item", {"uri": uri, "track_index": track_index, "is_return_track": is_return_track})

def load_plugin_device(
    track_index: int,
    plugin_name: str,
    plugin_format: str = "au",
) -> dict:
    """Load a third-party AU or VST plugin onto a track by name."""
    return _send("load_plugin_device", {
        "track_index": track_index,
        "plugin_name": plugin_name,
        "plugin_format": plugin_format,
    })


def add_native_device(track_index: int, device_name: str, is_return_track: bool = False) -> dict:
    """Add a native Ableton device to a track by name."""
    return _send("add_native_device", {
        "track_index": track_index,
        "device_name": device_name,
        "is_return_track": is_return_track,
    })

def set_mixer_snapshot(states: list[dict]) -> dict:
    """Set volume, pan, sends, mute, and/or arm on multiple tracks in a single call."""
    return _send("set_mixer_snapshot", {"states": states})

def set_return_track_volume(index: int, value: float) -> dict:
    """Set the volume of the return track at index (0.0-1.0)."""
    return _send("set_return_track_volume", {"index": index, "value": value})

def set_return_track_pan(index: int, value: float) -> dict:
    """Set the panning of the return track at index (-1.0 to 1.0)."""
    return _send("set_return_track_pan", {"index": index, "value": value})

def set_return_track_name(index: int, name: str) -> dict:
    """Rename the return track at index."""
    return _send("set_return_track_name", {"index": index, "name": name})

def set_return_track_mute(index: int, mute: bool) -> dict:
    """Mute or unmute the return track at index."""
    return _send("set_return_track_mute", {"index": index, "mute": mute})

def begin_undo_step(name: str = "MCP Operation") -> dict:
    """Begin a named undo step. All changes made until end_undo_step() will be grouped into a single Cmd+Z undo action in Live."""
    return _send("begin_undo_step", {"name": name})

def end_undo_step() -> dict:
    """Close the current undo step opened by begin_undo_step()."""
    return _send("end_undo_step", {})


# ---------------------------------------------------------------------------
# Relative parameter adjustment
# ---------------------------------------------------------------------------

_DIRECTION_ALIASES: dict[str, int] = {
    "up": 1,
    "increase": 1,
    "more": 1,
    "boost": 1,
    "raise": 1,
    "down": -1,
    "decrease": -1,
    "less": -1,
    "reduce": -1,
    "lower": -1,
}


def adjust_device_parameter(
    track_index: int,
    device_index: int,
    parameter_name: str,
    direction: str,
    amount: str = "a little",
) -> dict:
    """Adjust a device parameter using natural language magnitude descriptions."""
    direction_lower = direction.strip().lower()
    direction_sign = _DIRECTION_ALIASES.get(direction_lower)
    if direction_sign is None:
        raise ValueError(
            "Unknown direction '{}'. Use one of: {}".format(
                direction, ", ".join(_DIRECTION_ALIASES)
            )
        )

    delta = resolve_intensity(amount)

    # Retrieve all parameters for this device and find the matching one
    params_result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    })
    parameters = params_result if isinstance(params_result, list) else params_result.get("parameters", [])

    search = parameter_name.strip().lower()
    match = None
    for p in parameters:
        if search in p.get("name", "").lower():
            match = p
            break

    if match is None:
        raise ValueError(
            "No parameter matching '{}' found on device {} of track {}.".format(
                parameter_name, device_index, track_index
            )
        )

    resolved_name = match.get("name", parameter_name)
    param_index = match.get("index", match.get("parameter_index", 0))
    previous_value = float(match.get("value", 0.0))

    raw_new = previous_value + direction_sign * delta
    new_value = max(0.0, min(1.0, raw_new))
    clamped = new_value != raw_new

    _send("set_device_parameter", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": param_index,
        "value": new_value,
    })

    return {
        "parameter_name": resolved_name,
        "previous_value": previous_value,
        "new_value": new_value,
        "delta_applied": direction_sign * delta,
        "amount_resolved": amount,
        "direction": direction,
        "clamped": clamped,
    }


# ---------------------------------------------------------------------------
# N — Device/parameter alias registry
# ---------------------------------------------------------------------------

def find_device_by_name(track_index: int, device_name: str) -> dict:
    """Find a device on a track by name, supporting natural language aliases."""
    resolved = resolve_device_name(device_name)
    alias_used: str | None = device_name if resolved != device_name else None

    tracks = _send("get_tracks")
    if not isinstance(tracks, list) or track_index >= len(tracks):
        return {
            "found": False,
            "device_index": None,
            "device_name": resolved,
            "alias_used": alias_used,
            "parameters": [],
        }

    devices = tracks[track_index].get("devices", [])
    for i, d in enumerate(devices):
        dname = d.get("name", "")
        if dname.lower() == resolved.lower() or resolved.lower() in dname.lower():
            params = d.get("parameters", [])
            return {
                "found": True,
                "device_index": i,
                "device_name": dname,
                "alias_used": alias_used,
                "parameters": [
                    {
                        "name": p.get("name"),
                        "value": p.get("value"),
                        "min": p.get("min"),
                        "max": p.get("max"),
                    }
                    for p in params
                ],
            }

    return {
        "found": False,
        "device_index": None,
        "device_name": resolved,
        "alias_used": alias_used,
        "parameters": [],
    }


def set_device_parameters_batch(
    track_index: int,
    device_index: int,
    updates: list,
    is_return_track: bool = False,
    visual_refresh: bool = True,
    skip_unchanged: bool = True,
    clamp_values: bool = True,
) -> dict:
    """Set multiple device parameters in a single round trip."""
    return _send("set_device_parameters_batch", {
        "track_index": track_index,
        "device_index": device_index,
        "updates": updates,
        "is_return_track": is_return_track,
        "visual_refresh": visual_refresh,
        "skip_unchanged": skip_unchanged,
        "clamp_values": clamp_values,
    })


def perform_device_parameter_moves(
    track_index: int,
    device_index: int,
    moves: list,
    is_return_track: bool = False,
    visual_refresh: bool = True,
    step_ms: int = 30,
) -> dict:
    """Animate one or more device parameters to target values over time."""
    return _send("perform_device_parameter_moves", {
        "track_index": track_index,
        "device_index": device_index,
        "moves": moves,
        "is_return_track": is_return_track,
        "visual_refresh": visual_refresh,
        "step_ms": step_ms,
    })


def randomize_device_parameters(
    track_index: int,
    device_index: int,
    parameter_indices: list[int] | None = None,
    min_value: float = 0.0,
    max_value: float = 1.0,
    seed: int | None = None,
    is_return_track: bool = False,
) -> dict:
    """Randomize device parameters within a specified range."""
    return _send("randomize_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_indices": parameter_indices,
        "min_value": min_value,
        "max_value": max_value,
        "seed": seed,
        "is_return_track": is_return_track,
    })


