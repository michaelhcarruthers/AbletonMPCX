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

@mcp.tool()
def m4l_analyzer_ping() -> dict:
    """
    Check if the AMCPX_Analyzer Max for Live device is running and reachable.

    Returns:
        status: "pong" if connected
        version: analyzer version string
        message: human-readable status

    If this fails, the M4L device is not loaded. Drop AMCPX_Analyzer.amxd onto
    any track in your Live set and make sure it is active (not bypassed).
    """
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


@mcp.tool()
def m4l_get_levels() -> dict:
    """
    Get full real-time measurements from the AMCPX_Analyzer M4L device.

    Returns peak dBFS, RMS dBFS, short-term LUFS (3-second window),
    integrated LUFS, crest factor in dB, clip count, and measuring state.

    Requires AMCPX_Analyzer.amxd to be loaded on the track you want to analyze.

    Returns:
        peak_db: float or null — peak level in dBFS
        rms_db: float or null — RMS level in dBFS
        lufs_short: float or null — 3-second short-term LUFS approximation
        lufs_integrated: float or null — integrated LUFS since last reset
        crest_factor_db: float or null — crest factor in dB (peak minus RMS)
        clip_count: int — number of measurements at or above 0 dBFS
        last_updated: str or null — ISO timestamp of last measurement
        measuring: bool — whether active measuring mode is on
    """
    return _send_analyzer("get_levels")


@mcp.tool()
def m4l_get_lufs() -> dict:
    """
    Get LUFS measurements from the AMCPX_Analyzer M4L device.

    Returns short-term (3-second window) and integrated LUFS values.
    Values are approximated from RMS — not true ITU-R BS.1770 K-weighted LUFS,
    but useful for relative comparisons and gain staging decisions.

    Requires AMCPX_Analyzer.amxd to be loaded on the track you want to analyze.

    Returns:
        lufs_short: float or null — 3-second short-term LUFS approximation
        lufs_integrated: float or null — integrated LUFS since last reset
    """
    return _send_analyzer("get_lufs")


@mcp.tool()
def m4l_get_peak_level() -> dict:
    """
    Get the peak dBFS level and clip count from the AMCPX_Analyzer M4L device.

    Returns the highest peak level seen since the last reset and the number of
    times the signal reached or exceeded 0 dBFS (true clipping).

    Requires AMCPX_Analyzer.amxd to be loaded on the track you want to analyze.

    Returns:
        peak_db: float or null — peak level in dBFS
        clip_count: int — number of measurements at or above 0 dBFS
    """
    return _send_analyzer("get_peak")


@mcp.tool()
def m4l_get_crest_factor() -> dict:
    """
    Get the crest factor from the AMCPX_Analyzer M4L device.

    The crest factor (peak dB − RMS dB) indicates dynamic range.
    A high crest factor (> 15 dB) suggests dynamic content;
    a low crest factor (< 6 dB) suggests heavy compression or limiting.

    Requires AMCPX_Analyzer.amxd to be loaded on the track you want to analyze.

    Returns:
        crest_factor_db: float or null — crest factor in dB (peak minus RMS)
        peak_db: float or null — peak level in dBFS
        rms_db: float or null — RMS level in dBFS
    """
    return _send_analyzer("get_crest_factor")


@mcp.tool()
def m4l_reset_analyzer() -> dict:
    """
    Reset all measurements and clip counter in the AMCPX_Analyzer M4L device.

    Clears peak, RMS, LUFS short-term and integrated rolling buffers, and the
    clip count. Use before starting a new measurement session.

    Requires AMCPX_Analyzer.amxd to be loaded on the track you want to analyze.

    Returns:
        reset: True
    """
    return _send_analyzer("reset")


@mcp.tool()
def m4l_measure_for_seconds(duration: float = 5.0) -> dict:
    """
    Measure audio levels for a given duration and return the final results.

    Sends start_measuring, waits for the specified number of seconds (Python-side
    sleep), then sends stop_measuring and returns the accumulated measurements.

    Requires AMCPX_Analyzer.amxd to be loaded on the track you want to analyze.

    Args:
        duration: Number of seconds to measure (default: 5.0, clamped to 0.1–60.0).

    Returns:
        peak_db: float or null — peak level in dBFS
        rms_db: float or null — RMS level in dBFS
        lufs_short: float or null — 3-second short-term LUFS approximation
        lufs_integrated: float or null — integrated LUFS since last reset
        crest_factor_db: float or null — crest factor in dB (peak minus RMS)
        clip_count: int — number of measurements at or above 0 dBFS
        last_updated: str or null — ISO timestamp of last measurement
        measuring: bool — False (measuring has stopped)
    """
    duration = max(0.1, min(float(duration), 60.0))
    _send_analyzer("start_measuring")
    time.sleep(duration)
    return _send_analyzer("stop_measuring")
