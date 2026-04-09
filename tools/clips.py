"""Clip tools — clip slots, clips, scenes, clip notes, and automation envelopes."""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

import helpers
from helpers import mcp, _send, _send_silent

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
def get_clip_playing_state(track_index: int, slot_index: int) -> dict:
    """Return the playing state of a clip slot."""
    return _send("get_clip_playing_state", {"track_index": track_index, "slot_index": slot_index})


@mcp.tool()
def get_clip_info(track_index: int, slot_index: int) -> dict:
    """Return full details for the clip at (track_index, slot_index)."""
    return _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def get_clip_playing_position(track_index: int, slot_index: int) -> dict:
    """Return the current playhead position within the clip (in beats). Only meaningful while the clip is playing."""
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
def set_clip_color_batch(updates: list) -> dict:
    """Set the color of multiple clips in a single round trip."""
    return _send("set_clip_color_batch", {"updates": updates})

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
    """Set the velocity amount for a MIDI clip (-1.0 to 1.0). Controls how much note velocity affects clip volume."""
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
    """Return all follow action properties for the clip at (track_index, slot_index)."""
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
    """Set follow action properties on the clip at (track_index, slot_index)."""
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
    """Return all automation envelopes present on a clip."""
    return _send("get_clip_envelopes", {"track_index": track_index, "slot_index": slot_index})


@mcp.tool()
def get_clip_envelope(track_index: int, slot_index: int, envelope_index: int) -> dict:
    """Return all automation points for one envelope on a clip."""
    return _send("get_clip_envelope", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
    })


@mcp.tool()
def clear_clip_envelope(track_index: int, slot_index: int, envelope_index: int) -> dict:
    """Clear all automation points from a clip envelope."""
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
    """Insert a single automation point into a clip envelope."""
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
    """Replace all automation points in a clip envelope atomically."""
    return _send("set_clip_envelope_points", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
        "points": points,
    })

@mcp.tool()
def get_notes(track_index: int, slot_index: int) -> dict:
    """Return all MIDI notes in the clip at (track_index, slot_index)."""
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
        if not clip_info.get("is_midi_clip", False):
            return {"notes": [], "note_count": 0}
    except Exception as exc:
        logger.debug("Could not check is_midi_clip for track %s slot %s: %s", track_index, slot_index, exc)
    return _send("get_notes", {"track_index": track_index, "slot_index": slot_index})

