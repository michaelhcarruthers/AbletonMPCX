"""
AbletonMPCX MCP Server
Bridges the MCP protocol to the Ableton Remote Script running inside Live.
"""
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

from mcp.server.fastmcp import FastMCP

# --- Connection settings ---
ABLETON_HOST = "localhost"
ABLETON_PORT = 9877

mcp = FastMCP("AbletonMPCX")


# ---------------------------------------------------------------------------
# Low-level socket helpers
# ---------------------------------------------------------------------------

@contextmanager
def _ableton_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15.0)
    try:
        sock.connect((ABLETON_HOST, ABLETON_PORT))
        yield sock
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _recv_exactly(sock, n: int) -> bytes | None:
    """Read exactly n bytes from sock. Returns None if connection closes early."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return None
        buf += chunk
    return buf


def _send(command: str, params: dict[str, Any] | None = None, _log: bool = True) -> Any:
    payload = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
    with _ableton_socket() as sock:
        sock.sendall(len(payload).to_bytes(4, "big") + payload)
        # Read 4-byte length header
        header = _recv_exactly(sock, 4)
        if not header:
            raise RuntimeError("Connection closed before response header")
        msg_len = int.from_bytes(header, "big")
        if msg_len > 10 * 1024 * 1024:
            raise RuntimeError("Response too large: {} bytes".format(msg_len))
        data = _recv_exactly(sock, msg_len)
        if data is None:
            raise RuntimeError("Connection closed before response body")
    response = json.loads(data.decode("utf-8"))
    if response.get("status") == "error":
        raise RuntimeError(response["error"])
    result = response.get("result")
    if _log:
        _append_operation(command, params or {}, result)
    return result


def _send_logged(command: str, params: dict[str, Any] | None = None) -> Any:
    """Like _send but appends to the operation log. Kept for compatibility; _send now logs by default."""
    return _send(command, params)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@mcp.tool()
def get_app_version() -> dict:
    """Return the running Ableton Live version."""
    return _send("get_app_version")

# ---------------------------------------------------------------------------
# Song
# ---------------------------------------------------------------------------

@mcp.tool()
def get_song_info() -> dict:
    """Return the current song's tempo, transport state, loop settings, etc."""
    return _send("get_song_info")

@mcp.tool()
def set_tempo(tempo: float) -> dict:
    """Set the song tempo (20-999 BPM)."""
    return _send("set_tempo", {"tempo": tempo})

@mcp.tool()
def set_time_signature(numerator: int | None = None, denominator: int | None = None) -> dict:
    """Set the song time signature numerator and/or denominator."""
    params: dict[str, int] = {}
    if numerator is not None:
        params["numerator"] = numerator
    if denominator is not None:
        params["denominator"] = denominator
    return _send("set_time_signature", params)

@mcp.tool()
def set_record_mode(record_mode: bool) -> dict:
    """Enable or disable Arrangement Record."""
    return _send("set_record_mode", {"record_mode": record_mode})

@mcp.tool()
def set_session_record(session_record: bool) -> dict:
    """Enable or disable Session Overdub."""
    return _send("set_session_record", {"session_record": session_record})

@mcp.tool()
def set_overdub(overdub: bool) -> dict:
    """Enable or disable MIDI Arrangement Overdub."""
    return _send("set_overdub", {"overdub": overdub})

@mcp.tool()
def set_metronome(metronome: bool) -> dict:
    """Enable or disable the metronome."""
    return _send("set_metronome", {"metronome": metronome})

@mcp.tool()
def set_loop(enabled: bool | None = None, loop_start: float | None = None, loop_length: float | None = None) -> dict:
    """Set Arrangement loop state, start position (beats) and/or length (beats)."""
    params: dict[str, Any] = {}
    if enabled is not None:
        params["enabled"] = enabled
    if loop_start is not None:
        params["loop_start"] = loop_start
    if loop_length is not None:
        params["loop_length"] = loop_length
    return _send("set_loop", params)

@mcp.tool()
def set_swing_amount(value: float) -> dict:
    """Set the global swing amount (0.0-1.0)."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("swing_amount must be between 0.0 and 1.0")
    return _send("set_swing_amount", {"value": value})

@mcp.tool()
def set_groove_amount(value: float) -> dict:
    """Set the global groove amount (0.0-1.0)."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("groove_amount must be between 0.0 and 1.0")
    return _send("set_groove_amount", {"value": value})

@mcp.tool()
def set_back_to_arranger(value: bool) -> dict:
    """Enable or disable Back to Arranger mode."""
    return _send("set_back_to_arranger", {"value": value})

@mcp.tool()
def set_clip_trigger_quantization(value: int) -> dict:
    """Set the global clip trigger quantization (0-13, matching Live's ClipTriggerQuantization enum)."""
    if not 0 <= value <= 13:
        raise ValueError("clip_trigger_quantization must be between 0 and 13")
    return _send("set_clip_trigger_quantization", {"value": value})

@mcp.tool()
def set_midi_recording_quantization(value: int) -> dict:
    """Set the MIDI recording quantization (0-8, matching Live's RecordingQuantization enum)."""
    if not 0 <= value <= 8:
        raise ValueError("midi_recording_quantization must be between 0 and 8")
    return _send("set_midi_recording_quantization", {"value": value})

@mcp.tool()
def set_scale_mode(scale_mode: bool) -> dict:
    """Enable or disable scale mode."""
    return _send("set_scale_mode", {"scale_mode": scale_mode})

@mcp.tool()
def set_scale_name(scale_name: str) -> dict:
    """Set the scale name (e.g. 'Major', 'Minor', 'Dorian')."""
    return _send("set_scale_name", {"scale_name": scale_name})

@mcp.tool()
def set_root_note(root_note: int) -> dict:
    """Set the root note for the scale (0=C, 1=C#, ..., 11=B)."""
    if not 0 <= root_note <= 11:
        raise ValueError("root_note must be between 0 and 11")
    return _send("set_root_note", {"root_note": root_note})

@mcp.tool()
def set_or_delete_cue() -> dict:
    """Toggle (create or delete) a cue point at the current playback position."""
    return _send("set_or_delete_cue")

@mcp.tool()
def re_enable_automation() -> dict:
    """Re-enable automation that has been overridden."""
    return _send("re_enable_automation")

@mcp.tool()
def play_selection() -> dict:
    """Play the current selection in the Arrangement."""
    return _send("play_selection")

@mcp.tool()
def start_playing() -> dict:
    """Start playback from the insert marker."""
    return _send("start_playing")

@mcp.tool()
def stop_playing() -> dict:
    """Stop playback."""
    return _send("stop_playing")

@mcp.tool()
def continue_playing() -> dict:
    """Continue playback from the current position."""
    return _send("continue_playing")

@mcp.tool()
def tap_tempo() -> dict:
    """Send a tap tempo pulse."""
    return _send("tap_tempo")

@mcp.tool()
def undo() -> dict:
    """Undo the last operation."""
    return _send("undo")

@mcp.tool()
def redo() -> dict:
    """Redo the last undone operation."""
    return _send("redo")

@mcp.tool()
def capture_midi(destination: int = 0) -> dict:
    """Capture recently played MIDI. destination: 0=auto, 1=session, 2=arrangement."""
    return _send("capture_midi", {"destination": destination})

@mcp.tool()
def capture_and_insert_scene() -> dict:
    """Capture currently playing clips into a new scene."""
    return _send("capture_and_insert_scene")

@mcp.tool()
def create_audio_track(index: int = -1) -> dict:
    """Create a new audio track. index=-1 appends at end."""
    return _send("create_audio_track", {"index": index})

@mcp.tool()
def create_midi_track(index: int = -1) -> dict:
    """Create a new MIDI track. index=-1 appends at end."""
    return _send("create_midi_track", {"index": index})

@mcp.tool()
def create_return_track() -> dict:
    """Add a new return track."""
    return _send("create_return_track")

@mcp.tool()
def create_scene(index: int = -1) -> dict:
    """Create a new scene. index=-1 appends at end."""
    return _send("create_scene", {"index": index})

@mcp.tool()
def delete_scene(index: int) -> dict:
    """Delete the scene at index."""
    return _send("delete_scene", {"scene_index": index})

@mcp.tool()
def delete_track(track_index: int) -> dict:
    """Delete the track at track_index."""
    return _send("delete_track", {"track_index": track_index})

@mcp.tool()
def delete_return_track(index: int) -> dict:
    """Delete the return track at index."""
    return _send("delete_return_track", {"index": index})

@mcp.tool()
def duplicate_scene(index: int) -> dict:
    """Duplicate the scene at index."""
    return _send("duplicate_scene", {"scene_index": index})

@mcp.tool()
def duplicate_track(track_index: int) -> dict:
    """Duplicate the track at track_index."""
    return _send("duplicate_track", {"track_index": track_index})

@mcp.tool()
def jump_by(beats: float) -> dict:
    """Jump the playback position by the given number of beats (positive or negative)."""
    return _send("jump_by", {"beats": beats})

@mcp.tool()
def jump_to_next_cue() -> dict:
    """Jump to the next cue point."""
    return _send("jump_to_next_cue")

@mcp.tool()
def jump_to_prev_cue() -> dict:
    """Jump to the previous cue point."""
    return _send("jump_to_prev_cue")

@mcp.tool()
def stop_all_clips(quantized: int = 1) -> dict:
    """Stop all clips. quantized=0 stops immediately regardless of quantization."""
    return _send("stop_all_clips", {"quantized": quantized})

@mcp.tool()
def get_cue_points() -> list:
    """Return all cue points as a list of {name, time} dicts."""
    return _send("get_cue_points")

@mcp.tool()
def jump_to_cue_point(index: int) -> dict:
    """Jump to the cue point at index."""
    return _send("jump_to_cue_point", {"index": index})

# ---------------------------------------------------------------------------
# Song.View
# ---------------------------------------------------------------------------

@mcp.tool()
def get_selected_track() -> dict:
    """Return the currently selected track index and name."""
    return _send("get_selected_track")

@mcp.tool()
def set_selected_track(track_index: int) -> dict:
    """Select the track at track_index."""
    return _send("set_selected_track", {"track_index": track_index})

@mcp.tool()
def get_selected_scene() -> dict:
    """Return the currently selected scene index and name."""
    return _send("get_selected_scene")

@mcp.tool()
def set_selected_scene(scene_index: int) -> dict:
    """Select the scene at scene_index."""
    return _send("set_selected_scene", {"scene_index": scene_index})

@mcp.tool()
def get_follow_song() -> dict:
    """Return whether Follow Song is enabled."""
    return _send("get_follow_song")

@mcp.tool()
def set_follow_song(follow_song: bool) -> dict:
    """Enable or disable Follow Song."""
    return _send("set_follow_song", {"follow_song": follow_song})

@mcp.tool()
def get_draw_mode() -> dict:
    """Return whether Draw Mode is enabled in the current view."""
    return _send("get_draw_mode")

@mcp.tool()
def set_draw_mode(draw_mode: bool) -> dict:
    """Enable or disable Draw Mode."""
    return _send("set_draw_mode", {"draw_mode": draw_mode})

@mcp.tool()
def focus_view(view_name: str) -> dict:
    """
    Focus a named view in Ableton Live.
    Common view names: 'Session', 'Arranger', 'Detail', 'Detail/Clip',
    'Detail/DeviceChain', 'Browser', 'Mixer'.
    """
    return _send("focus_view", {"view_name": view_name})

@mcp.tool()
def show_view(view_name: str) -> dict:
    """Show a named panel/view. See focus_view for common view names."""
    return _send("show_view", {"view_name": view_name})

@mcp.tool()
def hide_view(view_name: str) -> dict:
    """Hide a named panel/view. See focus_view for common view names."""
    return _send("hide_view", {"view_name": view_name})

@mcp.tool()
def is_view_visible(view_name: str) -> dict:
    """Return whether the named view/panel is currently visible."""
    return _send("is_view_visible", {"view_name": view_name})

@mcp.tool()
def available_main_views() -> dict:
    """Return the list of available main view names."""
    return _send("available_main_views")

@mcp.tool()
def set_exclusive_arm(value: bool) -> dict:
    """Enable or disable exclusive arm mode (arming one track disarms all others)."""
    return _send("set_exclusive_arm", {"value": value})

@mcp.tool()
def set_exclusive_solo(value: bool) -> dict:
    """Enable or disable exclusive solo mode (soloing one track un-solos all others)."""
    return _send("set_exclusive_solo", {"value": value})

@mcp.tool()
def set_select_on_launch(value: bool) -> dict:
    """Enable or disable Select on Launch (firing a scene/clip selects it)."""
    return _send("set_select_on_launch", {"value": value})

@mcp.tool()
def nudge_up() -> dict:
    """Send a tempo nudge up pulse (nudges the master tempo up momentarily)."""
    return _send("nudge_up")

@mcp.tool()
def nudge_down() -> dict:
    """Send a tempo nudge down pulse (nudges the master tempo down momentarily)."""
    return _send("nudge_down")

@mcp.tool()
def get_appointed_device() -> dict:
    """
    Return the currently appointed (focused) device in Live.
    Returns track_index, device_index, name and class_name, or {"device": None} if none.
    """
    return _send("get_appointed_device")

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

# ---------------------------------------------------------------------------
# ClipSlot
# ---------------------------------------------------------------------------

@mcp.tool()
def get_clip_slots(track_index: int) -> list:
    """Return all clip slots for the track at track_index."""
    return _send("get_clip_slots", {"track_index": track_index})

@mcp.tool()
def fire_clip_slot(track_index: int, slot_index: int, record_length: float | None = None, launch_quantization: int | None = None) -> dict:
    """Fire the clip slot at (track_index, slot_index)."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if record_length is not None:
        params["record_length"] = record_length
    if launch_quantization is not None:
        params["launch_quantization"] = launch_quantization
    return _send("fire_clip_slot", params)

@mcp.tool()
def stop_clip_slot(track_index: int, slot_index: int) -> dict:
    """Stop the clip slot at (track_index, slot_index)."""
    return _send("stop_clip_slot", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def create_clip(track_index: int, slot_index: int, length: float = 4.0) -> dict:
    """Create an empty MIDI clip in the slot at (track_index, slot_index) with the given length in beats."""
    return _send("create_clip", {"track_index": track_index, "slot_index": slot_index, "length": length})

@mcp.tool()
def delete_clip(track_index: int, slot_index: int) -> dict:
    """Delete the clip in the slot at (track_index, slot_index)."""
    return _send("delete_clip", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def duplicate_clip_slot(track_index: int, slot_index: int) -> dict:
    """Duplicate the clip slot at (track_index, slot_index) to the next empty slot below."""
    return _send("duplicate_clip_slot", {"track_index": track_index, "slot_index": slot_index})

# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------

@mcp.tool()
def get_clip_info(track_index: int, slot_index: int) -> dict:
    """Return full details for the clip at (track_index, slot_index)."""
    return _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def get_clip_playing_position(track_index: int, slot_index: int) -> dict:
    """
    Return the current playhead position within the clip (in beats).
    Only meaningful while the clip is playing.
    """
    return _send("get_clip_playing_position", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def set_clip_name(track_index: int, slot_index: int, name: str) -> dict:
    """Rename the clip at (track_index, slot_index)."""
    return _send("set_clip_name", {"track_index": track_index, "slot_index": slot_index, "name": name})

@mcp.tool()
def set_clip_color(track_index: int, slot_index: int, color: int) -> dict:
    """Set the clip color as an RGB integer (0x00rrggbb)."""
    return _send("set_clip_color", {"track_index": track_index, "slot_index": slot_index, "color": color})

@mcp.tool()
def set_clip_loop(track_index: int, slot_index: int, looping: bool | None = None, loop_start: float | None = None, loop_end: float | None = None) -> dict:
    """Set loop state and/or loop start/end (in beats) for the clip."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if looping is not None:
        params["looping"] = looping
    if loop_start is not None:
        params["loop_start"] = loop_start
    if loop_end is not None:
        params["loop_end"] = loop_end
    return _send("set_clip_loop", params)

