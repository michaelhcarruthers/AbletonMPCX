"""FabFilter Pro-Q 4 band control helpers.

Provides Hz/dB/Q ↔ normalized value conversions and ``set_proq4_band`` for
writing parameters to a Pro-Q 4 instance via ``set_device_parameters_batch``.

Frequency scaling verified against live parameter dump data points:
  60 Hz   → 0.22379
  250 Hz  → 0.40204
  500 Hz  → 0.48861
  1000 Hz → 0.57519
  2000 Hz → 0.66176
  6000 Hz → 0.79898
  10000 Hz → 0.86278

Correct scale constants (derived from live data): F_min = 10 Hz, F_max = 30 000 Hz.
"""
from __future__ import annotations

import math

from helpers import _send

# ---------------------------------------------------------------------------
# Frequency scaling  (logarithmic, 13.75 Hz – 96 000 Hz)
# ---------------------------------------------------------------------------

_FREQ_MIN_HZ = 10.0
_FREQ_MAX_HZ = 30000.0


def hz_to_proq4(hz: float) -> float:
    """Convert Hz to Pro-Q 4 normalized frequency value (0.0–1.0)."""
    hz = max(_FREQ_MIN_HZ, min(_FREQ_MAX_HZ, hz))
    return math.log10(hz / _FREQ_MIN_HZ) / math.log10(_FREQ_MAX_HZ / _FREQ_MIN_HZ)


def proq4_to_hz(norm: float) -> float:
    """Convert Pro-Q 4 normalized frequency value back to Hz."""
    return _FREQ_MIN_HZ * (_FREQ_MAX_HZ / _FREQ_MIN_HZ) ** norm


# ---------------------------------------------------------------------------
# Gain scaling  (linear, ±30 dB)
# ---------------------------------------------------------------------------

def db_to_proq4(db: float) -> float:
    """Convert dB to Pro-Q 4 normalized gain value (0.0–1.0). Range: ±30 dB."""
    db = max(-30.0, min(30.0, db))
    return (db + 30.0) / 60.0


def proq4_to_db(norm: float) -> float:
    """Convert Pro-Q 4 normalized gain value back to dB."""
    return norm * 60.0 - 30.0


# ---------------------------------------------------------------------------
# Q scaling  (logarithmic, 0.025–40)
# ---------------------------------------------------------------------------

_Q_MIN = 0.025
_Q_MAX = 40.0


def q_to_proq4(q: float) -> float:
    """Convert Q value to Pro-Q 4 normalized Q (0.0–1.0). Range: 0.025–40."""
    q = max(_Q_MIN, min(_Q_MAX, q))
    return math.log10(q / _Q_MIN) / math.log10(_Q_MAX / _Q_MIN)


# ---------------------------------------------------------------------------
# Band parameter index map  (derived from live parameter dump)
# ---------------------------------------------------------------------------

# Layout: {band_number (1-based): {property: parameter_index}}
_BAND_PARAM_MAP = {
    1: {"freq": 2,  "gain": 13, "q": 3,  "shape": 1,  "enabled": 43},
    2: {"freq": 17, "gain": 14, "q": 18, "shape": 20, "enabled": 42},
    3: {"freq": 21, "gain": 15, "q": 24, "shape": 22, "enabled": 40},
    4: {"freq": 5,  "gain": 16, "q": 7,  "shape": 6,  "enabled": 41},
    5: {"freq": 52, "gain": 50, "q": 51, "shape": 48, "enabled": None},
    6: {"freq": 33, "gain": 34, "q": None, "shape": 53, "enabled": 36},
}

# ---------------------------------------------------------------------------
# Filter shape values
# ---------------------------------------------------------------------------

_SHAPE_VALUES: dict[str, float] = {
    "bell": 0.0,
    "low_shelf": 1.0,
    "high_shelf": 2.0,
    "low_cut": 3.0,
    "high_cut": 4.0,
    "notch": 5.0,
    "band_pass": 6.0,
    "tilt_shelf": 7.0,
}

# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def set_proq4_band(
    track_index: int,
    device_index: int,
    band: int,
    freq_hz: float | None = None,
    gain_db: float | None = None,
    q: float | None = None,
    shape: str | None = None,
    enabled: bool | None = None,
    is_return_track: bool = False,
) -> dict:
    """Set one or more parameters on a specific Pro-Q 4 band with musical values.

    Parameters
    ----------
    track_index : int
        0-based track index in Ableton.
    device_index : int
        0-based device index on the track.
    band : int
        1-based band number (1–6 supported).
    freq_hz : float | None
        Target frequency in Hz (e.g. 250.0).
    gain_db : float | None
        Gain in dB (e.g. -3.0). Range: ±30 dB.
    q : float | None
        Q / bandwidth value (e.g. 1.0). Range: 0.025–40.
    shape : str | None
        Filter shape: 'bell', 'low_shelf', 'high_shelf', 'low_cut', 'high_cut',
        'notch', 'band_pass', 'tilt_shelf'.
    enabled : bool | None
        Enable or disable the band.
    is_return_track : bool
        Set True if targeting a return track.

    Returns
    -------
    dict
        Contains status, band, track/device indices, applied changes, and the
        raw result from the batch parameter write.
    """
    if band not in _BAND_PARAM_MAP:
        return {
            "status": "error",
            "error": f"Band {band} not supported. Valid bands: {sorted(_BAND_PARAM_MAP.keys())}",
        }

    param_map = _BAND_PARAM_MAP[band]
    updates: list[dict] = []
    applied: dict = {}

    if freq_hz is not None:
        norm = hz_to_proq4(freq_hz)
        updates.append({"parameter_index": param_map["freq"], "value": norm})
        applied["freq_hz"] = freq_hz
        applied["freq_normalized"] = round(norm, 6)

    if gain_db is not None:
        norm = db_to_proq4(gain_db)
        updates.append({"parameter_index": param_map["gain"], "value": norm})
        applied["gain_db"] = gain_db
        applied["gain_normalized"] = round(norm, 6)

    if q is not None and param_map.get("q") is not None:
        norm = q_to_proq4(q)
        updates.append({"parameter_index": param_map["q"], "value": norm})
        applied["q"] = q
        applied["q_normalized"] = round(norm, 6)

    if shape is not None:
        shape_key = shape.lower().replace(" ", "_")
        if shape_key not in _SHAPE_VALUES:
            return {
                "status": "error",
                "error": f"Unknown shape '{shape}'. Valid: {list(_SHAPE_VALUES.keys())}",
            }
        updates.append({"parameter_index": param_map["shape"], "value": _SHAPE_VALUES[shape_key]})
        applied["shape"] = shape

    if enabled is not None and param_map.get("enabled") is not None:
        updates.append({"parameter_index": param_map["enabled"], "value": 1.0 if enabled else 0.0})
        applied["enabled"] = enabled

    if not updates:
        return {
            "status": "error",
            "error": "No parameters specified. Provide at least one of: freq_hz, gain_db, q, shape, enabled.",
        }

    result = _send("set_device_parameters_batch", {
        "track_index": track_index,
        "device_index": device_index,
        "updates": updates,
        "is_return_track": is_return_track,
        "visual_refresh": True,
        "skip_unchanged": False,
        "clamp_values": True,
    })

    return {
        "status": "ok",
        "band": band,
        "track_index": track_index,
        "device_index": device_index,
        "applied": applied,
        "raw_result": result,
    }
