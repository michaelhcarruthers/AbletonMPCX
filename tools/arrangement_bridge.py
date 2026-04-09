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
    """Check if the AMCPX_Bridge Max for Live device is running and reachable."""
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
    """List ALL clips in the Arrangement View using the AMCPX_Bridge M4L device."""
    params: dict[str, Any] = {}
    if track_index is not None:
        params["track_index"] = track_index
    clips = _send_m4l("get_arrangement_clips", params)
    if not isinstance(clips, list):
        clips = []
    return {"clips": clips, "total_clips": len(clips)}


@mcp.tool()
def m4l_get_arrangement_clip_info(track_index: int, clip_index: int) -> dict:
    """Get full info for a specific arrangement clip."""
    return _send_m4l("get_arrangement_clip_info", {
        "track_index": track_index,
        "clip_index": clip_index,
    })


@mcp.tool()
def m4l_get_arrangement_clip_notes(track_index: int, clip_index: int) -> dict:
    """Read ALL MIDI notes from a specific arrangement clip."""
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
    """Replace ALL MIDI notes in a specific arrangement clip atomically."""
    return _send_m4l("set_arrangement_clip_notes", {
        "track_index": track_index,
        "clip_index": clip_index,
        "notes": notes,
    })


@mcp.tool()
def m4l_get_detail_clip() -> dict:
    """Read the clip currently open in Live's Detail View (the clip you last double-clicked)."""
    return _send_m4l("get_detail_clip", {})


@mcp.tool()
def m4l_get_arrangement_overview() -> dict:
    """Return a high-level structural overview of the entire arrangement."""
    return _send_m4l("get_arrangement_overview", {})


@mcp.tool()
def m4l_find_clip_by_name(name: str, track_index: int | None = None) -> dict:
    """Find arrangement clips by name (case-insensitive substring match)."""
    return _send_m4l("find_clip_by_name", {"name": name, "track_index": track_index})


@mcp.tool()
def m4l_find_clips_at_bar(bar: int, track_index: int | None = None) -> dict:
    """Find all arrangement clips playing at a specific bar number (1-based)."""
    return _send_m4l("find_clips_at_bar", {"bar": bar, "track_index": track_index})
