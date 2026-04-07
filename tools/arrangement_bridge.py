"""Arrangement Bridge tools — full arrangement view access via the AMCPX_Bridge M4L device.

These tools require the AMCPX_Bridge.amxd Max for Live device to be running in your Live set.
Drop AMCPX_Bridge.amxd onto any track and leave it there.

Port 9878 (M4L device) vs port 9877 (Remote Script) — separate connections.
"""
from __future__ import annotations

import json
import socket
from typing import Any

from helpers import mcp

# ---------------------------------------------------------------------------
# Transport — connects to the M4L device on port 9878
# ---------------------------------------------------------------------------

M4L_HOST = "localhost"
M4L_PORT = 9878
M4L_TIMEOUT = 10.0
_MAX_M4L_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def _recv_exactly_m4l(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return None
        buf += chunk
    return buf


def _send_m4l(command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a command to the AMCPX_Bridge M4L device on port 9878."""
    payload = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(M4L_TIMEOUT)
        sock.connect((M4L_HOST, M4L_PORT))
        sock.sendall(len(payload).to_bytes(4, "big") + payload)
        header = _recv_exactly_m4l(sock, 4)
        if not header:
            raise RuntimeError("M4L bridge closed connection before response header")
        msg_len = int.from_bytes(header, "big")
        if msg_len > _MAX_M4L_RESPONSE_BYTES:
            raise RuntimeError("M4L bridge response too large: {} bytes".format(msg_len))
        data = _recv_exactly_m4l(sock, msg_len)
        if data is None:
            raise RuntimeError("M4L bridge closed connection before response body")
        sock.close()
    except ConnectionRefusedError:
        raise RuntimeError(
            "Cannot connect to AMCPX_Bridge on port {}. "
            "Make sure AMCPX_Bridge.amxd is loaded on a track in your Live set "
            "and the device is active.".format(M4L_PORT)
        )
    response = json.loads(data.decode("utf-8"))
    if response.get("status") == "error":
        raise RuntimeError(response["error"])
    return response.get("result")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def m4l_ping() -> dict:
    """
    Check if the AMCPX_Bridge Max for Live device is running and reachable.

    Returns:
        status: "pong" if connected
        version: bridge version string
        message: human-readable status

    If this fails, the M4L device is not loaded. Drop AMCPX_Bridge.amxd onto
    any track in your Live set and make sure it is active (not bypassed).
    """
    try:
        result = _send_m4l("ping")
        result["message"] = "AMCPX_Bridge is running on port {}.".format(M4L_PORT)
        return result
    except RuntimeError as e:
        return {
            "status": "error",
            "message": str(e),
            "fix": (
                "Drop AMCPX_Bridge.amxd onto any track in your Live set. "
                "The device must be active (green power button). "
                "It only needs to be loaded once per session."
            ),
        }


@mcp.tool()
def m4l_get_arrangement_clips(track_index: int | None = None) -> dict:
    """
    List ALL clips in the Arrangement View using the AMCPX_Bridge M4L device.

    Unlike list_arrangement_clips() (which is limited by the Python Remote Script API),
    this tool uses Max for Live's full LiveAPI access to read arrangement clips directly.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Args:
        track_index: Optional. If provided, only return clips from this track.

    Returns:
        clips: list of {track_index, track_name, clip_index, clip_name,
                        start_time, end_time, length, start_bar, length_bars,
                        is_midi_clip, is_audio_clip, color, muted, looping}
        total_clips: int
    """
    params: dict[str, Any] = {}
    if track_index is not None:
        params["track_index"] = track_index
    clips = _send_m4l("get_arrangement_clips", params)
    if not isinstance(clips, list):
        clips = []
    return {"clips": clips, "total_clips": len(clips)}


@mcp.tool()
def m4l_get_arrangement_clip_info(track_index: int, clip_index: int) -> dict:
    """
    Get full info for a specific arrangement clip.

    Use m4l_get_arrangement_clips() first to find track_index and clip_index.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Args:
        track_index: Zero-based track index.
        clip_index: Zero-based index into the track's arrangement clips.

    Returns:
        track_index, track_name, clip_index, clip_name,
        start_time (beats), end_time (beats), length (beats),
        start_bar, length_bars, is_midi_clip, color, muted, looping,
        loop_start, loop_end
    """
    return _send_m4l("get_arrangement_clip_info", {
        "track_index": track_index,
        "clip_index": clip_index,
    })


@mcp.tool()
def m4l_get_arrangement_clip_notes(track_index: int, clip_index: int) -> dict:
    """
    Read ALL MIDI notes from a specific arrangement clip.

    This is the full solution for reading arrangement clip notes — no workarounds,
    no need to click anything in Live first. Uses Max for Live's LiveAPI.

    Use m4l_get_arrangement_clips() first to find track_index and clip_index.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Args:
        track_index: Zero-based track index.
        clip_index: Zero-based index into the track's arrangement clips.

    Returns:
        notes: list of {pitch, start_time, duration, velocity, mute}
        clip_name: str
        track_index: int
        clip_index: int
        clip_start_time: float  -- position in arrangement (beats)
        clip_length: float      -- clip length in beats
        note_count: int
    """
    return _send_m4l("get_arrangement_clip_notes", {
        "track_index": track_index,
        "clip_index": clip_index,
    })


@mcp.tool()
def m4l_set_arrangement_clip_notes(
    track_index: int,
    clip_index: int,
    notes: list[dict],
) -> dict:
    """
    Replace ALL MIDI notes in a specific arrangement clip atomically.

    The operation is wrapped in a single Live undo step, so the clip never
    passes through a zero-note transient state that could trigger auto-deletion
    in some Live versions.  The entire replace appears as one entry in Live's
    undo history.

    On Live 11.1+ the faster ``replace_all_notes`` API is attempted first
    (atomically replaces all notes in a single call).  If that API is not
    available the implementation falls back to
    ``begin_undo_step`` → ``remove_notes`` → ``set_notes`` → ``end_undo_step``.

    Use m4l_get_arrangement_clips() first to find track_index and clip_index.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Args:
        track_index: Zero-based track index.
        clip_index: Zero-based index into the track's arrangement clips.
        notes: List of note dicts. Each requires:
            pitch (int 0-127), start_time (float beats), duration (float beats)
            Optional: velocity (int 0-127, default 100), mute (bool, default False)

    Returns:
        track_index, clip_index, note_count
    """
    return _send_m4l("set_arrangement_clip_notes", {
        "track_index": track_index,
        "clip_index": clip_index,
        "notes": notes,
    })


@mcp.tool()
def m4l_get_detail_clip() -> dict:
    """
    Read the clip currently open in Live's Detail View (the clip you last double-clicked).

    Returns full metadata and all MIDI notes for the clip in the Detail View without
    needing to know its track or clip index.  For arrangement clips you must double-click
    the clip in Live first to bring it into the Detail View.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Returns:
        clip_name: str
        start_time: float   -- position in arrangement (beats), 0 for session clips
        end_time: float
        length: float       -- clip length in beats
        is_midi_clip: bool
        looping: bool
        loop_start: float
        loop_end: float
        notes: list of {pitch, start_time, duration, velocity, mute}
        note_count: int
        start_bar: int
        length_bars: float
    """
    return _send_m4l("get_detail_clip", {})


@mcp.tool()
def m4l_get_arrangement_overview() -> dict:
    """
    Return a high-level structural overview of the entire arrangement.

    Uses Max for Live's LiveAPI for full arrangement access.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Returns:
        total_clips: int
        total_bars: int
        tracks_with_clips: int
        clips_per_track: list of {track_index, track_name, clip_count, first_bar, last_bar}
        tempo: float
    """
    return _send_m4l("get_arrangement_overview", {})


@mcp.tool()
def m4l_get_detail_clip() -> dict:
    """
    Read the clip currently open in Live's Detail View (the piano roll at the bottom).

    This is a fallback for when arrangement clip indexing fails — it reads whatever
    clip the user has open in the editor without needing to know its track/clip index.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Returns:
        name: str
        length: float (beats)
        is_midi_clip: bool
        start_time: float (beats — arrangement position)
        end_time: float (beats)
        loop_start: float (beats)
        loop_end: float (beats)
        looping: bool
        notes: list of {pitch, start_time, duration, velocity, mute} (empty for audio clips)
        note_count: int
    """
    return _send_m4l("get_detail_clip", {})


@mcp.tool()
def m4l_find_clip_by_name(name: str, track_index: int | None = None) -> dict:
    """
    Find arrangement clips by name (case-insensitive substring match).

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Args:
        name: Substring to search for (case-insensitive). E.g. "bass", "intro".
        track_index: Optional. If provided, only search this track.

    Returns:
        clips: list of matching clip objects (same fields as m4l_get_arrangement_clips)
        total_found: int
    """
    return _send_m4l("find_clip_by_name", {"name": name, "track_index": track_index})


@mcp.tool()
def m4l_find_clips_at_bar(bar: int, track_index: int | None = None) -> dict:
    """
    Find all arrangement clips playing at a specific bar number (1-based).

    Bar 1 = beat 0, bar 5 = beat 16, bar 9 = beat 32, etc.
    Returns every clip whose time range covers the given bar position.

    Requires AMCPX_Bridge.amxd to be loaded on a track in your Live set.

    Args:
        bar: 1-based bar number (bar 1 is the very start of the arrangement).
        track_index: Optional. If provided, only search this track.

    Returns:
        clips: list of matching clip objects
        bar: int — the bar number queried
        beat_position: float — beat position corresponding to the bar
        total_found: int
    """
    return _send_m4l("find_clips_at_bar", {"bar": bar, "track_index": track_index})
