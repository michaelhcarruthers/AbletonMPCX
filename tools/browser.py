"""Browser tools — browser tree navigation and device/plugin loading."""
from __future__ import annotations

from helpers import _send

def get_browser_tree(category_type: str = "all") -> dict:
    """Return the Ableton browser tree up to 2 levels deep for the given category type."""
    return _send("get_browser_tree", {"category_type": category_type})

def get_browser_items_at_path(path: str) -> dict:
    """Return browser items at the given path (e.g. 'instruments/Drum Rack')."""
    return _send("get_browser_items_at_path", {"path": path})

def load_browser_item(uri: str, track_index: int = 0, is_return_track: bool = False) -> dict:
    """Load a browser item by URI onto a track; use get_browser_items_at_path to discover valid URIs."""
    return _send("load_browser_item", {"uri": uri, "track_index": track_index, "is_return_track": is_return_track})

def load_plugin_device(
    track_index: int,
    plugin_name: str,
    plugin_format: str = "au",
) -> dict:
    """Load a third-party AU or VST plugin onto a track by name."""
    return _send("load_plugin_device", {
        "track_index": track_index,
        "plugin_name": plugin_name,
        "plugin_format": plugin_format,
    })
