"""Device tools — instruments, audio effects, MIDI effects, MixerDevice, RackDevice, GroovePool, and Browser."""
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
from helpers.vocabulary import resolve_device_name, DEVICE_ALIASES

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
def get_rack_chains(track_index: int, device_index: int) -> list:
    """Return the chains of a Rack device at (track_index, device_index)."""
    return _send("get_rack_chains", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def get_rack_drum_pads(track_index: int, device_index: int) -> list:
    """Return the drum pads of a Drum Rack device at (track_index, device_index)."""
    return _send("get_rack_drum_pads", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def randomize_rack_macros(track_index: int, device_index: int) -> dict:
    """Randomize the macro controls of a Rack device."""
    return _send("randomize_rack_macros", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def store_rack_variation(track_index: int, device_index: int) -> dict:
    """Store the current macro state as a new variation in a Rack device."""
    return _send("store_rack_variation", {"track_index": track_index, "device_index": device_index})

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
def load_browser_item(uri: str, track_index: int = 0) -> dict:
    """
    Load a browser item by URI onto the track at track_index.
    Use get_browser_items_at_path to discover URIs.
    """
    return _send("load_browser_item", {"uri": uri, "track_index": track_index})

@mcp.tool()
def add_native_device(track_index: int, device_name: str) -> dict:
    """
    Add a native Ableton device to a track by name.

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

    Returns:
        dict with 'device_name' key confirming the matched device name.
    """
    return _send("add_native_device", {"track_index": track_index, "device_name": device_name})

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
    alias_used: str | None = None
    lower_input = device_name.lower().strip()
    resolved = resolve_device_name(device_name)
    if resolved != device_name:
        alias_used = device_name

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

