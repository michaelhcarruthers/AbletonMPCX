"""Transport and navigation tools — playback, cue points, and session view selection."""
from __future__ import annotations

from helpers import _send


def get_app_version() -> dict:
    """Return the running Ableton Live version."""
    return _send("get_app_version")

def start_playing() -> dict:
    """Start playback from the insert marker."""
    return _send("start_playing")

def stop_playing() -> dict:
    """Stop playback."""
    return _send("stop_playing")

def continue_playing() -> dict:
    """Continue playback from the current position."""
    return _send("continue_playing")

def play_selection() -> dict:
    """Play the current selection in the Arrangement."""
    return _send("play_selection")

def tap_tempo() -> dict:
    """Send a tap tempo pulse."""
    return _send("tap_tempo")

def undo() -> dict:
    """Undo the last operation."""
    return _send("undo")

def redo() -> dict:
    """Redo the last undone operation."""
    return _send("redo")

def capture_midi(destination: int = 0) -> dict:
    """Capture recently played MIDI. destination: 0=auto, 1=session, 2=arrangement."""
    return _send("capture_midi", {"destination": destination})

def capture_and_insert_scene() -> dict:
    """Capture currently playing clips into a new scene."""
    return _send("capture_and_insert_scene")

def jump_by(beats: float) -> dict:
    """Jump the playback position by the given number of beats (positive or negative)."""
    return _send("jump_by", {"beats": beats})

def jump_to_next_cue() -> dict:
    """Jump to the next cue point."""
    return _send("jump_to_next_cue")

def jump_to_prev_cue() -> dict:
    """Jump to the previous cue point."""
    return _send("jump_to_prev_cue")

def jump_to_cue_point(index: int) -> dict:
    """Jump to the cue point at index."""
    return _send("jump_to_cue_point", {"index": index})

def stop_all_clips(quantized: int = 1) -> dict:
    """Stop all clips. quantized=0 stops immediately regardless of quantization."""
    return _send("stop_all_clips", {"quantized": quantized})

def get_cue_points() -> list:
    """Return all cue points as a list of {name, time} dicts."""
    return _send("get_cue_points")

def set_or_delete_cue() -> dict:
    """Toggle (create or delete) a cue point at the current playback position."""
    return _send("set_or_delete_cue")

def re_enable_automation() -> dict:
    """Re-enable automation that has been overridden."""
    return _send("re_enable_automation")

def get_follow_song() -> dict:
    """Return whether Follow Song is enabled."""
    return _send("get_follow_song")

def set_follow_song(follow_song: bool) -> dict:
    """Enable or disable Follow Song."""
    return _send("set_follow_song", {"follow_song": follow_song})

def get_selected_track() -> dict:
    """Return the currently selected track index and name."""
    return _send("get_selected_track")

def set_selected_track(track_index: int) -> dict:
    """Select the track at track_index."""
    return _send("set_selected_track", {"track_index": track_index})

def get_selected_scene() -> dict:
    """Return the currently selected scene index and name."""
    return _send("get_selected_scene")

def set_selected_scene(scene_index: int) -> dict:
    """Select the scene at scene_index."""
    return _send("set_selected_scene", {"scene_index": scene_index})
