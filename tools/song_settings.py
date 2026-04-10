"""Song settings tools — tempo, time signature, scale, loop, and recording settings."""
from __future__ import annotations

from typing import Any

from helpers import _send


def get_song_info() -> dict:
    """Return the current song's tempo, transport state, loop settings, etc."""
    return _send("get_song_info")

def get_song_info_minimal() -> dict:
    """Return only tempo, time signature, bar count, and playhead — no track or clip data. Use this instead of get_song_info when you only need timing context."""
    return _send("get_song_info_minimal", {})

def set_tempo(tempo: float) -> dict:
    """Set the song tempo (20-999 BPM)."""
    return _send("set_tempo", {"tempo": tempo})

def set_time_signature(numerator: int | None = None, denominator: int | None = None) -> dict:
    """Set the song time signature numerator and/or denominator."""
    params: dict[str, int] = {}
    if numerator is not None:
        params["numerator"] = numerator
    if denominator is not None:
        params["denominator"] = denominator
    return _send("set_time_signature", params)

def set_scale_name(scale_name: str) -> dict:
    """Set the scale name (e.g. 'Major', 'Minor', 'Dorian')."""
    return _send("set_scale_name", {"scale_name": scale_name})

def set_root_note(root_note: int) -> dict:
    """Set the root note for the scale (0=C, 1=C#, ..., 11=B)."""
    if not 0 <= root_note <= 11:
        raise ValueError("root_note must be between 0 and 11")
    return _send("set_root_note", {"root_note": root_note})

def set_record_mode(record_mode: bool) -> dict:
    """Enable or disable Arrangement Record."""
    return _send("set_record_mode", {"record_mode": record_mode})

def set_session_record(session_record: bool) -> dict:
    """Enable or disable Session Overdub."""
    return _send("set_session_record", {"session_record": session_record})

def set_overdub(overdub: bool) -> dict:
    """Enable or disable MIDI Arrangement Overdub."""
    return _send("set_overdub", {"overdub": overdub})

def set_metronome(metronome: bool) -> dict:
    """Enable or disable the metronome."""
    return _send("set_metronome", {"metronome": metronome})

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

def set_arrangement_position(position_beats: float) -> dict:
    """Set the arrangement playhead position in beats (absolute song time)."""
    return _send("set_arrangement_position", {"position": position_beats})

def set_back_to_arranger(value: bool) -> dict:
    """Enable or disable Back to Arranger mode."""
    return _send("set_back_to_arranger", {"value": value})

def set_swing_amount(value: float) -> dict:
    """Set the global swing amount (0.0-1.0)."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("swing_amount must be between 0.0 and 1.0")
    return _send("set_swing_amount", {"value": value})

def set_groove_amount(value: float) -> dict:
    """Set the global groove amount (0.0-1.0)."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("groove_amount must be between 0.0 and 1.0")
    return _send("set_groove_amount", {"value": value})

def set_clip_trigger_quantization(value: int) -> dict:
    """Set the global clip trigger quantization (0-13, matching Live's ClipTriggerQuantization enum)."""
    if not 0 <= value <= 13:
        raise ValueError("clip_trigger_quantization must be between 0 and 13")
    return _send("set_clip_trigger_quantization", {"value": value})

def set_midi_recording_quantization(value: int) -> dict:
    """Set the MIDI recording quantization (0-8, matching Live's RecordingQuantization enum)."""
    if not 0 <= value <= 8:
        raise ValueError("midi_recording_quantization must be between 0 and 8")
    return _send("set_midi_recording_quantization", {"value": value})

def set_scale_mode(scale_mode: bool) -> dict:
    """Enable or disable scale mode."""
    return _send("set_scale_mode", {"scale_mode": scale_mode})
