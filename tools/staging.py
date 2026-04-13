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
    """Assign a semantic role to a track (e.g. 'kick', 'snare', 'bass', 'lead', 'pad', 'fx', 'master')."""
    mem = _get_memory()
    roles = mem.setdefault("track_roles", {})
    roles[str(track_index)] = role
    if persist:
        _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "role": role, "persisted": persist}


@mcp.tool()
def get_track_roles() -> dict:
    """Return all stored track roles from project memory."""
    _load_reference_profiles_from_project()
    mem = _get_memory()
    roles = mem.get("track_roles", {})
    return {"roles": roles, "count": len(roles)}


@mcp.tool()
def clear_track_role(track_index: int, persist: bool = True) -> dict:
    """Remove the role assigned to a track."""
    mem = _get_memory()
    roles = mem.setdefault("track_roles", {})
    removed = str(track_index) in roles
    roles.pop(str(track_index), None)
    if persist:
        _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "removed": removed, "persisted": persist}


@mcp.tool()
def validate_track_roles() -> dict:
    """Validate stored track roles against the current session."""
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
    """Analyse current track volumes and flag gain-staging issues."""
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
    """Set track volumes to a target dB level relative to unity."""
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
        current_db = round(_vol_to_db(old_vol), 2)
        delta = round(target_db - current_db, 2)
        changes.append({
            "track_index": ti,
            "track_name": t.get("name", ""),
            "old_volume": old_vol,
            "new_volume": round(target_scalar, 6),
            "current_db": current_db,
            "target_db": round(target_db, 2),
            "delta": delta,
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


# ---------------------------------------------------------------------------
# Studio-style gain staging helpers
# ---------------------------------------------------------------------------

def _db_to_gain_linear(db: float) -> float:
    """Convert dB to a linear gain multiplier (0 dB → 1.0)."""
    return 10.0 ** (db / 20.0)


def _gain_linear_to_db(linear: float) -> float:
    """Convert a linear gain multiplier to dB (1.0 → 0 dB)."""
    # Floor at 1e-9 to prevent log10(0) → -inf
    return 20.0 * math.log10(max(linear, 1e-9))


def _select_tracks(
    tracks: list[dict],
    track_indices: list[int] | None,
    track_names: list[str] | None,
) -> list[dict]:
    """Return tracks that match the given index or name filter (or all tracks if neither is set)."""
    if track_indices is not None:
        idx_set = set(track_indices)
        return [t for t in tracks if t.get("track_index") in idx_set]
    if track_names is not None:
        name_set = set(track_names)
        return [t for t in tracks if t.get("name", "") in name_set]
    return list(tracks)


def _get_all_clips() -> list[dict]:
    """Fetch all clip slots from the session and normalise the response to a flat list."""
    clips_raw = _send("get_session_clips", {"slim": True})
    if isinstance(clips_raw, list):
        return clips_raw
    if isinstance(clips_raw, dict):
        return clips_raw.get("clips", [])
    return []


def gain_analyze(
    target_clip_db: float = -6.0,
    headroom_db: float = 6.0,
    track_indices: list[int] | None = None,
    track_names: list[str] | None = None,
) -> dict:
    """Inspect audio clip gains and track faders separately.

    Returns:
      - clips_above_target: audio clips whose clip gain exceeds *target_clip_db*
      - tracks_above_headroom: tracks whose fader is above the headroom threshold
    MIDI clips are ignored for clip-gain analysis.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    selected = _select_tracks(tracks, track_indices, track_names)

    headroom_threshold_db = -headroom_db

    clips_above_target: list[dict] = []
    tracks_above_headroom: list[dict] = []

    all_clips = _get_all_clips()

    selected_indices = {t.get("track_index") for t in selected}

    for clip in all_clips:
        ti = clip.get("track_index")
        if ti not in selected_indices:
            continue
        si = clip.get("slot_index")
        try:
            info = _send("get_clip_info", {"track_index": ti, "slot_index": si})
        except Exception:
            continue
        if info.get("is_midi_clip", False):
            continue
        raw_gain = info.get("gain")
        if raw_gain is None:
            continue
        clip_gain_db = round(_gain_linear_to_db(float(raw_gain)), 2)
        if clip_gain_db > target_clip_db:
            track_name = next((t.get("name", "") for t in selected if t.get("track_index") == ti), "")
            clips_above_target.append({
                "track_index": ti,
                "track_name": track_name,
                "slot_index": si,
                "clip_name": info.get("name", ""),
                "clip_gain_db": clip_gain_db,
                "target_clip_db": target_clip_db,
                "excess_db": round(clip_gain_db - target_clip_db, 2),
            })

    for t in selected:
        vol = float(t.get("volume", _UNITY_VOLUME))
        fader_db = round(_vol_to_db(vol), 2)
        if fader_db > headroom_threshold_db:
            tracks_above_headroom.append({
                "track_index": t.get("track_index"),
                "track_name": t.get("name", ""),
                "fader_volume": vol,
                "fader_db": fader_db,
                "headroom_db": headroom_db,
                "excess_db": round(fader_db - headroom_threshold_db, 2),
            })

    return {
        "clips_above_target": clips_above_target,
        "tracks_above_headroom": tracks_above_headroom,
        "target_clip_db": target_clip_db,
        "headroom_db": headroom_db,
        "clips_checked": len([c for c in all_clips if c.get("track_index") in selected_indices]),
        "tracks_checked": len(selected),
    }


def gain_trim_clips(
    target_clip_db: float = -6.0,
    only_above_target: bool = True,
    dry_run: bool = False,
    track_indices: list[int] | None = None,
    track_names: list[str] | None = None,
) -> dict:
    """Trim audio clip gain toward *target_clip_db*. Never touches track faders.

    Args:
        target_clip_db: Target clip gain in dB (default -6.0).
        only_above_target: When True (default), only reduce clips that are
            currently above the target; clips below are left untouched.
        dry_run: When True, report planned changes without applying them.
        track_indices: Optional list of track indices to restrict to.
        track_names: Optional list of track names to restrict to.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    selected = _select_tracks(tracks, track_indices, track_names)
    selected_indices = {t.get("track_index") for t in selected}
    track_name_by_index = {t.get("track_index"): t.get("name", "") for t in selected}

    all_clips = _get_all_clips()
    changes: list[dict] = []
    skipped: list[dict] = []

    for clip in all_clips:
        ti = clip.get("track_index")
        if ti not in selected_indices:
            continue
        si = clip.get("slot_index")
        try:
            info = _send("get_clip_info", {"track_index": ti, "slot_index": si})
        except Exception as exc:
            skipped.append({"track_index": ti, "slot_index": si, "reason": str(exc)})
            continue
        if info.get("is_midi_clip", False):
            skipped.append({"track_index": ti, "slot_index": si, "reason": "midi_clip"})
            continue
        raw_gain = info.get("gain")
        if raw_gain is None:
            skipped.append({"track_index": ti, "slot_index": si, "reason": "gain_read_failed"})
            continue

        current_gain_db = round(_gain_linear_to_db(float(raw_gain)), 2)
        if only_above_target and current_gain_db <= target_clip_db:
            skipped.append({"track_index": ti, "slot_index": si, "reason": "below_target", "clip_gain_db": current_gain_db})
            continue

        new_gain_db = target_clip_db
        # Clamp to valid range: Live clip gain is 0.0 (silence) to 1.0 (0 dB)
        new_gain_linear = max(0.0, min(1.0, _db_to_gain_linear(new_gain_db)))
        changes.append({
            "track_index": ti,
            "track_name": track_name_by_index.get(ti, ""),
            "slot_index": si,
            "clip_name": info.get("name", ""),
            "old_gain_db": current_gain_db,
            "new_gain_db": new_gain_db,
            "delta_db": round(new_gain_db - current_gain_db, 2),
            "new_gain_linear": round(new_gain_linear, 6),
        })

    if not dry_run and changes:
        _send("begin_undo_step", {"name": "gain_trim_clips"})
        try:
            for change in changes:
                _send("set_clip_gain", {
                    "track_index": change["track_index"],
                    "slot_index": change["slot_index"],
                    "gain": change["new_gain_linear"],
                })
        finally:
            _send("end_undo_step")

    return {
        "applied": not dry_run,
        "dry_run": dry_run,
        "target_clip_db": target_clip_db,
        "only_above_target": only_above_target,
        "changes": changes,
        "skipped": skipped,
        "changed_count": len(changes),
        "skipped_count": len(skipped),
    }


def gain_protect_headroom(
    headroom_db: float = 6.0,
    dry_run: bool = False,
    track_indices: list[int] | None = None,
    track_names: list[str] | None = None,
) -> dict:
    """Reduce track faders for tracks that exceed the headroom threshold.

    This is a safety pass only — it never raises faders and never touches
    clip gain. Tracks already within headroom are left unchanged.

    Args:
        headroom_db: The maximum allowed fader level expressed as headroom
            below 0 dBFS (default 6.0, meaning faders must stay ≤ -6 dB).
        dry_run: When True, report planned changes without applying them.
        track_indices: Optional list of track indices to restrict to.
        track_names: Optional list of track names to restrict to.
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    selected = _select_tracks(tracks, track_indices, track_names)

    headroom_threshold_db = -headroom_db
    target_scalar = (10 ** (headroom_threshold_db / 20.0)) * _UNITY_VOLUME
    target_scalar = max(0.0, min(1.0, target_scalar))

    changes: list[dict] = []
    skipped: list[dict] = []

    for t in selected:
        ti = t.get("track_index")
        vol = float(t.get("volume", _UNITY_VOLUME))
        fader_db = round(_vol_to_db(vol), 2)
        if fader_db <= headroom_threshold_db:
            skipped.append({
                "track_index": ti,
                "track_name": t.get("name", ""),
                "fader_db": fader_db,
                "reason": "within_headroom",
            })
            continue
        changes.append({
            "track_index": ti,
            "track_name": t.get("name", ""),
            "old_volume": vol,
            "new_volume": round(target_scalar, 6),
            "old_fader_db": fader_db,
            "new_fader_db": headroom_threshold_db,
            "delta_db": round(headroom_threshold_db - fader_db, 2),
        })

    if not dry_run and changes:
        _send("begin_undo_step", {"name": "gain_protect_headroom"})
        try:
            for change in changes:
                _send("set_track_volume", {"track_index": change["track_index"], "value": change["new_volume"]})
        finally:
            _send("end_undo_step")

    return {
        "applied": not dry_run,
        "dry_run": dry_run,
        "headroom_db": headroom_db,
        "changes": changes,
        "skipped": skipped,
        "changed_count": len(changes),
        "skipped_count": len(skipped),
    }
