"""Track and scene management tools — create, delete, and duplicate tracks and scenes."""
from __future__ import annotations

from helpers import _send


def create_audio_track(index: int = -1) -> dict:
    """Create a new audio track. index=-1 appends at end."""
    return _send("create_audio_track", {"index": index})

def create_midi_track(index: int = -1) -> dict:
    """Create a new MIDI track. index=-1 appends at end."""
    return _send("create_midi_track", {"index": index})

def create_return_track() -> dict:
    """Add a new return track."""
    return _send("create_return_track")

def create_scene(index: int = -1) -> dict:
    """Create a new scene. index=-1 appends at end."""
    return _send("create_scene", {"index": index})

def delete_scene(index: int) -> dict:
    """Delete the scene at index."""
    return _send("delete_scene", {"scene_index": index})

def duplicate_scene(index: int) -> dict:
    """Duplicate the scene at index."""
    return _send("duplicate_scene", {"scene_index": index})

def delete_track(track_index: int) -> dict:
    """Delete the track at track_index."""
    return _send("delete_track", {"track_index": track_index})

def delete_return_track(index: int) -> dict:
    """Delete the return track at index."""
    return _send("delete_return_track", {"index": index})

def duplicate_track(track_index: int) -> dict:
    """Duplicate the track at track_index."""
    return _send("duplicate_track", {"track_index": track_index})
