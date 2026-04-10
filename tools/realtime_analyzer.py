"""Real-time Analyzer tools — LUFS, RMS, and crest factor via the AMCPX_Analyzer M4L device.

These tools require the AMCPX_Analyzer.amxd Max for Live device to be running in your Live set.
Drop AMCPX_Analyzer.amxd onto any track, bus, or master channel you want to measure.

Port 9880 (Analyzer device) — separate from port 9878 (Bridge device) and port 9877 (Remote Script).
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any

from helpers import mcp

# ---------------------------------------------------------------------------
# Transport — connects to the M4L Analyzer device on port 9880
# ---------------------------------------------------------------------------

ANALYZER_HOST = "localhost"
ANALYZER_PORT = 9880
ANALYZER_TIMEOUT = 5.0
_MAX_ANALYZER_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def _recv_exactly_analyzer(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return None
        buf += chunk
    return buf


def _send_analyzer(command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a command to the AMCPX_Analyzer M4L device on port 9880."""
    payload = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(ANALYZER_TIMEOUT)
        sock.connect((ANALYZER_HOST, ANALYZER_PORT))
        sock.sendall(len(payload).to_bytes(4, "big") + payload)
        header = _recv_exactly_analyzer(sock, 4)
        if not header:
            raise RuntimeError("Analyzer closed connection before response header")
        msg_len = int.from_bytes(header, "big")
        if msg_len > _MAX_ANALYZER_RESPONSE_BYTES:
            raise RuntimeError("Analyzer response too large: {} bytes".format(msg_len))
        data = _recv_exactly_analyzer(sock, msg_len)
        if data is None:
            raise RuntimeError("Analyzer closed connection before response body")
        sock.close()
    except ConnectionRefusedError:
        raise RuntimeError(
            "Cannot connect to AMCPX_Analyzer on port {}. "
            "Make sure AMCPX_Analyzer.amxd is loaded on a track in your Live set "
            "and the device is active.".format(ANALYZER_PORT)
        )
    response = json.loads(data.decode("utf-8"))
    if response.get("status") == "error":
        raise RuntimeError(response["error"])
    return response.get("result")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def m4l_analyzer_ping() -> dict:
    """Check if the AMCPX_Analyzer Max for Live device is running and reachable."""
    try:
        result = _send_analyzer("ping")
        result["message"] = "AMCPX_Analyzer is running on port {}.".format(ANALYZER_PORT)
        return result
    except RuntimeError as e:
        return {
            "status": "error",
            "message": str(e),
            "fix": (
                "Drop AMCPX_Analyzer.amxd onto any track in your Live set. "
                "The device must be active (green power button). "
                "It only needs to be loaded once per session."
            ),
        }


def m4l_get_levels() -> dict:
    """Get full real-time measurements from the AMCPX_Analyzer M4L device."""
    return _send_analyzer("get_levels")


def m4l_get_lufs() -> dict:
    """Get LUFS measurements from the AMCPX_Analyzer M4L device."""
    return _send_analyzer("get_lufs")


def m4l_get_peak_level() -> dict:
    """Get the peak dBFS level and clip count from the AMCPX_Analyzer M4L device."""
    return _send_analyzer("get_peak")


def m4l_get_crest_factor() -> dict:
    """Get the crest factor from the AMCPX_Analyzer M4L device."""
    return _send_analyzer("get_crest_factor")


def m4l_reset_analyzer() -> dict:
    """Reset all measurements and clip counter in the AMCPX_Analyzer M4L device."""
    return _send_analyzer("reset")


def m4l_measure_for_seconds(duration: float = 5.0) -> dict:
    """Measure audio levels for a given duration and return the final results."""
    duration = max(0.1, min(float(duration), 60.0))
    _send_analyzer("start_measuring")
    time.sleep(duration)
    return _send_analyzer("stop_measuring")
