"""Staging tools — gain staging and track role management."""
from __future__ import annotations

import math
from typing import Any

from helpers import (
    mcp,
    _send,
    _get_memory,
    _save_memory,
    _load_reference_profiles_from_project,
)
import helpers

# Live's mixer scalar that corresponds to 0 dBFS (unity gain).
_UNITY_VOLUME: float = 0.85


# ---------------------------------------------------------------------------
# Track role management
# ---------------------------------------------------------------------------

@mcp.tool()
def set_track_role(track_index: int, role: str, persist: bool = True) -> dict:
    """Assign a semantic role to a track (e.g. 'kick', 'snare', 'bass', 'lead', 'pad', 'fx', 'master').

    Args:
        track_index: Zero-based index of the track.
        role: Semantic role string to assign.
        persist: If True (default), saves the role to project memory.

    Returns:
        dict with track_index, role, and persisted flag.
    """
    mem = _get_memory()
    roles = mem.setdefault("track_roles", {})
    roles[str(track_index)] = role
    if persist:
        _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "role": role, "persisted": persist}


@mcp.tool()
def get_track_roles() -> dict:
    """Return all stored track roles from project memory.

    Returns:
        dict with roles mapping (track_index_str -> role) and count.
    """
    _load_reference_profiles_from_project()
    mem = _get_memory()
    roles = mem.get("track_roles", {})
    return {"roles": roles, "count": len(roles)}


@mcp.tool()
def clear_track_role(track_index: int, persist: bool = True) -> dict:
    """Remove the role assigned to a track.

    Args:
        track_index: Zero-based index of the track.
        persist: If True (default), saves the updated memory to disk.

    Returns:
        dict with track_index and removed flag.
    """
    mem = _get_memory()
    roles = mem.setdefault("track_roles", {})
    removed = str(track_index) in roles
    roles.pop(str(track_index), None)
    if persist:
        _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "removed": removed, "persisted": persist}


@mcp.tool()
def validate_track_roles() -> dict:
    """Validate stored track roles against the current session.

    Checks whether each stored track index still exists and whether the
    stored track name matches the current name. Flags mismatches as
    'unverified' rather than silently remapping them.

    Returns:
        dict with valid, unverified, and missing lists, plus total count.
    """
    mem = _get_memory()
    stored_roles: dict[str, str] = mem.get("track_roles", {})
    if not stored_roles:
        return {"valid": [], "unverified": [], "missing": [], "total": 0}

    try:
        snapshot = _send("get_session_snapshot")
    except Exception:
        snapshot = None

    tracks_by_index: dict[int, dict] = {}
    if snapshot and isinstance(snapshot, dict):
        for t in snapshot.get("tracks", []):
            idx = t.get("track_index")
            if idx is not None:
                tracks_by_index[int(idx)] = t

    valid = []
    unverified = []
    missing = []

    for idx_str, role in stored_roles.items():
        idx = int(idx_str)
        if idx not in tracks_by_index:
            missing.append({"track_index": idx, "role": role})
        else:
            track = tracks_by_index[idx]
            entry = {"track_index": idx, "track_name": track.get("name", ""), "role": role}
            valid.append(entry)

    return {
        "valid": valid,
        "unverified": unverified,
        "missing": missing,
        "total": len(stored_roles),
    }


# ---------------------------------------------------------------------------
# Gain staging
# ---------------------------------------------------------------------------

def _vol_to_db(vol: float) -> float:
    """Convert Live's 0-1 volume to an approximate dBFS relative to unity (0.85)."""
    return 20.0 * math.log10(max(vol, 1e-9) / _UNITY_VOLUME)


@mcp.tool()
def suggest_gain_staging(headroom_db: float = 6.0) -> dict:
    """Analyse current track volumes and flag gain-staging issues.

    Live's mixer volume runs 0.0–1.0 where 0.85 ≈ unity (0 dBFS).
    Tracks above `(0 - headroom_db)` dB or at exactly 0.0 are flagged.

    Args:
        headroom_db: Desired headroom in dB below unity (default 6.0).

    Returns:
        dict with suggestions list, headroom_db, and track_count.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    threshold_db = -headroom_db
    suggestions = []
    for t in tracks:
        vol = float(t.get("volume", _UNITY_VOLUME))
        estimated_db = _vol_to_db(vol)
        flag: str | None = None
        if vol == 0.0:
            flag = "silenced"
        elif estimated_db > threshold_db:
            flag = "above_headroom"
        suggestions.append({
            "track_index": t.get("track_index"),
            "track_name": t.get("name", ""),
            "volume": vol,
            "estimated_db": round(estimated_db, 2),
            "flag": flag,
        })
    # Sort by impact: flagged first, then by estimated_db descending
    suggestions.sort(key=lambda s: (s["flag"] is None, -s["estimated_db"]))
    return {"suggestions": suggestions, "headroom_db": headroom_db, "track_count": len(suggestions)}


@mcp.tool()
def apply_gain_staging(
    target_db: float = -6.0,
    track_indices: list[int] | None = None,
    dry_run: bool = True,
) -> dict:
    """Set track volumes to a target dB level relative to unity.

    Calculates `target_scalar = 10^(target_db/20) * 0.85` and applies it
    to all specified tracks (or all tracks if `track_indices` is empty).

    Args:
        target_db: Target level in dBFS relative to unity (default -6.0).
        track_indices: Specific track indices to adjust; all tracks if empty/None.
        dry_run: If True (default), returns the plan without touching Live.

    Returns:
        dict with applied, dry_run, changes list, and target_db.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    target_scalar = (10 ** (target_db / 20.0)) * _UNITY_VOLUME
    target_scalar = max(0.0, min(1.0, target_scalar))

    selected = set(track_indices) if track_indices else None
    changes = []
    for t in tracks:
        ti = t.get("track_index")
        if selected is not None and ti not in selected:
            continue
        old_vol = float(t.get("volume", _UNITY_VOLUME))
        changes.append({
            "track_index": ti,
            "track_name": t.get("name", ""),
            "old_volume": old_vol,
            "new_volume": round(target_scalar, 6),
        })

    if not dry_run:
        _send("begin_undo_step", {"name": "apply_gain_staging"})
        try:
            for change in changes:
                _send("set_track_volume", {"track_index": change["track_index"], "value": change["new_volume"]})
        finally:
            _send("end_undo_step")

    return {
        "applied": not dry_run,
        "dry_run": dry_run,
        "changes": changes,
        "target_db": target_db,
    }
