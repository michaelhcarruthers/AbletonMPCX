"""Scene management tools — scene info, naming, tempo, and color."""
from __future__ import annotations

from helpers import _send

def get_scenes() -> list:
    """Return all scenes with name, tempo, color, and state."""
    return _send("get_scenes")

def get_scene_info(scene_index: int) -> dict:
    """Return full details for the scene at scene_index."""
    return _send("get_scene_info", {"scene_index": scene_index})

def set_scene_name(scene_index: int, name: str) -> dict:
    """Rename the scene at scene_index."""
    return _send("set_scene_name", {"scene_index": scene_index, "name": name})

def set_scene_tempo(scene_index: int, tempo: float) -> dict:
    """Set the scene tempo at scene_index."""
    return _send("set_scene_tempo", {"scene_index": scene_index, "tempo": tempo})

def set_scene_color(scene_index: int, color: int) -> dict:
    """Set the scene color as an RGB integer (0x00rrggbb)."""
    return _send("set_scene_color", {"scene_index": scene_index, "color": color})
