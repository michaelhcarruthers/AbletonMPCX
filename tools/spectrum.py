"""Spectrum telemetry tools — read real-time band energy from the MCPSpectrumTelemetry plugin."""
from __future__ import annotations

from helpers import mcp, _send


# Band parameter names as exposed by the MCPSpectrumTelemetry plugin
_BAND_PARAMS = ["sub", "bass", "punch", "body", "mid", "upmid", "presence", "air"]


def _find_spectrum_device(track_index: int) -> dict | None:
    """Return the first MCPSpectrumTelemetry device on a track, or None."""
    devices = _send("get_devices", {"track_index": track_index})
    if not isinstance(devices, list):
        return None
    for d in devices:
        name = d.get("name", "")
        if "spectrum" in name.lower() or "telemetry" in name.lower():
            return d
    return None


@mcp.tool()
def get_spectrum_bands(track_index: int) -> dict:
    """Read the current 8-band spectrum energy from the MCPSpectrumTelemetry plugin on a track."""
    device = _find_spectrum_device(track_index)
    if device is None:
        return {
            "track_index": track_index,
            "device_name": None,
            "bands": {},
            "error": (
                "No MCPSpectrumTelemetry device found on track {}. "
                "Add the plugin to the track first.".format(track_index)
            ),
        }

    device_index = device.get("index", device.get("device_index", 0))
    params = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    })

    bands = {}
    if isinstance(params, list):
        for p in params:
            name = p.get("name", "").lower()
            if name in _BAND_PARAMS:
                bands[name] = round(float(p.get("value", 0.0)), 2)

    return {
        "track_index": track_index,
        "device_name": device.get("name"),
        "bands": bands,
        "error": None,
    }


@mcp.tool()
def get_spectrum_overview() -> dict:
    """Read spectrum band energy from all tracks that have a MCPSpectrumTelemetry plugin."""
    tracks_data = _send("get_tracks")
    if not isinstance(tracks_data, list):
        return {"tracks": [], "track_count": 0, "error": "Could not retrieve tracks"}

    results = []
    for track in tracks_data:
        idx = track.get("index", track.get("track_index"))
        name = track.get("name", "Unnamed")
        if idx is None:
            continue
        snap = get_spectrum_bands(idx)
        if snap.get("bands"):
            results.append({
                "track_index": idx,
                "track_name": name,
                "device_name": snap.get("device_name"),
                "bands": snap.get("bands", {}),
            })

    return {
        "tracks": results,
        "track_count": len(results),
        "error": None,
    }
