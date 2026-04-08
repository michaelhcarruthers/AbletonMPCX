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
def get_tracks() -> list:
    """Return all tracks with their name, color, mute/solo/arm state and mixer values."""
    return _send("get_tracks")

@mcp.tool()
def get_track_info(track_index: int) -> dict:
    """Return full details for the track at track_index, including clip slots and devices. Use track_index=-1 to target the master track."""
    return _send("get_track_info", {"track_index": track_index})

@mcp.tool()
def get_track_playing_state(track_index: int) -> dict:
    """
    Return the currently playing and queued slot indices for a track.
    playing_slot_index: index of the currently playing clip slot (-1 if none).
    fired_slot_index: index of the next queued clip slot (-1 if none).
    """
    return _send("get_track_playing_state", {"track_index": track_index})

@mcp.tool()
def get_track_names(include_returns: bool = False, include_master: bool = False) -> list:
    """
    Return a lightweight list of all track names and their indices.
    Much faster than get_tracks() when you only need names.

    Args:
        include_returns: If True, also include return tracks (marked with is_return=True).
        include_master: If True, also include the master track at index -1.

    Returns:
        List of dicts with 'index' and 'name' keys.
        Return tracks also include 'is_return': True when include_returns is True.
        Master track also includes 'is_master': True when include_master is True.
        Use the returned indices with any track_index parameter.
        Master track is always at index -1.
    """
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
    """
    Set send levels on multiple tracks in a single round trip.

    Much more efficient than calling set_track_send() per track.
    All changes are applied in the same main-thread call.

    Each update dict requires:
        track_index (int): track to update
        send_index (int): send slot index (0-based)
        value (float): send level 0.0–1.0

    Example:
        set_track_send_batch([
            {"track_index": 0, "send_index": 0, "value": 0.6},
            {"track_index": 1, "send_index": 0, "value": 0.4},
            {"track_index": 2, "send_index": 0, "value": 0.0},
            {"track_index": 3, "send_index": 1, "value": 0.3},
        ])

    Returns:
        applied: int (number of sends set)
        errors: list of {track_index, send_index, error}
    """
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
    """
    Return the full routing state for a track: input/output type and channel,
    plus the list of available options for each routing type property.

    Use the 'available_input_routing_types' and 'available_output_routing_types'
    lists to discover valid index values for the setter tools.

    Args:
        track_index: Track index (-1 not supported for routing).

    Returns:
        input_routing_type, input_routing_channel,
        output_routing_type, output_routing_channel,
        available_input_routing_types (list of str),
        available_output_routing_types (list of str)
    """
    return _send("get_track_routing", {"track_index": track_index})