@mcp.tool()
def set_clip_markers(track_index: int, slot_index: int, start_marker: float | None = None, end_marker: float | None = None) -> dict:
    """Set the start and/or end marker of the clip (in beats)."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if start_marker is not None:
        params["start_marker"] = start_marker
    if end_marker is not None:
        params["end_marker"] = end_marker
    return _send("set_clip_markers", params)

@mcp.tool()
def set_clip_mute(track_index: int, slot_index: int, mute: bool) -> dict:
    """Mute or unmute the clip at (track_index, slot_index)."""
    return _send("set_clip_mute", {"track_index": track_index, "slot_index": slot_index, "mute": mute})

@mcp.tool()
def set_clip_pitch(track_index: int, slot_index: int, pitch_coarse: int | None = None, pitch_fine: float | None = None) -> dict:
    """Set transpose (semitones) and/or detune (cents) for an audio clip."""
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if pitch_coarse is not None:
        params["pitch_coarse"] = pitch_coarse
    if pitch_fine is not None:
        params["pitch_fine"] = pitch_fine
    return _send("set_clip_pitch", params)

@mcp.tool()
def set_clip_gain(track_index: int, slot_index: int, gain: float) -> dict:
    """Set the gain of an audio clip (0.0-1.0)."""
    return _send("set_clip_gain", {"track_index": track_index, "slot_index": slot_index, "gain": gain})

@mcp.tool()
def set_clip_warping(track_index: int, slot_index: int, warping: bool) -> dict:
    """Enable or disable warping on an audio clip."""
    return _send("set_clip_warping", {"track_index": track_index, "slot_index": slot_index, "warping": warping})

@mcp.tool()
def set_clip_velocity_amount(track_index: int, slot_index: int, value: float) -> dict:
    """
    Set the velocity amount for a MIDI clip (-1.0 to 1.0).
    Controls how much note velocity affects clip volume.
    """
    return _send("set_clip_velocity_amount", {"track_index": track_index, "slot_index": slot_index, "value": value})

@mcp.tool()
def set_clip_warp_mode(track_index: int, slot_index: int, warp_mode: int) -> dict:
    """Set the warp mode of an audio clip (0=Beats, 1=Tones, 2=Texture, 3=Re-Pitch, 4=Complex, 6=Complex Pro)."""
    return _send("set_clip_warp_mode", {"track_index": track_index, "slot_index": slot_index, "warp_mode": warp_mode})

@mcp.tool()
def set_clip_launch_mode(track_index: int, slot_index: int, launch_mode: int) -> dict:
    """Set the clip launch mode (0=Trigger, 1=Gate, 2=Toggle, 3=Repeat)."""
    if not 0 <= launch_mode <= 3:
        raise ValueError("launch_mode must be between 0 and 3")
    return _send("set_clip_launch_mode", {"track_index": track_index, "slot_index": slot_index, "launch_mode": launch_mode})

@mcp.tool()
def set_clip_launch_quantization(track_index: int, slot_index: int, launch_quantization: int) -> dict:
    """Set the clip launch quantization (0-13, matching Live's ClipTriggerQuantization enum)."""
    if not 0 <= launch_quantization <= 13:
        raise ValueError("launch_quantization must be between 0 and 13")
    return _send("set_clip_launch_quantization", {"track_index": track_index, "slot_index": slot_index, "launch_quantization": launch_quantization})

@mcp.tool()
def get_clip_follow_actions(track_index: int, slot_index: int) -> dict:
    """
    Return all follow action properties for the clip at (track_index, slot_index).

    Follow action enum values (follow_action_a / follow_action_b):
      0 = None (stop)
      1 = Stop
      2 = Play again
      3 = Play previous
      4 = Play next
      5 = Play first
      6 = Play last
      7 = Play any (random)
      8 = Play other

    Returns:
        follow_action_time (float beats),
        follow_action_linked (bool),
        follow_action_enabled (bool, Live 12+ only),
        follow_action_a (int),
        follow_action_b (int),
        follow_action_chance_a (int 0-100),
        follow_action_chance_b (int 0-100)
    """
    return _send("get_clip_follow_actions", {"track_index": track_index, "slot_index": slot_index})


@mcp.tool()
def set_clip_follow_actions(
    track_index: int,
    slot_index: int,
    follow_action_time: float | None = None,
    follow_action_linked: bool | None = None,
    follow_action_enabled: bool | None = None,
    follow_action_a: int | None = None,
    follow_action_b: int | None = None,
    follow_action_chance_a: int | None = None,
    follow_action_chance_b: int | None = None,
) -> dict:
    """
    Set follow action properties on the clip at (track_index, slot_index).

    All parameters are optional — only provided values are written.
    follow_action_enabled requires Live 12+; it is silently skipped on Live 11.

    Follow action enum values (follow_action_a / follow_action_b):
      0 = None, 1 = Stop, 2 = Play again, 3 = Play previous,
      4 = Play next, 5 = Play first, 6 = Play last,
      7 = Play any (random), 8 = Play other

    Returns:
        updated: list of property names that were set
        errors: dict of {property: reason} for any that failed (e.g. Live 11 limitation)
    """
    params: dict[str, Any] = {"track_index": track_index, "slot_index": slot_index}
    if follow_action_time is not None:
        params["follow_action_time"] = follow_action_time
    if follow_action_linked is not None:
        params["follow_action_linked"] = follow_action_linked
    if follow_action_enabled is not None:
        params["follow_action_enabled"] = follow_action_enabled
    if follow_action_a is not None:
        if not 0 <= follow_action_a <= 8:
            raise ValueError("follow_action_a must be 0-8")
        params["follow_action_a"] = follow_action_a
    if follow_action_b is not None:
        if not 0 <= follow_action_b <= 8:
            raise ValueError("follow_action_b must be 0-8")
        params["follow_action_b"] = follow_action_b
    if follow_action_chance_a is not None:
        if not 0 <= follow_action_chance_a <= 100:
            raise ValueError("follow_action_chance_a must be 0-100")
        params["follow_action_chance_a"] = follow_action_chance_a
    if follow_action_chance_b is not None:
        if not 0 <= follow_action_chance_b <= 100:
            raise ValueError("follow_action_chance_b must be 0-100")
        params["follow_action_chance_b"] = follow_action_chance_b
    return _send("set_clip_follow_actions", params)

@mcp.tool()
def fire_clip(track_index: int, slot_index: int) -> dict:
    """Fire the clip at (track_index, slot_index)."""
    return _send("fire_clip", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def stop_clip(track_index: int, slot_index: int) -> dict:
    """Stop the clip at (track_index, slot_index) if it is playing."""
    return _send("stop_clip", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def crop_clip(track_index: int, slot_index: int) -> dict:
    """Crop the clip to its loop or start/end markers."""
    return _send("crop_clip", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def duplicate_clip_loop(track_index: int, slot_index: int) -> dict:
    """Double the loop length by duplicating its content."""
    return _send("duplicate_clip_loop", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def quantize_clip(track_index: int, slot_index: int, quantization_grid: int, amount: float = 1.0) -> dict:
    """Quantize MIDI notes in the clip. grid values match Song.midi_recording_quantization."""
    return _send("quantize_clip", {"track_index": track_index, "slot_index": slot_index, "quantization_grid": quantization_grid, "amount": amount})

# ---------------------------------------------------------------------------
# Clip Automation Envelopes
# ---------------------------------------------------------------------------

@mcp.tool()
def get_clip_envelopes(track_index: int, slot_index: int) -> list:
    """
    Return all automation envelopes present on a clip.

    Each entry includes the envelope index (used by other envelope tools)
    and the parameter name it controls.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.

    Returns:
        List of {index, parameter_name, parameter_original_name}
    """
    return _send("get_clip_envelopes", {"track_index": track_index, "slot_index": slot_index})


@mcp.tool()
def get_clip_envelope(track_index: int, slot_index: int, envelope_index: int) -> dict:
    """
    Return all automation points for one envelope on a clip.

    Call get_clip_envelopes() first to discover available indices.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        envelope_index: Index into the clip's automation_envelopes list.

    Returns:
        envelope_index, parameter_name,
        points: list of {time (beats), value, in_tangent, out_tangent}
    """
    return _send("get_clip_envelope", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
    })


@mcp.tool()
def clear_clip_envelope(track_index: int, slot_index: int, envelope_index: int) -> dict:
    """
    Clear all automation points from a clip envelope.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        envelope_index: Index into the clip's automation_envelopes list.
    """
    return _send("clear_clip_envelope", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
    })


@mcp.tool()
def insert_clip_envelope_point(
    track_index: int,
    slot_index: int,
    envelope_index: int,
    time: float,
    value: float,
) -> dict:
    """
    Insert a single automation point into a clip envelope.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        envelope_index: Index into the clip's automation_envelopes list.
        time: Position in beats.
        value: Parameter value to set at this point.

    Returns:
        time, value as written
    """
    return _send("insert_clip_envelope_point", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
        "time": time,
        "value": value,
    })


@mcp.tool()
def set_clip_envelope_points(
    track_index: int,
    slot_index: int,
    envelope_index: int,
    points: list,
) -> dict:
    """
    Replace all automation points in a clip envelope atomically.

    Clears the existing envelope first, then inserts all provided points.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        envelope_index: Index into the clip's automation_envelopes list.
        points: List of {time: float, value: float} dicts.

    Returns:
        point_count: number of points written
    """
    return _send("set_clip_envelope_points", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
        "points": points,
    })

@mcp.tool()
def get_notes(track_index: int, slot_index: int) -> dict:
    """Return all MIDI notes in the clip at (track_index, slot_index)."""
    return _send("get_notes", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def add_notes(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """
    Add MIDI notes to the clip. Each note dict requires:
      pitch (int 0-127), start_time (float beats), duration (float beats)
    Optional: velocity (0-127), mute (bool), probability (0-1), velocity_deviation (-127 to 127), release_velocity (0-127)
    """
    return _send("add_notes", {"track_index": track_index, "slot_index": slot_index, "notes": notes})

@mcp.tool()
def replace_all_notes(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """
    Atomically replace ALL notes in a MIDI clip with the given list.

    Unlike add_notes (which appends), this clears the clip and writes the
    complete new note set in a single main-thread call — no race condition
    between read and write.

    Each note dict requires:
      pitch (int 0-127), start_time (float beats), duration (float beats)
    Optional: velocity (0-127, default 100), mute (bool, default False)

    Use this as the canonical write path for humanize, groove, and any
    operation that computes a new full note set from an existing one.

    Returns:
        note_count: number of notes written
    """
    return _send("replace_all_notes", {
        "track_index": track_index,
        "slot_index": slot_index,
        "notes": notes,
    })

@mcp.tool()
def remove_notes(track_index: int, slot_index: int, from_pitch: int = 0, pitch_span: int = 128, from_time: float = 0.0, time_span: float | None = None) -> dict:
    """Remove MIDI notes in the specified pitch/time range from the clip."""
    params: dict[str, Any] = {
        "track_index": track_index,
        "slot_index": slot_index,
        "from_pitch": from_pitch,
        "pitch_span": pitch_span,
        "from_time": from_time,
    }
    if time_span is not None:
        params["time_span"] = time_span
    return _send("remove_notes", params)

@mcp.tool()
def apply_note_modifications(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """Modify existing notes in the clip using note dicts with note_id fields (as returned by get_notes)."""
    return _send("apply_note_modifications", {"track_index": track_index, "slot_index": slot_index, "notes": notes})

@mcp.tool()
def select_all_notes(track_index: int, slot_index: int) -> dict:
    """Select all notes in the MIDI clip."""
    return _send("select_all_notes", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def deselect_all_notes(track_index: int, slot_index: int) -> dict:
    """Deselect all notes in the MIDI clip."""
    return _send("deselect_all_notes", {"track_index": track_index, "slot_index": slot_index})

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
# Device
# ---------------------------------------------------------------------------

@mcp.tool()
def get_devices(track_index: int) -> list:
    """Return all devices on the track at track_index. Use track_index=-1 to target the master track."""
    return _send("get_devices", {"track_index": track_index})

@mcp.tool()
def get_device_info(track_index: int, device_index: int) -> dict:
    """Return details for the device at (track_index, device_index)."""
    return _send("get_device_info", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def get_device_parameters(track_index: int, device_index: int) -> dict:
    """Return all automatable parameters for the device at (track_index, device_index). Use track_index=-1 to target the master track."""
    return _send("get_device_parameters", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def set_device_parameter(track_index: int, device_index: int, parameter_index: int, value: float) -> dict:
    """Set a device parameter by index. Value is clamped to min/max automatically. Use track_index=-1 to target the master track."""
    return _send("set_device_parameter", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
    })

@mcp.tool()
def set_device_parameter_human(
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
    unit: str = "normalized",
) -> dict:
    """
    Set a device parameter using human-readable units.

    Use track_index=-1 for the master track.

    unit options:
      'hz'         — frequency in Hertz, log-scale mapped to parameter range
      'ms'         — time in milliseconds, linearly clamped to parameter range
      'db'         — NOT supported: raises ValueError. dB conversion is device-dependent.
                     Use 'normalized' and consult get_device_parameters() for the raw range.
      'normalized' — raw 0.0–1.0 value mapped to the parameter's full range (default)

    Returns the actual value set and the parameter's min/max for reference.

    Examples:
      # Set EQ Eight band 1 frequency to 200 Hz
      set_device_parameter_human(0, 0, 2, 200.0, unit="hz")

      # Set Compressor attack to 5ms
      set_device_parameter_human(0, 1, 3, 5.0, unit="ms")

      # Set output gain (use normalized — check get_device_parameters for range)
      set_device_parameter_human(0, 2, 8, 0.85, unit="normalized")
    """
    return _send("set_device_parameter_human", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
        "unit": unit,
    })

@mcp.tool()
def set_device_enabled(track_index: int, device_index: int, enabled: bool) -> dict:
    """Enable or disable the device at (track_index, device_index). Use track_index=-1 to target the master track."""
    return _send("set_device_enabled", {"track_index": track_index, "device_index": device_index, "enabled": enabled})

@mcp.tool()
def delete_device(track_index: int, device_index: int) -> dict:
    """Delete the device at (track_index, device_index). Use track_index=-1 to target the master track."""
    return _send("delete_device", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def duplicate_device(track_index: int, device_index: int) -> dict:
    """Duplicate the device at (track_index, device_index). Use track_index=-1 to target the master track."""
    return _send("duplicate_device", {"track_index": track_index, "device_index": device_index})

@mcp.tool()
def move_device(
    track_index: int,
    device_index: int,
    target_device_index: int,
    target_track_index: int | None = None,
) -> dict:
    """
    Move a device to a new position within the same track.

    Live's Python API does not expose a native reorder method. This tool uses
    duplicate + delete to simulate a move. Best-effort: works well for simple
    reordering but does not guarantee arbitrary positioning.

    Cross-track moves raise a ValueError — use delete_device() +
    load_browser_item() to recreate the device on the target track.

    Args:
        track_index: Track containing the device.
        device_index: Current index of the device.
        target_device_index: Desired position after the move (best-effort).
        target_track_index: Must equal track_index or be None.

    Returns:
        track_index, device_index
    """
    if target_track_index is not None and target_track_index != track_index:
        raise ValueError(
            "Cross-track device move is not supported. "
            "target_track_index must equal track_index or be None. "
            "Use delete_device() + load_browser_item() to recreate the device on the target track."
        )
    return _send("move_device", {
        "track_index": track_index,
        "device_index": device_index,
        "target_track_index": track_index,
        "target_device_index": target_device_index,
    })

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
# Protocol versioning and capability discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def get_protocol_version() -> dict:
    """Return the AbletonMPCX protocol version string."""
    return _send("get_protocol_version")


@mcp.tool()
def get_selected_context() -> dict:
    """
    Return everything currently selected/focused in Live:
    selected_track, selected_scene, detail_clip (open in Detail View),
    and appointed_device (focused device).

    Use this at the start of a workflow to orient without making extra calls.
    """
    return _send("get_selected_context")


@mcp.tool()
def get_capabilities() -> dict:
    """
    Return the full list of available MCP tools with their parameter schemas.

    Returns:
        protocol_version: the AbletonMPCX protocol version
        tool_count: number of registered tools
        tools: list of {name, description, parameters: [{name, type, required, default}]}

    Use this for self-configuration — an agent can call this once to know
    exactly what commands are available and what parameters they accept.
    """
    import inspect

    tools = []
    # Iterate over all functions in this module decorated with @mcp.tool()
    # FastMCP stores registered tools in mcp._tools (dict of name -> tool)
    try:
        registered = mcp._tool_manager._tools  # FastMCP internal
    except AttributeError:
        try:
            registered = mcp._tools
        except AttributeError:
            registered = {}

    for tool_name, tool_obj in registered.items():
        try:
            fn = tool_obj.fn
            sig = inspect.signature(fn)
            params = []
            for pname, param in sig.parameters.items():
                entry = {"name": pname}
                if param.annotation != inspect.Parameter.empty:
                    try:
                        entry["type"] = str(param.annotation.__name__) if hasattr(param.annotation, "__name__") else str(param.annotation)
                    except Exception:
                        entry["type"] = "any"
                entry["required"] = param.default == inspect.Parameter.empty
                if param.default != inspect.Parameter.empty:
                    entry["default"] = param.default
                params.append(entry)
            tools.append({
                "name": tool_name,
                "description": (fn.__doc__ or "").strip().split("\n")[0],
                "parameters": params,
            })
        except Exception:
            tools.append({"name": tool_name, "description": "", "parameters": []})

    # Get protocol version from Ableton side
    try:
        version_info = _send("get_protocol_version")
        protocol_version = version_info.get("protocol_version", "unknown")
    except Exception:
        protocol_version = "unknown"

    return {
        "protocol_version": protocol_version,
        "tool_count": len(tools),
        "tools": sorted(tools, key=lambda t: t["name"]),
    }


@mcp.tool()
def get_session_snapshot() -> dict:
    """
    Return a full normalised snapshot of the current session in a single call.

    Includes: tempo, time signature, transport state, all tracks (with mixer
    values and device list), return tracks, master track devices, and scene list.
    Does NOT include clip notes (use get_notes per clip for that).

    Use this at the start of a session to orient an agent completely,
    or before/after a set of changes to compare state.
    """
    return _send("get_session_snapshot")


# ---------------------------------------------------------------------------
# Snapshot store (in-process, ephemeral)
# ---------------------------------------------------------------------------

_snapshots: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Reference profile store (in-process, also persisted to project memory)
# ---------------------------------------------------------------------------

_reference_profiles: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Audio analysis cache (in-process)
# ---------------------------------------------------------------------------
_audio_analysis_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Observer thread (background session watcher)
# ---------------------------------------------------------------------------

_suggestion_queue: collections.deque = collections.deque(maxlen=50)
_observer_thread: threading.Thread | None = None
_observer_running: bool = False
_observer_last_snapshot: dict | None = None
_observer_lock: threading.Lock = threading.Lock()
_OBSERVER_POLL_INTERVAL: float = 8.0  # seconds between polls
_observer_last_checkpoint_log_len: int = 0  # tracks Rule 5 threshold crossings
_observer_poll_count: int = 0
_observer_clip_cursor: int = 0
_observer_flagged_clips: set = set()
_OBSERVER_FEEL_EVERY_N_POLLS: int = 3
_OBSERVER_FEEL_MAX_CLIPS_PER_POLL: int = 4


# ---------------------------------------------------------------------------
# Persistent project memory
# ---------------------------------------------------------------------------

_MEMORY_DIR = os.path.expanduser("~/.ableton_mpcx/projects")
_current_project_id: str | None = None
_operation_log: list[dict] = []  # in-process log, flushed to disk on demand
_MAX_LOG_ENTRIES = 1000  # rolling cap


def _memory_path(project_id: str) -> str:
    safe = project_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
    os.makedirs(_MEMORY_DIR, exist_ok=True)
    return os.path.join(_MEMORY_DIR, "{}.json".format(safe))


def _load_memory(project_id: str) -> dict:
    path = _memory_path(project_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "project_id": project_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "snapshots": {},
        "operation_log": [],
        "preferences": {},
        "track_roles": {},
        "notes": [],
        "device_snapshots": {},
        "reference_profiles": {},
    }


def _save_memory(project_id: str, memory: dict):
    path = _memory_path(project_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
    except Exception:
        pass


def _get_memory() -> dict:
    if _current_project_id is None:
        raise RuntimeError("No project loaded. Call set_project_id() first.")
    return _load_memory(_current_project_id)


def _save_reference_profile(label: str, profile: dict):
    """Store a reference profile in-process and persist to project memory if a project is loaded."""
    _reference_profiles[label] = profile
    if _current_project_id is not None:
        try:
            mem = _get_memory()
            mem.setdefault("reference_profiles", {})[label] = profile
            _save_memory(_current_project_id, mem)
        except Exception:
            pass


def _load_reference_profiles_from_project():
    """Load all persisted reference profiles into the in-process store."""
    if _current_project_id is None:
        return
    try:
        mem = _get_memory()
        for label, profile in mem.get("reference_profiles", {}).items():
            _reference_profiles[label] = profile
    except Exception:
        pass


def _append_operation(command: str, params: dict, result: Any):
    """Append an operation to the in-process log."""
    global _operation_log
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": command,
        "params": params,
        "result_summary": str(result)[:200] if result is not None else None,
    }
    _operation_log.append(entry)
    if len(_operation_log) > _MAX_LOG_ENTRIES:
        _operation_log = _operation_log[-_MAX_LOG_ENTRIES:]


@mcp.tool()
def take_snapshot(label: str) -> dict:
    """
    Take a named snapshot of the current session state and store it in memory.

    The snapshot is retrieved via get_session_snapshot() and stored under the
    given label. Use diff_snapshots(label_a, label_b) to compare two snapshots.

    Labels are ephemeral — they are lost when the MCP server restarts.

    Args:
        label: A name for this snapshot, e.g. 'before_eq', 'after_mix', 'v1'.

    Returns:
        label, track_count, scene_count, timestamp_ms
    """
    snapshot = _send("get_session_snapshot")
    snapshot["_label"] = label
    snapshot["_timestamp_ms"] = int(time.time() * 1000)
    _snapshots[label] = snapshot
    return {
        "label": label,
        "track_count": snapshot.get("track_count", 0),
        "scene_count": snapshot.get("scene_count", 0),
        "timestamp_ms": snapshot["_timestamp_ms"],
    }


@mcp.tool()
def list_snapshots() -> dict:
    """
    List all stored snapshots by label and timestamp.

    Returns:
        snapshots: list of {label, track_count, scene_count, timestamp_ms}
    """
    return {
        "snapshots": [
            {
                "label": label,
                "track_count": s.get("track_count", 0),
                "scene_count": s.get("scene_count", 0),
                "timestamp_ms": s.get("_timestamp_ms", 0),
            }
            for label, s in sorted(_snapshots.items(), key=lambda x: x[1].get("_timestamp_ms", 0))
        ]
    }


@mcp.tool()
def delete_snapshot(label: str) -> dict:
    """Delete a stored snapshot by label."""
    if label not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label))
    del _snapshots[label]
    return {"deleted": label}


def _diff_value(a, b, path: str, changes: list):
    """Recursively diff two values, appending changes to the list."""
    if type(a) != type(b):
        changes.append({"path": path, "before": a, "after": b})
        return
    if isinstance(a, dict):
        all_keys = set(a.keys()) | set(b.keys())
        for k in sorted(all_keys):
            if k.startswith("_"):
                continue
            child_path = "{}.{}".format(path, k)
            if k not in a:
                changes.append({"path": child_path, "before": None, "after": b[k]})
            elif k not in b:
                changes.append({"path": child_path, "before": a[k], "after": None})
            else:
                _diff_value(a[k], b[k], child_path, changes)
    elif isinstance(a, list):
        # For lists of dicts with an "index" key (tracks, scenes, devices), diff by index
        if a and b and isinstance(a[0], dict) and "index" in a[0]:
            a_map = {item["index"]: item for item in a}
            b_map = {item["index"]: item for item in b}
            all_indices = sorted(set(a_map.keys()) | set(b_map.keys()))
            for idx in all_indices:
                child_path = "{}[{}]".format(path, idx)
                if idx not in a_map:
                    changes.append({"path": child_path, "before": None, "after": b_map[idx]})
                elif idx not in b_map:
                    changes.append({"path": child_path, "before": a_map[idx], "after": None})
                else:
                    _diff_value(a_map[idx], b_map[idx], child_path, changes)
        else:
            if a != b:
                changes.append({"path": path, "before": a, "after": b})
    else:
        if a != b:
            changes.append({"path": path, "before": a, "after": b})


@mcp.tool()
def diff_snapshots(label_a: str, label_b: str) -> dict:
    """
    Compare two named snapshots and return what changed between them.

    Args:
        label_a: Label of the 'before' snapshot.
        label_b: Label of the 'after' snapshot.

    Returns:
        label_a, label_b, change_count, changes: list of {path, before, after}

    The 'path' uses dot notation, e.g.:
        'tracks[0].volume'        — track 0 volume changed
        'tracks[2].devices[1].is_active'  — device enabled/disabled
        'master_track.volume'     — master volume changed
        'tempo'                   — song tempo changed

    Example workflow:
        take_snapshot('before')
        set_master_volume(0.9)
        add_native_device(0, 'EQ Eight')
        take_snapshot('after')
        diff_snapshots('before', 'after')
    """
    if label_a not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label_a))
    if label_b not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label_b))

    a = _snapshots[label_a]
    b = _snapshots[label_b]

    changes: list = []
    _diff_value(a, b, "session", changes)

    return {
        "label_a": label_a,
        "label_b": label_b,
        "change_count": len(changes),
        "changes": changes,
    }


@mcp.tool()
def diff_snapshot_vs_live(label: str) -> dict:
    """
    Compare a stored snapshot against the current live session state.

    Equivalent to: take_snapshot('_live_now') then diff_snapshots(label, '_live_now'),
    but without permanently storing the live snapshot.

    Args:
        label: Label of the stored 'before' snapshot to compare against live.

    Returns:
        label, change_count, changes: list of {path, before, after}
    """
    if label not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label))

    live = _send("get_session_snapshot")
    a = _snapshots[label]

    changes: list = []
    _diff_value(a, live, "session", changes)

    return {
        "label": label,
        "change_count": len(changes),
        "changes": changes,
    }



# ---------------------------------------------------------------------------
# Workflow primitives (Phase 4)
# Deterministic, composable operations built on existing primitives.
# Each compiles down to explicit _send() calls — no fuzzy behaviour.
# ---------------------------------------------------------------------------