@mcp.tool()
def add_notes(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """Add MIDI notes to the clip. Each note dict requires: pitch (int 0-127), start_time (float beats), duration (float..."""
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
        if not clip_info.get("is_midi_clip", False):
            return {"skipped": True, "reason": "not a MIDI clip"}
    except Exception as exc:
        logger.debug("Could not check is_midi_clip for track %s slot %s: %s", track_index, slot_index, exc)
        return {"skipped": True, "reason": "could not verify clip type"}
    return _send("add_notes", {"track_index": track_index, "slot_index": slot_index, "notes": notes})

@mcp.tool()
def replace_all_notes(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """Atomically replace ALL notes in a MIDI clip with the given list."""
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
        if not clip_info.get("is_midi_clip", False):
            return {"skipped": True, "reason": "not a MIDI clip"}
    except Exception as exc:
        logger.debug("Could not check is_midi_clip for track %s slot %s: %s", track_index, slot_index, exc)
        return {"skipped": True, "reason": "could not verify clip type"}
    return _send("replace_all_notes", {
        "track_index": track_index,
        "slot_index": slot_index,
        "notes": notes,
    })

@mcp.tool()
def remove_notes(track_index: int, slot_index: int, from_pitch: int = 0, pitch_span: int = 128, from_time: float = 0.0, time_span: float | None = None) -> dict:
    """Remove MIDI notes in the specified pitch/time range from the clip."""
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
        if not clip_info.get("is_midi_clip", False):
            return {"skipped": True, "reason": "not a MIDI clip"}
    except Exception as exc:
        logger.debug("Could not check is_midi_clip for track %s slot %s: %s", track_index, slot_index, exc)
        return {"skipped": True, "reason": "could not verify clip type"}
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
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
        if not clip_info.get("is_midi_clip", False):
            return {"skipped": True, "reason": "not a MIDI clip"}
    except Exception as exc:
        logger.debug("Could not check is_midi_clip for track %s slot %s: %s", track_index, slot_index, exc)
        return {"skipped": True, "reason": "could not verify clip type"}
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
def get_devices(track_index: int, is_return_track: bool = False) -> list:
    """Return all devices on a track (use track_index=-1 for master, is_return_track=True for return tracks)."""
    return _send("get_devices", {"track_index": track_index, "is_return_track": is_return_track})

@mcp.tool()
def get_device_info(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Return details for the device at (track_index, device_index). Set is_return_track=True to target a return track."""
    return _send("get_device_info", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def get_device_parameters(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Return all automatable parameters for a device (use track_index=-1 for master, is_return_track=True for return tracks)."""
    return _send("get_device_parameters", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def set_device_parameter(track_index: int, device_index: int, parameter_index: int, value: float, is_return_track: bool = False) -> dict:
    """Set a device parameter by index; value is clamped to min/max automatically (use track_index=-1 for master)."""
    return _send("set_device_parameter", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
        "is_return_track": is_return_track,
    })

@mcp.tool()
def set_device_parameter_cs(
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
    is_return_track: bool = False,
) -> dict:
    """Set a device parameter using the control surface path; forces third-party plugin UI refresh (Pro-Q 4, FabFilter, etc.)."""
    return _send("set_device_parameter_cs", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
        "is_return_track": is_return_track,
    })

@mcp.tool()
def set_device_parameter_human(
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
    unit: str = "normalized",
) -> dict:
    """Set a device parameter using human-readable units."""
    return _send("set_device_parameter_human", {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
        "unit": unit,
    })

@mcp.tool()
def set_device_enabled(track_index: int, device_index: int, enabled: bool, is_return_track: bool = False) -> dict:
    """Enable or disable a device (use track_index=-1 for master, is_return_track=True for return tracks)."""
    return _send("set_device_enabled", {"track_index": track_index, "device_index": device_index, "enabled": enabled, "is_return_track": is_return_track})

@mcp.tool()
def delete_device(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Delete a device (use track_index=-1 for master, is_return_track=True for return tracks)."""
    return _send("delete_device", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def duplicate_device(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Duplicate a device (use track_index=-1 for master, is_return_track=True for return tracks)."""
    return _send("duplicate_device", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

@mcp.tool()
def move_device(
    track_index: int,
    device_index: int,
    target_device_index: int,
    target_track_index: int | None = None,
    is_return_track: bool = False,
) -> dict:
    """Move a device to a new position within the same track."""
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
        "is_return_track": is_return_track,
    })


# ---------------------------------------------------------------------------
# Arrangement clip tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_detail_clip(include_notes: bool = True) -> dict:
    """Return info and MIDI notes for the clip currently open in Live's Detail View (the clip editor at the bottom of the..."""
    result = _send_silent("get_detail_clip", {"include_notes": include_notes})
    return result


@mcp.tool()
def list_arrangement_clips(
    track_index: int = None,
    start_bar: int = None,
    end_bar: int = None,
) -> dict:
    """List all clips in the arrangement view, optionally filtered by track or time range."""
    try:
        raw = _send("get_arrangement_clips", {})
        all_clips = raw if isinstance(raw, list) else raw.get("clips", [])
    except Exception as e:
        return {
            "clips": [],
            "total_clips": 0,
            "filtered_by": {},
            "error": str(e),
            "prompt": (
                "Could not read arrangement clips directly (Live API limitation). "
                "To read a specific arrangement clip: click it in Live's Arrangement View "
                "to open it in the Detail View, then call get_detail_clip()."
            ),
        }

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
def get_arrangement_clip_notes(
    track_index: int,
    clip_index: int,
) -> dict:
    """Read the MIDI notes from a specific arrangement clip."""
    result = _send_silent("get_arrangement_clip_notes", {
        "track_index": track_index,
        "clip_index": clip_index,
    })
    if isinstance(result, dict):
        result["note_count"] = len(result.get("notes", []))
    return result


@mcp.tool()
def delete_arrangement_clip(track_index: int, clip_index: int) -> dict:
    """Delete a clip from the Arrangement View by track index and clip index."""
    return _send("delete_arrangement_clip", {
        "track_index": track_index,
        "clip_index": clip_index,
    })


@mcp.tool()
def get_arrangement_automation(
    track_index: int,
    device_index: int | None,
    parameter_index: int,
    start_beat: float = 0.0,
    end_beat: float | None = None,
) -> dict:
    """Read automation points for a parameter in the Arrangement View."""
    params: dict = {
        "track_index": track_index,
        "parameter_index": parameter_index,
        "start_beat": start_beat,
    }
    if device_index is not None:
        params["device_index"] = device_index
    if end_beat is not None:
        params["end_beat"] = end_beat
    result = _send("get_arrangement_automation", params)
    if isinstance(result, dict):
        result["point_count"] = len(result.get("points", []))
    return result


@mcp.tool()
def clear_arrangement_automation(
    track_index: int,
    device_index: int | None,
    parameter_index: int,
    start_beat: float = 0.0,
    end_beat: float | None = None,
) -> dict:
    """Clear all automation points from a parameter in the Arrangement View within the given time range."""
    params: dict = {
        "track_index": track_index,
        "parameter_index": parameter_index,
        "start_beat": start_beat,
    }
    if device_index is not None:
        params["device_index"] = device_index
    if end_beat is not None:
        params["end_beat"] = end_beat
    return _send("clear_arrangement_automation", params)


@mcp.tool()
def get_arrangement_overview() -> dict:
    """Return a high-level structural overview of the arrangement."""
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
    # Build a set of all "occupied" bars; use math.ceil so sub-bar clips still
    # occupy at least 1 bar, consistent with how length_bars is displayed.
    occupied_bars: set[int] = set()
    for clip in all_clips:
        bar_start = clip["start_bar"]
        bar_end = bar_start + max(1, math.ceil(clip["length_bars"]))
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

