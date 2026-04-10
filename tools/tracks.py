"""Track tools — master track, audio/MIDI tracks, return tracks, routing, volume, pan, mute, solo, arm, sends, and fold state."""
from __future__ import annotations

import helpers
from helpers import mcp, _send

# ---------------------------------------------------------------------------
# Master Track
# ---------------------------------------------------------------------------

@mcp.tool()
def get_master_track() -> dict:
    """Return the master track's volume, pan and crossfader values."""
    return _send("get_master_track")

@mcp.tool()
def set_master_volume(value: float) -> dict:
    """Set the master track volume (0.0-1.0)."""
    return _send("set_master_volume", {"value": value})

@mcp.tool()
def set_master_pan(value: float) -> dict:
    """Set the master track panning (-1.0 = full left, 0 = centre, 1.0 = full right)."""
    return _send("set_master_pan", {"value": value})

@mcp.tool()
def set_crossfader(value: float) -> dict:
    """Set the master crossfader position (-1.0 = full A, 0 = centre, 1.0 = full B)."""
    return _send("set_crossfader", {"value": value})

# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------

@mcp.tool()
def get_tracks(slim: bool = True) -> list:
    """Return all tracks with their name, color, mute/solo/arm state and mixer values. slim=True (default) returns only index, name, type — use this when you don't need device chains or routing details. Pass slim=False to get full track data including color, mixer values and device counts."""
    return _send("get_tracks", {"slim": slim})

@mcp.tool()
def get_track_info(track_index: int) -> dict:
    """Return full details for a track, including clip slots and devices (use track_index=-1 for master)."""
    return _send("get_track_info", {"track_index": track_index})

@mcp.tool()
def get_track_playing_state(track_index: int) -> dict:
    """Return the currently playing and queued slot indices for a track."""
    return _send("get_track_playing_state", {"track_index": track_index})

@mcp.tool()
def get_track_names(include_returns: bool = False, include_master: bool = False) -> list:
    """Return a lightweight list of all track names and their indices."""
    return _send("get_track_names", {
        "include_returns": include_returns,
        "include_master": include_master,
    })

@mcp.tool()
def set_track_name(track_index: int, name: str) -> dict:
    """Rename the track at track_index."""
    return _send("set_track_name", {"track_index": track_index, "name": name})

@mcp.tool()
def set_track_color(track_index: int, color: int) -> dict:
    """Set the track color as an RGB integer (0x00rrggbb)."""
    return _send("set_track_color", {"track_index": track_index, "color": color})

@mcp.tool()
def set_track_mute(track_index: int, mute: bool) -> dict:
    """Mute or unmute the track at track_index."""
    return _send("set_track_mute", {"track_index": track_index, "mute": mute})

@mcp.tool()
def set_track_solo(track_index: int, solo: bool) -> dict:
    """Solo or unsolo the track at track_index."""
    return _send("set_track_solo", {"track_index": track_index, "solo": solo})

@mcp.tool()
def set_track_arm(track_index: int, arm: bool) -> dict:
    """Arm or disarm the track at track_index for recording."""
    return _send("set_track_arm", {"track_index": track_index, "arm": arm})

@mcp.tool()
def set_track_volume(track_index: int, value: float) -> dict:
    """Set the track volume (0.0-1.0 maps to -inf to +6 dB)."""
    return _send("set_track_volume", {"track_index": track_index, "value": value})

@mcp.tool()
def set_track_pan(track_index: int, value: float) -> dict:
    """Set the track panning (-1.0 = full left, 0 = centre, 1.0 = full right)."""
    return _send("set_track_pan", {"track_index": track_index, "value": value})

@mcp.tool()
def set_track_send(track_index: int, send_index: int, value: float) -> dict:
    """Set a send level on the track at track_index (value 0.0-1.0)."""
    return _send("set_track_send", {"track_index": track_index, "send_index": send_index, "value": value})

@mcp.tool()
def set_track_send_batch(
    updates: list[dict],
) -> dict:
    """Set send levels on multiple tracks in a single round trip."""
    return _send("set_track_send_batch", {"updates": updates})


@mcp.tool()
def stop_track_clips(track_index: int) -> dict:
    """Stop all clips on the track at track_index."""
    return _send("stop_track_clips", {"track_index": track_index})

@mcp.tool()
def set_track_fold_state(track_index: int, fold_state: int) -> dict:
    """Set the fold state of a group track (0=unfolded, 1=folded)."""
    if fold_state not in (0, 1):
        raise ValueError("fold_state must be 0 (unfolded) or 1 (folded)")
    return _send("set_track_fold_state", {"track_index": track_index, "fold_state": fold_state})

@mcp.tool()
def get_return_tracks() -> list:
    """Return all return tracks with name and volume."""
    return _send("get_return_tracks")

@mcp.tool()
def get_track_routing(track_index: int) -> dict:
    """Return the full routing state for a track: input/output type, channel, and lists of available options."""
    return _send("get_track_routing", {"track_index": track_index})


