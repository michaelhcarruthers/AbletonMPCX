#!/usr/bin/env python3
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
# Observer thread (background session watcher)
# ---------------------------------------------------------------------------

_suggestion_queue: collections.deque = collections.deque(maxlen=50)
_observer_thread: threading.Thread | None = None
_observer_running: bool = False
_observer_last_snapshot: dict | None = None
_observer_lock: threading.Lock = threading.Lock()
_OBSERVER_POLL_INTERVAL: float = 8.0  # seconds between polls
_observer_last_checkpoint_log_len: int = 0  # tracks Rule 5 threshold crossings


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
# Observer thread functions
# ---------------------------------------------------------------------------

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
    global _observer_last_checkpoint_log_len
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
# Entry point
# ---------------------------------------------------------------------------

# Start observer on module load
_start_observer()

if __name__ == "__main__":
    mcp.run()