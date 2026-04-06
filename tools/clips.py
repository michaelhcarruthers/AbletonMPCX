"""Clip tools — clip slots, clips, scenes, clip notes, and automation envelopes."""
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
# Arrangement clip tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_arrangement_clips(
    track_index: int = None,
    start_bar: int = None,
    end_bar: int = None,
) -> dict:
    """
    List all clips in the arrangement view, optionally filtered by track or time range.

    Args:
        track_index: If provided, only return clips from this track
        start_bar: If provided, only return clips starting at or after this bar
        end_bar: If provided, only return clips starting before this bar

    Returns:
        clips: list of {track_index, track_name, clip_index, clip_name,
                        start_time, end_time, start_bar, length_bars,
                        is_audio, is_midi, color, muted}
        total_clips: int
        filtered_by: dict
    """
    try:
        raw = _send("get_arrangement_clips", {})
        all_clips = raw if isinstance(raw, list) else raw.get("clips", [])
    except Exception:
        all_clips = []

    clips = []
    for clip in all_clips:
        t_idx = clip.get("track_index", clip.get("track_idx", 0))
        t_name = clip.get("track_name", "")
        c_idx = clip.get("clip_index", clip.get("clip_idx", 0))
        c_name = clip.get("name", clip.get("clip_name", ""))
        start_time = float(clip.get("start_time", clip.get("start", 0.0)))
        end_time = float(clip.get("end_time", clip.get("end", start_time)))
        # Convert beat times to bars (1 bar = 4 beats for 4/4; use raw beat position as bar proxy)
        clip_start_bar = int(start_time // 4) + 1
        length_beats = max(0.0, end_time - start_time)
        length_bars = length_beats / 4.0
        is_midi = bool(clip.get("is_midi_clip", clip.get("is_midi", False)))
        is_audio = not is_midi
        color = clip.get("color", 0)
        muted = bool(clip.get("muted", clip.get("mute", False)))

        # Apply filters
        if track_index is not None and t_idx != track_index:
            continue
        if start_bar is not None and clip_start_bar < start_bar:
            continue
        if end_bar is not None and clip_start_bar >= end_bar:
            continue

        clips.append({
            "track_index": t_idx,
            "track_name": t_name,
            "clip_index": c_idx,
            "clip_name": c_name,
            "start_time": start_time,
            "end_time": end_time,
            "start_bar": clip_start_bar,
            "length_bars": length_bars,
            "is_audio": is_audio,
            "is_midi": is_midi,
            "color": color,
            "muted": muted,
        })

    filtered_by: dict[str, Any] = {}
    if track_index is not None:
        filtered_by["track_index"] = track_index
    if start_bar is not None:
        filtered_by["start_bar"] = start_bar
    if end_bar is not None:
        filtered_by["end_bar"] = end_bar

    return {
        "clips": clips,
        "total_clips": len(clips),
        "filtered_by": filtered_by,
    }


@mcp.tool()
def get_arrangement_overview() -> dict:
    """
    Return a high-level structural overview of the arrangement.

    Returns:
        total_bars: int
        tracks_with_clips: int
        clips_per_track: list of {track_index, track_name, clip_count, first_bar, last_bar}
        empty_regions: list of {start_bar, end_bar, length_bars}  # gaps with no clips on any track
        total_clips: int
        tempo: float
    """
    # Fetch all arrangement clips (unfiltered)
    clips_result = list_arrangement_clips()
    all_clips = clips_result["clips"]

    # Tempo
    try:
        song_info = _send("get_song_info", {})
        tempo = float(song_info.get("tempo", 0.0))
    except Exception:
        tempo = 0.0

    if not all_clips:
        return {
            "total_bars": 0,
            "tracks_with_clips": 0,
            "clips_per_track": [],
            "empty_regions": [],
            "total_clips": 0,
            "tempo": tempo,
        }

    # Build per-track summary
    track_map: dict[int, dict] = {}
    for clip in all_clips:
        t_idx = clip["track_index"]
        if t_idx not in track_map:
            track_map[t_idx] = {
                "track_index": t_idx,
                "track_name": clip["track_name"],
                "clip_count": 0,
                "first_bar": clip["start_bar"],
                "last_bar": clip["start_bar"],
            }
        entry = track_map[t_idx]
        entry["clip_count"] += 1
        if clip["start_bar"] < entry["first_bar"]:
            entry["first_bar"] = clip["start_bar"]
        clip_last_bar = int(clip["start_bar"] + clip["length_bars"])
        if clip_last_bar > entry["last_bar"]:
            entry["last_bar"] = clip_last_bar

    clips_per_track = sorted(track_map.values(), key=lambda x: x["track_index"])

    # Total bars = last bar across all clips
    total_bars = max(
        int(c["start_bar"] + c["length_bars"]) for c in all_clips
    )

    # Detect empty regions: bars where NO track has a clip
    # Build a set of all "occupied" bars
    occupied_bars: set[int] = set()
    for clip in all_clips:
        bar_start = clip["start_bar"]
        bar_end = int(bar_start + max(1, clip["length_bars"]))
        for b in range(bar_start, bar_end):
            occupied_bars.add(b)

    empty_regions = []
    in_gap = False
    gap_start = 1
    for bar in range(1, total_bars + 1):
        if bar not in occupied_bars:
            if not in_gap:
                in_gap = True
                gap_start = bar
        else:
            if in_gap:
                gap_end = bar
                empty_regions.append({
                    "start_bar": gap_start,
                    "end_bar": gap_end,
                    "length_bars": gap_end - gap_start,
                })
                in_gap = False
    if in_gap:
        empty_regions.append({
            "start_bar": gap_start,
            "end_bar": total_bars + 1,
            "length_bars": total_bars + 1 - gap_start,
        })

    return {
        "total_bars": total_bars,
        "tracks_with_clips": len(track_map),
        "clips_per_track": clips_per_track,
        "empty_regions": empty_regions,
        "total_clips": len(all_clips),
        "tempo": tempo,
    }