@mcp.tool()
def set_track_input_routing_type(track_index: int, value: int) -> dict:
    """
    Set the input routing type for a track by index into the available options.

    Call get_track_routing() first to see available options and their indices.

    Args:
        track_index: Track to modify.
        value: Index into track.available_input_routing_types (0-based).
    """
    return _send("set_track_input_routing_type", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_input_routing_channel(track_index: int, value: int) -> dict:
    """
    Set the input routing channel for a track by index into the available options.

    Call get_track_routing() first to see available channel options.

    Args:
        track_index: Track to modify.
        value: Index into track.available_input_routing_channels (0-based).
    """
    return _send("set_track_input_routing_channel", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_output_routing_type(track_index: int, value: int) -> dict:
    """
    Set the output routing type for a track by index into the available options.

    Call get_track_routing() first to see available options and their indices.

    Args:
        track_index: Track to modify.
        value: Index into track.available_output_routing_types (0-based).
    """
    return _send("set_track_output_routing_type", {"track_index": track_index, "value": value})


@mcp.tool()
def set_track_output_routing_channel(track_index: int, value: int) -> dict:
    """
    Set the output routing channel for a track by index into the available options.

    Call get_track_routing() first to see available channel options.

    Args:
        track_index: Track to modify.
        value: Index into track.available_output_routing_channels (0-based).
    """
    return _send("set_track_output_routing_channel", {"track_index": track_index, "value": value})


@mcp.tool()
def get_available_routings(track_index: int) -> dict:
    """
    Return all available input and output routing types and channels for a track.

    Useful for discovering valid display name values before calling
    set_track_input_routing or set_track_output_routing.

    Args:
        track_index: Track index.

    Returns:
        input_routing_types (list of str), input_routing_channels (list of str),
        output_routing_types (list of str), output_routing_channels (list of str)
    """
    return _send("get_available_routings", {"track_index": track_index})


@mcp.tool()
def set_track_input_routing(
    track_index: int,
    routing_type_name: str | None = None,
    routing_channel_name: str | None = None,
) -> dict:
    """
    Set the input routing for a track by display name.

    routing_type_name: display name of the routing type (e.g. "Resampling", "No Input", "1-Ext. In").
    routing_channel_name: display name of the routing channel (e.g. "1/2", "3/4").
    Call get_available_routings first to discover valid values.

    Args:
        track_index: Track to modify.
        routing_type_name: Display name of the desired input routing type (optional).
        routing_channel_name: Display name of the desired input routing channel (optional).
    """
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
    """
    Set the output routing for a track by display name.

    routing_type_name: display name of the routing type (e.g. "Master", "Sends Only", "1-Ext. Out").
    routing_channel_name: display name of the routing channel (e.g. "1/2", "3/4").
    Call get_available_routings first to discover valid values.

    Args:
        track_index: Track to modify.
        routing_type_name: Display name of the desired output routing type (optional).
        routing_channel_name: Display name of the desired output routing channel (optional).
    """
    return _send("set_track_output_routing", {
        "track_index": track_index,
        "routing_type_name": routing_type_name,
        "routing_channel_name": routing_channel_name,
    })


@mcp.tool()
def group_tracks(track_indices: list[int]) -> dict:
    """
    Group the specified tracks into a new group track.

    Uses Live's internal _do_group_tracks method (available in Live 10-12).
    Track indices must be contiguous and in ascending order — Live requires
    tracks to be adjacent to group them.

    Args:
        track_indices: List of track indices to group (must be contiguous).

    Returns:
        status: "ok" on success
        grouped_count: number of tracks grouped
    """
    return _send("group_tracks", {"track_indices": track_indices})


@mcp.tool()
def ungroup_tracks(track_index: int) -> dict:
    """
    Ungroup the group track at track_index.

    Uses Live's internal _do_ungroup_tracks method (available in Live 10-12).

    Args:
        track_index: Index of the group track to ungroup.

    Returns:
        status: "ok" on success
    """
    return _send("ungroup_tracks", {"track_index": track_index})


@mcp.tool()
def setup_resampling_route(dest_track_index: int, source_track_name: str) -> dict:
    """
    Configure a destination track to record resampled audio from a source track.

    Performs the complete resampling setup in a single main-thread call inside Live:
      1. Selects the destination track in song.view so Live registers routing changes.
      2. Finds the source track routing type by matching source_track_name in
         available_input_routing_types.
      3. Sets input_routing_channel to "Post FX" (falls back to the first available
         channel if "Post FX" is not present, and reports a warning).
      4. Sets current_monitoring_state = 1 (Monitor: In).
      5. Arms the track last (Live requires routing to be committed before arming).

    Returns confirmed values for arm, monitoring_state, input_routing_type, and
    input_routing_channel so the caller can verify the route stuck. Any routing
    errors are included in the response keys ending with "_error".

    Args:
        dest_track_index: Index of the track that will capture the resampled audio.
        source_track_name: Display name of the source track (e.g. "Sax (Bounce)").

    Returns:
        confirmed_arm (bool), confirmed_monitoring_state (int),
        confirmed_input_routing_type (str), confirmed_input_routing_channel (str),
        plus any _error or _warning keys if a step could not be applied.
    """
    return _send("setup_resampling_route", {
        "dest_track_index": dest_track_index,
        "source_track_name": source_track_name,
    })


@mcp.tool()
def get_track_devices(track_index: int, is_return_track: bool = False) -> dict:
    """
    Return the device names and count for a track without fetching parameters.

    Much lighter than get_track_info() — use this for session orientation
    to find device indices before calling get_device_parameters.

    Args:
        track_index: Track index (use -1 for master track).
        is_return_track: If True, track_index refers to a return track.

    Returns:
        track_name: str
        device_count: int
        devices: list of {index: int, name: str, type: str, is_active: bool}
    """
    return _send("get_track_devices", {"track_index": track_index, "is_return_track": is_return_track})


@mcp.tool()
def get_track_levels_all(include_returns: bool = True, include_master: bool = True) -> dict:
    """
    Return volume and pan for all tracks in a single call.

    Use for mix overview — much cheaper than calling get_mixer_device per track.

    Args:
        include_returns: Include return tracks (default True).
        include_master: Include master track (default True).

    Returns:
        tracks: list of {index, name, volume, pan, mute, solo}
        returns: list of {index, name, volume, pan, mute} (if include_returns)
        master: {volume, pan} (if include_master)
    """
    return _send("get_track_levels_all", {
        "include_returns": include_returns,
        "include_master": include_master,
    })


@mcp.tool()
def teardown_resampling_route(dest_track_index: int) -> dict:
    """
    Disarm the destination track and reset its monitoring state after resampling.

    Reverses the changes made by setup_resampling_route:
      1. Sets arm = False.
      2. Sets current_monitoring_state = 0 (Monitor: Auto).

    Returns confirmed arm and monitoring_state values.

    Args:
        dest_track_index: Index of the track that was used for resampling.
    """
    return _send("teardown_resampling_route", {"dest_track_index": dest_track_index})

