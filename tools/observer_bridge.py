"""Observer Bridge tools — selected track/device/parameter/playhead via AMCPX_Observer M4L device.

These tools require the AMCPX_Observer.amxd Max for Live device to be running in your Live set.
Drop AMCPX_Observer.amxd onto any track and leave it there.

Port 9879 (Observer device) — separate from the Bridge on 9878 and Remote Script on 9877.
"""
from __future__ import annotations

import json
import socket
from typing import Any

from helpers import mcp

# ---------------------------------------------------------------------------
# Transport — connects to the AMCPX_Observer M4L device on port 9879
# ---------------------------------------------------------------------------

M4L_OBSERVER_HOST = "localhost"
M4L_OBSERVER_PORT = 9879
M4L_OBSERVER_TIMEOUT = 10.0
_MAX_OBSERVER_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB


def _recv_exactly_observer(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return None
        buf += chunk
    return buf


def _send_observer(command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a command to the AMCPX_Observer M4L device on port 9879."""
    payload = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(M4L_OBSERVER_TIMEOUT)
        sock.connect((M4L_OBSERVER_HOST, M4L_OBSERVER_PORT))
        sock.sendall(len(payload).to_bytes(4, "big") + payload)
        header = _recv_exactly_observer(sock, 4)
        if not header:
            raise RuntimeError("Observer bridge closed connection before response header")
        msg_len = int.from_bytes(header, "big")
        if msg_len > _MAX_OBSERVER_RESPONSE_BYTES:
            raise RuntimeError("Observer bridge response too large: {} bytes".format(msg_len))
        data = _recv_exactly_observer(sock, msg_len)
        if data is None:
            raise RuntimeError("Observer bridge closed connection before response body")
        sock.close()
    except ConnectionRefusedError:
        raise RuntimeError(
            "Cannot connect to AMCPX_Observer on port {}. "
            "Make sure AMCPX_Observer.amxd is loaded on a track in your Live set "
            "and the device is active.".format(M4L_OBSERVER_PORT)
        )
    response = json.loads(data.decode("utf-8"))
    if response.get("status") == "error":
        raise RuntimeError(response["error"])
    return response.get("result")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def m4l_observer_ping() -> dict:
    """
    Check if the AMCPX_Observer Max for Live device is running and reachable.

    Returns:
        status: "pong" if connected
        version: observer version string
        message: human-readable status

    If this fails, the M4L device is not loaded. Drop AMCPX_Observer.amxd onto
    any track in your Live set and make sure it is active (not bypassed).
    """
    try:
        result = _send_observer("ping")
        result["message"] = "AMCPX_Observer is running on port {}.".format(M4L_OBSERVER_PORT)
        return result
    except RuntimeError as e:
        return {
            "status": "error",
            "message": str(e),
            "fix": (
                "Drop AMCPX_Observer.amxd onto any track in your Live set. "
                "The device must be active (green power button). "
                "It only needs to be loaded once per session."
            ),
        }


@mcp.tool()
def m4l_get_observer_state() -> dict:
    """
    Return the full current observer state snapshot — selected track, device,
    parameter, and playhead position — as maintained by the AMCPX_Observer device.

    The observer pushes state continuously without polling, so this always
    reflects the current Live selection without any round-trip to the LOM.

    Requires AMCPX_Observer.amxd to be loaded on a track in your Live set.

    Returns:
        selected_track_index: int or null
        selected_track_name: str or null
        selected_device_name: str or null
        selected_parameter_name: str or null
        selected_parameter_value: float or null
        current_song_time: float (beats) or null
        last_updated: ISO timestamp of last state change
    """
    return _send_observer("get_state")


@mcp.tool()
def m4l_get_selected_track() -> dict:
    """
    Return the currently selected track index and name.

    Uses the AMCPX_Observer device's in-memory state — no polling required.

    Requires AMCPX_Observer.amxd to be loaded on a track in your Live set.

    Returns:
        selected_track_index: int or null
        selected_track_name: str or null
        last_updated: ISO timestamp of last change
    """
    return _send_observer("get_selected_track")


@mcp.tool()
def m4l_get_selected_device() -> dict:
    """
    Return the name of the currently selected device.

    Uses the AMCPX_Observer device's in-memory state — no polling required.

    Requires AMCPX_Observer.amxd to be loaded on a track in your Live set.

    Returns:
        selected_device_name: str or null (null if no device is selected)
        last_updated: ISO timestamp of last change
    """
    return _send_observer("get_selected_device")


@mcp.tool()
def m4l_get_selected_parameter() -> dict:
    """
    Return the name and current value of the currently selected device parameter.

    Uses the AMCPX_Observer device's in-memory state — no polling required.

    Requires AMCPX_Observer.amxd to be loaded on a track in your Live set.

    Returns:
        selected_parameter_name: str or null (null if no parameter is selected)
        selected_parameter_value: float or null
        last_updated: ISO timestamp of last change
    """
    return _send_observer("get_selected_parameter")


@mcp.tool()
def m4l_get_playhead() -> dict:
    """
    Return the current song playhead position in beats and bars.

    Uses the AMCPX_Observer device's in-memory state which is updated continuously
    by a live.observer watching live_set.current_song_time (throttled to 100ms).

    Note: bar and beat_in_bar are calculated assuming 4/4 time. For projects with
    non-4/4 time signatures or variable meter, use current_song_time (beats) directly
    rather than relying on bar/beat_in_bar fields.

    Requires AMCPX_Observer.amxd to be loaded on a track in your Live set.

    Returns:
        current_song_time: float (beats from song start) or null
        bar: int (1-based bar number, assuming 4/4) or null
        beat_in_bar: float (beat position within the bar, 1-based) or null
        last_updated: ISO timestamp of last change
    """
    return _send_observer("get_playhead")
