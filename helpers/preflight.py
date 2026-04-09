"""
Pre-flight helpers that fetch Live session state once per request
and cache results locally. Reduces round-trips to Live.
"""
from __future__ import annotations
from helpers import _send

_session_cache: dict = {}


def get_session_state(force_refresh: bool = False) -> dict:
    """Fetch tempo, time_sig_numerator, time_sig_denominator from Live. Cached per-process."""
    global _session_cache
    if not _session_cache or force_refresh:
        result = _send("get_song_info")
        _session_cache = {
            "tempo": float(result.get("tempo", 120.0)),
            "time_sig_numerator": int(result.get("time_sig_numerator", 4)),
            "time_sig_denominator": int(result.get("time_sig_denominator", 4)),
        }
    return _session_cache


def invalidate_session_cache() -> None:
    """Clear the cached session state so the next call re-fetches from Live."""
    global _session_cache
    _session_cache = {}


def get_track_index_by_name(track_name: str) -> int | None:
    """Find a track index by name (case-insensitive substring match). Returns None if not found."""
    tracks = _send("get_tracks")
    if not isinstance(tracks, list):
        return None
    name_lower = track_name.strip().lower()
    for i, t in enumerate(tracks):
        if name_lower in t.get("name", "").lower():
            return i
    return None


def get_device_index_by_name(track_index: int, device_name: str) -> int | None:
    """Find a device index on a track by name (case-insensitive substring match). Returns None if not found."""
    result = _send("get_track_devices", {"track_index": track_index, "is_return_track": False})
    devices = result.get("devices", []) if isinstance(result, dict) else []
    name_lower = device_name.strip().lower()
    for i, d in enumerate(devices):
        if name_lower in d.get("name", "").lower():
            return i
    return None


def get_device_parameter_value(
    track_index: int,
    device_index: int,
    parameter_name: str,
) -> float | None:
    """Fetch the current normalised value (0.0–1.0) of a named parameter on a device. Returns None if not found."""
    result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    })
    params = result if isinstance(result, list) else (result.get("parameters", []) if isinstance(result, dict) else [])
    name_lower = parameter_name.strip().lower()
    for p in params:
        if name_lower in p.get("name", "").lower():
            return float(p.get("value", 0.0))
    return None
