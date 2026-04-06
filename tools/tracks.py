"""Track tools — master track, audio/MIDI tracks, return tracks, routing, volume, pan, mute, solo, arm, sends, and fold state."""
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
# Master Track
# ---------------------------------------------------------------------------

@mcp.tool()
def get_master_track() -> dict:
    """Return the master track's volume, pan and crossfader values."""
    return _send("get_master_track")

@mcp.tool()
def set_master_volume(value: float) -> dict:
    """Set the master track volume (0.0-1.0)."""
    return _send("set_master_volume", {"value": value})

@mcp.tool()
def set_master_pan(value: float) -> dict:
    """Set the master track panning (-1.0 = full left, 0 = centre, 1.0 = full right)."""
    return _send("set_master_pan", {"value": value})

@mcp.tool()
def set_crossfader(value: float) -> dict:
    """Set the master crossfader position (-1.0 = full A, 0 = centre, 1.0 = full B)."""
    return _send("set_crossfader", {"value": value})

# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------

@mcp.tool()
def get_tracks() -> list:
    """Return all tracks with their name, color, mute/solo/arm state and mixer values."""
    return _send("get_tracks")

@mcp.tool()
def get_track_info(track_index: int) -> dict:
    """Return full details for the track at track_index, including clip slots and devices. Use track_index=-1 to target the master track."""
    return _send("get_track_info", {"track_index": track_index})

@mcp.tool()
def get_track_playing_state(track_index: int) -> dict:
    """
    Return the currently playing and queued slot indices for a track.
    playing_slot_index: index of the currently playing clip slot (-1 if none).
    fired_slot_index: index of the next queued clip slot (-1 if none).
    """
    return _send("get_track_playing_state", {"track_index": track_index})

@mcp.tool()
def get_track_names(include_returns: bool = False, include_master: bool = False) -> list:
    """
    Return a lightweight list of all track names and their indices.
    Much faster than get_tracks() when you only need names.

    Args:
        include_returns: If True, also include return tracks (marked with is_return=True).
        include_master: If True, also include the master track at index -1.

    Returns:
        List of dicts with 'index' and 'name' keys.
        Return tracks also include 'is_return': True when include_returns is True.
        Master track also includes 'is_master': True when include_master is True.
        Use the returned indices with any track_index parameter.
        Master track is always at index -1.
    """
    return _send("get_track_names", {
        "include_returns": include_returns,
        "include_master": include_master,
    })

@mcp.tool()
def set_track_name(track_index: int, name: str) -> dict:
    """Rename the track at track_index."""
    return _send("set_track_name", {"track_index": track_index, "name": name})

@mcp.tool()
def set_track_color(track_index: int, color: int) -> dict:
    """Set the track color as an RGB integer (0x00rrggbb)."""
    return _send("set_track_color", {"track_index": track_index, "color": color})

@mcp.tool()
def set_track_mute(track_index: int, mute: bool) -> dict:
    """Mute or unmute the track at track_index."""
    return _send("set_track_mute", {"track_index": track_index, "mute": mute})

@mcp.tool()
def set_track_solo(track_index: int, solo: bool) -> dict:
    """Solo or unsolo the track at track_index."""
    return _send("set_track_solo", {"track_index": track_index, "solo": solo})

@mcp.tool()
def set_track_arm(track_index: int, arm: bool) -> dict:
    """Arm or disarm the track at track_index for recording."""
    return _send("set_track_arm", {"track_index": track_index, "arm": arm})

@mcp.tool()
def set_track_volume(track_index: int, value: float) -> dict:
    """Set the track volume (0.0-1.0 maps to -inf to +6 dB)."""
    return _send("set_track_volume", {"track_index": track_index, "value": value})

@mcp.tool()
def set_track_pan(track_index: int, value: float) -> dict:
    """Set the track panning (-1.0 = full left, 0 = centre, 1.0 = full right)."""
    return _send("set_track_pan", {"track_index": track_index, "value": value})

@mcp.tool()
def set_track_send(track_index: int, send_index: int, value: float) -> dict:
    """Set a send level on the track at track_index (value 0.0-1.0)."""
    return _send("set_track_send", {"track_index": track_index, "send_index": send_index, "value": value})

@mcp.tool()
def stop_track_clips(track_index: int) -> dict:
    """Stop all clips on the track at track_index."""
    return _send("stop_track_clips", {"track_index": track_index})

