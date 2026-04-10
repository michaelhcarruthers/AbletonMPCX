"""Spectrum tools — real-time tonal band energy from the AMCPX_Analyzer M4L device.

Requires AMCPX_Analyzer.amxd to be loaded on the master or a bus in your Live set.
Reads from port 9880 via the same TCP transport used by realtime_analyzer.py.
"""
from __future__ import annotations

from tools.realtime_analyzer import _send_analyzer


def get_spectrum_bands(track_index: int = 0) -> dict:
    """Get current tonal band energy from the AMCPX_Analyzer M4L device.

    track_index is accepted for API compatibility but ignored — the analyzer
    runs on the master bus and reports master tonal balance.
    """
    try:
        result = _send_analyzer("get_tonal_balance")
        return {
            "source": "AMCPX_Analyzer",
            "bands": result.get("bands", {}),
            "spectral_centroid_hz": result.get("spectral_centroid_hz"),
            "spectral_tilt": result.get("spectral_tilt"),
            "dominant_peak_hz": result.get("dominant_peak_hz"),
            "flags": result.get("flags", []),
            "last_updated": result.get("last_updated"),
            "error": None,
        }
    except RuntimeError as e:
        return {
            "source": "AMCPX_Analyzer",
            "bands": {},
            "flags": [],
            "error": str(e),
        }


def get_spectrum_overview() -> dict:
    """Get full tonal summary from the AMCPX_Analyzer M4L device.

    Returns overall tilt, band classifications, flags, and a plain-English
    suggestion_focus string from the analyzer server.
    """
    try:
        result = _send_analyzer("get_analyzer_summary")
        return {
            "source": "AMCPX_Analyzer",
            "overall_tilt": result.get("overall_tilt"),
            "bands": result.get("bands", {}),
            "flags": result.get("flags", []),
            "spectral_centroid_hz": result.get("spectral_centroid_hz"),
            "spectral_tilt": result.get("spectral_tilt"),
            "dominant_peak_hz": result.get("dominant_peak_hz"),
            "suggestion_focus": result.get("suggestion_focus"),
            "last_updated": result.get("last_updated"),
            "error": None,
        }
    except RuntimeError as e:
        return {
            "source": "AMCPX_Analyzer",
            "overall_tilt": None,
            "bands": {},
            "flags": [],
            "suggestion_focus": None,
            "error": str(e),
        }