@mcp.tool()
def set_track_input_routing_type(track_index: int, value: int) -> dict:
    """Set the input routing type for a track by index into the available options."""
    return _send("set_track_input_routing_type", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_input_routing_channel(track_index: int, value: int) -> dict:
    """Set the input routing channel for a track by index into the available options."""
    return _send("set_track_input_routing_channel", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_output_routing_type(track_index: int, value: int) -> dict:
    """Set the output routing type for a track by index into the available options."""
    return _send("set_track_output_routing_type", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_output_routing_channel(track_index: int, value: int) -> dict:
    """Set the output routing channel for a track by index into the available options."""
    return _send("set_track_output_routing_channel", {"track_index": track_index, "value": value})


@mcp.tool()
def get_available_routings(track_index: int) -> dict:
    """Return all available input and output routing types and channels for a track."""
    return _send("get_available_routings", {"track_index": track_index})


@mcp.tool()
def set_track_input_routing(
    track_index: int,
    routing_type_name: str | None = None,
    routing_channel_name: str | None = None,
) -> dict:
    """Set the input routing for a track by display name."""
    return _send("set_track_input_routing", {
        "track_index": track_index,
        "routing_type_name": routing_type_name,
        "routing_channel_name": routing_channel_name,
    })


@mcp.tool()
def set_track_output_routing(
    track_index: int,
    routing_type_name: str | None = None,
    routing_channel_name: str | None = None,
) -> dict:
    """Set the output routing for a track by display name."""
    return _send("set_track_output_routing", {
        "track_index": track_index,
        "routing_type_name": routing_type_name,
        "routing_channel_name": routing_channel_name,
    })


@mcp.tool()
def group_tracks(track_indices: list[int]) -> dict:
    """Group the specified tracks into a new group track."""
    _send("begin_undo_step", {"name": "group_tracks"})
    try:
        result = _send("group_tracks", {"track_indices": track_indices})
    finally:
        _send("end_undo_step", {})
    return result


@mcp.tool()
def ungroup_tracks(track_index: int) -> dict:
    """Ungroup the group track at track_index."""
    _send("begin_undo_step", {"name": "ungroup_tracks"})
    try:
        result = _send("ungroup_tracks", {"track_index": track_index})
    finally:
        _send("end_undo_step", {})
    return result


@mcp.tool()
def clone_track(
    track_index: int,
    new_name: str | None = None,
    insert_after: bool = True,
) -> dict:
    """Duplicate a track and optionally rename the clone."""
    _send("begin_undo_step", {"name": "clone_track"})
    try:
        result = _send("duplicate_track", {"track_index": track_index})
        # Live always inserts the duplicate immediately after the source; fall back to track_index + 1
        new_track_index = result.get("new_track_index", track_index + 1)

        if new_name is not None:
            _send("set_track_name", {"track_index": new_track_index, "name": new_name})
            resolved_name = new_name
        else:
            resolved_name = result.get("new_track_name", "")
    finally:
        _send("end_undo_step", {})

    return {
        "original_track_index": track_index,
        "new_track_index": new_track_index,
        "new_track_name": resolved_name,
        "applied": True,
    }


@mcp.tool()
def get_track_devices(track_index: int, is_return_track: bool = False) -> dict:
    """Return the device names and count for a track without fetching parameters."""
    return _send("get_track_devices", {"track_index": track_index, "is_return_track": is_return_track})


@mcp.tool()
def get_devices(track_index: int, is_return_track: bool = False, slim: bool = True) -> list:
    """Return the devices on a track. slim=True (default) returns index, name, type, is_active only. Pass slim=False to get full parameter lists for each device."""
    return _send("get_devices", {"track_index": track_index, "is_return_track": is_return_track, "slim": slim})


@mcp.tool()
def get_mix_snapshot(slim: bool = True) -> dict:
    """Return a snapshot of the mixer state for all tracks. slim=True (default) returns volume, pan, mute, solo per track only. Pass slim=False for full snapshot with sends and routing."""
    return _send("get_mix_snapshot", {"slim": slim})


def get_track_levels_all(include_returns: bool = True, include_master: bool = True) -> dict:
    """Return volume and pan for all tracks in a single call."""
    return _send("get_track_levels_all", {
        "include_returns": include_returns,
        "include_master": include_master,
    })


@mcp.tool()
def teardown_resampling_route(dest_track_index: int) -> dict:
    """Disarm the destination track and reset its monitoring state after resampling."""
    return _send("teardown_resampling_route", {"dest_track_index": dest_track_index})


# ---------------------------------------------------------------------------
# Track creation / deletion / duplication (moved from tools.session)
# ---------------------------------------------------------------------------

@mcp.tool()
def create_audio_track(index: int = -1) -> dict:
    """Create a new audio track. index=-1 appends at end."""
    return _send("create_audio_track", {"index": index})


@mcp.tool()
def create_midi_track(index: int = -1) -> dict:
    """Create a new MIDI track. index=-1 appends at end."""
    return _send("create_midi_track", {"index": index})


@mcp.tool()
def create_return_track() -> dict:
    """Add a new return track."""
    return _send("create_return_track")


@mcp.tool()
def delete_track(track_index: int) -> dict:
    """Delete the track at track_index."""
    return _send("delete_track", {"track_index": track_index})


@mcp.tool()
def delete_return_track(index: int) -> dict:
    """Delete the return track at index."""
    return _send("delete_return_track", {"index": index})


@mcp.tool()
def duplicate_track(track_index: int) -> dict:
    """Duplicate the track at track_index."""
    return _send("duplicate_track", {"track_index": track_index})

