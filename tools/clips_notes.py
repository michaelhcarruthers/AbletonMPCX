"""Clip notes tools — MIDI note read/write."""
from __future__ import annotations
import logging
from typing import Any
from helpers import mcp, _send
logger = logging.getLogger(__name__)

@mcp.tool()
def get_notes(track_index: int, slot_index: int, slim: bool = True) -> dict:
    """Return MIDI notes in the clip at (track_index, slot_index). slim=True (default) returns note_count, pitch_classes, duration_beats only. Pass slim=False to get the full note list."""
    tracks = _send("get_tracks", {"slim": True})
    if isinstance(tracks, list) and (track_index < 0 or track_index >= len(tracks)):
        return {"error": f"track_index {track_index} out of range — song has {len(tracks)} tracks"}
    return _send("get_notes", {"track_index": track_index, "slot_index": slot_index, "slim": slim})

@mcp.tool()
def add_notes(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """Add MIDI notes to a clip slot."""
    return _send("add_notes", {"track_index": track_index, "slot_index": slot_index, "notes": notes})

@mcp.tool()
def replace_all_notes(track_index: int, slot_index: int, notes: list[dict]) -> dict:
    """Atomically replace ALL notes in a MIDI clip with the given list."""
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
