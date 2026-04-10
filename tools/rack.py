"""Rack tools — rack chains, drum pads, and rack macro randomization."""
from __future__ import annotations

from helpers import _send

def get_rack_chains(track_index: int, device_index: int, is_return_track: bool = False) -> list:
    """Return the chains of a Rack device at (track_index, device_index). Set is_return_track=True to target a return track."""
    return _send("get_rack_chains", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

def get_rack_drum_pads(track_index: int, device_index: int, is_return_track: bool = False) -> list:
    """Return the drum pads of a Drum Rack device (use is_return_track=True for return tracks)."""
    return _send("get_rack_drum_pads", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

def randomize_rack_macros(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Randomize the macro controls of a Rack device. Set is_return_track=True to target a return track."""
    return _send("randomize_rack_macros", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})

def store_rack_variation(track_index: int, device_index: int, is_return_track: bool = False) -> dict:
    """Store the current macro state as a new variation in a Rack device. Set is_return_track=True to target a return track."""
    return _send("store_rack_variation", {"track_index": track_index, "device_index": device_index, "is_return_track": is_return_track})
