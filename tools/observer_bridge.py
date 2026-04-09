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
    """Check if the AMCPX_Observer Max for Live device is running and reachable."""
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
    """Return the full current observer state snapshot: selected track, device, parameter, and playhead position."""
    return _send_observer("get_state")


@mcp.tool()
def m4l_get_selected_track() -> dict:
    """Return the currently selected track index and name."""
    return _send_observer("get_selected_track")


@mcp.tool()
def m4l_get_selected_device() -> dict:
    """Return the name of the currently selected device."""
    return _send_observer("get_selected_device")


@mcp.tool()
def m4l_get_selected_parameter() -> dict:
    """Return the name and current value of the currently selected device parameter."""
    return _send_observer("get_selected_parameter")


@mcp.tool()
def m4l_get_playhead() -> dict:
    """Return the current song playhead position in beats and bars."""
    return _send_observer("get_playhead")
