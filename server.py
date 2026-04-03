#!/usr/bin/env python3
"""
AbletonMPCX MCP Server
Bridges the MCP protocol to the Ableton Remote Script running inside Live.
"""
from __future__ import annotations

import json
import socket
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


def _send(command: str, params: dict[str, Any] | None = None) -> Any:
    payload = json.dumps({"command": command, "params": params or {}}).encode()
    response = None
    with _ableton_socket() as sock:
        sock.sendall(payload)
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            try:
                response = json.loads(b"".join(chunks).decode())
                break
            except json.JSONDecodeError:
                continue
    if response is None:
        raise RuntimeError("No valid JSON response received from Ableton")
    if response.get("status") != "ok":
        raise RuntimeError(f"Ableton error: {response.get('error', 'unknown')}")
    return response.get("result")


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
def get_track_names(include_returns: bool = False, include_master: bool = False) -> list:
    """
    Return a lightweight list of all track names and their indices.
    Much faster than get_tracks() when you only need names.

    Args:
        include_returns: If True, also include return tracks (marked with is_return=True).
        include_master: If True, also include the master track at index -1.

    Returns:
        List of dicts with 'index' and 'name' keys.
        Use the returned indices with any track_index parameter.
        Return tracks (is_return=True) use a separate 0-based index for return_track parameters.
        Master track is always at index -1.
    """
    return _send("get_track_names", {
        "include_returns": include_returns,
        "include_master": include_master,
    })

@mcp.tool()
def get_track_info(track_index: int) -> dict:
    """Return full details for the track at track_index, including clip slots and devices. Use track_index=-1 to target the master track."""
    return _send("get_track_info", {"track_index": track_index})

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
    Use track_index=-1 to target the master track.

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
                     Use -1 for the master track.
        device_name: Display name of the device (case-insensitive substring).

    Returns:
        dict with 'device_name' key confirming the matched device name.
    """
    return _send("add_native_device", {"track_index": track_index, "device_name": device_name})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()