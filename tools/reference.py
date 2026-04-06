"""Reference tools — import reference track, toggle mute, set volume, compare mix to reference."""
from __future__ import annotations

import math
from typing import Any

from helpers import (
    mcp,
    _send,
)

# Live's mixer scalar that corresponds to 0 dBFS (unity gain).
_UNITY_VOLUME: float = 0.85


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_to_scalar(db: float) -> float:
    """Convert dBFS (relative to Live's unity at 0.85) to a 0–1 scalar, clamped."""
    scalar = (10 ** (db / 20.0)) * _UNITY_VOLUME
    return max(0.0, min(1.0, scalar))


def _scalar_to_db(scalar: float) -> float:
    """Convert Live's 0–1 scalar to dBFS relative to unity (0.85)."""
    return 20.0 * math.log10(max(scalar, 1e-9) / _UNITY_VOLUME)


# ---------------------------------------------------------------------------
# Import reference track
# ---------------------------------------------------------------------------

@mcp.tool()
def import_reference_track(
    file_path: str,
    track_name: str = "Reference",
    volume: float = 0.7,
) -> dict:
    """Create a new audio track configured as a reference track.

    Note: Ableton's Python API does not support loading audio files into clips
    programmatically. After this tool runs, drag `file_path` to the created
    track manually in the Session or Arrangement view.

    Args:
        file_path: Path to the reference audio file (for your records; must be
            loaded manually).
        track_name: Name for the new track (default "Reference").
        volume: Initial volume scalar 0.0–1.0 (default 0.7).

    Returns:
        dict with track_index, track_name, volume, file_path, and a note about
        manual loading.
    """
    result = _send("create_audio_track", {"index": -1})
    track_index = result.get("track_index") if isinstance(result, dict) else None

    if track_index is not None:
        _send("set_track_name", {"track_index": track_index, "name": track_name})
        _send("set_track_volume", {"track_index": track_index, "value": volume})

    return {
        "track_index": track_index,
        "track_name": track_name,
        "volume": volume,
        "file_path": file_path,
        "note": (
            "Ableton's Python API does not support loading audio files into clips "
            "programmatically. Please drag '{}' to the created track manually.".format(file_path)
        ),
    }


# ---------------------------------------------------------------------------
# Toggle reference track mute
# ---------------------------------------------------------------------------

@mcp.tool()
def toggle_reference_track(track_index: int, mute: bool | None = None) -> dict:
    """Toggle or set the mute state of a reference track.

    Args:
        track_index: Track to mute/unmute.
        mute: If None (default), reads the current state and toggles it.
            Otherwise sets mute to the given bool.

    Returns:
        dict with track_index and muted (the resulting mute state).
    """
    if mute is None:
        track_info = _send("get_track_info", {"track_index": track_index})
        current_mute = bool(track_info.get("mute", False)) if isinstance(track_info, dict) else False
        mute = not current_mute

    _send("set_track_mute", {"track_index": track_index, "mute": mute})
    return {"track_index": track_index, "muted": mute}


# ---------------------------------------------------------------------------
# Set reference volume by dB
# ---------------------------------------------------------------------------

@mcp.tool()
def set_reference_volume(track_index: int, volume_db: float) -> dict:
    """Set the volume of a reference track using dBFS.

    Converts `volume_db` to Live's 0–1 scale: `scalar = 10^(volume_db/20) * 0.85`,
    clamped to [0.0, 1.0].

    Args:
        track_index: Track to adjust.
        volume_db: Target level in dBFS relative to unity (0.85).

    Returns:
        dict with track_index, volume_db, and the applied scalar.
    """
    scalar = _db_to_scalar(volume_db)
    _send("set_track_volume", {"track_index": track_index, "value": scalar})
    return {"track_index": track_index, "volume_db": volume_db, "scalar": scalar}


# ---------------------------------------------------------------------------
# Compare mix to reference
# ---------------------------------------------------------------------------

@mcp.tool()
def compare_mix_to_reference(
    mix_track_indices: list[int],
    reference_track_index: int,
) -> dict:
    """Compare the average volume of mix tracks to a reference track.

    Reads volumes and panning for all listed mix tracks and the reference
    track via the session snapshot. Flags if the mix average is more than
    3 dB above or below the reference.

    Args:
        mix_track_indices: List of track indices representing the mix.
        reference_track_index: Track index of the reference track.

    Returns:
        dict with reference_volume, mix_average_volume, delta_db, flags list,
        and per_track breakdown.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    tracks_by_index: dict[int, dict] = {
        int(t.get("track_index", -1)): t for t in tracks
    }

    ref_track = tracks_by_index.get(reference_track_index, {})
    reference_volume = float(ref_track.get("volume", _UNITY_VOLUME))
    ref_db = _scalar_to_db(reference_volume)

    per_track = []
    mix_volumes = []
    for ti in mix_track_indices:
        t = tracks_by_index.get(ti, {})
        vol = float(t.get("volume", _UNITY_VOLUME))
        mix_volumes.append(vol)
        track_db = _scalar_to_db(vol)
        per_track.append({
            "track_index": ti,
            "track_name": t.get("name", ""),
            "volume": vol,
            "delta_db_vs_reference": round(track_db - ref_db, 2),
        })

    # Sort by absolute delta descending (most impactful first)
    per_track.sort(key=lambda x: abs(x["delta_db_vs_reference"]), reverse=True)

    mix_average_volume = sum(mix_volumes) / len(mix_volumes) if mix_volumes else 0.0
    mix_avg_db = _scalar_to_db(mix_average_volume)
    delta_db = round(mix_avg_db - ref_db, 2)

    flags = []
    if delta_db > 3.0:
        flags.append("mix_above_reference_by_{}_db".format(round(delta_db, 1)))
    elif delta_db < -3.0:
        flags.append("mix_below_reference_by_{}_db".format(round(abs(delta_db), 1)))

    return {
        "reference_volume": reference_volume,
        "mix_average_volume": mix_average_volume,
        "delta_db": delta_db,
        "flags": flags,
        "per_track": per_track,
    }