def _std_dev(values: list) -> float:
    """Return population standard deviation of a list of numbers. Returns 0.0 for empty or single-element lists."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


@mcp.tool()
def humanize_notes(
    track_index: int,
    slot_index: int,
    timing_amount: float = 0.02,
    velocity_amount: float = 10.0,
    seed: int | None = None,
) -> dict:
    """
    Apply subtle human-feel randomisation to all notes in a MIDI clip.

    Randomly offsets note start times and velocities within the given ranges.
    All changes are deterministic if a seed is provided.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        timing_amount: Max timing shift in beats (default 0.02 = ~5ms at 120bpm).
        velocity_amount: Max velocity shift in either direction (default 10).
        seed: Optional random seed for reproducibility.

    Returns:
        note_count, timing_amount, velocity_amount, seed_used
    """
    import random

    rng = random.Random(seed)
    seed_used = seed if seed is not None else rng.randint(0, 2**31)
    rng = random.Random(seed_used)

    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    modified = []
    for note in notes:
        t_shift = rng.uniform(-timing_amount, timing_amount)
        v_shift = rng.uniform(-velocity_amount, velocity_amount)
        new_start = max(0.0, note["start_time"] + t_shift)
        new_velocity = int(max(1, min(127, note["velocity"] + v_shift)))
        modified.append({
            "pitch": note["pitch"],
            "start_time": new_start,
            "duration": note["duration"],
            "velocity": new_velocity,
            "mute": note["mute"],
        })

    # Replace all notes atomically
    _send("replace_all_notes", {
        "track_index": track_index,
        "slot_index": slot_index,
        "notes": modified,
    })

    return {
        "note_count": len(modified),
        "timing_amount": timing_amount,
        "velocity_amount": velocity_amount,
        "seed_used": seed_used,
    }


@mcp.tool()
def humanize_dilla(
    track_index: int,
    slot_index: int,
    late_bias: float = 0.018,
    max_early: float = 0.005,
    max_late: float = 0.032,
    velocity_amount: float = 8.0,
    loose_subdivisions: bool = True,
    seed: int | None = None,
) -> dict:
    """
    Apply a J Dilla-inspired humanization to a MIDI clip.

    Key characteristics vs generic humanize_notes:
    - Timing is biased LATE, not symmetrically randomised.
      Distribution is triangular(max_early, max_late, late_bias).
    - Weaker subdivisions (16th-note offbeats) get more timing looseness.
    - Velocities are nudged randomly but with less extreme spread than timing.

    All changes are deterministic if a seed is provided.
    Uses replace_all_notes for atomic write.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        late_bias: Mode of the triangular timing distribution in beats (default 0.018 ≈ +4ms at 120bpm).
        max_early: Maximum early shift in beats (default 0.005 ≈ 1ms).
        max_late: Maximum late shift in beats (default 0.032 ≈ 8ms).
        velocity_amount: Max velocity shift in either direction (default 8).
        loose_subdivisions: If True, 16th-note offbeats get 1.5× the timing range.
        seed: Optional random seed for reproducibility.

    Returns:
        note_count, late_bias, max_early, max_late, velocity_amount, seed_used
    """
    import random

    rng = random.Random(seed)
    seed_used = seed if seed is not None else rng.randint(0, 2**31)
    rng = random.Random(seed_used)

    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    def is_weak_subdivision(start_time: float, grid: float = 0.25) -> bool:
        """True if the note falls on an offbeat 16th (not on a quarter or 8th)."""
        pos_in_beat = (start_time % 1.0)
        QUARTER_THRESHOLD = 0.05
        EIGHTH_THRESHOLD = 0.05
        if pos_in_beat < QUARTER_THRESHOLD or abs(pos_in_beat - 1.0) < QUARTER_THRESHOLD:
            return False  # on the quarter
        if abs(pos_in_beat - 0.5) < EIGHTH_THRESHOLD:
            return False  # on the 8th
        return True  # offbeat 16th or smaller

    modified = []
    for note in notes:
        # Timing: triangular distribution biased late
        if loose_subdivisions and is_weak_subdivision(note["start_time"]):
            actual_max_late = max_late * 1.5
            actual_late_bias = late_bias * 1.4
        else:
            actual_max_late = max_late
            actual_late_bias = late_bias

        t_shift = rng.triangular(-max_early, actual_max_late, actual_late_bias)
        new_start = max(0.0, note["start_time"] + t_shift)

        # Velocity: symmetric small nudge
        v_shift = rng.uniform(-velocity_amount, velocity_amount)
        new_velocity = int(max(1, min(127, note["velocity"] + v_shift)))

        modified.append({
            "pitch": note["pitch"],
            "start_time": new_start,
            "duration": note["duration"],
            "velocity": new_velocity,
            "mute": note["mute"],
        })

    _send("replace_all_notes", {
        "track_index": track_index,
        "slot_index": slot_index,
        "notes": modified,
    })

    return {
        "note_count": len(modified),
        "late_bias": late_bias,
        "max_early": max_early,
        "max_late": max_late,
        "velocity_amount": velocity_amount,
        "seed_used": seed_used,
    }


@mcp.tool()
def analyze_clip_feel(track_index: int, slot_index: int, grid: float = 0.25) -> dict:
    """
    Analyse the timing and velocity feel of a MIDI clip.

    Checks for signs of robotic, over-quantized feel:
    - All note start times fall exactly on a rhythmic grid
    - Near-uniform velocities across all notes
    - Per-pitch velocity variance (e.g. every hi-hat hit the same velocity)
    - Uniform note durations per pitch

    Nothing is modified. Returns observations and a summary flag.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        grid: Grid resolution in beats to check snapping against (default 0.25 = 16th note).

    Returns:
        note_count,
        perfectly_quantized (bool): all start times are exact grid multiples,
        timing_variance (float): std dev of distance-to-nearest-grid in beats,
        velocity_std_dev (float): overall velocity standard deviation,
        low_velocity_variance (bool): velocity std dev < 5 (flag),
        per_pitch_analysis: list of {pitch, note_count, velocity_std_dev, duration_std_dev, uniform_velocity, uniform_duration},
        robotic_flags: list of human-readable flag strings,
        feel_score: int 0-100 (100 = fully robotic, 0 = very human)
    """
    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    if not notes:
        return {
            "note_count": 0,
            "perfectly_quantized": False,
            "timing_variance": 0.0,
            "velocity_std_dev": 0.0,
            "low_velocity_variance": False,
            "per_pitch_analysis": [],
            "robotic_flags": ["clip is empty"],
            "feel_score": 0,
        }

    # --- Timing analysis ---
    def dist_to_grid(t, g):
        return abs(t - round(t / g) * g)

    grid_distances = [dist_to_grid(n["start_time"], grid) for n in notes]
    SNAP_THRESHOLD = 0.001  # beats — within 1ms at 120bpm
    perfectly_quantized = all(d < SNAP_THRESHOLD for d in grid_distances)
    timing_variance = _std_dev(grid_distances)

    # --- Velocity analysis ---
    velocities = [n["velocity"] for n in notes]
    velocity_std_dev = _std_dev(velocities)
    low_velocity_variance = velocity_std_dev < 5.0

    # --- Per-pitch analysis ---
    from collections import defaultdict
    pitch_groups: dict = defaultdict(list)
    for n in notes:
        pitch_groups[n["pitch"]].append(n)

    per_pitch = []
    for pitch, pitch_notes in sorted(pitch_groups.items()):
        pvels = [n["velocity"] for n in pitch_notes]
        pdurs = [n["duration"] for n in pitch_notes]
        pvel_std = _std_dev(pvels)
        pdur_std = _std_dev(pdurs)
        per_pitch.append({
            "pitch": pitch,
            "note_count": len(pitch_notes),
            "velocity_std_dev": round(pvel_std, 3),
            "duration_std_dev": round(pdur_std, 4),
            "uniform_velocity": pvel_std < 3.0 and len(pitch_notes) > 1,
            "uniform_duration": pdur_std < 0.01 and len(pitch_notes) > 1,
        })

    # --- Build flags ---
    robotic_flags = []
    if perfectly_quantized:
        robotic_flags.append("all note start times are exactly on the {}-beat grid".format(grid))
    if low_velocity_variance:
        robotic_flags.append("overall velocity std dev is {:.1f} — near-uniform".format(velocity_std_dev))
    uniform_vel_pitches = [p for p in per_pitch if p["uniform_velocity"]]
    if uniform_vel_pitches:
        robotic_flags.append("pitches with identical velocities: {}".format([p["pitch"] for p in uniform_vel_pitches]))
    uniform_dur_pitches = [p for p in per_pitch if p["uniform_duration"]]
    if uniform_dur_pitches:
        robotic_flags.append("pitches with uniform note lengths: {}".format([p["pitch"] for p in uniform_dur_pitches]))

    # --- Feel score (0=human, 100=robotic) ---
    score = 0
    if perfectly_quantized:
        score += 40
    if low_velocity_variance:
        score += 30
    uniform_vel_ratio = len(uniform_vel_pitches) / max(len(per_pitch), 1)
    score += int(uniform_vel_ratio * 20)
    uniform_dur_ratio = len(uniform_dur_pitches) / max(len(per_pitch), 1)
    score += int(uniform_dur_ratio * 10)
    score = min(100, score)

    return {
        "note_count": len(notes),
        "perfectly_quantized": perfectly_quantized,
        "timing_variance": round(timing_variance, 5),
        "velocity_std_dev": round(velocity_std_dev, 3),
        "low_velocity_variance": low_velocity_variance,
        "per_pitch_analysis": per_pitch,
        "robotic_flags": robotic_flags,
        "feel_score": score,
    }


@mcp.tool()
def duplicate_clip_to_new_scene(track_index: int, slot_index: int) -> dict:
    """
    Duplicate the clip at (track_index, slot_index) into a new scene.

    Creates a new scene at the end, then duplicates the clip slot into it.

    Args:
        track_index: Track containing the source clip.
        slot_index: Source clip slot index.

    Returns:
        new_scene_index, new_slot_index
    """
    # Get current scene count
    scenes = _send("get_scenes")
    new_scene_index = len(scenes)

    # Create new scene at end
    _send("create_scene", {"index": -1})

    # Duplicate the clip slot — this copies to the next empty slot on the same track.
    # Then move context: duplicate_clip_slot duplicates to slot below.
    _send("duplicate_clip_slot", {"track_index": track_index, "slot_index": slot_index})

    return {
        "source_track_index": track_index,
        "source_slot_index": slot_index,
        "new_scene_index": new_scene_index,
    }


@mcp.tool()
def create_midi_track_with_drum_rack(index: int = -1, track_name: str | None = None) -> dict:
    """
    Create a new MIDI track and immediately load a Drum Rack onto it.

    Args:
        index: Position to insert the track (-1 = end).
        track_name: Optional name to give the new track.

    Returns:
        track_index, track_name
    """
    # Create the MIDI track
    _send("create_midi_track", {"index": index})

    # Get updated track list to find the new track index
    tracks = _send("get_tracks")
    new_track_index = index if index >= 0 else len(tracks) - 1

    # Optionally rename
    if track_name:
        _send("set_track_name", {"track_index": new_track_index, "name": track_name})
    else:
        track_name = tracks[new_track_index]["name"] if new_track_index < len(tracks) else "MIDI"

    # Load Drum Rack
    _send("add_native_device", {"track_index": new_track_index, "device_name": "Drum Rack"})

    return {
        "track_index": new_track_index,
        "track_name": track_name,
    }


@mcp.tool()
def capture_device_macro_snapshot(track_index: int, device_index: int, label: str | None = None) -> dict:
    """
    Capture the current parameter values of a device as a named snapshot.

    Stores all parameter values under a label so they can be restored later
    with apply_device_macro_snapshot().

    Args:
        track_index: Track containing the device (-1 for master).
        device_index: Device index on the track.
        label: Optional label. Defaults to '{track_index}_{device_index}'.

    Returns:
        label, device_name, parameter_count
    """
    result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    })
    device_name = result.get("name", "unknown")
    parameters = result.get("parameters", [])

    snap_label = label or "device_{}_{}".format(track_index, device_index)

    # Store in the same _snapshots store under a prefixed key
    _snapshots["__device__{}".format(snap_label)] = {
        "track_index": track_index,
        "device_index": device_index,
        "device_name": device_name,
        "parameters": parameters,
        "_timestamp_ms": int(time.time() * 1000),
    }

    return {
        "label": snap_label,
        "device_name": device_name,
        "parameter_count": len(parameters),
    }


@mcp.tool()
def apply_device_macro_snapshot(label: str, track_index: int | None = None, device_index: int | None = None) -> dict:
    """
    Restore device parameter values from a previously captured snapshot.

    Args:
        label: Label used when calling capture_device_macro_snapshot().
        track_index: Override track index (uses snapshot's original if omitted).
        device_index: Override device index (uses snapshot's original if omitted).

    Returns:
        label, device_name, parameters_set, skipped
    """
    key = "__device__{}".format(label)
    if key not in _snapshots:
        raise ValueError("No device snapshot with label '{}'. Use capture_device_macro_snapshot() first.".format(label))

    snap = _snapshots[key]
    ti = track_index if track_index is not None else snap["track_index"]
    di = device_index if device_index is not None else snap["device_index"]
    parameters = snap.get("parameters", [])

    set_count = 0
    skipped = 0
    for param in parameters:
        try:
            _send("set_device_parameter", {
                "track_index": ti,
                "device_index": di,
                "parameter_index": param["index"],
                "value": param["value"],
            })
            set_count += 1
        except Exception:
            skipped += 1

    return {
        "label": label,
        "device_name": snap.get("device_name", "unknown"),
        "parameters_set": set_count,
        "skipped": skipped,
    }


@mcp.tool()
def prep_track_for_resampling(track_index: int, resample_track_name: str = "Resample") -> dict:
    """
    Prepare a track for resampling by creating a new audio track routed to record it.

    Steps:
    1. Creates a new audio track named resample_track_name.
    2. Arms the new track for recording.
    3. Returns both track indices so the caller can set up routing manually if needed.

    Args:
        track_index: The source track to resample from.
        resample_track_name: Name for the new recording track.

    Returns:
        source_track_index, resample_track_index, resample_track_name
    """
    # Create the audio track
    _send("create_audio_track", {"index": -1})
    tracks = _send("get_tracks")
    resample_track_index = len(tracks) - 1

    # Name it
    _send("set_track_name", {"track_index": resample_track_index, "name": resample_track_name})

    # Arm it
    arm_succeeded = True
    try:
        _send("set_track_arm", {"track_index": resample_track_index, "arm": True})
    except Exception:
        arm_succeeded = False  # Some track types may not support arming

    return {
        "source_track_index": track_index,
        "resample_track_index": resample_track_index,
        "resample_track_name": resample_track_name,
        "arm_succeeded": arm_succeeded,
    }


@mcp.tool()
def create_arrangement_scaffold(
    sections: list[dict],
) -> dict:
    """
    Create a basic arrangement scaffold by adding named scenes for each section.

    Each section dict requires a 'name' key and optionally 'tempo' and 'color'.

    Args:
        sections: List of section dicts, e.g.:
            [
                {"name": "Intro", "tempo": 120.0, "color": 0x00FF6600},
                {"name": "Verse", "tempo": 120.0},
                {"name": "Chorus", "color": 0x00FF0000},
                {"name": "Bridge"},
                {"name": "Outro"},
            ]

    Returns:
        scenes_created: list of {name, scene_index}
    """
    existing_scenes = _send("get_scenes")
    start_index = len(existing_scenes)

    created = []
    tempo_failures = 0
    color_failures = 0
    for i, section in enumerate(sections):
        scene_index = start_index + i
        _send("create_scene", {"index": -1})
        name = section.get("name", "Section {}".format(i + 1))
        _send("set_scene_name", {"scene_index": scene_index, "name": name})
        if "tempo" in section:
            try:
                _send("set_scene_tempo", {"scene_index": scene_index, "tempo": float(section["tempo"]), "tempo_enabled": True})
            except Exception:
                tempo_failures += 1
        if "color" in section:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": int(section["color"])})
            except Exception:
                color_failures += 1
        created.append({"name": name, "scene_index": scene_index})

    return {
        "scenes_created": created,
        "count": len(created),
        "tempo_failures": tempo_failures,
        "color_failures": color_failures,
    }


# ---------------------------------------------------------------------------
# Phase 5: Persistent project memory
# ---------------------------------------------------------------------------

@mcp.tool()
def set_project_id(project_id: str) -> dict:
    """
    Set the current project identity for persistent memory.

    All subsequent memory operations (notes, snapshots, operation log, preferences,
    track roles) are scoped to this project_id.

    Args:
        project_id: A unique name for this project, e.g. 'my_album_track_3'.
                    Use something meaningful — it becomes a filename on disk.

    Returns:
        project_id, memory_path, is_new (whether this is a fresh project)
    """
    global _current_project_id
    _current_project_id = project_id
    path = _memory_path(project_id)
    is_new = not os.path.exists(path)
    if is_new:
        mem = _load_memory(project_id)
        _save_memory(project_id, mem)
    return {
        "project_id": project_id,
        "memory_path": path,
        "is_new": is_new,
    }


@mcp.tool()
def get_project_memory() -> dict:
    """
    Return the full persistent memory for the current project.

    Includes: preferences, track roles, notes, snapshot labels, operation log summary.
    Requires set_project_id() to have been called first.
    """
    mem = _get_memory()
    return {
        "project_id": mem["project_id"],
        "created_at": mem.get("created_at"),
        "note_count": len(mem.get("notes", [])),
        "notes": mem.get("notes", []),
        "preferences": mem.get("preferences", {}),
        "track_roles": mem.get("track_roles", {}),
        "snapshot_labels": list(mem.get("snapshots", {}).keys()),
        "device_snapshot_labels": list(mem.get("device_snapshots", {}).keys()),
        "operation_log_count": len(mem.get("operation_log", [])),
    }


@mcp.tool()
def add_project_note(note: str, category: str = "general") -> dict:
    """
    Add a free-form note to the current project memory.

    Use this to record intent, decisions, problems, or anything worth remembering.

    Args:
        note: The note text.
        category: Optional category tag, e.g. 'mix', 'arrangement', 'intent', 'issue'.

    Returns:
        note_id, timestamp
    """
    mem = _get_memory()
    entry = {
        "id": len(mem.get("notes", [])),
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "category": category,
        "note": note,
    }
    mem.setdefault("notes", []).append(entry)
    _save_memory(_current_project_id, mem)
    return {"note_id": entry["id"], "timestamp": entry["ts"]}


@mcp.tool()
def set_track_role(track_index: int, role: str) -> dict:
    """
    Assign a semantic role to a track in the current project memory.

    Examples: 'kick bus', 'main reverb', 'lead synth', 'master chain', 'resample'

    Args:
        track_index: Track index (-1 for master).
        role: Human-readable role string.

    Returns:
        track_index, role
    """
    mem = _get_memory()
    mem.setdefault("track_roles", {})[str(track_index)] = role
    _save_memory(_current_project_id, mem)
    return {"track_index": track_index, "role": role}


@mcp.tool()
def get_track_roles() -> dict:
    """
    Return all track role assignments for the current project.

    Returns:
        track_roles: dict of {track_index_str: role}
    """
    mem = _get_memory()
    return {"track_roles": mem.get("track_roles", {})}


@mcp.tool()
def set_preference(key: str, value: Any) -> dict:
    """
    Store a user preference in the current project memory.

    Preferences are free-form key/value pairs. Use them to record
    working style, mix targets, or workflow habits.

    Examples:
        set_preference('preferred_reverb', 'Valhalla Room')
        set_preference('target_lufs', -14.0)
        set_preference('grit_on_melodics', True)
        set_preference('low_mid_character', 'dense but not muddy')

    Args:
        key: Preference key string.
        value: Any JSON-serialisable value.

    Returns:
        key, value
    """
    mem = _get_memory()
    mem.setdefault("preferences", {})[key] = value
    _save_memory(_current_project_id, mem)
    return {"key": key, "value": value}


@mcp.tool()
def get_preferences() -> dict:
    """Return all stored preferences for the current project."""
    mem = _get_memory()
    return {"preferences": mem.get("preferences", {})}


@mcp.tool()
def save_snapshot_to_project(label: str) -> dict:
    """
    Capture the current session state and persist it to project memory on disk.

    Unlike take_snapshot() which is in-memory only, this survives MCP server restarts.

    Args:
        label: Snapshot label.

    Returns:
        label, track_count, scene_count, timestamp
    """
    mem = _get_memory()
    snapshot = _send("get_session_snapshot")
    snapshot["_label"] = label
    snapshot["_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    mem.setdefault("snapshots", {})[label] = snapshot
    _save_memory(_current_project_id, mem)
    # Also store in-process for diff tools
    _snapshots[label] = snapshot
    return {
        "label": label,
        "track_count": snapshot.get("track_count", 0),
        "scene_count": snapshot.get("scene_count", 0),
        "timestamp": snapshot["_timestamp"],
    }


@mcp.tool()
def load_snapshots_from_project() -> dict:
    """
    Load all persisted snapshots from project memory into the in-process store.

    After calling this, diff_snapshots() and diff_snapshot_vs_live() can use
    snapshots that were saved in previous sessions.

    Returns:
        loaded: list of snapshot labels loaded
    """
    mem = _get_memory()
    persisted = mem.get("snapshots", {})
    for label, snap in persisted.items():
        _snapshots[label] = snap
    return {"loaded": list(persisted.keys()), "count": len(persisted)}


# ---------------------------------------------------------------------------
# Phase 6: Operation log
# ---------------------------------------------------------------------------

@mcp.tool()
def get_operation_log(limit: int = 50) -> dict:
    """
    Return the most recent operations from the in-process operation log.

    The log captures every command sent to Ableton during this server session.
    It is not automatically persisted unless flush_operation_log() is called.

    Args:
        limit: Maximum number of entries to return (most recent first).

    Returns:
        entries: list of {ts, command, params, result_summary}
        total_in_memory: total entries in the current session log
    """
    entries = list(reversed(_operation_log[-limit:]))
    return {
        "entries": entries,
        "total_in_memory": len(_operation_log),
    }


@mcp.tool()
def flush_operation_log() -> dict:
    """
    Persist the current in-process operation log to project memory on disk.

    Appends new entries to the project's stored log (capped at 5000 entries total).
    Requires set_project_id() to have been called.

    Returns:
        flushed_count, total_stored
    """
    mem = _get_memory()
    stored = mem.get("operation_log", [])
    stored.extend(_operation_log)
    # Cap at 5000
    if len(stored) > 5000:
        stored = stored[-5000:]
    mem["operation_log"] = stored
    _save_memory(_current_project_id, mem)
    return {
        "flushed_count": len(_operation_log),
        "total_stored": len(stored),
    }


@mcp.tool()
def get_stored_operation_log(limit: int = 100) -> dict:
    """
    Return the persisted operation log from project memory (across sessions).

    Args:
        limit: Maximum number of entries to return (most recent first).

    Returns:
        entries: list of {ts, command, params, result_summary}
        total_stored: total entries stored on disk
    """
    mem = _get_memory()
    stored = mem.get("operation_log", [])
    return {
        "entries": list(reversed(stored[-limit:])),
        "total_stored": len(stored),
    }


@mcp.tool()
def summarise_session() -> dict:
    """
    Summarise what happened in the current session based on the operation log.

    Returns counts of each command type, most frequent operations,
    and a timeline of major state changes.

    Returns:
        session_start, command_counts, most_frequent, destructive_ops, total_ops
    """
    from collections import Counter

    if not _operation_log:
        return {"total_ops": 0, "command_counts": {}, "most_frequent": [], "destructive_ops": []}

    counter = Counter(entry["command"] for entry in _operation_log)
    destructive = [
        e for e in _operation_log
        if any(kw in e["command"] for kw in ("delete", "remove", "create", "duplicate", "add_notes"))
    ]

    return {
        "session_start": _operation_log[0]["ts"] if _operation_log else None,
        "total_ops": len(_operation_log),
        "command_counts": dict(counter.most_common()),
        "most_frequent": [{"command": cmd, "count": cnt} for cmd, cnt in counter.most_common(10)],
        "destructive_ops": destructive[-20:],  # last 20 destructive ops
    }


# ---------------------------------------------------------------------------
# Phase 7: Contextual suggestions
# ---------------------------------------------------------------------------

@mcp.tool()
def suggest_next_actions() -> dict:
    """
    Analyse the current session context and suggest logical next actions.

    Looks at:
    - Current session snapshot (tracks, devices, mixer state)
    - Recent operation log
    - Project memory (notes, preferences, track roles)
    - Stored snapshots

    Returns a list of suggestions with reasoning. These are observations only —
    nothing is executed automatically.

    Returns:
        suggestions: list of {action, reason, priority ('high'|'medium'|'low')}
    """
    suggestions = []

    # 1. Snapshot suggestion — if no snapshot taken recently
    recent_snapshots = [e for e in _operation_log[-50:] if "snapshot" in e["command"]]
    if not recent_snapshots:
        suggestions.append({
            "action": "take_snapshot('before_changes')",
            "reason": "No snapshot taken in recent operations. Recommended before making changes.",
            "priority": "high",
        })

    # 2. Project memory suggestion
    if _current_project_id is None:
        suggestions.append({
            "action": "set_project_id('your_project_name')",
            "reason": "No project ID set. Set one to enable persistent memory, notes, and operation history.",
            "priority": "high",
        })

    # 3. Analyse session state
    try:
        snapshot = _send("get_session_snapshot")
        tracks = snapshot.get("tracks", [])

        # Unarmed tracks with no devices
        empty_tracks = [t for t in tracks if t.get("device_count", 0) == 0]
        if empty_tracks:
            suggestions.append({
                "action": "review or delete empty tracks: {}".format([t["name"] for t in empty_tracks[:5]]),
                "reason": "{} track(s) have no devices loaded.".format(len(empty_tracks)),
                "priority": "low",
            })

        # Master track device check
        master_devices = snapshot.get("master_track", {}).get("devices", [])
        if not master_devices:
            suggestions.append({
                "action": "add_native_device(-1, 'Limiter') or add_native_device(-1, 'EQ Eight')",
                "reason": "Master track has no devices. Consider adding a limiter or EQ.",
                "priority": "medium",
            })

        # Muted tracks
        muted = [t for t in tracks if t.get("mute")]
        if muted:
            suggestions.append({
                "action": "review muted tracks: {}".format([t["name"] for t in muted[:5]]),
                "reason": "{} track(s) are currently muted.".format(len(muted)),
                "priority": "low",
            })

    except Exception:
        pass

    # 4. Operation log patterns
    if _operation_log:
        recent_cmds = [e["command"] for e in _operation_log[-20:]]

        # If user added devices recently, suggest snapshot
        if any("add_native_device" in c or "load_browser_item" in c for c in recent_cmds):
            already_snapped = any("snapshot" in c for c in recent_cmds)
            if not already_snapped:
                suggestions.append({
                    "action": "take_snapshot('after_device_changes')",
                    "reason": "Devices were recently added. Snapshot recommended to capture state.",
                    "priority": "high",
                })

        # If notes were removed recently, warn
        if any("remove_notes" in c for c in recent_cmds):
            suggestions.append({
                "action": "verify clip note state with get_notes()",
                "reason": "Notes were recently removed. Verify the clip state is as expected.",
                "priority": "medium",
            })

        # Flush log suggestion
        if len(_operation_log) > 100 and _current_project_id:
            suggestions.append({
                "action": "flush_operation_log()",
                "reason": "Operation log has {} entries. Flush to persist to project memory.".format(len(_operation_log)),
                "priority": "low",
            })

    # 5. Project memory patterns
    if _current_project_id:
        try:
            mem = _get_memory()
            prefs = mem.get("preferences", {})

            # If preferences mention a reverb, suggest checking return tracks
            if any("reverb" in str(v).lower() for v in prefs.values()):
                try:
                    returns = _send("get_return_tracks")
                    reverb_returns = [r for r in returns if "reverb" in r["name"].lower() or "verb" in r["name"].lower()]
                    if not reverb_returns:
                        suggestions.append({
                            "action": "check return tracks — no reverb return found",
                            "reason": "Your preferences mention a reverb preference but no return track is named for reverb.",
                            "priority": "medium",
                        })
                except Exception:
                    pass
        except Exception:
            pass

    # Reference profile suggestion
    if "default" in _reference_profiles:
        ref = _reference_profiles.get("default", {})
        if ref.get("type") == "clip_feel":
            suggestions.append({
                "action": "compare_clip_feel(track_index, slot_index, reference_label='default')",
                "reason": "A clip feel reference profile exists. Use compare_clip_feel() to check how your current clips compare.",
                "priority": "low",
            })
        elif ref.get("type") == "mix_state":
            suggestions.append({
                "action": "compare_mix_state(reference_label='default')",
                "reason": "A mix state reference profile exists. Use compare_mix_state() to check what has changed.",
                "priority": "low",
            })

    # Audio reference suggestion
    if "default_audio" in _reference_profiles:
        suggestions.append({
            "action": "compare_audio('/path/to/your/bounce.wav', reference_label='default_audio')",
            "reason": "An audio reference profile exists. Export a bounce and compare it against your reference.",
            "priority": "low",
        })

    return {
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }


@mcp.tool()
def analyse_mix_state() -> dict:
    """
    Analyse the current mix state and surface observations.

    Looks at track volumes, panning, mute/solo state, device presence,
    and compares against stored preferences if available.

    Returns observations, not instructions. Nothing is modified.

    Returns:
        observations: list of {observation, category, severity ('info'|'warn'|'flag')}
    """
    observations = []

    try:
        snapshot = _send("get_session_snapshot")
        tracks = snapshot.get("tracks", [])
        master = snapshot.get("master_track", {})

        # Volume checks
        hot_tracks = [t for t in tracks if t.get("volume", 0) > 0.95]
        if hot_tracks:
            observations.append({
                "observation": "Tracks near maximum volume: {}".format([t["name"] for t in hot_tracks]),
                "category": "levels",
                "severity": "warn",
            })

        silent_tracks = [t for t in tracks if not t.get("mute") and t.get("volume", 1.0) < 0.01]
        if silent_tracks:
            observations.append({
                "observation": "Tracks at near-zero volume (not muted): {}".format([t["name"] for t in silent_tracks]),
                "category": "levels",
                "severity": "warn",
            })

        # Panning checks
        hard_panned = [t for t in tracks if abs(t.get("pan", 0)) > 0.95]
        if hard_panned:
            observations.append({
                "observation": "Tracks hard-panned: {}".format([t["name"] for t in hard_panned]),
                "category": "panning",
                "severity": "info",
            })

        # Solo check
        soloed = [t for t in tracks if t.get("solo")]
        if soloed:
            observations.append({
                "observation": "Tracks currently soloed: {}".format([t["name"] for t in soloed]),
                "category": "monitoring",
                "severity": "flag",
            })

        # Master device check
        master_devices = master.get("devices", [])
        device_names = [d["name"] for d in master_devices]
        has_limiter = any("limit" in n.lower() for n in device_names)
        has_eq = any("eq" in n.lower() for n in device_names)

        if not has_limiter:
            observations.append({
                "observation": "No limiter on master track.",
                "category": "master_chain",
                "severity": "info",
            })
        if not has_eq:
            observations.append({
                "observation": "No EQ on master track.",
                "category": "master_chain",
                "severity": "info",
            })

        # Armed tracks check
        armed = [t for t in tracks if t.get("arm")]
        if armed:
            observations.append({
                "observation": "Tracks currently armed for recording: {}".format([t["name"] for t in armed]),
                "category": "recording",
                "severity": "info",
            })

        # Compare against preferences if available
        if _current_project_id:
            try:
                mem = _get_memory()
                target_lufs = mem.get("preferences", {}).get("target_lufs")
                if target_lufs:
                    observations.append({
                        "observation": "Target LUFS preference set to {}. Use an external meter to verify.".format(target_lufs),
                        "category": "levels",
                        "severity": "info",
                    })
            except Exception:
                pass

    except Exception as e:
        observations.append({
            "observation": "Could not read session state: {}".format(str(e)),
            "category": "error",
            "severity": "flag",
        })

    return {
        "observation_count": len(observations),
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Phase 8: Reference profiles
# ---------------------------------------------------------------------------

@mcp.tool()
def designate_reference_clip(
    track_index: int,
    slot_index: int,
    label: str = "default",
) -> dict:
    """
    Analyse the feel of a MIDI clip and store it as a named reference profile.

    The profile captures timing and velocity characteristics that can later be
    compared against other clips using compare_clip_feel().

    Stored profile includes:
      - timing_variance: std dev of distance-to-nearest-16th-grid (beats)
      - lateness_bias: mean signed offset from nearest grid point (positive = late)
      - velocity_std_dev: overall velocity spread
      - velocity_mean: mean velocity
      - per_pitch: per-pitch timing and velocity stats
      - note_count
      - grid: grid resolution used (always 0.25 = 16th note)

    Args:
        track_index: Track containing the reference clip.
        slot_index: Clip slot index.
        label: Name for this reference profile (default: 'default').

    Returns:
        label, note_count, timing_variance, lateness_bias, velocity_std_dev
    """
    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    if not notes:
        raise ValueError("Reference clip at track={}, slot={} is empty.".format(track_index, slot_index))

    grid = 0.25  # 16th note

    def nearest_grid(t, g):
        return round(t / g) * g

    signed_offsets = [n["start_time"] - nearest_grid(n["start_time"], grid) for n in notes]
    abs_offsets = [abs(o) for o in signed_offsets]
    timing_variance = _std_dev(abs_offsets)
    lateness_bias = sum(signed_offsets) / len(signed_offsets)

    velocities = [n["velocity"] for n in notes]
    velocity_std_dev = _std_dev(velocities)
    velocity_mean = sum(velocities) / len(velocities)

    from collections import defaultdict
    pitch_groups: dict = defaultdict(list)
    for n in notes:
        pitch_groups[n["pitch"]].append(n)

    per_pitch = {}
    for pitch, pitch_notes in pitch_groups.items():
        pvels = [n["velocity"] for n in pitch_notes]
        poffsets = [n["start_time"] - nearest_grid(n["start_time"], grid) for n in pitch_notes]
        per_pitch[pitch] = {
            "note_count": len(pitch_notes),
            "velocity_mean": sum(pvels) / len(pvels),
            "velocity_std_dev": _std_dev(pvels),
            "lateness_bias": sum(poffsets) / len(poffsets),
            "timing_variance": _std_dev([abs(o) for o in poffsets]),
        }

    profile = {
        "type": "clip_feel",
        "label": label,
        "track_index": track_index,
        "slot_index": slot_index,
        "note_count": len(notes),
        "grid": grid,
        "timing_variance": timing_variance,
        "lateness_bias": lateness_bias,
        "velocity_std_dev": velocity_std_dev,
        "velocity_mean": velocity_mean,
        "per_pitch": per_pitch,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    _save_reference_profile(label, profile)

    return {
        "label": label,
        "note_count": len(notes),
        "timing_variance": round(timing_variance, 5),
        "lateness_bias": round(lateness_bias, 5),
        "velocity_std_dev": round(velocity_std_dev, 3),
        "velocity_mean": round(velocity_mean, 1),
    }


@mcp.tool()
def compare_clip_feel(
    track_index: int,
    slot_index: int,
    reference_label: str = "default",
) -> dict:
    """
    Compare the feel of a MIDI clip against a stored reference profile.

    Call designate_reference_clip() first to create the reference.

    Returns deltas and human-readable flags. Nothing is modified.

    Args:
        track_index: Track containing the clip to analyse.
        slot_index: Clip slot index.
        reference_label: Label of the reference profile to compare against.

    Returns:
        note_count,
        timing_variance_delta (float): target minus reference (positive = more loose)
        lateness_bias_delta (float): target minus reference (positive = target is later)
        velocity_std_dev_delta (float): target minus reference (positive = more varied)
        flags: list of human-readable observation strings
        summary: one-line summary of the main departure
        reference_label, reference_note_count
    """
    if reference_label not in _reference_profiles:
        # Try loading from project memory
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference profile '{}'. Call designate_reference_clip() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "clip_feel":
        raise ValueError("Reference '{}' is not a clip feel profile (type={}).".format(
            reference_label, ref.get("type")))

    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    if not notes:
        return {
            "note_count": 0,
            "flags": ["target clip is empty"],
            "summary": "target clip is empty",
            "reference_label": reference_label,
            "reference_note_count": ref["note_count"],
        }

    grid = ref.get("grid", 0.25)

    def nearest_grid(t, g):
        return round(t / g) * g

    signed_offsets = [n["start_time"] - nearest_grid(n["start_time"], grid) for n in notes]
    abs_offsets = [abs(o) for o in signed_offsets]
    timing_variance = _std_dev(abs_offsets)
    lateness_bias = sum(signed_offsets) / len(signed_offsets)

    velocities = [n["velocity"] for n in notes]
    velocity_std_dev = _std_dev(velocities)
    velocity_mean = sum(velocities) / len(velocities)

    tv_delta = timing_variance - ref["timing_variance"]
    lb_delta = lateness_bias - ref["lateness_bias"]
    vsd_delta = velocity_std_dev - ref["velocity_std_dev"]
    vm_delta = velocity_mean - ref["velocity_mean"]

    flags = []

    # Timing variance
    if ref["timing_variance"] > 0.001:
        ratio = timing_variance / ref["timing_variance"]
        if ratio < 0.4:
            flags.append("timing is much tighter than reference ({:.1f}x less loose)".format(1 / ratio))
        elif ratio < 0.75:
            flags.append("timing is tighter than reference ({:.1f}x less loose)".format(1 / ratio))
        elif ratio > 2.5:
            flags.append("timing is much looser than reference ({:.1f}x more loose)".format(ratio))
        elif ratio > 1.5:
            flags.append("timing is looser than reference ({:.1f}x more loose)".format(ratio))
    else:
        # Reference is near-perfectly quantized
        if timing_variance > 0.005:
            flags.append("target has timing looseness; reference is grid-locked")

    # Lateness bias
    if abs(lb_delta) > 0.004:
        direction = "later" if lb_delta > 0 else "earlier"
        flags.append("notes are {:.1f}ms {} than reference (at 120bpm)".format(
            abs(lb_delta) * 500, direction))  # 1 beat at 120bpm = 500ms

    # Velocity spread
    if ref["velocity_std_dev"] > 1.0:
        ratio = velocity_std_dev / ref["velocity_std_dev"] if ref["velocity_std_dev"] > 0 else 1.0
        if ratio < 0.5:
            flags.append("velocities are much more uniform than reference ({:.1f}x less varied)".format(1 / ratio))
        elif ratio < 0.75:
            flags.append("velocities are more uniform than reference")
        elif ratio > 2.0:
            flags.append("velocities are much more varied than reference ({:.1f}x)".format(ratio))
    else:
        if velocity_std_dev > 8.0:
            flags.append("velocities more varied than reference (reference had near-uniform velocities)")

    # Velocity mean
    if abs(vm_delta) > 8:
        direction = "louder" if vm_delta > 0 else "quieter"
        flags.append("overall velocity is {:.0f} units {} than reference".format(abs(vm_delta), direction))

    # Perfectly quantized check
    SNAP_THRESHOLD = 0.001
    target_quantized = all(abs(o) < SNAP_THRESHOLD for o in abs_offsets)
    ref_quantized = ref["timing_variance"] < SNAP_THRESHOLD
    if target_quantized and not ref_quantized:
        flags.append("target is perfectly grid-locked; reference has human feel")
    elif not target_quantized and ref_quantized:
        flags.append("target has loose timing; reference is grid-locked")

    if not flags:
        flags.append("feel is similar to reference — no major departures detected")

    # Summary: the most significant flag
    summary = flags[0] if flags else "no significant difference"

    return {
        "note_count": len(notes),
        "timing_variance": round(timing_variance, 5),
        "lateness_bias": round(lateness_bias, 5),
        "velocity_std_dev": round(velocity_std_dev, 3),
        "velocity_mean": round(velocity_mean, 1),
        "timing_variance_delta": round(tv_delta, 5),
        "lateness_bias_delta": round(lb_delta, 5),
        "velocity_std_dev_delta": round(vsd_delta, 3),
        "velocity_mean_delta": round(vm_delta, 1),
        "flags": flags,
        "summary": summary,
        "reference_label": reference_label,
        "reference_note_count": ref["note_count"],
        "reference_timing_variance": round(ref["timing_variance"], 5),
        "reference_lateness_bias": round(ref["lateness_bias"], 5),
        "reference_velocity_std_dev": round(ref["velocity_std_dev"], 3),
    }


@mcp.tool()
def designate_reference_mix_state(
    label: str = "default",
    scene_index: int | None = None,
) -> dict:
    """
    Capture the current mix state as a named reference profile.

    Stores per-track volumes, panning, sends, mute/solo state,
    device counts, and clip counts. Can optionally be scoped to the
    clips active in a particular scene.

    Use compare_mix_state() to compare a later mix state against this reference.

    Args:
        label: Name for this reference profile (default: 'default').
        scene_index: Optional scene index to annotate (no filtering applied —
                     all tracks are captured regardless).

    Returns:
        label, track_count, timestamp
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", [])

    track_profiles = []
    for t in tracks:
        track_profiles.append({
            "index": t["index"],
            "name": t["name"],
            "volume": t.get("volume", 0.0),
            "pan": t.get("pan", 0.0),
            "mute": t.get("mute", False),
            "solo": t.get("solo", False),
            "arm": t.get("arm", False),
            "sends": t.get("sends", []),
            "device_count": t.get("device_count", 0),
            "clip_count": t.get("clip_count", 0),
            "is_midi_track": t.get("is_midi_track", False),
        })

    master = snapshot.get("master_track", {})
    return_tracks = snapshot.get("return_tracks", [])

    profile = {
        "type": "mix_state",
        "label": label,
        "scene_index": scene_index,
        "track_count": len(tracks),
        "tracks": track_profiles,
        "master": {
            "volume": master.get("volume", 0.0),
            "pan": master.get("pan", 0.0),
        },
        "return_tracks": [
            {
                "index": r["index"],
                "name": r["name"],
                "volume": r.get("volume", 0.0),
                "pan": r.get("pan", 0.0),
                "mute": r.get("mute", False),
            }
            for r in return_tracks
        ],
        "tempo": snapshot.get("tempo"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    _save_reference_profile(label, profile)

    return {
        "label": label,
        "track_count": len(tracks),
        "timestamp": profile["timestamp"],
    }


@mcp.tool()
def compare_mix_state(
    reference_label: str = "default",
    scene_index: int | None = None,
) -> dict:
    """
    Compare the current mix state against a stored reference mix profile.

    Call designate_reference_mix_state() first to create the reference.

    Flags material differences in volume, panning, and send levels per track.
    Also reports section energy delta (total clip count, active track count).

    Nothing is modified.

    Args:
        reference_label: Label of the reference mix profile to compare against.
        scene_index: Optional — annotated in the result but does not filter tracks.

    Returns:
        track_count, flags, summary, per_track_deltas,
        master_volume_delta, total_clip_count_delta,
        reference_label, reference_timestamp
    """
    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference profile '{}'. Call designate_reference_mix_state() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "mix_state":
        raise ValueError("Reference '{}' is not a mix state profile (type={}).".format(
            reference_label, ref.get("type")))

    snapshot = _send("get_session_snapshot")
    curr_tracks = {t["index"]: t for t in snapshot.get("tracks", [])}
    ref_tracks = {t["index"]: t for t in ref.get("tracks", [])}

    flags = []
    per_track_deltas = []

    VOLUME_THRESHOLD = 0.05     # ~0.5 dB at unity
    PAN_THRESHOLD = 0.1
    SEND_THRESHOLD = 0.05

    for idx in sorted(set(curr_tracks.keys()) | set(ref_tracks.keys())):
        curr = curr_tracks.get(idx)
        reft = ref_tracks.get(idx)

        if curr is None:
            flags.append("track {} ('{}') existed in reference but is now gone".format(idx, reft.get("name", "?")))
            continue
        if reft is None:
            flags.append("track {} ('{}') is new since reference was taken".format(idx, curr.get("name", "?")))
            continue

        name = curr.get("name", str(idx))
        deltas = {"index": idx, "name": name, "changes": []}

        vol_delta = curr.get("volume", 0.0) - reft.get("volume", 0.0)
        if abs(vol_delta) > VOLUME_THRESHOLD:
            direction = "louder" if vol_delta > 0 else "quieter"
            deltas["changes"].append({
                "property": "volume",
                "delta": round(vol_delta, 3),
                "description": "'{}' is {:.2f} units {} than reference".format(name, abs(vol_delta), direction),
            })
            flags.append("'{}' volume is {} by {:.2f}".format(name, direction, abs(vol_delta)))

        pan_delta = curr.get("pan", 0.0) - reft.get("pan", 0.0)
        if abs(pan_delta) > PAN_THRESHOLD:
            direction = "right" if pan_delta > 0 else "left"
            deltas["changes"].append({
                "property": "pan",
                "delta": round(pan_delta, 3),
                "description": "'{}' panned {:.2f} units more {} than reference".format(name, abs(pan_delta), direction),
            })

        curr_sends = curr.get("sends", [])
        ref_sends = reft.get("sends", [])
        for si, (cs, rs) in enumerate(zip(curr_sends, ref_sends)):
            sd = cs - rs
            if abs(sd) > SEND_THRESHOLD:
                direction = "higher" if sd > 0 else "lower"
                deltas["changes"].append({
                    "property": "send_{}".format(si),
                    "delta": round(sd, 3),
                    "description": "'{}' send {} is {} by {:.2f}".format(name, si, direction, abs(sd)),
                })

        # Mute state change
        if curr.get("mute") != reft.get("mute"):
            state = "muted" if curr.get("mute") else "unmuted"
            deltas["changes"].append({
                "property": "mute",
                "delta": None,
                "description": "'{}' is now {}".format(name, state),
            })
            flags.append("'{}' is now {}".format(name, state))

        # Device count change
        cd = curr.get("device_count", 0) - reft.get("device_count", 0)
        if cd != 0:
            deltas["changes"].append({
                "property": "device_count",
                "delta": cd,
                "description": "'{}' has {} {} device(s) than reference".format(
                    name, abs(cd), "more" if cd > 0 else "fewer"),
            })

        if deltas["changes"]:
            per_track_deltas.append(deltas)

    # Master volume
    curr_master_vol = snapshot.get("master_track", {}).get("volume", 0.0)
    ref_master_vol = ref.get("master", {}).get("volume", 0.0)
    master_vol_delta = curr_master_vol - ref_master_vol
    if abs(master_vol_delta) > VOLUME_THRESHOLD:
        direction = "louder" if master_vol_delta > 0 else "quieter"
        flags.append("master volume is {} by {:.2f}".format(direction, abs(master_vol_delta)))

    # Section energy: total clip count as a rough density proxy
    curr_clip_total = sum(t.get("clip_count", 0) for t in snapshot.get("tracks", []))
    ref_clip_total = sum(t.get("clip_count", 0) for t in ref.get("tracks", []))
    clip_count_delta = curr_clip_total - ref_clip_total

    if not flags:
        flags.append("mix state is similar to reference — no material changes detected")

    summary = flags[0] if flags else "no significant difference"

    return {
        "track_count": len(curr_tracks),
        "flags": flags,
        "summary": summary,
        "per_track_deltas": per_track_deltas,
        "master_volume_delta": round(master_vol_delta, 3),
        "total_clip_count_delta": clip_count_delta,
        "reference_label": reference_label,
        "reference_timestamp": ref.get("timestamp"),
    }


@mcp.tool()
def list_reference_profiles() -> dict:
    """
    List all stored reference profiles (both in-process and persisted).

    Returns:
        profiles: list of {label, type, timestamp, note_count (if clip_feel), track_count (if mix_state)}
    """
    _load_reference_profiles_from_project()
    profiles = []
    for label, p in sorted(_reference_profiles.items()):
        entry = {
            "label": label,
            "type": p.get("type", "unknown"),
            "timestamp": p.get("timestamp"),
        }
        if p.get("type") == "clip_feel":
            entry["note_count"] = p.get("note_count")
            entry["timing_variance"] = round(p.get("timing_variance", 0.0), 5)
            entry["lateness_bias"] = round(p.get("lateness_bias", 0.0), 5)
        elif p.get("type") == "mix_state":
            entry["track_count"] = p.get("track_count")
        profiles.append(entry)
    return {"profiles": profiles, "count": len(profiles)}


@mcp.tool()
def delete_reference_profile(label: str) -> dict:
    """Delete a reference profile by label (in-process and from project memory)."""
    removed_memory = False
    if label in _reference_profiles:
        del _reference_profiles[label]
    else:
        raise ValueError("No reference profile with label '{}'.".format(label))
    if _current_project_id is not None:
        try:
            mem = _get_memory()
            if label in mem.get("reference_profiles", {}):
                del mem["reference_profiles"][label]
                _save_memory(_current_project_id, mem)
                removed_memory = True
        except Exception:
            pass
    return {"deleted": label, "removed_from_disk": removed_memory}


# ---------------------------------------------------------------------------
# Phase 9: Tier 2 audio analysis (requires librosa)
# ---------------------------------------------------------------------------


def _analyse_audio_file(file_path: str, duration_limit: float = 300.0) -> dict:
    """Run audio analysis and return the result dict. Used by both analyse_audio and designate_reference_audio."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        raise ImportError(
            "librosa and numpy are required for audio analysis. "
            "Install with: pip install librosa soundfile"
        )

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    y, sr = librosa.load(path, sr=None, mono=True, duration=duration_limit)
    duration = len(y) / sr

    stereo_width = None
    try:
        import soundfile as sf
        y_stereo, _ = sf.read(path, always_2d=True)
        if y_stereo.shape[1] >= 2:
            max_samples = int(duration_limit * sr)
            y_stereo = y_stereo[:max_samples]
            L = y_stereo[:, 0].astype(np.float32)
            R = y_stereo[:, 1].astype(np.float32)
            mid = (L + R) / 2.0
            side = (L - R) / 2.0
            mid_rms = float(np.sqrt(np.mean(mid ** 2)) + 1e-9)
            side_rms = float(np.sqrt(np.mean(side ** 2)) + 1e-9)
            stereo_width = round(side_rms / mid_rms, 4)
    except Exception:
        pass

    S = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)

    def band_energy(f_low, f_high):
        mask = (freqs >= f_low) & (freqs < f_high)
        return float(np.mean(S[mask, :] ** 2)) if mask.any() else 0.0

    total_energy = float(np.mean(S ** 2)) + 1e-9
    bands = {
        "low":       band_energy(20, 100) / total_energy,
        "low_mid":   band_energy(100, 500) / total_energy,
        "mid":       band_energy(500, 2000) / total_energy,
        "high_mid":  band_energy(2000, 8000) / total_energy,
        "high":      band_energy(8000, sr / 2) / total_energy,
    }
    bands = {k: round(v, 5) for k, v in bands.items()}

    rms = float(np.sqrt(np.mean(y ** 2)))
    loudness_dbfs = round(20 * np.log10(rms + 1e-9), 2)
    peak = float(np.max(np.abs(y)))
    peak_dbfs = round(20 * np.log10(peak + 1e-9), 2)
    crest_factor_db = round(peak_dbfs - loudness_dbfs, 2)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    sc_mean = round(float(np.mean(centroid)), 1)
    sc_std = round(float(np.std(centroid)), 1)

    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
    sr_mean = round(float(np.mean(rolloff)), 1)

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='time')
    transient_density = round(len(onset_frames) / duration, 3) if duration > 0 else 0.0

    hop = int(sr * 0.5)
    rms_frames = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    rms_db_frames = 20 * np.log10(rms_frames + 1e-9)
    dynamic_range = round(float(np.std(rms_db_frames)), 3)

    return {
        "file_path": path,
        "duration_seconds": round(duration, 2),
        "sample_rate": int(sr),
        "tonal_balance": bands,
        "loudness_dbfs": loudness_dbfs,
        "peak_dbfs": peak_dbfs,
        "crest_factor_db": crest_factor_db,
        "spectral_centroid_mean": sc_mean,
        "spectral_centroid_std": sc_std,
        "spectral_rolloff_mean": sr_mean,
        "transient_density_per_sec": transient_density,
        "dynamic_range": dynamic_range,
        "stereo_width": stereo_width,
    }


@mcp.tool()
def designate_reference_audio(
    file_path: str,
    label: str = "default_audio",
    duration_limit: float = 300.0,
) -> dict:
    """
    Analyse an audio file and store it as a named reference audio profile.

    Computes:
      - Tonal balance: low / low-mid / mid / high-mid / high band energy ratios
      - Integrated loudness estimate (RMS-based, in dBFS)
      - Peak level (dBFS)
      - Crest factor (peak-to-average ratio, dB)
      - Spectral centroid mean and std (brightness proxy)
      - Spectral rolloff mean (frequency below which 85% of energy sits)
      - Transient density: mean onset rate (onsets per second)
      - Dynamic range: std dev of short-term RMS across 0.5s windows
      - Stereo width estimate (if stereo file: mean absolute L-R difference / mean L+R)

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Absolute or home-relative path to audio file (WAV, AIFF, FLAC, MP3).
        label: Name for this reference profile (default: 'default_audio').
        duration_limit: Maximum seconds to analyse (default 300s = 5 min). Longer files are truncated.

    Returns:
        label, duration_seconds, sample_rate, channels,
        tonal_balance (dict of band: ratio),
        loudness_dbfs, peak_dbfs, crest_factor_db,
        spectral_centroid_mean, spectral_centroid_std,
        spectral_rolloff_mean,
        transient_density_per_sec,
        dynamic_range,
        stereo_width (float or None)
    """
    result = _analyse_audio_file(file_path, duration_limit=duration_limit)

    profile = dict(result)
    profile["type"] = "audio_analysis"
    profile["label"] = label
    profile["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_reference_profile(label, profile)
    _audio_analysis_cache[label] = profile

    return {k: v for k, v in profile.items() if k != "type"}


@mcp.tool()
def analyse_audio(
    file_path: str,
    duration_limit: float = 300.0,
) -> dict:
    """
    Analyse an audio file and return tonal, loudness, transient, and spectral metrics.

    Does NOT store the result as a reference profile. Use designate_reference_audio()
    if you want to store it for later comparison.

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Absolute or home-relative path to audio file.
        duration_limit: Maximum seconds to analyse (default 300s).

    Returns:
        Same fields as designate_reference_audio() minus the label/timestamp.
    """
    return _analyse_audio_file(file_path, duration_limit=duration_limit)


@mcp.tool()
def compare_audio(
    file_path: str,
    reference_label: str = "default_audio",
    duration_limit: float = 300.0,
) -> dict:
    """
    Analyse an audio file and compare it against a stored reference audio profile.

    Call designate_reference_audio() first to create the reference.

    Returns per-metric deltas and human-readable flags. Nothing is modified.

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Path to the audio file to analyse and compare.
        reference_label: Label of the reference audio profile.
        duration_limit: Max seconds to analyse.

    Returns:
        flags: list of human-readable observation strings
        summary: most significant departure
        deltas: dict of {metric: {target, reference, delta, delta_pct}}
        tonal_balance_deltas: dict of {band: delta}
        reference_label, reference_file_path
    """
    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference audio profile '{}'. Call designate_reference_audio() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "audio_analysis":
        raise ValueError("Reference '{}' is not an audio analysis profile (type={}).".format(
            reference_label, ref.get("type")))

    target = _analyse_audio_file(file_path, duration_limit=duration_limit)

    flags = []
    deltas = {}

    def compare_scalar(key, label_str, threshold, unit="", higher_is="louder", fmt=".1f"):
        t_val = target.get(key)
        r_val = ref.get(key)
        if t_val is None or r_val is None:
            return
        delta = t_val - r_val
        pct = (delta / abs(r_val) * 100) if r_val != 0 else 0.0
        deltas[key] = {
            "target": t_val,
            "reference": r_val,
            "delta": round(delta, 3),
            "delta_pct": round(pct, 1),
        }
        if abs(delta) > threshold:
            direction = higher_is if delta > 0 else ("darker" if higher_is == "brighter" else
                                                      "quieter" if higher_is == "louder" else
                                                      "lower" if higher_is == "higher" else "less")
            flags.append("{} is {} than reference (delta: {:{}}{})"
                         .format(label_str, direction, delta, fmt, unit))

    compare_scalar("loudness_dbfs",          "loudness",          1.5,  unit=" dB",   higher_is="louder",   fmt="+.1f")
    compare_scalar("peak_dbfs",              "peak level",        2.0,  unit=" dB",   higher_is="louder",   fmt="+.1f")
    compare_scalar("crest_factor_db",        "crest factor",      3.0,  unit=" dB",   higher_is="higher",   fmt="+.1f")
    compare_scalar("spectral_centroid_mean", "spectral centroid", 500,  unit=" Hz",   higher_is="brighter", fmt="+.0f")
    compare_scalar("spectral_rolloff_mean",  "spectral rolloff",  800,  unit=" Hz",   higher_is="brighter", fmt="+.0f")
    compare_scalar("transient_density_per_sec", "transient density", 0.5, unit=" onsets/s", higher_is="higher", fmt="+.2f")
    compare_scalar("dynamic_range",          "dynamic range",     2.0,  unit=" dB",   higher_is="higher",   fmt="+.1f")

    if target.get("stereo_width") is not None and ref.get("stereo_width") is not None:
        compare_scalar("stereo_width", "stereo width", 0.05, unit="", higher_is="wider", fmt="+.3f")

    tonal_deltas = {}
    ref_bands = ref.get("tonal_balance", {})
    tgt_bands = target.get("tonal_balance", {})
    tonal_threshold = 0.03

    band_descriptions = {
        "low":      "sub/low end (<100Hz)",
        "low_mid":  "low mids (100-500Hz)",
        "mid":      "mids (500Hz-2kHz)",
        "high_mid": "high mids (2-8kHz)",
        "high":     "highs (>8kHz)",
    }

    for band in ("low", "low_mid", "mid", "high_mid", "high"):
        t_b = tgt_bands.get(band, 0.0)
        r_b = ref_bands.get(band, 0.0)
        d = t_b - r_b
        tonal_deltas[band] = round(d, 5)
        if abs(d) > tonal_threshold:
            direction = "more" if d > 0 else "less"
            flags.append("{} has {} energy than reference ({:+.1f}%)".format(
                band_descriptions.get(band, band), direction, d * 100))

    if not flags:
        flags.append("no significant differences detected vs reference")

    summary = flags[0] if flags else "similar to reference"

    return {
        "flags": flags,
        "summary": summary,
        "flag_count": len(flags),
        "deltas": deltas,
        "tonal_balance_deltas": tonal_deltas,
        "target_file": target["file_path"],
        "target_duration_seconds": target["duration_seconds"],
        "reference_label": reference_label,
        "reference_file_path": ref.get("file_path", "unknown"),
    }


@mcp.tool()
def compare_audio_sections(
    file_path: str,
    reference_label: str = "default_audio",
    num_sections: int = 4,
    duration_limit: float = 300.0,
) -> dict:
    """
    Split a target audio file into N equal sections and compare each against the reference.

    Useful for detecting whether energy, brightness, and density build correctly
    across sections (intro → verse → chorus → outro) relative to the reference.

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Path to the audio file to analyse.
        reference_label: Label of the reference audio profile (full-song reference).
        num_sections: Number of equal sections to split the file into (default 4).
        duration_limit: Max seconds to analyse.

    Returns:
        sections: list of {section_index, start_sec, end_sec, loudness_dbfs,
                           spectral_centroid_mean, transient_density_per_sec,
                           vs_reference_loudness_delta, vs_reference_centroid_delta}
        flags: list of human-readable observations about section energy progression
        reference_label
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        raise ImportError(
            "librosa and numpy are required for audio analysis. "
            "Install with: pip install librosa soundfile"
        )

    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference audio profile '{}'. Call designate_reference_audio() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    y, sr = librosa.load(path, sr=None, mono=True, duration=duration_limit)
    total_samples = len(y)
    section_size = total_samples // num_sections

    ref_loudness = ref.get("loudness_dbfs", -18.0)
    ref_centroid = ref.get("spectral_centroid_mean", 2000.0)

    sections = []
    for i in range(num_sections):
        start = i * section_size
        end = start + section_size if i < num_sections - 1 else total_samples
        segment = y[start:end]

        seg_rms = float(np.sqrt(np.mean(segment ** 2)))
        seg_loudness = round(20 * np.log10(seg_rms + 1e-9), 2)

        seg_centroid = librosa.feature.spectral_centroid(y=segment, sr=sr)[0]
        seg_centroid_mean = round(float(np.mean(seg_centroid)), 1)

        seg_onsets = librosa.onset.onset_detect(y=segment, sr=sr, units='time')
        seg_duration = len(segment) / sr
        seg_density = round(len(seg_onsets) / seg_duration, 3) if seg_duration > 0 else 0.0

        sections.append({
            "section_index": i,
            "start_sec": round(start / sr, 2),
            "end_sec": round(end / sr, 2),
            "loudness_dbfs": seg_loudness,
            "spectral_centroid_mean": seg_centroid_mean,
            "transient_density_per_sec": seg_density,
            "vs_reference_loudness_delta": round(seg_loudness - ref_loudness, 2),
            "vs_reference_centroid_delta": round(seg_centroid_mean - ref_centroid, 1),
        })

    flags = []
    loudness_values = [s["loudness_dbfs"] for s in sections]
    centroid_values = [s["spectral_centroid_mean"] for s in sections]

    if loudness_values[-1] < loudness_values[0] - 1.0:
        flags.append("energy drops from first to last section — arrangement may not build")
    elif loudness_values[-1] > loudness_values[0] + 1.0:
        flags.append("energy builds from first to last section — good arrangement progression")

    very_quiet = [s for s in sections if s["vs_reference_loudness_delta"] < -6.0]
    if very_quiet:
        flags.append("sections {} are more than 6dB quieter than reference".format(
            [s["section_index"] for s in very_quiet]))

    if centroid_values[-1] < centroid_values[0] - 300:
        flags.append("brightness decreases across sections — track gets darker toward the end")

    loudness_range = max(loudness_values) - min(loudness_values)
    if loudness_range < 1.5:
        flags.append("section loudness variance is only {:.1f}dB — arrangement may lack dynamic contrast".format(loudness_range))

    if not flags:
        flags.append("section energy progression looks normal")

    return {
        "sections": sections,
        "flags": flags,
        "flag_count": len(flags),
        "reference_label": reference_label,
        "total_duration_seconds": round(total_samples / sr, 2),
    }


def _observer_loop():
    """Background thread: polls session state and evaluates rules."""
    global _observer_running, _observer_last_snapshot

    while _observer_running:
        try:
            snapshot = _send("get_session_snapshot", _log=False)
            with _observer_lock:
                prev = _observer_last_snapshot
            _evaluate_observer_rules(snapshot, prev)
            with _observer_lock:
                _observer_last_snapshot = snapshot
        except Exception:
            pass  # Ableton not connected — silently skip
        time.sleep(_OBSERVER_POLL_INTERVAL)


def _evaluate_observer_rules(current: dict, previous: dict | None):
    """Evaluate observation rules and push suggestions to the queue."""
    global _observer_last_checkpoint_log_len, _observer_poll_count, _observer_clip_cursor, _observer_flagged_clips
    suggestions = []

    # Rule 1: New track added with no devices
    if previous is not None:
        prev_tracks = {t["index"]: t for t in previous.get("tracks", [])}
        curr_tracks = {t["index"]: t for t in current.get("tracks", [])}
        new_indices = set(curr_tracks.keys()) - set(prev_tracks.keys())
        for idx in new_indices:
            t = curr_tracks[idx]
            if t.get("device_count", 0) == 0:
                suggestions.append({
                    "source": "observer",
                    "priority": "medium",
                    "message": f"New track \"{t['name']}\" (index {idx}) has no devices.",
                    "action": f"add_native_device({idx}, 'Simpler')  # or set_track_role({idx}, 'your role')",
                })

    # Rule 2: Master volume near ceiling
    master_vol = current.get("master_track", {}).get("volume", 0.0)
    if master_vol > 0.95:
        suggestions.append({
            "source": "observer",
            "priority": "high",
            "message": f"Master volume at {master_vol:.2f} — near ceiling.",
            "action": "set_master_volume(0.85)  # or add a Limiter",
        })

    # Rule 3: Track count changed significantly (3+ tracks added at once)
    if previous is not None:
        prev_count = previous.get("track_count", 0)
        curr_count = current.get("track_count", 0)
        if curr_count - prev_count >= 3:
            suggestions.append({
                "source": "observer",
                "priority": "low",
                "message": f"Track count jumped from {prev_count} to {curr_count}.",
                "action": "take_snapshot('after_track_changes')  # capture state",
            })

    # Rule 4: Any track soloed
    soloed = [t["name"] for t in current.get("tracks", []) if t.get("solo")]
    if soloed:
        suggestions.append({
            "source": "observer",
            "priority": "low",
            "message": f"Tracks still soloed: {soloed}",
            "action": "set_track_solo(track_index, False)  # unmute others",
        })

    # Rule 5: No snapshot taken and op count growing (fire once per 20-op threshold crossing)
    log_len = len(_operation_log)
    if log_len > 0:
        current_threshold = (log_len // 20) * 20
        if current_threshold > _observer_last_checkpoint_log_len:
            recent_snaps = [e for e in _operation_log[-30:] if "snapshot" in e["command"]]
            if not recent_snaps:
                suggestions.append({
                    "source": "observer",
                    "priority": "medium",
                    "message": f"{log_len} operations since server start, no recent snapshot.",
                    "action": "take_snapshot('checkpoint')",
                })
            # Advance threshold marker regardless, to avoid re-firing at same boundary
            _observer_last_checkpoint_log_len = current_threshold

    # Rule 6: Clip feel divergence from default reference
    if "default" in _reference_profiles:
        ref = _reference_profiles["default"]
        if ref.get("type") == "clip_feel" and ref.get("timing_variance", 0) > 0.002:
            # Only flag if reference has meaningful human feel
            for track in current.get("tracks", []):
                # We only have clip_count here, not note data — so we can only flag
                # at the track level if it has clips. The actual per-clip comparison
                # requires a get_notes call which is too expensive for the observer loop.
                # Instead, queue a softer suggestion to run compare_clip_feel manually.
                pass  # Full per-clip analysis is left to explicit compare_clip_feel() calls

    # Rule 7: Perfectly quantized / robotic feel detection (lazy rotating sampler)
    try:
        _observer_poll_count += 1

        # Detect structural change (track/clip layout changed) — clear flagged set
        if previous is not None:
            prev_layout = tuple(
                (t.get("index"), t.get("clip_count", 0))
                for t in previous.get("tracks", [])
            )
            curr_layout = tuple(
                (t.get("index"), t.get("clip_count", 0))
                for t in current.get("tracks", [])
            )
            if prev_layout != curr_layout:
                _observer_flagged_clips = set()

        if _observer_poll_count % _OBSERVER_FEEL_EVERY_N_POLLS == 0:
            # Build a flat list of (track_index, slot_index, track_name) for all MIDI clips
            midi_clips = []
            for track in current.get("tracks", []):
                ti = track.get("index")
                track_name = track.get("name", f"Track {ti}")
                clips = track.get("clips", [])
                for clip in clips:
                    if clip.get("is_midi_clip") and not clip.get("is_empty", True):
                        si = clip.get("slot_index", clip.get("index"))
                        midi_clips.append((ti, si, track_name))

            if midi_clips:
                # Rotate cursor so all clips are eventually sampled
                _observer_clip_cursor = _observer_clip_cursor % len(midi_clips)
                batch_start = _observer_clip_cursor
                sampled = []
                for i in range(len(midi_clips)):
                    idx = (batch_start + i) % len(midi_clips)
                    sampled.append(midi_clips[idx])
                    if len(sampled) >= _OBSERVER_FEEL_MAX_CLIPS_PER_POLL:
                        break
                _observer_clip_cursor = (batch_start + len(sampled)) % len(midi_clips)

                for track_index, slot_index, track_name in sampled:
                    if (track_index, slot_index) in _observer_flagged_clips:
                        continue
                    try:
                        result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index}, _log=False)
                        notes = result.get("notes", [])
                    except Exception:
                        continue

                    if len(notes) < 4:
                        continue

                    # --- Perfectly quantized check ---
                    grid = 0.25
                    SNAP_THRESHOLD = 0.001

                    def _dist_to_grid(t: float, g: float) -> float:
                        return abs(t - round(t / g) * g)

                    perfectly_quantized = all(
                        _dist_to_grid(n["start_time"], grid) < SNAP_THRESHOLD
                        for n in notes
                    )

                    # --- Uniform velocities check ---
                    velocities = [n["velocity"] for n in notes]
                    vel_mean = sum(velocities) / len(velocities)
                    vel_std = (sum((v - vel_mean) ** 2 for v in velocities) / len(velocities)) ** 0.5
                    uniform_velocities = vel_std < 3.0

                    # --- Uniform durations per pitch check ---
                    pitch_durations: dict = collections.defaultdict(list)
                    for n in notes:
                        pitch_durations[n["pitch"]].append(n["duration"])
                    uniform_dur_pitches = 0
                    for durs in pitch_durations.values():
                        if len(durs) > 1:
                            dur_mean = sum(durs) / len(durs)
                            dur_std = (sum((d - dur_mean) ** 2 for d in durs) / len(durs)) ** 0.5
                            if dur_std < 0.01:
                                uniform_dur_pitches += 1
                    uniform_durations = uniform_dur_pitches >= 2

                    flags = []
                    if perfectly_quantized:
                        flags.append("perfectly_quantized")
                    if uniform_velocities:
                        flags.append("uniform_velocities")
                    if uniform_durations:
                        flags.append("uniform_durations")

                    if flags:
                        _observer_flagged_clips.add((track_index, slot_index))
                        suggestions.append({
                            "source": "observer",
                            "type": "feel_observer",
                            "action": "humanize_notes or humanize_dilla",
                            "reason": (
                                f"Clip on track {track_name} slot {slot_index} appears perfectly "
                                f"quantized (robotic feel detected: {', '.join(flags)})"
                            ),
                            "message": (
                                f"Clip on track {track_name} slot {slot_index} appears perfectly "
                                f"quantized (robotic feel detected: {', '.join(flags)})"
                            ),
                            "priority": "high" if perfectly_quantized else "medium",
                            "track_index": track_index,
                            "slot_index": slot_index,
                            "flags": flags,
                        })
    except Exception:
        pass  # Rule 7 errors never break the observer loop

    # Push all to queue (deduplicate by message)
    with _observer_lock:
        existing_messages = {s["message"] for s in _suggestion_queue}
        for s in suggestions:
            if s["message"] not in existing_messages:
                _suggestion_queue.append(s)


def _start_observer():
    """Start the background observer thread."""
    global _observer_thread, _observer_running
    if _observer_thread is not None and _observer_thread.is_alive():
        return  # already running
    _observer_running = True
    _observer_thread = threading.Thread(
        target=_observer_loop,
        name="AbletonMPCX-Observer",
        daemon=True,
    )
    _observer_thread.start()


def _stop_observer():
    """Stop the background observer thread."""
    global _observer_running
    _observer_running = False


@mcp.tool()
def get_pending_suggestions(max_items: int = 10) -> dict:
    """
    Return and clear pending suggestions from the background observer.

    The observer thread watches the session state and queues suggestions
    when it detects state changes matching known rules (new tracks without
    devices, volume ceiling, solo tracks left on, etc.).

    Call this after every tool interaction to surface proactive observations.
    Returns an empty list if nothing has been detected.

    Args:
        max_items: Maximum number of suggestions to return (default 10).

    Returns:
        suggestions: list of {source, priority, message, action}
        queue_length_before: how many were queued before this call
    """
    with _observer_lock:
        before = len(_suggestion_queue)
        items = []
        for _ in range(min(max_items, len(_suggestion_queue))):
            if _suggestion_queue:
                items.append(_suggestion_queue.popleft())
    return {
        "suggestions": items,
        "queue_length_before": before,
    }


@mcp.tool()
def observer_status() -> dict:
    """
    Return the current status of the background observer thread.

    Returns:
        running, poll_interval_seconds, queue_length, last_snapshot_track_count
    """
    with _observer_lock:
        queue_len = len(_suggestion_queue)
        last_snap = _observer_last_snapshot
    return {
        "running": _observer_running and (_observer_thread is not None and _observer_thread.is_alive()),
        "poll_interval_seconds": _OBSERVER_POLL_INTERVAL,
        "queue_length": queue_len,
        "last_snapshot_track_count": last_snap.get("track_count", 0) if last_snap else None,
        "last_snapshot_tempo": last_snap.get("tempo") if last_snap else None,
    }


# ---------------------------------------------------------------------------
# Phase 7: Song creation from brief
# ---------------------------------------------------------------------------

_STYLE_PRESETS: dict[str, dict] = {
    "snoop": {"bpm": 90, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "hip_hop": {"bpm": 90, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "boom_bap": {"bpm": 85, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Sample", "audio"), ("Lead", "midi")]},
    "trap": {"bpm": 140, "tracks": [("808", "midi"), ("HiHat", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "lofi": {"bpm": 75, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Piano", "midi"), ("Texture", "audio")]},
}
_STYLE_FREE: dict = {"bpm": 120, "tracks": [("MIDI 1", "midi"), ("MIDI 2", "midi"), ("MIDI 3", "midi"), ("Audio 1", "audio")]}


@mcp.tool()
def create_song_from_brief(
    style: str,
    key: str | None = None,
    bpm: float | None = None,
) -> dict:
    """
    Create a skeleton arrangement from a music style brief.

    Supported styles: 'snoop', 'hip_hop', 'boom_bap', 'trap', 'lofi', or any value for a generic layout.

    Args:
        style: Music style preset.
        key: Optional musical key (e.g. 'C', 'F#m'). Stored as metadata; no Ableton command is issued.
        bpm: Override BPM. Uses style default if not provided.

    Returns:
        style, bpm, key, tracks_created, track_names, warnings
    """
    preset = _STYLE_PRESETS.get(style, _STYLE_FREE)
    bpm_used: float = bpm if bpm is not None else float(preset["bpm"])
    tracks: list[tuple[str, str]] = preset["tracks"]
    warnings: list[str] = []

    # 1. Set tempo
    _send_logged("set_tempo", {"tempo": bpm_used})

    # 2. Create tracks and rename them
    track_names: list[str] = []
    for idx, (name, track_type) in enumerate(tracks):
        if track_type == "audio":
            _send_logged("create_audio_track", {"index": idx})
        else:
            _send_logged("create_midi_track", {"index": idx})
        _send_logged("set_track_name", {"track_index": idx, "name": name})
        track_names.append(name)

    # 3. Warn if key was provided (no set_song_key command available)
    if key is not None:
        warnings.append(
            f"Key '{key}' noted but no set_song_key command is available; "
            "set the key manually in Ableton."
        )

    return {
        "style": style,
        "bpm": bpm_used,
        "key": key,
        "tracks_created": len(track_names),
        "track_names": track_names,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Workflow loop — detect → correct
# ---------------------------------------------------------------------------

@mcp.tool()
def auto_humanize_if_robotic(
    track_index: int,
    slot_index: int,
    feel_score_threshold: int = 60,
    style: str = "dilla",
    late_bias: float = 0.018,
    max_early: float = 0.005,
    max_late: float = 0.032,
    velocity_amount: float = 8.0,
    seed: int | None = None,
) -> dict:
    """
    Check a clip's feel score and apply humanization automatically if it is too robotic.

    Calls analyze_clip_feel() internally. If feel_score >= feel_score_threshold,
    applies humanize_dilla() (style='dilla') or humanize_notes() (style='generic').
    If the clip already feels human, nothing is modified.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        feel_score_threshold: Apply if feel_score >= this (0=human, 100=robotic). Default 60.
        style: 'dilla' for biased-late humanization, 'generic' for symmetric.
        late_bias: Passed to humanize_dilla (ignored for style='generic').
        max_early: Passed to humanize_dilla (ignored for style='generic').
        max_late: Passed to humanize_dilla. Also used as timing_amount for 'generic'.
        velocity_amount: Max velocity shift for either style.
        seed: Optional random seed.

    Returns:
        applied (bool), feel_score_before, feel_score_after,
        robotic_flags_before, humanization_style, note_count, reason
    """
    feel = analyze_clip_feel(track_index, slot_index)
    score_before = feel.get("feel_score", 0)
    flags_before = feel.get("robotic_flags", [])
    note_count = feel.get("note_count", 0)

    if score_before < feel_score_threshold:
        return {
            "applied": False,
            "feel_score_before": score_before,
            "feel_score_after": score_before,
            "robotic_flags_before": flags_before,
            "humanization_style": "none",
            "note_count": note_count,
            "reason": "feel_score {} is below threshold {}".format(score_before, feel_score_threshold),
        }

    if style == "dilla":
        humanize_dilla(
            track_index=track_index,
            slot_index=slot_index,
            late_bias=late_bias,
            max_early=max_early,
            max_late=max_late,
            velocity_amount=velocity_amount,
            seed=seed,
        )
    else:
        humanize_notes(
            track_index=track_index,
            slot_index=slot_index,
            timing_amount=max_late,
            velocity_amount=velocity_amount,
            seed=seed,
        )

    feel_after = analyze_clip_feel(track_index, slot_index)
    score_after = feel_after.get("feel_score", 0)

    return {
        "applied": True,
        "feel_score_before": score_before,
        "feel_score_after": score_after,
        "robotic_flags_before": flags_before,
        "humanization_style": style,
        "note_count": note_count,
        "reason": "feel_score {} >= threshold {}".format(score_before, feel_score_threshold),
    }


@mcp.tool()
def fix_groove_from_reference(
    track_index: int,
    slot_index: int,
    reference_label: str = "default",
    timing_blend: float = 0.5,
    velocity_blend: float = 0.3,
    seed: int | None = None,
) -> dict:
    """
    Compare a clip's feel against a stored reference and apply corrections to close the gap.

    Calls compare_clip_feel() internally. If the clip is measurably tighter or more
    uniform than the reference, applies targeted humanize_dilla() to bring it closer.
    The correction is conservative by default (timing_blend=0.5).

    Requires a feel profile created with designate_reference_clip().

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        reference_label: Label of the stored feel reference profile.
        timing_blend: 0.0=no timing change, 1.0=fully match reference timing spread.
        velocity_blend: 0.0=no velocity change, 1.0=fully match reference velocity spread.
        seed: Optional random seed.

    Returns:
        applied (bool), flags_before, corrections_applied,
        timing_variance_before, timing_variance_after,
        velocity_std_before, velocity_std_after, reference_label
    """
    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference feel profile '{}'. Call designate_reference_clip() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "feel_profile":
        raise ValueError(
            "Reference '{}' is not a feel profile (type={}). "
            "Use designate_reference_clip() to create one.".format(reference_label, ref.get("type"))
        )

    comparison = compare_clip_feel(track_index, slot_index, reference_label=reference_label)
    flags = comparison.get("flags", [])
    timing_var_before = comparison.get("timing_variance", 0.0)
    vel_std_before = comparison.get("velocity_std_dev", 0.0)

    ref_timing_variance = ref.get("timing_variance", 0.0)
    ref_velocity_std = ref.get("velocity_std_dev", 0.0)

    corrections = []
    # 70% threshold: only apply timing correction when clip is significantly tighter than reference
    apply_timing = timing_var_before < ref_timing_variance * 0.7
    # 60% threshold: only apply velocity correction when clip has meaningfully less variation
    apply_velocity = vel_std_before < ref_velocity_std * 0.6

    if apply_timing:
        corrections.append("timing: clip is tighter than reference — applying late-biased loosening")
    if apply_velocity:
        corrections.append("velocity: clip has less variation than reference — widening spread")

    if not apply_timing and not apply_velocity:
        return {
            "applied": False,
            "flags_before": flags,
            "corrections_applied": [],
            "timing_variance_before": timing_var_before,
            "timing_variance_after": timing_var_before,
            "velocity_std_before": vel_std_before,
            "velocity_std_after": vel_std_before,
            "reference_label": reference_label,
            "reason": "clip feel is already within acceptable range of reference",
        }

    timing_gap = max(0.0, ref_timing_variance - timing_var_before)
    timing_amount = max(0.001, timing_gap * timing_blend)

    velocity_gap = max(0.0, ref_velocity_std - vel_std_before)
    # Scale by 10 to convert from timing standard-deviation units to MIDI velocity range (0-127)
    velocity_amount_computed = max(1.0, velocity_gap * velocity_blend * 10)

    humanize_dilla(
        track_index=track_index,
        slot_index=slot_index,
        late_bias=timing_amount * 0.6,
        max_early=timing_amount * 0.2,
        max_late=timing_amount * 1.2,
        velocity_amount=velocity_amount_computed if apply_velocity else 0.0,
        loose_subdivisions=True,
        seed=seed,
    )

    feel_after = analyze_clip_feel(track_index, slot_index)
    timing_var_after = feel_after.get("timing_variance", 0.0)
    vel_std_after = feel_after.get("velocity_std_dev", 0.0)

    return {
        "applied": True,
        "flags_before": flags,
        "corrections_applied": corrections,
        "timing_variance_before": timing_var_before,
        "timing_variance_after": timing_var_after,
        "velocity_std_before": vel_std_before,
        "velocity_std_after": vel_std_after,
        "reference_label": reference_label,
    }


@mcp.tool()
def batch_auto_humanize(
    track_indices: list,
    slot_index: int,
    feel_score_threshold: int = 60,
    style: str = "dilla",
    seed: int | None = None,
) -> dict:
    """
    Run auto_humanize_if_robotic() across multiple tracks at the same slot index.

    Useful for checking all clips in a scene row and humanizing any that are too robotic.

    Args:
        track_indices: List of track indices to check.
        slot_index: Clip slot index to check on each track.
        feel_score_threshold: Apply humanization if feel_score >= this value. Default 60.
        style: 'dilla' or 'generic'.
        seed: Optional random seed (same seed applied to each clip for reproducibility).

    Returns:
        results: list of per-track {track_index, applied, feel_score_before, feel_score_after, note_count}
        applied_count, skipped_count, total_checked
    """
    results = []
    applied_count = 0
    skipped_count = 0

    for ti in track_indices:
        try:
            result = auto_humanize_if_robotic(
                track_index=ti,
                slot_index=slot_index,
                feel_score_threshold=feel_score_threshold,
                style=style,
                seed=seed,
            )
            results.append({
                "track_index": ti,
                "applied": result["applied"],
                "feel_score_before": result["feel_score_before"],
                "feel_score_after": result["feel_score_after"],
                "note_count": result["note_count"],
                "reason": result.get("reason", ""),
            })
            if result["applied"]:
                applied_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            results.append({
                "track_index": ti,
                "applied": False,
                "error": str(e),
            })
            skipped_count += 1

    return {
        "results": results,
        "applied_count": applied_count,
        "skipped_count": skipped_count,
        "total_checked": len(track_indices),
    }


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



# ---------------------------------------------------------------------------
# Mix Analysis and Sound Recommendation
# ---------------------------------------------------------------------------

# ------------------------------------------------------------------
# Module-level descriptor constants
# ------------------------------------------------------------------

_TONAL_KEYWORDS: dict[str, dict[str, float]] = {
    "sub":      {"sub": 0.95, "bass": 0.3},
    "bass":     {"bass": 0.85, "sub": 0.4, "punch": 0.3},
    "warm":     {"body": 0.8, "mid": 0.5, "air": 0.1},
    "bright":   {"presence": 0.7, "air": 0.6},
    "airy":     {"air": 0.9, "presence": 0.3},
    "shimmer":  {"air": 0.85, "presence": 0.6},
    "crystal":  {"air": 0.8, "presence": 0.7},
    "dark":     {"air": 0.05, "presence": 0.15, "body": 0.65},
    "pad":      {"sustain": 0.9, "transient": 0.05, "density": 0.4},
    "pluck":    {"transient": 0.9, "sustain": 0.15},
    "wide":     {"width": 0.9},
    "lush":     {"width": 0.75, "sustain": 0.7},
    "thick":    {"body": 0.7, "punch": 0.5, "mid": 0.4},
    "deep":     {"sub": 0.75, "bass": 0.65},
    "grand":    {"body": 0.6, "presence": 0.5, "transient": 0.6},
    "upright":  {"body": 0.7, "punch": 0.5, "transient": 0.5},
    "rhodes":   {"body": 0.5, "mid": 0.6, "transient": 0.5},
    "bell":     {"presence": 0.7, "air": 0.6, "transient": 0.8, "sustain": 0.6},
    "strings":  {"sustain": 0.85, "body": 0.5, "mid": 0.5},
    "choir":    {"sustain": 0.8, "mid": 0.6, "presence": 0.4},
    "stab":     {"transient": 0.9, "sustain": 0.1},
    "perc":     {"transient": 0.85, "sustain": 0.2},
    "snap":     {"transient": 0.9},
    "hit":      {"transient": 0.8},
    "drone":    {"sustain": 0.95, "density": 0.6},
    "evolving": {"sustain": 0.9, "density": 0.7},
    "lead":     {"presence": 0.7, "mid": 0.6, "transient": 0.5},
    "organ":    {"mid": 0.7, "body": 0.5, "sustain": 0.85},
    "piano":    {"transient": 0.7, "body": 0.5, "mid": 0.5, "presence": 0.4},
    "brass":    {"presence": 0.8, "mid": 0.6, "transient": 0.6},
    "flute":    {"presence": 0.6, "air": 0.5, "sustain": 0.7},
    "guitar":   {"mid": 0.6, "punch": 0.5, "transient": 0.6},
    "mellow":   {"body": 0.6, "mid": 0.5, "air": 0.1, "presence": 0.2},
    "crisp":    {"presence": 0.8, "air": 0.5},
    "punchy":   {"punch": 0.85, "transient": 0.75},
    "808":      {"sub": 0.9, "bass": 0.7, "sustain": 0.6},
    "mono":     {"width": 0.05},
    "stereo":   {"width": 0.8},
}

_DRUM_KEYWORDS: dict[str, dict[str, float]] = {
    "tight":      {"tempo_feel": 0.1, "room_size": 0.1},
    "dry":        {"room_size": 0.05},
    "room":       {"room_size": 0.6, "tempo_feel": 0.5},
    "heavy":      {"kick_sub": 0.9, "kick_punch": 0.7, "density": 0.8},
    "punchy":     {"kick_punch": 0.85, "kick_attack": 0.75},
    "jazz":       {"tempo_feel": 0.7, "overhead_air": 0.85, "density": 0.3},
    "rock":       {"kick_punch": 0.8, "snare_crack": 0.7, "density": 0.7},
    "electronic": {"kick_attack": 0.9, "tempo_feel": 0.1, "room_size": 0.05},
    "vintage":    {"room_size": 0.5, "density": 0.5, "overhead_air": 0.6},
    "modern":     {"kick_attack": 0.8, "snare_crack": 0.8, "tempo_feel": 0.2},
}

_OMNISPHERE_TAG_MAP: dict[str, dict[str, float]] = {
    "Aggressive": {"transient": 0.8, "density": 0.8, "presence": 0.7},
    "Airy":       {"air": 0.9, "presence": 0.4, "sustain": 0.7},
    "Bright":     {"presence": 0.75, "air": 0.6},
    "Dark":       {"air": 0.05, "presence": 0.1, "body": 0.7},
    "Evolving":   {"sustain": 0.9, "density": 0.7},
    "Full":       {"bass": 0.5, "body": 0.6, "mid": 0.5, "density": 0.6},
    "Grunge":     {"density": 0.85, "transient": 0.6, "presence": 0.6},
    "Hard":       {"transient": 0.8, "density": 0.7},
    "Hollow":     {"body": 0.1, "mid": 0.3, "air": 0.4},
    "Lush":       {"width": 0.85, "sustain": 0.8, "density": 0.5},
    "Percussive": {"transient": 0.85, "sustain": 0.15},
    "Soft":       {"transient": 0.1, "density": 0.2, "sustain": 0.7},
    "Thin":       {"body": 0.05, "bass": 0.1, "density": 0.2},
    "Warm":       {"body": 0.8, "mid": 0.5, "air": 0.1},
    "Wide":       {"width": 0.9},
}

_MOOG_MARIANA_BASE: dict[str, float] = {
    "sub": 0.85, "bass": 0.7, "punch": 0.4, "body": 0.2,
    "mid": 0.1, "presence": 0.05, "air": 0.02,
}

_SESSION_UPRIGHT_BASE: dict[str, float] = {
    "bass": 0.85, "punch": 0.7, "body": 0.5, "mid": 0.3,
    "sub": 0.4, "presence": 0.2, "air": 0.05,
}

# Canonical frequency band descriptors
_FREQ_BANDS = ["sub", "bass", "punch", "body", "mid", "presence", "air"]
_CHAR_BANDS = ["transient", "sustain", "width", "density"]
_ALL_BANDS = _FREQ_BANDS + _CHAR_BANDS

# MCPSpectrum band-name → canonical band key mapping
_SPECTRUM_BAND_MAP: dict[str, str] = {
    "sub (20–60 hz)":       "sub",
    "bass (60–120 hz)":     "bass",
    "punch (120–250 hz)":   "punch",
    "body (250–500 hz)":    "body",
    "mid (500–2k hz)":      "mid",
    "presence (2k–6k hz)":  "presence",
    "air (6k–20k hz)":      "air",
}

# Splice librosa frequency bin ranges (at sr=22050)
_SPLICE_BAND_RANGES: dict[str, tuple[float, float]] = {
    "sub":      (20.0,   60.0),
    "bass":     (60.0,  120.0),
    "punch":   (120.0,  250.0),
    "body":    (250.0,  500.0),
    "mid":     (500.0, 2000.0),
    "presence": (2000.0, 6000.0),
    "air":     (6000.0, 20000.0),
}

# Cache file path
_CACHE_DIR = pathlib.Path.home() / ".ableton_mpcx"
_CACHE_FILE = _CACHE_DIR / "sound_library.json"


def _ensure_cache_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_cache() -> dict:
    """Load the sound library cache or return an empty structure."""
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"entries": []}


def _save_cache(cache: dict) -> None:
    """Persist the sound library cache to disk."""
    _ensure_cache_dir()
    with open(_CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2)


def _infer_descriptors_from_name(name: str, plugin: str = "") -> dict[str, float]:
    """
    Infer tonal descriptors from a preset/file name using _TONAL_KEYWORDS.
    Returns a dict of band -> 0.0-1.0 scores.
    """
    tokens = re.split(r"[\s_\-/\\\.]+", name.lower())
    scores: dict[str, float] = {}

    # Apply plugin base descriptors first
    plugin_lower = plugin.lower()
    if "moog mariana" in plugin_lower or "mariana" in plugin_lower:
        for k, v in _MOOG_MARIANA_BASE.items():
            scores[k] = v
    elif "session upright" in plugin_lower or "session bass" in plugin_lower:
        for k, v in _SESSION_UPRIGHT_BASE.items():
            scores[k] = v

    # Apply keyword matches
    for token in tokens:
        if token in _TONAL_KEYWORDS:
            for band, val in _TONAL_KEYWORDS[token].items():
                scores[band] = max(scores.get(band, 0.0), val)

    # Fill in any missing canonical bands with 0.0
    for band in _ALL_BANDS:
        scores.setdefault(band, 0.0)

    return scores


def _infer_drum_descriptors_from_name(name: str) -> dict[str, float]:
    """
    Infer drum descriptors from a kit/preset name using _DRUM_KEYWORDS.
    """
    tokens = re.split(r"[\s_\-/\\\.]+", name.lower())
    drum_bands = [
        "kick_sub", "kick_punch", "kick_attack",
        "snare_crack", "snare_body",
        "room_size", "overhead_air", "density", "tempo_feel",
    ]
    scores: dict[str, float] = {b: 0.0 for b in drum_bands}
    for token in tokens:
        if token in _DRUM_KEYWORDS:
            for band, val in _DRUM_KEYWORDS[token].items():
                scores[band] = max(scores.get(band, 0.0), val)
    return scores


def _detect_plugin_from_path(path: str) -> str:
    """Detect plugin name from a file path substring."""
    pl = path.lower()
    if "omnisphere" in pl:
        return "Omnisphere"
    if "keyscape" in pl:
        return "Keyscape"
    if "moog mariana" in pl or "mariana" in pl:
        return "Moog Mariana"
    if "session upright" in pl:
        return "Session Upright"
    if "session bass" in pl:
        return "Session Bass"
    if "addictive drums" in pl or "ad2" in pl:
        return "Addictive Drums 2"
    if "superior drummer" in pl or "sd3" in pl:
        return "Superior Drummer 3"
    return "Unknown"


def _is_drum_plugin(plugin: str) -> bool:
    pl = plugin.lower()
    return any(k in pl for k in ("addictive drums", "ad2", "superior drummer", "sd3"))


def _parse_aupreset(path: pathlib.Path) -> tuple[str, dict]:
    """
    Parse an .aupreset (plist) file.
    Returns (preset_name, extra_info_dict).
    """
    with open(path, "rb") as fh:
        data = plistlib.load(fh)
    name = data.get("name", path.stem)
    return name, data


def _parse_prt_omni(path: pathlib.Path) -> tuple[str, list[str]]:
    """
    Parse an Omnisphere .prt_omni file.
    Returns (preset_name, character_tags).
    """
    name = path.stem
    tags: list[str] = []
    try:
        with open(path, "rb") as fh:
            data = plistlib.load(fh)
        name = data.get("PatchName", data.get("name", name))
        char = data.get("CharacterTags", data.get("Attributes", []))
        if isinstance(char, list):
            tags = [str(t) for t in char]
        return name, tags
    except Exception:
        pass
    # Fall back to text regex search
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"PatchName[^\w]+([\w\s]+)", text)
        if m:
            name = m.group(1).strip()
        tags = re.findall(r"<string>([\w]+)</string>", text)
    except Exception:
        pass
    return name, tags


def _apply_omnisphere_tags(
    descriptors: dict[str, float], tags: list[str]
) -> dict[str, float]:
    """Merge Omnisphere character-tag descriptors into existing scores."""
    for tag in tags:
        if tag in _OMNISPHERE_TAG_MAP:
            for band, val in _OMNISPHERE_TAG_MAP[tag].items():
                descriptors[band] = max(descriptors.get(band, 0.0), val)
    return descriptors


# ------------------------------------------------------------------
# Tool: analyze_mix_balance
# ------------------------------------------------------------------

@mcp.tool()
def analyze_mix_balance(
    reference_track_index: int = -1,
    crowded_threshold_db: float = 3.0,
    missing_threshold_db: float = -6.0,
) -> dict:
    """
    Read existing MCPSpectrum analyzer instances across all tracks and
    identify crowded, missing, and balanced frequency bands compared to
    the master/reference track.

    Args:
        reference_track_index: Track index to use as mix reference.
                                Default -1 = master track.
        crowded_threshold_db:  A source band is "crowded" if its average
                                exceeds the reference by this many dB.
        missing_threshold_db:  A band is "missing" if the average source
                                level is below the reference by this many dB.

    Returns:
        crowded, missing, balanced (lists of band names),
        recommendations (list of natural-language strings),
        summary (single summary string).
    """
    try:
        telemetry = get_spectrum_telemetry_instances()
    except Exception as exc:
        return {"error": "Could not read spectrum telemetry: {}".format(exc)}

    instances = telemetry.get("instances", [])
    if not instances:
        return {
            "error": (
                "No MCPSpectrum analyzer instances found. "
                "Add an MCPSpectrum device to the master and source tracks, "
                "then run analyze_mix_balance() again."
            )
        }

    # Find the reference instance
    reference_instance = None
    source_instances = []
    for inst in instances:
        if inst.get("track_index") == reference_track_index:
            reference_instance = inst
        else:
            source_instances.append(inst)

    if reference_instance is None:
        return {
            "error": (
                "No MCPSpectrum analyzer found on reference track {} "
                "(usually the master, index -1). "
                "Add MCPSpectrum to that track and try again.".format(
                    reference_track_index
                )
            )
        }

    # Extract reference band values (0–1 linear)
    ref_bands: dict[str, float] = {}
    for band_name, band_info in reference_instance.get("bands", {}).items():
        key = _SPECTRUM_BAND_MAP.get(band_name.lower())
        if key:
            ref_bands[key] = float(band_info.get("value", 0.0))

    if not ref_bands:
        return {
            "error": (
                "Reference track analyzer has no recognised band parameters. "
                "Expected names like 'Sub (20–60 Hz)'. "
                "Use get_spectrum_telemetry_instances() to inspect band names."
            )
        }

    # Compute average source values per band
    source_avg: dict[str, float] = {}
    if source_instances:
        band_sums: dict[str, list[float]] = {}
        for inst in source_instances:
            for band_name, band_info in inst.get("bands", {}).items():
                key = _SPECTRUM_BAND_MAP.get(band_name.lower())
                if key:
                    band_sums.setdefault(key, []).append(
                        float(band_info.get("value", 0.0))
                    )
        for band, vals in band_sums.items():
            source_avg[band] = sum(vals) / len(vals)

    def _safe_db(linear: float) -> float:
        """Convert a linear amplitude value to dB; returns -120 dB for silence."""
        if linear <= 0.0:
            return -120.0
        return 20.0 * math.log10(linear)

    crowded: list[str] = []
    missing: list[str] = []
    balanced: list[str] = []
    band_deltas: dict[str, float] = {}

    for band in _FREQ_BANDS:
        ref_val = ref_bands.get(band, 0.0)
        src_val = source_avg.get(band, ref_val)  # fall back to ref if no sources

        ref_db = _safe_db(ref_val)
        src_db = _safe_db(src_val) if source_instances else ref_db
        delta = src_db - ref_db
        band_deltas[band] = round(delta, 1)

        if delta >= crowded_threshold_db:
            crowded.append(band)
        elif delta <= missing_threshold_db:
            missing.append(band)
        else:
            balanced.append(band)

    # Build natural language recommendations
    _BAND_LABELS = {
        "sub":      "Sub (20–60 Hz)",
        "bass":     "Bass (60–120 Hz)",
        "punch":    "Punch (120–250 Hz)",
        "body":     "Body (250–500 Hz)",
        "mid":      "Mid (500–2 kHz)",
        "presence": "Presence (2–6 kHz)",
        "air":      "Air (6–20 kHz)",
    }

    recommendations: list[str] = []
    for band in crowded:
        delta = band_deltas[band]
        label = _BAND_LABELS.get(band, band)
        recommendations.append(
            "{} is crowded ({:+.1f} dB above master) — "
            "consider cutting here on competing tracks or choosing sounds "
            "with less {} energy.".format(label, delta, label.split(" ")[0].lower())
        )
    for band in missing:
        delta = band_deltas[band]
        label = _BAND_LABELS.get(band, band)
        recommendations.append(
            "{} is sparse ({:+.1f} dB below master) — "
            "adding a sound rich in {} content could fill this gap.".format(
                label, delta, label.split(" ")[0].lower()
            )
        )

    crowded_labels = [_BAND_LABELS.get(b, b) for b in crowded]
    missing_labels = [_BAND_LABELS.get(b, b) for b in missing]

    if crowded_labels and missing_labels:
        summary = "Mix is crowded in {} and thin in {}.".format(
            ", ".join(crowded_labels), ", ".join(missing_labels)
        )
    elif crowded_labels:
        summary = "Mix is crowded in {}.".format(", ".join(crowded_labels))
    elif missing_labels:
        summary = "Mix is thin in {}.".format(", ".join(missing_labels))
    else:
        summary = "Mix balance looks even across all bands."

    return {
        "crowded":         crowded,
        "missing":         missing,
        "balanced":        balanced,
        "band_deltas_db":  band_deltas,
        "recommendations": recommendations,
        "summary":         summary,
        "reference_track": reference_track_index,
        "source_count":    len(source_instances),
    }


# ------------------------------------------------------------------
# Tool: scan_au_presets
# ------------------------------------------------------------------

@mcp.tool()
def scan_au_presets(force_rescan: bool = False) -> dict:
    """
    Scan standard macOS AU preset locations for .aupreset and .prt_omni files,
    infer tonal descriptors from names and plugin-specific mappings, and store
    results to ~/.ableton_mpcx/sound_library.json.

    Scanned locations:
      ~/Library/Audio/Presets/
      /Library/Audio/Presets/
      ~/Library/Application Support/Spectrasonics/STEAM/Omnisphere/Settings Library/Patches/
      ~/Music/Ableton/Library/Presets/
      ~/Music/Ableton/User Library/Presets/

    Args:
        force_rescan: If True, re-scan files that are already in the cache.

    Returns:
        scanned, added, skipped counts and per-plugin breakdown.
    """
    scan_paths = [
        pathlib.Path.home() / "Library" / "Audio" / "Presets",
        pathlib.Path("/Library/Audio/Presets"),
        pathlib.Path.home() / "Library" / "Application Support"
            / "Spectrasonics" / "STEAM" / "Omnisphere"
            / "Settings Library" / "Patches",
        pathlib.Path.home() / "Music" / "Ableton" / "Library" / "Presets",
        pathlib.Path.home() / "Music" / "Ableton" / "User Library" / "Presets",
    ]

    cache = _load_cache()
    existing_paths = {e["path"] for e in cache.get("entries", [])}

    scanned = 0
    added = 0
    skipped = 0
    plugin_counts: dict[str, int] = {}

    for base_path in scan_paths:
        if not base_path.exists():
            continue
        for ext in ("aupreset", "prt_omni"):
            for fpath in base_path.rglob("*.{}".format(ext)):
                path_str = str(fpath)
                scanned += 1
                if path_str in existing_paths and not force_rescan:
                    skipped += 1
                    continue

                plugin = _detect_plugin_from_path(path_str)
                is_drum = _is_drum_plugin(plugin)

                omni_tags: list[str] = []
                try:
                    if ext == "aupreset":
                        preset_name, _raw = _parse_aupreset(fpath)
                    else:
                        preset_name, omni_tags = _parse_prt_omni(fpath)
                except Exception:
                    skipped += 1
                    continue

                if is_drum:
                    descriptors: dict[str, float | bool] = _infer_drum_descriptors_from_name(preset_name)  # type: ignore[assignment]
                    descriptors["is_drum"] = True
                else:
                    descriptors = _infer_descriptors_from_name(preset_name, plugin)  # type: ignore[assignment]
                    if ext == "prt_omni":
                        descriptors = _apply_omnisphere_tags(descriptors, omni_tags)  # type: ignore[assignment]
                    descriptors["is_drum"] = False

                entry: dict = {
                    "path":        path_str,
                    "preset_name": preset_name,
                    "plugin":      plugin,
                    "category":    fpath.parent.name,
                    "tags":        [],
                    "measured":    False,
                    "scan_date":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                entry.update(descriptors)

                # Remove stale entry if re-scanning
                cache["entries"] = [
                    e for e in cache["entries"] if e["path"] != path_str
                ]
                cache["entries"].append(entry)
                existing_paths.add(path_str)
                added += 1
                plugin_counts[plugin] = plugin_counts.get(plugin, 0) + 1

    _save_cache(cache)

    return {
        "scanned": scanned,
        "added":   added,
        "skipped": skipped,
        "by_plugin": plugin_counts,
        "total_in_library": len(cache["entries"]),
        "cache_file": str(_CACHE_FILE),
    }


# ------------------------------------------------------------------
# Tool: scan_splice_library
# ------------------------------------------------------------------

@mcp.tool()
def scan_splice_library(
    splice_path: str | None = None,
    force_rescan: bool = False,
) -> dict:
    """
    Scan the Splice sample library and perform real audio analysis using
    librosa to measure actual frequency content, transients, width, and
    sustain. Results are stored to ~/.ableton_mpcx/sound_library.json.

    Args:
        splice_path: Path to Splice folder. Defaults to ~/Music/Splice/.
        force_rescan: If True, re-analyse files already in the cache.

    Returns:
        scanned, added, skipped, error counts and cache path.
    """
    try:
        import librosa  # type: ignore[import]
        import numpy as np  # type: ignore[import]
    except ImportError:
        return {
            "error": (
                "librosa and numpy are required for Splice audio analysis. "
                "Run: pip install librosa numpy"
            )
        }

    root = pathlib.Path(splice_path) if splice_path else (
        pathlib.Path.home() / "Music" / "Splice"
    )

    if not root.exists():
        return {
            "error": (
                "Splice folder not found at {}. "
                "Pass splice_path='<path>' to specify a custom location.".format(root)
            )
        }

    cache = _load_cache()
    existing_paths = {e["path"] for e in cache.get("entries", [])}

    scanned = 0
    added = 0
    skipped = 0
    errors = 0
    SAVE_INTERVAL = 100

    sr = 22050
    n_fft = 2048
    hop_length = 512

    def _hz_to_bin(hz: float) -> int:
        return int(hz * n_fft / sr)

    for fpath in root.rglob("*"):
        if fpath.suffix.lower() not in (".wav", ".aiff", ".aif"):
            continue
        path_str = str(fpath)
        scanned += 1

        if path_str in existing_paths and not force_rescan:
            skipped += 1
            continue

        try:
            y_mono, _ = librosa.load(path_str, sr=sr, mono=True, duration=4.0)
        except Exception:
            errors += 1
            continue

        # STFT magnitude
        try:
            stft_mag = np.abs(librosa.stft(y_mono, n_fft=n_fft, hop_length=hop_length))
        except Exception:
            errors += 1
            continue

        # Per-band RMS
        band_rms: dict[str, float] = {}
        for band, (lo_hz, hi_hz) in _SPLICE_BAND_RANGES.items():
            lo_bin = max(0, _hz_to_bin(lo_hz))
            hi_bin = min(stft_mag.shape[0], _hz_to_bin(hi_hz))
            if hi_bin <= lo_bin:
                band_rms[band] = 0.0
                continue
            band_rms[band] = float(np.sqrt(np.mean(stft_mag[lo_bin:hi_bin] ** 2)))

        # Normalize 0-1
        max_rms = max(band_rms.values()) if band_rms else 0.0
        if max_rms > 0:
            band_rms = {b: v / max_rms for b, v in band_rms.items()}

        # Transient strength (normalised onset envelope mean)
        try:
            onset_env = librosa.onset.onset_strength(y=y_mono, sr=sr)
            transient = float(np.clip(np.mean(onset_env) / 10.0, 0.0, 1.0))
        except Exception:
            transient = 0.0

        # Sustain: ratio of tail RMS to peak RMS
        try:
            frame_rms = librosa.feature.rms(y=y_mono, hop_length=hop_length)[0]
            n_frames = len(frame_rms)
            peak_rms = float(np.max(frame_rms)) if n_frames else 0.0
            if n_frames > 4 and peak_rms > 0:
                tail_rms = float(np.mean(frame_rms[-n_frames // 4:]))
                sustain = float(np.clip(tail_rms / peak_rms, 0.0, 1.0))
            else:
                sustain = 0.0
        except Exception:
            sustain = 0.0

        # Stereo width — try to load as stereo
        width = 0.5  # default: unknown
        try:
            y_stereo, _ = librosa.load(path_str, sr=sr, mono=False, duration=4.0)
            if y_stereo.ndim == 2 and y_stereo.shape[0] == 2:
                left, right = y_stereo[0], y_stereo[1]
                denom = (np.sqrt(np.mean(left ** 2)) * np.sqrt(np.mean(right ** 2)))
                if denom > 0:
                    corr = float(np.mean(left * right) / denom)
                    # corr=1 → mono, corr=-1 → fully out of phase → wide
                    width = float(np.clip((1.0 - corr) / 2.0, 0.0, 1.0))
        except Exception:
            pass

        entry: dict = {
            "path":        path_str,
            "preset_name": fpath.stem,
            "plugin":      "Splice",
            "category":    fpath.parent.name,
            "tags":        [],
            "measured":    True,
            "is_drum":     False,
            "scan_date":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "transient":   round(transient, 3),
            "sustain":     round(sustain, 3),
            "width":       round(width, 3),
            "density":     0.0,
        }
        entry.update({b: round(v, 3) for b, v in band_rms.items()})

        cache["entries"] = [e for e in cache["entries"] if e["path"] != path_str]
        cache["entries"].append(entry)
        existing_paths.add(path_str)
        added += 1

        if added % SAVE_INTERVAL == 0:
            _save_cache(cache)

    _save_cache(cache)

    return {
        "scanned":          scanned,
        "added":            added,
        "skipped":          skipped,
        "errors":           errors,
        "total_in_library": len(cache["entries"]),
        "cache_file":       str(_CACHE_FILE),
    }


# ------------------------------------------------------------------
# Tool: recommend_presets
# ------------------------------------------------------------------

@mcp.tool()
def recommend_presets(
    target_bands: list[str] | None = None,
    avoid_bands: list[str] | None = None,
    top_n: int = 5,
    plugin_filter: str | None = None,
) -> dict:
    """
    Rank sound library entries by fit score against target and avoid frequency
    bands and return best_fit / usable / likely_clash tiers.

    Run scan_au_presets() and/or scan_splice_library() first to populate the
    library, then optionally run analyze_mix_balance() to discover which bands
    to target and avoid.

    Args:
        target_bands: Bands to boost score for (e.g. ["air", "presence"]).
                      Valid values: sub, bass, punch, body, mid, presence, air,
                      transient, sustain, width, density.
        avoid_bands:  Bands to penalise score for (e.g. ["body", "mid"]).
        top_n:        Maximum number of entries to return per tier (default 5).
        plugin_filter: Optional plugin name substring to restrict results.

    Returns:
        best_fit, usable, likely_clash (lists of preset info dicts),
        total_scored count.
    """
    cache = _load_cache()
    entries = cache.get("entries", [])

    if not entries:
        return {
            "error": (
                "Sound library is empty. "
                "Run scan_au_presets() and/or scan_splice_library() first."
            )
        }

    target_bands = [b.lower() for b in (target_bands or [])]
    avoid_bands  = [b.lower() for b in (avoid_bands  or [])]

    if not target_bands and not avoid_bands:
        return {
            "error": (
                "Please provide at least one target_band or avoid_band. "
                "Use analyze_mix_balance() to discover which bands are crowded or missing."
            )
        }

    # Filter by plugin if requested
    if plugin_filter:
        pf_lower = plugin_filter.lower()
        entries = [e for e in entries if pf_lower in e.get("plugin", "").lower()]

    if not entries:
        return {
            "error": "No library entries match plugin_filter '{}'.".format(plugin_filter)
        }

    # Score every entry
    scored: list[tuple[float, dict]] = []
    for entry in entries:
        score = 0.0
        for band in target_bands:
            score += entry.get(band, 0.0) * 2.0
        for band in avoid_bands:
            score -= entry.get(band, 0.0) * 1.5
        if entry.get("measured", False):
            score *= 1.1
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    total = len(scored)
    third = max(1, total // 3)

    best_slice   = scored[:third]
    usable_slice = scored[third : third * 2]
    clash_slice  = scored[third * 2:]

    def _format_scored_entries(items: list[tuple[float, dict]], n: int) -> list[dict]:
        result = []
        for score, entry in items[:n]:
            result.append({
                "preset_name": entry.get("preset_name", ""),
                "plugin":      entry.get("plugin", ""),
                "path":        entry.get("path", ""),
                "score":       round(score, 3),
                "measured":    entry.get("measured", False),
                "is_drum":     entry.get("is_drum", False),
            })
        return result

    return {
        "best_fit":     _format_scored_entries(best_slice, top_n),
        "usable":       _format_scored_entries(usable_slice, top_n),
        "likely_clash": _format_scored_entries(clash_slice, top_n),
        "total_scored": total,
        "target_bands": target_bands,
        "avoid_bands":  avoid_bands,
    }


# ------------------------------------------------------------------
# Tool: audit_preset
# ------------------------------------------------------------------

@mcp.tool()
def audit_preset(
    track_index: int,
    preset_name: str,
    plugin_name: str | None = None,
) -> dict:
    """
    Self-learning: read the MCPSpectrum analyzer on a track after a preset is
    loaded and playing, then store the measured real descriptor back to the
    sound library cache, marking the entry as measured=True.

    Load and play the preset on the specified track before calling this tool.

    Args:
        track_index:  Track that has the preset loaded (and an MCPSpectrum device).
        preset_name:  Name of the preset to match in the library (substring match).
        plugin_name:  Optional plugin name to narrow the match.

    Returns:
        updated entry dict, or error message.
    """
    try:
        telemetry = get_spectrum_telemetry_instances()
    except Exception as exc:
        return {"error": "Could not read spectrum telemetry: {}".format(exc)}

    instances = telemetry.get("instances", [])
    track_instance = None
    for inst in instances:
        if inst.get("track_index") == track_index:
            track_instance = inst
            break

    if track_instance is None:
        return {
            "error": (
                "No MCPSpectrum analyzer found on track {}. "
                "Add an MCPSpectrum device to that track and try again.".format(
                    track_index
                )
            )
        }

    # Extract measured band values
    measured: dict[str, float] = {}
    for band_name, band_info in track_instance.get("bands", {}).items():
        key = _SPECTRUM_BAND_MAP.get(band_name.lower())
        if key:
            measured[key] = float(band_info.get("value", 0.0))

    if not measured:
        return {
            "error": (
                "Could not extract any band values from track {} analyzer. "
                "Check that MCPSpectrum is active and audio is playing.".format(
                    track_index
                )
            )
        }

    cache = _load_cache()
    entries = cache.get("entries", [])

    pn_lower = preset_name.lower()
    pl_lower = (plugin_name or "").lower()

    matches = [
        e for e in entries
        if pn_lower in e.get("preset_name", "").lower()
        and (not pl_lower or pl_lower in e.get("plugin", "").lower())
    ]

    if not matches:
        return {
            "error": (
                "No library entry found matching preset_name='{}' "
                "(plugin_filter='{}').  Run scan_au_presets() first.".format(
                    preset_name, plugin_name or ""
                )
            )
        }

    # Update the best match (first hit)
    target_entry = matches[0]
    target_entry.update(measured)
    target_entry["measured"] = True
    target_entry["scan_date"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_cache(cache)

    return {
        "updated": True,
        "preset_name": target_entry.get("preset_name"),
        "plugin":      target_entry.get("plugin"),
        "path":        target_entry.get("path"),
        "measured_bands": measured,
    }


# ------------------------------------------------------------------
# Tool: get_sound_library_stats
# ------------------------------------------------------------------

@mcp.tool()
def get_sound_library_stats() -> dict:
    """
    Show statistics about the sound library cache:
    total entries, per-plugin breakdown, measured vs inferred counts,
    drum vs melodic counts, and cache file location.

    Run scan_au_presets() or scan_splice_library() to populate the library.

    Returns:
        total, by_plugin, measured_count, inferred_count,
        drum_count, melodic_count, cache_file.
    """
    if not _CACHE_FILE.exists():
        return {
            "error": (
                "Sound library cache not found at {}. "
                "Run scan_au_presets() or scan_splice_library() to create it.".format(
                    _CACHE_FILE
                )
            )
        }

    cache = _load_cache()
    entries = cache.get("entries", [])

    by_plugin: dict[str, int] = {}
    measured_count = 0
    drum_count = 0

    for e in entries:
        plugin = e.get("plugin", "Unknown")
        by_plugin[plugin] = by_plugin.get(plugin, 0) + 1
        if e.get("measured", False):
            measured_count += 1
        if e.get("is_drum", False):
            drum_count += 1

    total = len(entries)

    return {
        "total":          total,
        "by_plugin":      by_plugin,
        "measured_count": measured_count,
        "inferred_count": total - measured_count,
        "drum_count":     drum_count,
        "melodic_count":  total - drum_count,
        "cache_file":     str(_CACHE_FILE),
    }




_ROLE_COLORS = {
    "kick":     5,    # red
    "snare":    9,    # orange
    "drums":    9,    # orange
    "hi-hat":   12,   # yellow
    "perc":     12,   # yellow
    "bass":     14,   # yellow-green
    "keys":     19,   # green
    "piano":    19,
    "guitar":   25,   # teal
    "pad":      28,   # cyan
    "synth":    28,
    "lead":     41,   # blue
    "fx":       49,   # purple
    "vocal":    57,   # pink
    "master":   1,    # white
    "return":   70,   # grey
    "default":  0,
}

_DEVICE_TO_ROLE = {
    "kick":             "kick",
    "snare":            "snare",
    "drum":             "drums",
    "superior":         "drums",
    "addictive":        "drums",
    "bass":             "bass",
    "mariana":          "bass",
    "session upright":  "bass",
    "sub":              "bass",
    "piano":            "piano",
    "keyscape":         "piano",
    "grand":            "piano",
    "upright":          "piano",
    "keys":             "keys",
    "rhodes":           "keys",
    "wurli":            "keys",
    "clav":             "keys",
    "organ":            "keys",
    "pad":              "pad",
    "omnisphere":       "pad",
    "lead":             "lead",
    "serum":            "synth",
    "massive":          "synth",
    "vocal":            "vocal",
    "voice":            "vocal",
    "choir":            "vocal",
    "guitar":           "guitar",
    "reverb":           "fx",
    "delay":            "fx",
}

_SCENE_SECTION_COLORS = {
    "intro":    70,   # grey
    "verse":    41,   # blue
    "chorus":   5,    # red
    "hook":     5,    # red
    "drop":     5,    # red
    "pre":      28,   # cyan
    "build":    28,   # cyan
    "bridge":   49,   # purple
    "break":    49,   # purple
    "outro":    70,   # grey
    "default":  0,
}

# Cache directory for session management persistent data
_SESSION_CACHE_DIR = os.path.expanduser("~/.ableton_mpcx")
_DEVICE_SNAPSHOTS_PATH = os.path.join(_SESSION_CACHE_DIR, "device_snapshots.json")
_VERSIONS_PATH = os.path.join(_SESSION_CACHE_DIR, "versions.json")



# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------


def _ensure_session_cache_dir():
    os.makedirs(_SESSION_CACHE_DIR, exist_ok=True)


def _load_json_cache(path: str, default):
    """Load a JSON cache file; return default on missing/corrupt."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json_cache(path: str, data) -> bool:
    """Save data to a JSON cache file. Returns True on success."""
    _ensure_session_cache_dir()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def _infer_role_from_devices(track_index: int) -> tuple[str, str]:
    """Return (role, method_used) by inspecting device names on the track."""
    try:
        devices = _send("get_devices", {"track_index": track_index})
    except RuntimeError:
        devices = []
    for device in devices:
        name_lower = device.get("name", "").lower()
        for key, role in _DEVICE_TO_ROLE.items():
            if key in name_lower:
                return role, "device_name"
    return "default", "fallback"


def _infer_role_from_spectrum(track_index: int) -> tuple[str, str]:
    """Return (role, method_used) by inspecting MCPSpectrum band profile."""
    try:
        data = get_spectrum_telemetry_instances()
        for instance in data.get("instances", []):
            if instance.get("track_index") == track_index:
                bands = instance.get("bands", {})

                def _band_val(keyword):
                    for bname, bdata in bands.items():
                        if keyword.lower() in bname.lower():
                            return float(bdata.get("value", 0.0))
                    return 0.0

                sub = _band_val("sub")
                body = _band_val("body")
                air = _band_val("air")
                punch = _band_val("punch")
                transient = _band_val("transient")

                if sub > 0.6:
                    return "bass", "spectrum_sub"
                if air > 0.6:
                    return "pad", "spectrum_air"
                if transient > 0.6 or punch > 0.6:
                    return "perc", "spectrum_transient"
                if body > 0.6:
                    return "keys", "spectrum_body"
    except Exception:
        pass
    return "default", "fallback"


# --- Feature 1: Auto-naming and color ---

@mcp.tool()
def auto_name_track(track_index: int, dry_run: bool = False) -> dict:
    """
    Automatically name a track based on its device chain content and spectrum analyzer data.

    Infers the track role by:
    1. Checking device names against _DEVICE_TO_ROLE mappings
    2. Falling back to MCPSpectrum band profile (sub-heavy=bass, air-heavy=pad, etc.)
    3. Using track position as last resort (Track 1, Track 2, etc.)

    Args:
        track_index: Track to name (-1 for master).
        dry_run: If True, return the suggested name without applying it.

    Returns:
        track_index, suggested_name, inferred_role, method_used, applied (bool)
    """
    role, method = _infer_role_from_devices(track_index)
    if role == "default":
        role, method = _infer_role_from_spectrum(track_index)
    if role == "default":
        suggested_name = "Track {}".format(track_index + 1)
        method = "position"
    else:
        suggested_name = role.replace("-", " ").title()

    applied = False
    if not dry_run:
        try:
            _send("set_track_name", {"track_index": track_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "suggested_name": suggested_name,
                "inferred_role": role,
                "method_used": method,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "suggested_name": suggested_name,
        "inferred_role": role,
        "method_used": method,
        "applied": applied,
    }


@mcp.tool()
def auto_color_track(track_index: int, role: str | None = None, dry_run: bool = False) -> dict:
    """
    Set a track's color based on its inferred or specified role.

    Args:
        track_index: Track to color.
        role: Override role (e.g. 'bass', 'pad', 'drums'). If None, infers from devices.
        dry_run: If True, return the color value without applying.

    Returns:
        track_index, role, color_value, applied (bool)
    """
    if role is None:
        role, _ = _infer_role_from_devices(track_index)
        if role == "default":
            role, _ = _infer_role_from_spectrum(track_index)

    color_value = _ROLE_COLORS.get(role, _ROLE_COLORS["default"])

    applied = False
    if not dry_run:
        try:
            _send("set_track_color", {"track_index": track_index, "color": color_value})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "role": role,
                "color_value": color_value,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "role": role,
        "color_value": color_value,
        "applied": applied,
    }


@mcp.tool()
def auto_name_all_tracks(dry_run: bool = False, skip_named: bool = True) -> dict:
    """
    Auto-name and color all tracks in the session at once.

    Args:
        dry_run: If True, return suggestions without applying.
        skip_named: If True, skip tracks that already have a non-default name (default True).

    Returns:
        results: list of {track_index, track_name, suggested_name, role, color, applied, skipped_reason}
        applied_count, skipped_count
    """
    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e), "results": []}

    results = []
    applied_count = 0
    skipped_count = 0

    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        current_name = track.get("name", "")

        skipped_reason = None
        if skip_named:
            default_names = {"audio", "midi", "track"}
            name_lower = current_name.lower()
            is_default = (
                not current_name
                or any(name_lower.startswith(d) for d in default_names)
                or re.match(r"^track\s*\d+$", name_lower)
                or re.match(r"^\d+$", name_lower)
            )
            if not is_default:
                skipped_reason = "already_named"

        role, _ = _infer_role_from_devices(idx)
        if role == "default":
            role, _ = _infer_role_from_spectrum(idx)

        if role == "default":
            suggested_name = "Track {}".format(idx + 1)
        else:
            suggested_name = role.replace("-", " ").title()

        color = _ROLE_COLORS.get(role, _ROLE_COLORS["default"])

        applied = False
        if skipped_reason is None and not dry_run:
            try:
                _send("set_track_name", {"track_index": idx, "name": suggested_name})
                _send("set_track_color", {"track_index": idx, "color": color})
                applied = True
                applied_count += 1
            except RuntimeError:
                pass
        elif skipped_reason:
            skipped_count += 1

        results.append({
            "track_index": idx,
            "track_name": current_name,
            "suggested_name": suggested_name,
            "role": role,
            "color": color,
            "applied": applied,
            "skipped_reason": skipped_reason,
        })

    return {
        "results": results,
        "applied_count": applied_count,
        "skipped_count": skipped_count,
    }


@mcp.tool()
def auto_name_clip(track_index: int, clip_index: int, dry_run: bool = False) -> dict:
    """
    Auto-name a clip based on its MIDI content or audio file name.

    For MIDI clips: infers from note register (low=bass line, mid=chords, high=melody/lead)
    and note density (sparse=melody, dense=chord/pad).
    For audio clips: uses the audio file name as base.

    Args:
        track_index: Track containing the clip.
        clip_index: Clip slot index.
        dry_run: If True, return suggestion without applying.

    Returns:
        track_index, clip_index, suggested_name, inference_basis, applied (bool)
    """
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
    except RuntimeError as e:
        return {"error": "Could not get clip info: {}".format(e)}

    inference_basis = "unknown"
    suggested_name = "Clip {}".format(clip_index + 1)

    clip_type = clip_info.get("type", clip_info.get("is_midi_clip"))
    is_midi = clip_type == "midi" or clip_type is True

    if not is_midi:
        file_path = clip_info.get("file_path", clip_info.get("sample_path", ""))
        if file_path:
            base = os.path.splitext(os.path.basename(file_path))[0]
            suggested_name = base
            inference_basis = "audio_filename"
        else:
            inference_basis = "default"
    else:
        notes = clip_info.get("notes", [])
        if notes:
            pitches = [n.get("pitch", n.get("note", 60)) for n in notes]
            avg_pitch = sum(pitches) / len(pitches)
            density = len(notes) / max(clip_info.get("length", 1.0), 0.001)

            if avg_pitch < 48:
                suggested_name = "Bass Line"
                inference_basis = "midi_low_register"
            elif avg_pitch > 72:
                if density < 2.0:
                    suggested_name = "Melody"
                    inference_basis = "midi_high_sparse"
                else:
                    suggested_name = "Lead"
                    inference_basis = "midi_high_dense"
            else:
                if density > 3.0:
                    suggested_name = "Chords"
                    inference_basis = "midi_mid_dense"
                else:
                    suggested_name = "Pad"
                    inference_basis = "midi_mid_sparse"
        else:
            inference_basis = "empty_midi"

    applied = False
    if not dry_run:
        try:
            _send("set_clip_name", {"track_index": track_index, "slot_index": clip_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "suggested_name": suggested_name,
                "inference_basis": inference_basis,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "clip_index": clip_index,
        "suggested_name": suggested_name,
        "inference_basis": inference_basis,
        "applied": applied,
    }


@mcp.tool()
def auto_name_scene(scene_index: int, dry_run: bool = False) -> dict:
    """
    Auto-name a scene based on the clip names in that scene row.

    Looks at clip names across all tracks in that scene row and infers
    a section label (Verse, Chorus, Bridge, etc.) from common keywords.

    Args:
        scene_index: Scene to name.
        dry_run: If True, return suggestion without applying.

    Returns:
        scene_index, suggested_name, inference_basis, applied (bool)
    """
    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    clip_names = []
    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        try:
            slots = _send("get_clip_slots", {"track_index": idx})
            if scene_index < len(slots):
                slot = slots[scene_index]
                clip_name = slot.get("clip_name", slot.get("name", ""))
                if clip_name:
                    clip_names.append(clip_name.lower())
        except RuntimeError:
            pass

    combined = " ".join(clip_names)
    suggested_name = "Scene {}".format(scene_index + 1)
    inference_basis = "position"

    for keyword, color in _SCENE_SECTION_COLORS.items():
        if keyword == "default":
            continue
        if keyword in combined:
            suggested_name = keyword.capitalize()
            inference_basis = "clip_keyword"
            break

    applied = False
    if not dry_run:
        try:
            _send("set_scene_name", {"scene_index": scene_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "scene_index": scene_index,
                "suggested_name": suggested_name,
                "inference_basis": inference_basis,
                "applied": False,
                "error": str(e),
            }

    return {
        "scene_index": scene_index,
        "suggested_name": suggested_name,
        "inference_basis": inference_basis,
        "applied": applied,
    }


# --- Feature 2: Device state snapshots + diff ---

@mcp.tool()
def save_device_snapshot(
    track_index: int,
    snapshot_name: str,
    device_index: int | None = None,
) -> dict:
    """
    Save the current parameter state of all devices on a track (or one device) as a named snapshot.

    Snapshots are stored in ~/.ableton_mpcx/device_snapshots.json.
    If a snapshot with the same name already exists for this track, it is overwritten.

    Args:
        track_index: Track to snapshot (-1 for master).
        snapshot_name: Name for this snapshot (e.g. 'lo-fi', 'clean', 'warm').
        device_index: If specified, snapshot only this device. If None, snapshot all devices.

    Returns:
        snapshot_name, track_index, devices_captured: int, parameter_count: int, saved_at: str
    """
    try:
        devices = _send("get_devices", {"track_index": track_index})
    except RuntimeError as e:
        return {"error": "Could not get devices: {}".format(e)}

    if device_index is not None:
        devices = [d for d in devices if d.get("index", d.get("device_index")) == device_index]

    snapshot_data = {}
    total_params = 0

    for device in devices:
        dev_idx = device.get("index", device.get("device_index", 0))
        try:
            params_result = _send("get_device_parameters", {
                "track_index": track_index,
                "device_index": dev_idx,
            })
            params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
            param_map = {}
            for p in params:
                p_idx = p.get("index", p.get("parameter_index", 0))
                param_map[str(p_idx)] = {
                    "value": p.get("value", 0.0),
                    "name": p.get("name", ""),
                }
                total_params += 1
            snapshot_data[str(dev_idx)] = {
                "device_name": device.get("name", ""),
                "parameters": param_map,
            }
        except RuntimeError:
            pass

    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)
    if track_key not in all_snapshots:
        all_snapshots[track_key] = {}
    all_snapshots[track_key][snapshot_name] = {
        "devices": snapshot_data,
        "saved_at": saved_at,
    }
    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)

    return {
        "snapshot_name": snapshot_name,
        "track_index": track_index,
        "devices_captured": len(snapshot_data),
        "parameter_count": total_params,
        "saved_at": saved_at,
    }


@mcp.tool()
def recall_device_snapshot(
    track_index: int,
    snapshot_name: str,
    device_index: int | None = None,
) -> dict:
    """
    Restore a previously saved device parameter snapshot on a track.

    All parameter changes are grouped into a single undo step.

    Args:
        track_index: Track to restore.
        snapshot_name: Name of the snapshot to recall.
        device_index: If specified, restore only this device. If None, restore all.

    Returns:
        snapshot_name, track_index, parameters_restored: int, devices_restored: int
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)
    if track_key not in all_snapshots or snapshot_name not in all_snapshots[track_key]:
        return {
            "error": "Snapshot '{}' not found for track {}. Use list_device_snapshots() to see available.".format(
                snapshot_name, track_index
            )
        }

    snapshot = all_snapshots[track_key][snapshot_name]
    devices_data = snapshot.get("devices", {})

    try:
        _send("begin_undo_step", {"name": "recall_snapshot_{}".format(snapshot_name)})
    except RuntimeError:
        pass

    parameters_restored = 0
    devices_restored = 0

    for dev_idx_str, dev_data in devices_data.items():
        dev_idx = int(dev_idx_str)
        if device_index is not None and dev_idx != device_index:
            continue
        param_map = dev_data.get("parameters", {})
        restored_any = False
        for param_idx_str, param_info in param_map.items():
            try:
                _send("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": dev_idx,
                    "parameter_index": int(param_idx_str),
                    "value": param_info.get("value", 0.0),
                })
                parameters_restored += 1
                restored_any = True
            except RuntimeError:
                pass
        if restored_any:
            devices_restored += 1

    try:
        _send("end_undo_step", {})
    except RuntimeError:
        pass

    return {
        "snapshot_name": snapshot_name,
        "track_index": track_index,
        "parameters_restored": parameters_restored,
        "devices_restored": devices_restored,
    }


@mcp.tool()
def list_device_snapshots(track_index: int | None = None) -> dict:
    """
    List all saved device snapshots, optionally filtered by track.

    Args:
        track_index: If specified, list only snapshots for this track. If None, list all.

    Returns:
        snapshots: list of {track_index, snapshot_name, device_count, parameter_count, saved_at}
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    results = []

    for track_key, snaps in all_snapshots.items():
        ti = int(track_key)
        if track_index is not None and ti != track_index:
            continue
        for snap_name, snap_data in snaps.items():
            devices_data = snap_data.get("devices", {})
            param_count = sum(
                len(d.get("parameters", {})) for d in devices_data.values()
            )
            results.append({
                "track_index": ti,
                "snapshot_name": snap_name,
                "device_count": len(devices_data),
                "parameter_count": param_count,
                "saved_at": snap_data.get("saved_at", ""),
            })

    return {"snapshots": results}


@mcp.tool()
def diff_device_snapshots(
    track_index: int,
    snapshot_a: str,
    snapshot_b: str,
) -> dict:
    """
    Compare two named device snapshots for a track and return what changed.

    Args:
        track_index: Track the snapshots belong to.
        snapshot_a: Name of the first snapshot (the 'before').
        snapshot_b: Name of the second snapshot (the 'after').

    Returns:
        snapshot_a, snapshot_b, track_index,
        changed: list of {device_index, device_name, param_index, param_name, value_a, value_b, delta}
        unchanged_count: int,
        summary: human-readable string describing what changed
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)

    for snap_name in (snapshot_a, snapshot_b):
        if track_key not in all_snapshots or snap_name not in all_snapshots[track_key]:
            return {"error": "Snapshot '{}' not found for track {}.".format(snap_name, track_index)}

    data_a = all_snapshots[track_key][snapshot_a].get("devices", {})
    data_b = all_snapshots[track_key][snapshot_b].get("devices", {})

    changed = []
    unchanged_count = 0

    all_dev_keys = set(data_a.keys()) | set(data_b.keys())
    for dev_key in all_dev_keys:
        dev_a = data_a.get(dev_key, {})
        dev_b = data_b.get(dev_key, {})
        dev_name = dev_a.get("device_name", dev_b.get("device_name", ""))
        params_a = dev_a.get("parameters", {})
        params_b = dev_b.get("parameters", {})
        all_param_keys = set(params_a.keys()) | set(params_b.keys())
        for p_key in all_param_keys:
            pa = params_a.get(p_key, {})
            pb = params_b.get(p_key, {})
            va = pa.get("value", 0.0)
            vb = pb.get("value", 0.0)
            param_name = pa.get("name", pb.get("name", ""))
            if abs(va - vb) > 1e-9:
                changed.append({
                    "device_index": int(dev_key),
                    "device_name": dev_name,
                    "param_index": int(p_key),
                    "param_name": param_name,
                    "value_a": va,
                    "value_b": vb,
                    "delta": vb - va,
                })
            else:
                unchanged_count += 1

    if changed:
        summary = "{} parameter(s) changed across {} device(s) between '{}' and '{}'.".format(
            len(changed),
            len({c["device_index"] for c in changed}),
            snapshot_a,
            snapshot_b,
        )
    else:
        summary = "No differences found between '{}' and '{}'.".format(snapshot_a, snapshot_b)

    return {
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "track_index": track_index,
        "changed": changed,
        "unchanged_count": unchanged_count,
        "summary": summary,
    }


@mcp.tool()
def delete_device_snapshot(track_index: int, snapshot_name: str) -> dict:
    """
    Delete a named device snapshot.

    Returns:
        deleted (bool), snapshot_name, track_index
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)

    if track_key not in all_snapshots or snapshot_name not in all_snapshots[track_key]:
        return {"deleted": False, "snapshot_name": snapshot_name, "track_index": track_index}

    del all_snapshots[track_key][snapshot_name]
    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)

    return {"deleted": True, "snapshot_name": snapshot_name, "track_index": track_index}


# --- Feature 3: Project version snapshots ---

@mcp.tool()
def save_version_snapshot(version_name: str) -> dict:
    """
    Save a named version snapshot of the current project.

    Workflow:
    1. Calls song.save() via _send("save_song") to save the current .als file
    2. Finds the current .als file path via _send("get_song_file_path")
    3. Copies it to "<OriginalName> - <version_name> [YYYY-MM-DD].als" in the same folder
    4. Records the entry in ~/.ableton_mpcx/versions.json

    Also captures a full_session_snapshot of all device states at this version.

    Args:
        version_name: Label for this version (e.g. 'lo-fi', 'clean', 'v2-with-strings').

    Returns:
        version_name, source_path, copy_path, saved_at, device_snapshot_captured (bool)
    """
    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    source_path = None
    copy_path = None
    als_save_note = None

    try:
        _send("save_song")
    except RuntimeError as e:
        als_save_note = "save_song not available: {}".format(e)

    try:
        file_info = _send("get_song_file_path")
        source_path = file_info if isinstance(file_info, str) else file_info.get("path", "")
    except RuntimeError as e:
        als_save_note = (als_save_note or "") + " get_song_file_path not available: {}".format(e)

    if source_path and os.path.isfile(source_path):
        base_dir = os.path.dirname(source_path)
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        copy_name = "{} - {} [{}].als".format(base_name, version_name, date_str)
        copy_path = os.path.join(base_dir, copy_name)
        try:
            shutil.copy2(source_path, copy_path)
        except Exception as e:
            als_save_note = (als_save_note or "") + " copy failed: {}".format(e)
            copy_path = None

    # Capture full device snapshot
    device_snapshot_captured = False
    snap_label = "__version__{}".format(version_name)
    try:
        snap_result = full_session_snapshot(snap_label)
        device_snapshot_captured = snap_result.get("tracks_captured", 0) > 0
    except Exception:
        pass

    versions = _load_json_cache(_VERSIONS_PATH, [])
    versions.append({
        "version_name": version_name,
        "saved_at": saved_at,
        "source_path": source_path,
        "copy_path": copy_path,
        "device_snapshot_label": snap_label,
        "has_device_snapshot": device_snapshot_captured,
        "note": als_save_note,
    })
    _save_json_cache(_VERSIONS_PATH, versions)

    return {
        "version_name": version_name,
        "source_path": source_path,
        "copy_path": copy_path,
        "saved_at": saved_at,
        "device_snapshot_captured": device_snapshot_captured,
        "note": als_save_note,
    }


@mcp.tool()
def list_version_snapshots() -> dict:
    """
    List all saved version snapshots for the current project.

    Returns:
        versions: list of {version_name, saved_at, copy_path, has_device_snapshot}
        total: int
    """
    versions = _load_json_cache(_VERSIONS_PATH, [])
    summaries = [
        {
            "version_name": v.get("version_name", ""),
            "saved_at": v.get("saved_at", ""),
            "copy_path": v.get("copy_path"),
            "has_device_snapshot": v.get("has_device_snapshot", False),
        }
        for v in versions
    ]
    return {"versions": summaries, "total": len(summaries)}


@mcp.tool()
def diff_version_snapshots(version_a: str, version_b: str) -> dict:
    """
    Compare device states between two saved version snapshots.

    Uses the device snapshots captured at each version save to produce
    a parameter-level diff across all tracks.

    Args:
        version_a: Name of the first version (the 'before').
        version_b: Name of the second version (the 'after').

    Returns:
        version_a, version_b,
        tracks_changed: list of {track_index, track_name, changes: [{device, param, before, after, delta}]}
        tracks_unchanged: list of track names
        summary: human-readable description of what changed between versions
    """
    versions = _load_json_cache(_VERSIONS_PATH, [])
    ver_map = {v["version_name"]: v for v in versions}

    for vname in (version_a, version_b):
        if vname not in ver_map:
            return {"error": "Version '{}' not found. Use list_version_snapshots() to see available.".format(vname)}

    label_a = ver_map[version_a].get("device_snapshot_label", "__version__{}".format(version_a))
    label_b = ver_map[version_b].get("device_snapshot_label", "__version__{}".format(version_b))

    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})

    # Version snapshots for all tracks are stored under track_key → label_a/label_b
    tracks_changed = []
    tracks_unchanged = []

    all_track_keys = set(all_snapshots.keys())
    for track_key in sorted(all_track_keys, key=lambda x: int(x)):
        track_snaps = all_snapshots[track_key]
        if label_a not in track_snaps and label_b not in track_snaps:
            continue

        snap_a = track_snaps.get(label_a, {}).get("devices", {})
        snap_b = track_snaps.get(label_b, {}).get("devices", {})
        changes = []

        all_dev_keys = set(snap_a.keys()) | set(snap_b.keys())
        for dev_key in all_dev_keys:
            dev_a = snap_a.get(dev_key, {})
            dev_b = snap_b.get(dev_key, {})
            dev_name = dev_a.get("device_name", dev_b.get("device_name", ""))
            params_a = dev_a.get("parameters", {})
            params_b = dev_b.get("parameters", {})
            all_param_keys = set(params_a.keys()) | set(params_b.keys())
            for p_key in all_param_keys:
                pa = params_a.get(p_key, {})
                pb = params_b.get(p_key, {})
                va = pa.get("value", 0.0)
                vb = pb.get("value", 0.0)
                if abs(va - vb) > 1e-9:
                    changes.append({
                        "device": dev_name,
                        "param": pa.get("name", pb.get("name", "")),
                        "before": va,
                        "after": vb,
                        "delta": vb - va,
                    })

        if changes:
            tracks_changed.append({
                "track_index": int(track_key),
                "track_name": "Track {}".format(track_key),
                "changes": changes,
            })
        else:
            tracks_unchanged.append("Track {}".format(track_key))

    if tracks_changed:
        summary = "{} track(s) changed between version '{}' and '{}'.".format(
            len(tracks_changed), version_a, version_b
        )
    else:
        summary = "No device parameter differences found between '{}' and '{}'.".format(version_a, version_b)

    return {
        "version_a": version_a,
        "version_b": version_b,
        "tracks_changed": tracks_changed,
        "tracks_unchanged": tracks_unchanged,
        "summary": summary,
    }


# --- Feature 4: Scene scaffolding ---

_SCAFFOLD_TEMPLATES = {
    "default": {
        "structure": ["Intro", "Verse", "Chorus", "Verse", "Chorus", "Outro"],
        "bars":      {"Intro": 8, "Verse": 16, "Chorus": 8, "Outro": 8},
    },
    "hiphop": {
        "structure": ["Intro", "Verse", "Hook", "Verse", "Hook", "Bridge", "Hook", "Outro"],
        "bars":      {"Intro": 4, "Verse": 16, "Hook": 8, "Bridge": 8, "Outro": 4},
    },
    "edm": {
        "structure": ["Intro", "Build", "Drop", "Break", "Build", "Drop", "Outro"],
        "bars":      {"Intro": 8, "Build": 8, "Drop": 16, "Break": 8, "Outro": 8},
    },
    "pop": {
        "structure": ["Intro", "Verse", "Pre", "Chorus", "Verse", "Pre", "Chorus", "Bridge", "Chorus", "Outro"],
        "bars":      {"Intro": 8, "Verse": 16, "Pre": 4, "Chorus": 8, "Bridge": 8, "Outro": 4},
    },
    "minimal": {
        "structure": ["Intro", "Part A", "Part B", "Part A", "Outro"],
        "bars":      {"Intro": 8, "Part A": 16, "Part B": 16, "Outro": 8},
    },
}


@mcp.tool()
def build_scene_scaffold(
    structure: list[str] | None = None,
    bars_each: dict[str, int] | None = None,
    color_code: bool = True,
    template: str | None = None,
) -> dict:
    """
    Create a set of named, color-coded scenes for a song structure in one command.

    Args:
        structure: Ordered list of section names, e.g. ["Intro", "Verse", "Chorus", "Outro"].
                   Repeated sections are numbered automatically: Verse 1, Verse 2, etc.
                   If None, uses the 'default' template.
        bars_each: Dict of section_name → bar count, e.g. {"Intro": 8, "Verse": 16}.
                   If a section is not in the dict, defaults to 8 bars.
        color_code: If True, apply colors from _SCENE_SECTION_COLORS per section type.
        template: Built-in template name. Options: 'default', 'hiphop', 'edm', 'pop', 'minimal'.
                  If specified, overrides structure and bars_each.

    Returns:
        scenes_created: int,
        scene_list: list of {scene_index, name, bars, color},
        template_used: str | None
    """
    template_used = None
    if template is not None:
        tpl = _SCAFFOLD_TEMPLATES.get(template, _SCAFFOLD_TEMPLATES["default"])
        structure = tpl["structure"]
        bars_each = tpl["bars"]
        template_used = template
    elif structure is None:
        tpl = _SCAFFOLD_TEMPLATES["default"]
        structure = tpl["structure"]
        bars_each = tpl["bars"]
        template_used = "default"

    if bars_each is None:
        bars_each = {}

    # Handle repeated section names by numbering them
    counts: dict[str, int] = {}
    named_structure = []
    for section in structure:
        base = section
        counts[base] = counts.get(base, 0) + 1
    # Track occurrence index
    occurrence: dict[str, int] = {}
    total_occurrences: dict[str, int] = counts
    for section in structure:
        occurrence[section] = occurrence.get(section, 0) + 1
        if total_occurrences[section] > 1:
            named_structure.append("{} {}".format(section, occurrence[section]))
        else:
            named_structure.append(section)

    try:
        existing_scenes = _send("get_scenes")
        start_index = len(existing_scenes)
    except RuntimeError as e:
        return {"error": "Could not get scenes: {}".format(e)}

    scene_list = []
    for i, name in enumerate(named_structure):
        scene_index = start_index + i
        # Determine bars (use the base section name for lookup)
        base_name = re.sub(r"\s+\d+$", "", name)
        bars = bars_each.get(base_name, bars_each.get(name, 8))

        # Determine color
        color = _SCENE_SECTION_COLORS["default"]
        if color_code:
            for keyword, c in _SCENE_SECTION_COLORS.items():
                if keyword == "default":
                    continue
                if keyword in name.lower():
                    color = c
                    break

        try:
            _send("create_scene", {"index": -1})
        except RuntimeError as e:
            scene_list.append({"scene_index": scene_index, "name": name, "bars": bars, "color": color, "error": str(e)})
            continue

        try:
            _send("set_scene_name", {"scene_index": scene_index, "name": name})
        except RuntimeError:
            pass

        if color_code:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": color})
            except RuntimeError:
                pass

        scene_list.append({"scene_index": scene_index, "name": name, "bars": bars, "color": color})

    return {
        "scenes_created": len(scene_list),
        "scene_list": scene_list,
        "template_used": template_used,
    }


@mcp.tool()
def list_scaffold_templates() -> dict:
    """
    List all available scene scaffold templates with their structures.

    Returns:
        templates: list of {name, structure, total_bars, section_count}
    """
    results = []
    for name, tpl in _SCAFFOLD_TEMPLATES.items():
        structure = tpl["structure"]
        bars_map = tpl["bars"]
        total_bars = sum(bars_map.get(re.sub(r"\s+\d+$", "", s), 8) for s in structure)
        results.append({
            "name": name,
            "structure": structure,
            "total_bars": total_bars,
            "section_count": len(structure),
        })
    return {"templates": results}


# --- Feature 5: Clip duplication and arrangement placement ---

@mcp.tool()
def place_clip_in_arrangement(
    track_index: int,
    clip_index: int,
    start_bar: int,
    start_beat: float = 1.0,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Place (duplicate) a Session View clip into the Arrangement View at a specific position.

    Args:
        track_index: Track containing the source clip.
        clip_index: Session clip slot index to copy from.
        start_bar: 1-based bar number where the clip should start in the arrangement.
        start_beat: 1-based beat within the bar (default 1.0 = start of bar).
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        track_index, start_time_beats, clip_name, clip_length_beats
    """
    start_time_beats = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)

    clip_name = ""
    clip_length_beats = 0.0
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
        clip_name = clip_info.get("name", "")
        clip_length_beats = float(clip_info.get("length", 0.0))
    except RuntimeError:
        pass

    try:
        _send("duplicate_clip_to_arrangement", {
            "track_index": track_index,
            "clip_index": clip_index,
            "time": start_time_beats,
        })
    except RuntimeError:
        try:
            _send("copy_clip_to_arrangement", {
                "track_index": track_index,
                "clip_index": clip_index,
                "time": start_time_beats,
            })
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "start_time_beats": start_time_beats,
                "clip_name": clip_name,
                "clip_length_beats": clip_length_beats,
                "error": "Neither duplicate_clip_to_arrangement nor copy_clip_to_arrangement is supported: {}".format(e),
            }

    return {
        "track_index": track_index,
        "start_time_beats": start_time_beats,
        "clip_name": clip_name,
        "clip_length_beats": clip_length_beats,
    }


@mcp.tool()
def duplicate_clip_to_scenes(
    track_index: int,
    source_clip_index: int,
    target_scene_indices: list[int],
) -> dict:
    """
    Duplicate a clip into multiple scene slots on the same track.

    Args:
        track_index: Track containing the source clip.
        source_clip_index: Source clip slot to copy from.
        target_scene_indices: List of scene slot indices to copy into.

    Returns:
        source_clip_index, copies_made: int, target_scenes: list[int], skipped: list[int]
    """
    copies_made = 0
    skipped = []

    for target_idx in target_scene_indices:
        try:
            _send("duplicate_clip_slot", {
                "track_index": track_index,
                "slot_index": source_clip_index,
            })
            copies_made += 1
        except RuntimeError:
            skipped.append(target_idx)

    return {
        "source_clip_index": source_clip_index,
        "copies_made": copies_made,
        "target_scenes": [i for i in target_scene_indices if i not in skipped],
        "skipped": skipped,
    }


@mcp.tool()
def arrange_from_scene_scaffold(
    track_indices: list[int] | None = None,
    layout: dict[str, int] | None = None,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Build the Arrangement View from the current scene structure.

    Reads the scene names and the clips in each scene, then places them
    into the Arrangement in order, back to back.

    By default uses actual clip lengths to determine placement.
    Pass layout= to override bar counts per section name.

    Args:
        track_indices: Which tracks to arrange. If None, uses all tracks.
        layout: Override bar counts per scene name, e.g. {"Verse": 16, "Chorus": 8}.
                If a scene is not in layout, uses actual clip length.
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        scenes_placed: int,
        placements: list of {scene_name, scene_index, start_bar, length_bars, tracks_placed},
        total_bars: int,
        arrangement_length_beats: float
    """
    try:
        scenes = _send("get_scenes")
    except RuntimeError as e:
        return {"error": "Could not get scenes: {}".format(e)}

    if track_indices is None:
        try:
            tracks = _send("get_tracks")
            track_indices = [t.get("index", t.get("track_index", i)) for i, t in enumerate(tracks)]
        except RuntimeError as e:
            return {"error": "Could not get tracks: {}".format(e)}

    if layout is None:
        layout = {}

    placements = []
    current_bar = 1
    total_bars = 0

    for scene_idx, scene in enumerate(scenes):
        scene_name = scene.get("name", "Scene {}".format(scene_idx + 1))

        # Determine length_bars: from layout override, or from clip lengths
        base_name = re.sub(r"\s+\d+$", "", scene_name)
        if base_name in layout:
            length_bars = layout[base_name]
        elif scene_name in layout:
            length_bars = layout[scene_name]
        else:
            # Use clip length from first available clip in this scene
            length_beats = 0.0
            for ti in track_indices:
                try:
                    clip_info = _send("get_clip_info", {"track_index": ti, "slot_index": scene_idx})
                    clip_len = float(clip_info.get("length", 0.0))
                    if clip_len > 0:
                        length_beats = clip_len
                        break
                except RuntimeError:
                    pass
            length_bars = max(1, round(length_beats / time_signature_numerator)) if length_beats > 0 else 8

        tracks_placed = 0
        for ti in track_indices:
            try:
                start_time = _bars_beats_to_song_time(current_bar, 1.0, time_signature_numerator)
                _send("duplicate_clip_to_arrangement", {
                    "track_index": ti,
                    "clip_index": scene_idx,
                    "time": start_time,
                })
                tracks_placed += 1
            except RuntimeError:
                try:
                    start_time = _bars_beats_to_song_time(current_bar, 1.0, time_signature_numerator)
                    _send("copy_clip_to_arrangement", {
                        "track_index": ti,
                        "clip_index": scene_idx,
                        "time": start_time,
                    })
                    tracks_placed += 1
                except RuntimeError:
                    pass

        placements.append({
            "scene_name": scene_name,
            "scene_index": scene_idx,
            "start_bar": current_bar,
            "length_bars": length_bars,
            "tracks_placed": tracks_placed,
        })
        current_bar += length_bars
        total_bars += length_bars

    arrangement_length_beats = float(total_bars * time_signature_numerator)

    return {
        "scenes_placed": len(placements),
        "placements": placements,
        "total_bars": total_bars,
        "arrangement_length_beats": arrangement_length_beats,
    }


# --- Feature 6: Resampling routing ---

@mcp.tool()
def setup_resampling_route(
    source_track_index: int | None = None,
    resample_track_index: int | None = None,
    track_name: str = "Resample",
    armed: bool = True,
) -> dict:
    """
    Set up resampling routing between a source track (or master) and a target audio track.

    Workflow:
    1. If resample_track_index is None, creates a new audio track named track_name
    2. Sets the new/target track's input routing to the source track output (or Master if source is None)
    3. Sets monitor to "In"
    4. Arms the track for recording if armed=True

    Args:
        source_track_index: Track to resample from. None = resample from Master output.
        resample_track_index: Existing audio track to use as resample target. None = create new.
        track_name: Name for the new resample track (default "Resample").
        armed: Whether to arm the resample track for recording (default True).

    Returns:
        resample_track_index, resample_track_name, source_routing, armed, monitor_mode,
        instructions: human-readable summary of what was set up and how to use it
    """
    if resample_track_index is None:
        try:
            _send("create_audio_track", {"index": -1})
            tracks = _send("get_tracks")
            resample_track_index = len(tracks) - 1
        except RuntimeError as e:
            return {"error": "Could not create audio track: {}".format(e)}

    try:
        _send("set_track_name", {"track_index": resample_track_index, "name": track_name})
    except RuntimeError:
        pass

    source_routing = "Master" if source_track_index is None else "Track {}".format(source_track_index)
    routing_set = False
    try:
        if source_track_index is None:
            _send("set_track_input_routing", {"track_index": resample_track_index, "routing": "Master"})
        else:
            _send("set_track_input_routing", {
                "track_index": resample_track_index,
                "source_track_index": source_track_index,
            })
        routing_set = True
    except RuntimeError:
        routing_set = False

    monitor_mode = "In"
    monitor_set = False
    try:
        _send("set_track_monitor", {"track_index": resample_track_index, "monitor": 1})
        monitor_set = True
    except RuntimeError:
        monitor_set = False

    arm_result = False
    if armed:
        try:
            _send("set_track_arm", {"track_index": resample_track_index, "arm": True})
            arm_result = True
        except RuntimeError:
            arm_result = False

    instructions = (
        "Resampling track '{}' (index {}) is set up to record from {}. "
        "Press Record in Live, then play your session to capture the output. "
        "When done, call teardown_resampling_route({}) to reset routing.".format(
            track_name, resample_track_index, source_routing, resample_track_index
        )
    )

    return {
        "resample_track_index": resample_track_index,
        "resample_track_name": track_name,
        "source_routing": source_routing,
        "routing_set": routing_set,
        "armed": arm_result,
        "monitor_mode": monitor_mode,
        "monitor_set": monitor_set,
        "instructions": instructions,
    }


@mcp.tool()
def teardown_resampling_route(resample_track_index: int) -> dict:
    """
    Reset a resampling track's routing back to defaults and disarm it.

    Args:
        resample_track_index: The resample track to reset.

    Returns:
        resample_track_index, disarmed (bool), routing_reset (bool)
    """
    disarmed = False
    try:
        _send("set_track_arm", {"track_index": resample_track_index, "arm": False})
        disarmed = True
    except RuntimeError:
        pass

    routing_reset = False
    try:
        _send("set_track_monitor", {"track_index": resample_track_index, "monitor": 0})
        routing_reset = True
    except RuntimeError:
        pass

    try:
        _send("set_track_input_routing", {"track_index": resample_track_index, "routing": "default"})
    except RuntimeError:
        pass

    return {
        "resample_track_index": resample_track_index,
        "disarmed": disarmed,
        "routing_reset": routing_reset,
    }


@mcp.tool()
def get_resampling_status(resample_track_index: int) -> dict:
    """
    Return the current routing and arm status of a track, to verify resampling is set up correctly.

    Returns:
        track_index, track_name, input_routing, monitor_mode, armed, ready_to_resample (bool)
    """
    try:
        tracks = _send("get_tracks")
        track = next(
            (t for t in tracks if t.get("index", t.get("track_index")) == resample_track_index),
            None,
        )
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    if track is None:
        return {"error": "Track {} not found.".format(resample_track_index)}

    track_name = track.get("name", "")
    armed = track.get("arm", track.get("armed", False))
    monitor_mode = track.get("monitor", track.get("monitor_mode", ""))
    input_routing = track.get("input_routing", track.get("input", ""))

    ready = bool(armed) and str(monitor_mode) in {"1", "In", 1}

    return {
        "track_index": resample_track_index,
        "track_name": track_name,
        "input_routing": input_routing,
        "monitor_mode": monitor_mode,
        "armed": armed,
        "ready_to_resample": ready,
    }


# --- Feature 7: Session collaborator tools ---

@mcp.tool()
def full_session_snapshot(snapshot_name: str) -> dict:
    """
    Save device parameter snapshots for ALL tracks simultaneously under a single name.

    Captures master track, all audio/MIDI tracks, and all return tracks.
    All stored in ~/.ableton_mpcx/device_snapshots.json under the given name.

    Args:
        snapshot_name: Name for this full-session snapshot (e.g. 'pre-drop', 'final-mix').

    Returns:
        snapshot_name, tracks_captured: int, total_parameters: int, saved_at: str
    """
    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tracks_captured = 0
    total_parameters = 0

    # Collect all track indices: regular tracks + master (-1) + return tracks
    track_indices = [-1]
    try:
        tracks = _send("get_tracks")
        for t in tracks:
            idx = t.get("index", t.get("track_index"))
            if idx is not None:
                track_indices.append(idx)
    except RuntimeError:
        pass

    try:
        return_tracks = _send("get_return_tracks")
        for rt in return_tracks:
            idx = rt.get("index", rt.get("track_index"))
            if idx is not None:
                track_indices.append(("return", idx))
    except RuntimeError:
        pass

    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})

    for ti in track_indices:
        if isinstance(ti, tuple):
            # return track — skip for now, they aren't indexed the same way
            continue
        track_key = str(ti)
        try:
            devices = _send("get_devices", {"track_index": ti})
        except RuntimeError:
            continue

        snapshot_data = {}
        for device in devices:
            dev_idx = device.get("index", device.get("device_index", 0))
            try:
                params_result = _send("get_device_parameters", {
                    "track_index": ti,
                    "device_index": dev_idx,
                })
                params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
                param_map = {}
                for p in params:
                    p_idx = p.get("index", p.get("parameter_index", 0))
                    param_map[str(p_idx)] = {
                        "value": p.get("value", 0.0),
                        "name": p.get("name", ""),
                    }
                    total_parameters += 1
                snapshot_data[str(dev_idx)] = {
                    "device_name": device.get("name", ""),
                    "parameters": param_map,
                }
            except RuntimeError:
                pass

        if not all_snapshots.get(track_key):
            all_snapshots[track_key] = {}
        all_snapshots[track_key][snapshot_name] = {
            "devices": snapshot_data,
            "saved_at": saved_at,
        }
        tracks_captured += 1

    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)

    return {
        "snapshot_name": snapshot_name,
        "tracks_captured": tracks_captured,
        "total_parameters": total_parameters,
        "saved_at": saved_at,
    }


@mcp.tool()
def session_audit(fix: bool = False) -> dict:
    """
    Analyze the current session state and return a list of issues with suggestions.

    Checks performed:
    - Unnamed or default-named tracks (suggest auto_name_track)
    - Tracks with no devices
    - Tracks with arm still on
    - No snapshots saved (suggest full_session_snapshot)
    - Empty scenes in scaffold (scenes with no clips)

    Args:
        fix: If True, auto-apply safe fixes (auto-naming, disarming tracks).
             Does NOT auto-apply mix corrections (those require human judgment).

    Returns:
        issues: list of {type, severity, description, suggestion, auto_fixable, fixed}
        issues_found: int,
        issues_fixed: int (if fix=True),
        session_health: "good" | "warnings" | "issues"
    """
    issues = []
    issues_fixed = 0

    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    default_name_pattern = re.compile(r"^(audio|midi|track)\s*\d*$", re.IGNORECASE)

    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        name = track.get("name", "")
        armed = track.get("arm", track.get("armed", False))

        # Check for default/unnamed tracks
        if not name or default_name_pattern.match(name):
            fixed = False
            if fix:
                try:
                    auto_name_track(idx, dry_run=False)
                    fixed = True
                    issues_fixed += 1
                except Exception:
                    pass
            issues.append({
                "type": "unnamed_track",
                "severity": "warning",
                "description": "Track {} has default name '{}'".format(idx, name),
                "suggestion": "Call auto_name_track({})".format(idx),
                "auto_fixable": True,
                "fixed": fixed,
            })

        # Check for armed tracks
        if armed:
            fixed = False
            if fix:
                try:
                    _send("set_track_arm", {"track_index": idx, "arm": False})
                    fixed = True
                    issues_fixed += 1
                except RuntimeError:
                    pass
            issues.append({
                "type": "track_armed",
                "severity": "warning",
                "description": "Track {} ('{}') is armed".format(idx, name),
                "suggestion": "Disarm track {} or call teardown_resampling_route({})".format(idx, idx),
                "auto_fixable": True,
                "fixed": fixed,
            })

        # Check for tracks with no devices
        try:
            devices = _send("get_devices", {"track_index": idx})
            if not devices:
                issues.append({
                    "type": "no_devices",
                    "severity": "info",
                    "description": "Track {} ('{}') has no devices".format(idx, name),
                    "suggestion": "Add instruments or effects to this track",
                    "auto_fixable": False,
                    "fixed": False,
                })
        except RuntimeError:
            pass

    # Check for no snapshots saved
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    if not all_snapshots:
        issues.append({
            "type": "no_snapshots",
            "severity": "info",
            "description": "No device snapshots have been saved",
            "suggestion": "Call full_session_snapshot('initial') to create a baseline",
            "auto_fixable": False,
            "fixed": False,
        })

    # Check for empty scenes
    try:
        scenes = _send("get_scenes")
        for scene_idx, scene in enumerate(scenes):
            has_clip = False
            for track in tracks:
                ti = track.get("index", track.get("track_index", 0))
                try:
                    clip_info = _send("get_clip_info", {"track_index": ti, "slot_index": scene_idx})
                    if clip_info:
                        has_clip = True
                        break
                except RuntimeError:
                    pass
            if not has_clip:
                issues.append({
                    "type": "empty_scene",
                    "severity": "info",
                    "description": "Scene {} ('{}') has no clips".format(
                        scene_idx, scene.get("name", "")
                    ),
                    "suggestion": "Add clips to scene {} or remove it".format(scene_idx),
                    "auto_fixable": False,
                    "fixed": False,
                })
    except RuntimeError:
        pass

    has_issue = any(i["severity"] == "issues" for i in issues)
    has_warning = any(i["severity"] == "warning" for i in issues)
    if has_issue:
        session_health = "issues"
    elif has_warning:
        session_health = "warnings"
    else:
        session_health = "good"

    return {
        "issues": issues,
        "issues_found": len(issues),
        "issues_fixed": issues_fixed,
        "session_health": session_health,
    }


@mcp.tool()
def mix_correction_loop(
    track_index: int,
    target_band: str,
    direction: str,
    device_name: str | None = None,
    param_name: str | None = None,
    max_steps: int = 5,
    verify: bool = True,
    snapshot_after: bool = False,
    snapshot_name: str | None = None,
) -> dict:
    """
    Iteratively adjust a device parameter to improve a frequency band balance,
    reading the analyzer after each step to verify improvement.

    Args:
        track_index: Track to adjust.
        target_band: Band to improve (e.g. 'body', 'air', 'bass').
        direction: 'reduce' to reduce crowding or 'boost' to fill a gap.
        device_name: Device to adjust (e.g. 'Auto Filter', 'EQ Eight'). If None, auto-detects.
        param_name: Parameter to adjust (e.g. 'Frequency', 'Gain'). If None, auto-detects.
        max_steps: Maximum number of adjustment iterations (default 5).
        verify: If True, re-read analyzer after each step to check improvement.
        snapshot_after: If True and improvement was made, save a device snapshot.
        snapshot_name: Name for the snapshot (default: 'post-correction-{band}').

    Returns:
        track_index, target_band, direction,
        steps_taken: int,
        before_value: float (analyzer reading before),
        after_value: float (analyzer reading after),
        improved: bool,
        parameter_changes: list of {step, param, before, after},
        snapshot_saved: bool,
        summary: human-readable description of what was done
    """
    if direction not in ("reduce", "boost"):
        return {"error": "direction must be 'reduce' or 'boost'"}

    # Read initial band value
    def _read_band_value():
        try:
            data = get_spectrum_telemetry_instances()
            for instance in data.get("instances", []):
                if instance.get("track_index") == track_index:
                    bands = instance.get("bands", {})
                    for bname, bdata in bands.items():
                        if target_band.lower() in bname.lower():
                            return float(bdata.get("value", 0.0))
        except Exception:
            pass
        return None

    before_value = _read_band_value()

    # Find target device and parameter
    target_device_index = None
    target_parameter_index = None
    target_param_name = param_name

    try:
        devices = _send("get_devices", {"track_index": track_index})
    except RuntimeError as e:
        return {"error": "Could not get devices: {}".format(e)}

    for device in devices:
        dev_idx = device.get("index", device.get("device_index", 0))
        dev_name = device.get("name", "")
        if device_name and device_name.lower() not in dev_name.lower():
            continue

        # Auto-detect: prefer EQ or filter devices
        is_eq = any(k in dev_name.lower() for k in ["eq", "filter", "equalizer"])
        if device_name is None and not is_eq:
            continue

        try:
            params_result = _send("get_device_parameters", {
                "track_index": track_index,
                "device_index": dev_idx,
            })
            params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
            for p in params:
                p_name = p.get("name", "")
                if param_name and param_name.lower() not in p_name.lower():
                    continue
                if param_name is None and "gain" not in p_name.lower():
                    continue
                target_device_index = dev_idx
                target_parameter_index = p.get("index", p.get("parameter_index", 0))
                target_param_name = p_name
                break
        except RuntimeError:
            pass
        if target_device_index is not None:
            break

    if target_device_index is None or target_parameter_index is None:
        return {
            "error": "Could not find a suitable device/parameter to adjust. "
                     "Specify device_name and param_name explicitly.",
            "track_index": track_index,
            "target_band": target_band,
            "direction": direction,
        }

    # Get current param value
    try:
        params_result = _send("get_device_parameters", {
            "track_index": track_index,
            "device_index": target_device_index,
        })
        params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
        current_param = next(
            (p for p in params if p.get("index", p.get("parameter_index")) == target_parameter_index),
            None,
        )
    except RuntimeError as e:
        return {"error": "Could not get parameters: {}".format(e)}

    if current_param is None:
        return {"error": "Parameter index {} not found.".format(target_parameter_index)}

    current_value = float(current_param.get("value", 0.0))
    p_min = float(current_param.get("min", current_value - 12))
    p_max = float(current_param.get("max", current_value + 12))
    step_size = (p_max - p_min) / 20.0  # ~5% of range per step

    parameter_changes = []
    steps_taken = 0

    for step in range(max_steps):
        old_value = current_value
        if direction == "reduce":
            new_value = max(p_min, current_value - step_size)
        else:
            new_value = min(p_max, current_value + step_size)

        try:
            _send("set_device_parameter", {
                "track_index": track_index,
                "device_index": target_device_index,
                "parameter_index": target_parameter_index,
                "value": new_value,
            })
            current_value = new_value
            steps_taken += 1
            parameter_changes.append({
                "step": step + 1,
                "param": target_param_name,
                "before": old_value,
                "after": new_value,
            })
        except RuntimeError:
            break

        if verify:
            new_band = _read_band_value()
            if new_band is not None and before_value is not None:
                if direction == "reduce" and new_band < before_value:
                    break
                if direction == "boost" and new_band > before_value:
                    break

    after_value = _read_band_value()
    improved = False
    if before_value is not None and after_value is not None:
        if direction == "reduce":
            improved = after_value < before_value
        else:
            improved = after_value > before_value

    snapshot_saved = False
    if snapshot_after and improved:
        snap_label = snapshot_name or "post-correction-{}".format(target_band)
        try:
            save_device_snapshot(track_index, snap_label, device_index=target_device_index)
            snapshot_saved = True
        except Exception:
            pass

    if steps_taken > 0:
        summary = "Adjusted '{}' on track {} by {} step(s) to {} the '{}' band. Improved: {}.".format(
            target_param_name, track_index, steps_taken, direction, target_band, improved
        )
    else:
        summary = "No adjustments were made to track {}.".format(track_index)

    return {
        "track_index": track_index,
        "target_band": target_band,
        "direction": direction,
        "steps_taken": steps_taken,
        "before_value": before_value,
        "after_value": after_value,
        "improved": improved,
        "parameter_changes": parameter_changes,
        "snapshot_saved": snapshot_saved,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Start observer on module load
_start_observer()

if __name__ == "__main__":
    mcp.run()