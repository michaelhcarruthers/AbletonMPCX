"""Device tools — instruments, audio effects, MIDI effects, MixerDevice, RackDevice, GroovePool, and Browser."""
from __future__ import annotations

import helpers
from helpers import mcp, _send
from helpers.vocabulary import resolve_intensity, resolve_device_name, DEVICE_ALIASES

# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

@mcp.tool()
def get_scenes() -> list:
    """Return all scenes with name, tempo, color, and state."""
    return _send("get_scenes")

@mcp.tool()
def get_scene_info(scene_index: int) -> dict:
    """Return full details for the scene at scene_index."""
    return _send("get_scene_info", {"scene_index": scene_index})

@mcp.tool()
def set_scene_name(scene_index: int, name: str) -> dict:
    """Rename the scene at scene_index."""
    return _send("set_scene_name", {"scene_index": scene_index, "name": name})

@mcp.tool()
def set_scene_tempo(scene_index: int, tempo: float) -> dict:
    """Set the scene tempo at scene_index."""
    return _send("set_scene_tempo", {"scene_index": scene_index, "tempo": tempo})

@mcp.tool()
def set_scene_color(scene_index: int, color: int) -> dict:
    """Set the scene color as an RGB integer (0x00rrggbb)."""
    return _send("set_scene_color", {"scene_index": scene_index, "color": color})

@mcp.tool()
def fire_scene(scene_index: int) -> dict:
    """Launch the scene at scene_index."""
    return _send("fire_scene", {"scene_index": scene_index})

# ---------------------------------------------------------------------------
# MixerDevice
# ---------------------------------------------------------------------------

@mcp.tool()
def get_mixer_device(track_index: int) -> dict:
    """Return the mixer device state (volume, pan, sends) for the track. Use track_index=-1 to target the master track."""
    return _send("get_mixer_device", {"track_index": track_index})

@mcp.tool()
def set_crossfade_assign(track_index: int, value: int) -> dict:
    """Set crossfade assignment: 0=A, 1=none, 2=B."""
    return _send("set_crossfade_assign", {"track_index": track_index, "value": value})

# ---------------------------------------------------------------------------
# RackDevice
# ---------------------------------------------------------------------------