@mcp.tool()
def set_track_fold_state(track_index: int, fold_state: int) -> dict:
    """Set the fold state of a group track (0=unfolded, 1=folded)."""
    if fold_state not in (0, 1):
        raise ValueError("fold_state must be 0 (unfolded) or 1 (folded)")
    return _send("set_track_fold_state", {"track_index": track_index, "fold_state": fold_state})

@mcp.tool()
def get_return_tracks() -> list:
    """Return all return tracks with name and volume."""
    return _send("get_return_tracks")

@mcp.tool()
def get_track_routing(track_index: int) -> dict:
    """
    Return the full routing state for a track: input/output type and channel,
    plus the list of available options for each routing type property.

    Use the 'available_input_routing_types' and 'available_output_routing_types'
    lists to discover valid index values for the setter tools.

    Args:
        track_index: Track index (-1 not supported for routing).

    Returns:
        input_routing_type, input_routing_channel,
        output_routing_type, output_routing_channel,
        available_input_routing_types (list of str),
        available_output_routing_types (list of str)
    """
    return _send("get_track_routing", {"track_index": track_index})


@mcp.tool()
def set_track_input_routing_type(track_index: int, value: int) -> dict:
    """
    Set the input routing type for a track by index into the available options.

    Call get_track_routing() first to see available options and their indices.

    Args:
        track_index: Track to modify.
        value: Index into track.available_input_routing_types (0-based).
    """
    return _send("set_track_input_routing_type", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_input_routing_channel(track_index: int, value: int) -> dict:
    """
    Set the input routing channel for a track by index into the available options.

    Call get_track_routing() first to see available channel options.

    Args:
        track_index: Track to modify.
        value: Index into track.available_input_routing_channels (0-based).
    """
    return _send("set_track_input_routing_channel", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_output_routing_type(track_index: int, value: int) -> dict:
    """
    Set the output routing type for a track by index into the available options.

    Call get_track_routing() first to see available options and their indices.

    Args:
        track_index: Track to modify.
        value: Index into track.available_output_routing_types (0-based).
    """
    return _send("set_track_output_routing_type", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_output_routing_channel(track_index: int, value: int) -> dict:
    """
    Set the output routing channel for a track by index into the available options.

    Call get_track_routing() first to see available channel options.

    Args:
        track_index: Track to modify.
        value: Index into track.available_output_routing_channels (0-based).
    """
    return _send("set_track_output_routing_channel", {"track_index": track_index, "value": value})


@mcp.tool()
def get_available_routings(track_index: int) -> dict:
    """
    Return all available input and output routing types and channels for a track.

    Useful for discovering valid display name values before calling
    set_track_input_routing or set_track_output_routing.

    Args:
        track_index: Track index.

    Returns:
        input_routing_types (list of str), input_routing_channels (list of str),
        output_routing_types (list of str), output_routing_channels (list of str)
    """
    return _send("get_available_routings", {"track_index": track_index})


@mcp.tool()
def set_track_input_routing(
    track_index: int,
    routing_type_name: str | None = None,
    routing_channel_name: str | None = None,
) -> dict:
    """
    Set the input routing for a track by display name.

    routing_type_name: display name of the routing type (e.g. "Resampling", "No Input", "1-Ext. In").
    routing_channel_name: display name of the routing channel (e.g. "1/2", "3/4").
    Call get_available_routings first to discover valid values.

    Args:
        track_index: Track to modify.
        routing_type_name: Display name of the desired input routing type (optional).
        routing_channel_name: Display name of the desired input routing channel (optional).
    """
    return _send("set_track_input_routing", {
        "track_index": track_index,
        "routing_type_name": routing_type_name,
        "routing_channel_name": routing_channel_name,
    })


@mcp.tool()
def set_track_output_routing(
    track_index: int,
    routing_type_name: str | None = None,
    routing_channel_name: str | None = None,
) -> dict:
    """
    Set the output routing for a track by display name.

    routing_type_name: display name of the routing type (e.g. "Master", "Sends Only", "1-Ext. Out").
    routing_channel_name: display name of the routing channel (e.g. "1/2", "3/4").
    Call get_available_routings first to discover valid values.

    Args:
        track_index: Track to modify.
        routing_type_name: Display name of the desired output routing type (optional).
        routing_channel_name: Display name of the desired output routing channel (optional).
    """
    return _send("set_track_output_routing", {
        "track_index": track_index,
        "routing_type_name": routing_type_name,
        "routing_channel_name": routing_channel_name,
    })

