"""Clip envelope tools — automation envelopes on clips."""
from __future__ import annotations
import logging
from helpers import mcp, _send
logger = logging.getLogger(__name__)

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
def get_automation_data(track_index: int, slot_index: int, envelope_index: int, slim: bool = True) -> dict:
    """Return automation data for one envelope on a clip. slim=True (default) returns summary stats only (param_name, point_count, min_value, max_value, first_value, last_value). Pass slim=False for the full point list."""
    return _send("get_automation_data", {
        "track_index": track_index,
        "slot_index": slot_index,
        "envelope_index": envelope_index,
        "slim": slim,
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