@mcp.tool()
def get_rack_chains(track_index: int, device_index: int, is_return_track: bool = False) -> list:
    """Return the chains of a Rack device at (track_index, device_index). Set is_return_track=True to target a return track."""
    return _send("get_rack_chains", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def get_rack_drum_pads(track_index: int, device_index: int, is_return_track: bool = False) -> list:
    """Return the drum pads of a Drum Rack device at (track_index, device_index). Set is_return_track=True to target a return track."""
    return _send("get_rack_drum_pads", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def randomize_rack_macros(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Randomize the macro controls of a Rack device. Set is_return_track=True to target a return track."""
    return _send("randomize_rack_macros", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def store_rack_variation(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Store the current macro state as a new variation in a Rack device. Set is_return_track=True to target a return track."""
    return _send("store_rack_variation", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

# ---------------------------------------------------------------------------
# GroovePool
# ---------------------------------------------------------------------------

@mcp.tool()
def get_grooves() -> list:
    """Return all grooves in the groove pool."""
    return _send("get_grooves")

@mcp.tool()
def extract_groove_from_clip(
    track_index: int,
    slot_index: int,
    groove_name: str = "Extracted Groove",
) -> dict:
    """
    Extract the timing and velocity feel from a MIDI clip and add it to the groove pool.

    Requires Live 10+ (uses Song.create_midi_clip_groove).
    On older versions raises a clear error — use analyze_clip_feel() instead.

    Args:
        track_index: Track containing the source clip.
        slot_index: Clip slot of the source clip.
        groove_name: Name to assign to the new groove in the pool.

    Returns:
        method, groove_name, groove_count (total grooves in pool after extraction)
    """
    return _send("extract_groove_from_clip", {
        "track_index": track_index,
        "slot_index": slot_index,
        "groove_name": groove_name,
    })

# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

@mcp.tool()
def get_browser_tree(category_type: str = "all") -> dict:
    """
    Return the browser tree up to 2 levels deep.
    category_type: 'all', 'instruments', 'sounds', 'drums', 'audio_effects', or 'midi_effects'
    """
    return _send("get_browser_tree", {"category_type": category_type})

@mcp.tool()
def get_browser_items_at_path(path: str) -> dict:
    """
    Return browser items at the given path (e.g. 'instruments/Drum Rack').
    Root path segments: instruments, sounds, drums, audio_effects, midi_effects
    """
    return _send("get_browser_items_at_path", {"path": path})

@mcp.tool()
def load_browser_item(uri: str, track_index: int = 0, is_return_track: bool = False) -> dict:
    """
    Load a browser item by URI onto the track at track_index.
    Use get_browser_items_at_path to discover URIs.
    Set is_return_track=True to target a return track.
    """
    return _send("load_browser_item", {"uri": uri, "track_index": track_index, "is_return_track": is_return_track})

@mcp.tool()
def load_plugin_device(
    track_index: int,
    plugin_name: str,
    plugin_format: str = "au",
) -> dict:
    """
    Load a third-party AU or VST plugin onto a track by name.

    Searches the Ableton browser for a plugin matching the name and loads it
    onto the specified track. The track must exist. The plugin will be appended
    to the end of the device chain.

    Note: This selects the track in Live's UI as a side effect.

    Args:
        track_index: Index of the track to load the plugin onto.
        plugin_name: Name of the plugin to search for (e.g. "Pro-Q 4", "Fabfilter Pro-Q 4").
                     Partial name matching is used.
        plugin_format: "au", "vst", or "vst3". Default: "au".

    Returns:
        status: "ok" on success
        plugin_name: the exact name of the plugin that was loaded
    """
    return _send("load_plugin_device", {
        "track_index": track_index,
        "plugin_name": plugin_name,
        "plugin_format": plugin_format,
    })


@mcp.tool()
def add_native_device(track_index: int, device_name: str, is_return_track: bool = False) -> dict:
    """
    Add a native Ableton device to a track by name.

    Set is_return_track=True to target a return track (A, B, C...) by its
    zero-based index instead of a regular track.

    Searches the browser by display name (case-insensitive substring match).
    The device is loaded onto the currently selected track position.

    Common device names:
    - Mix/Dynamics: 'Compressor', 'Glue Compressor', 'Multiband Dynamics',
                    'Limiter', 'Gate', 'Saturator'
    - EQ/Filter:    'EQ Eight', 'EQ Three', 'Auto Filter'
    - Time-based:   'Reverb', 'Delay', 'Echo', 'Chorus-Ensemble'
    - Utility:      'Utility', 'Spectrum', 'Tuner'
    - Instruments:  'Drum Rack', 'Instrument Rack', 'Simpler', 'Operator',
                    'Wavetable', 'Analog', 'Electric', 'Tension'

    Args:
        track_index: Zero-based index of the track to add the device to.
        device_name: Display name of the device (case-insensitive substring).
        is_return_track: If True, track_index refers to a return track (default False).

    Returns:
        dict with 'device_name' key confirming the matched device name.
    """
    return _send("add_native_device", {
        "track_index": track_index,
        "device_name": device_name,
        "is_return_track": is_return_track,
    })

@mcp.tool()
def set_mixer_snapshot(states: list[dict]) -> dict:
    """
    Set volume, pan, sends, mute, and/or arm on multiple tracks in a single call.

    Much more efficient than calling set_track_volume / set_track_pan individually.
    All changes are applied in the same audio cycle.

    Use track_index=-1 in a state dict to target the master track.

    Each state dict can contain:
      track_index (int, required)
      volume      (float 0.0–1.0, optional)
      pan         (float -1.0 to 1.0, optional)
      sends       (list of floats 0.0–1.0, optional — indexed from 0)
      mute        (bool, optional)
      arm         (bool, optional)

    Example:
      set_mixer_snapshot([
        {"track_index": 0, "volume": 0.8, "pan": -0.2},
        {"track_index": 1, "volume": 0.75, "sends": [0.6, 0.0]},
        {"track_index": -1, "volume": 0.85},
      ])
    """
    return _send("set_mixer_snapshot", {"states": states})

@mcp.tool()
def set_return_track_volume(index: int, value: float) -> dict:
    """Set the volume of the return track at index (0.0-1.0)."""
    return _send("set_return_track_volume", {"index": index, "value": value})

@mcp.tool()
def set_return_track_pan(index: int, value: float) -> dict:
    """Set the panning of the return track at index (-1.0 to 1.0)."""
    return _send("set_return_track_pan", {"index": index, "value": value})

@mcp.tool()
def set_return_track_name(index: int, name: str) -> dict:
    """Rename the return track at index."""
    return _send("set_return_track_name", {"index": index, "name": name})

@mcp.tool()
def set_return_track_mute(index: int, mute: bool) -> dict:
    """Mute or unmute the return track at index."""
    return _send("set_return_track_mute", {"index": index, "mute": mute})

@mcp.tool()
def begin_undo_step(name: str = "MCP Operation") -> dict:
    """
    Begin a named undo step. All changes made until end_undo_step() will be
    grouped into a single Cmd+Z undo action in Live.

    Always call end_undo_step() after you are done, even if an error occurs.

    Example:
      begin_undo_step("Master chain setup")
      add_native_device(-1, "EQ Eight")
      add_native_device(-1, "Compressor")
      add_native_device(-1, "Limiter")
      end_undo_step()
      # Now Cmd+Z removes all three devices at once
    """
    return _send("begin_undo_step", {"name": name})

@mcp.tool()
def end_undo_step() -> dict:
    """
    Close the current undo step opened by begin_undo_step().
    All changes since begin_undo_step() will be undoable as a single action.
    """
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


@mcp.tool()
def adjust_device_parameter(
    track_index: int,
    device_index: int,
    parameter_name: str,
    direction: str,
    amount: str = "a little",
) -> dict:
    """
    Adjust a device parameter using natural language magnitude descriptions.

    Uses the vocabulary system (helpers/vocabulary.py) to resolve amount to
    an exact normalised delta, then applies it in the given direction.

    Args:
        track_index: Track index (0-based)
        device_index: Device index on the track (0-based)
        parameter_name: Parameter name (case-insensitive partial match)
        direction: "up", "down", "increase", "decrease", "more", "less"
        amount: Natural language amount — "a little", "a lot", "a touch",
                "slightly", "significantly", "halfway", etc.
                Defaults to "a little" (0.05 delta)

    Returns:
        parameter_name: str (resolved)
        previous_value: float
        new_value: float
        delta_applied: float
        amount_resolved: str
        direction: str
        clamped: bool  # True if value was clamped to 0.0 or 1.0
    """
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

@mcp.tool()
def find_device_by_name(track_index: int, device_name: str) -> dict:
    """Find a device on a track by name, supporting natural language aliases.

    Uses the device alias registry (helpers/vocabulary.py) to resolve
    common names like "eq", "comp", "reverb" to Ableton device names.

    Args:
        track_index: Track to search.
        device_name: Device name or alias (e.g. "eq", "compressor", "EQ Eight").

    Returns:
        found: bool
        device_index: int or None
        device_name: str (resolved name)
        alias_used: str or None
        parameters: list of {name, value, min, max}
    """
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


@mcp.tool()
def set_device_parameters_batch(
    track_index: int,
    device_index: int,
    updates: list,
    is_return_track: bool = False,
    visual_refresh: bool = True,
    skip_unchanged: bool = True,
    clamp_values: bool = True,
) -> dict:
    """
    Set multiple device parameters in a single round trip.

    Executes all writes inside one Live main-thread call — one network hop,
    one device resolve, one optional control-surface UI refresh, N writes.
    Use this instead of calling set_device_parameter repeatedly.

    Args:
        track_index: Track index (use -1 for master track).
        device_index: Device index on the track.
        updates: List of {parameter_index: int, value: float} dicts.
        is_return_track: Set True to target a return track.
        visual_refresh: If True (default), appoints the device and shows
            Detail/DeviceChain — forces third-party plugin UI to refresh
            (Pro-Q 4, FabFilter, etc.), same as Push 3.
        skip_unchanged: If True (default), skips writes where the parameter
            already has the target value.
        clamp_values: If True (default), clamps each value to the parameter's
            min/max range.

    Returns:
        dict with keys:
            device (str): device name
            applied (int): number of parameters actually changed
            changed (list): {parameter_index, name, value} for each write
            errors (list): {parameter_index, error} for any failures

    Example:
        set_device_parameters_batch(
            track_index=3,
            device_index=0,
            updates=[
                {"parameter_index": 1, "value": 0.72},
                {"parameter_index": 5, "value": 0.14},
                {"parameter_index": 8, "value": 0.88},
            ]
        )
    """
    return _send("set_device_parameters_batch", {
        "track_index": track_index,
        "device_index": device_index,
        "updates": updates,
        "is_return_track": is_return_track,
        "visual_refresh": visual_refresh,
        "skip_unchanged": skip_unchanged,
        "clamp_values": clamp_values,
    })


@mcp.tool()
def perform_device_parameter_moves(
    track_index: int,
    device_index: int,
    moves: list,
    is_return_track: bool = False,
    visual_refresh: bool = True,
    step_ms: int = 30,
) -> dict:
    """
    Animate one or more device parameters to target values over time.

    Fire-and-forget: one MCP call starts the motion, all stepping happens
    inside Live's main thread via schedule_message — no polling, no extra
    round trips. Returns immediately while the animation runs in the background.

    Args:
        track_index: Track index (use -1 for master track).
        device_index: Device index on the track.
        moves: List of move dicts. Each requires:
            parameter_index (int): parameter to move
            target (float): destination value
            duration_ms (float): how long the move takes in milliseconds (default 500)
            curve (str): "linear" | "ease_in" | "ease_out" | "ease_in_out" (default "linear")
        is_return_track: Set True to target a return track.
        visual_refresh: If True (default), appoints the device so the plugin
            UI updates visibly as parameters move.
        step_ms: Milliseconds between animation steps (default 30 ≈ 33fps).

    Returns:
        dict with key:
            moves_scheduled (int): number of moves queued

    Example — sweep EQ band 2 frequency from current to 800 Hz over 1.2 seconds:
        perform_device_parameter_moves(
            track_index=2,
            device_index=0,
            moves=[
                {
                    "parameter_index": 5,
                    "target": 800.0,
                    "duration_ms": 1200,
                    "curve": "ease_out"
                }
            ]
        )

    Example — slow attack/release ride while listening:
        perform_device_parameter_moves(
            track_index=0,
            device_index=1,
            moves=[
                {"parameter_index": 3, "target": 50.0, "duration_ms": 800, "curve": "ease_in_out"},
                {"parameter_index": 4, "target": 200.0, "duration_ms": 800, "curve": "ease_in_out"},
            ]
        )
    """
    return _send("perform_device_parameter_moves", {
        "track_index": track_index,
        "device_index": device_index,
        "moves": moves,
        "is_return_track": is_return_track,
        "visual_refresh": visual_refresh,
        "step_ms": step_ms,
    })


@mcp.tool()
def randomize_device_parameters(
    track_index: int,
    device_index: int,
    parameter_indices: list[int] | None = None,
    min_value: float = 0.0,
    max_value: float = 1.0,
    seed: int | None = None,
    is_return_track: bool = False,
) -> dict:
    """
    Randomize device parameters within a specified range.

    Args:
        track_index: Track index (use -1 for master track).
        device_index: Device index on the track.
        parameter_indices: List of parameter indices to randomize. If None, randomizes all.
        min_value: Minimum normalised value (0.0-1.0, default 0.0).
        max_value: Maximum normalised value (0.0-1.0, default 1.0).
        seed: Optional random seed for reproducible results.
        is_return_track: Set True to target a return track.

    Returns:
        device: str — device name
        randomized: list of {parameter_index, name, previous_value, new_value}
        seed_used: int or null
    """
    return _send("randomize_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_indices": parameter_indices,
        "min_value": min_value,
        "max_value": max_value,
        "seed": seed,
        "is_return_track": is_return_track,
    })


