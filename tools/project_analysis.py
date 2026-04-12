"""
Project-level mix analysis — two clearly separated workflows.

Workflow 1 – Debug Mode
    debug_mix_compare(tracks, labels)
    Goal: help the user fix mix-level issues using a small, controlled
    comparison set of *exactly* 3 tracks.  No sequencing logic.

Workflow 2 – Final Review Mode
    final_review_mode(tracks, track_names, anchor_index, sequence)
    Goal: evaluate full-project cohesion and suggest track ordering after
    mixes are already stable.  Supports N tracks and includes a sequencing
    engine.

These two workflows must remain separate:
  - Debug Mode   = fix mixes  (3-track constraint, no sequencing)
  - Final Review = album eval (N tracks, includes sequencing)
"""
from __future__ import annotations

import math
import re
from typing import Any

# ---------------------------------------------------------------------------
# Re-use helpers already defined in diagnostics
# ---------------------------------------------------------------------------
from tools.diagnostics import (
    _classify_low_mid_overlap,
    _detect_bus_processing,
    _is_vocal_track,
    _is_drum_track,
    _staging_score,
    _db_from_linear,
    _LOW_MID_HZ_LABEL,
    _MOVE_PROCESSED,
    _MOVE_UNPROCESSED,
)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_DEFAULT_LABELS = ("A", "B", "C")
_DEBUG_TRACK_LIMIT = 3

# Thresholds for outlier detection (Final Review Mode)
_LUFS_OUTLIER_DELTA = 3.0       # dB — flag if track differs from median by this much
_TONAL_OUTLIER_DELTA = 0.25     # spectral-tilt units
_DENSITY_OUTLIER_DELTA = 0.20   # normalised crest-factor units
_WIDTH_OUTLIER_DELTA = 0.20     # normalised width units


# ===========================================================================
# ── WORKFLOW 1 : DEBUG MODE ─────────────────────────────────────────────────
# ===========================================================================

def debug_mix_compare(
    tracks: list[dict],
    labels: list[str] | None = None,
) -> dict:
    """
    Workflow 1 — Debug Mode: small-set mix comparison.

    Accepts exactly 3 track dictionaries.  Analyses per-track mix
    characteristics and cross-track relationships, then returns conservative,
    auditable correction suggestions.

    Parameters
    ----------
    tracks : list[dict]
        Exactly 3 track dicts.  Each dict should contain at minimum:
          - ``name``         : str
          - ``mixer_device`` : dict with ``volume`` (linear 0–1)
          - ``devices``      : list of device dicts with ``name`` key
        Optional per-track keys used when present:
          - ``lufs``          : float  (integrated LUFS)
          - ``peak_dbfs``     : float
          - ``spectral_tilt`` : float
          - ``crest_factor``  : float  (0–1 normalised density proxy)
          - ``stereo_width``  : float  (0–1 normalised)
    labels : list[str] | None
        Optional custom labels for the three tracks (default: A / B / C).

    Returns
    -------
    dict with keys:
        ``mode``                   – always "debug"
        ``track_count``            – always 3
        ``per_track``              – list of per-track issue summaries
        ``cross_track_comparison`` – relative differences across all 3 tracks
        ``most_likely_problem_track`` – dict(name, label, reason)
        ``ranked_corrections``     – conservative corrective move list
        ``language_notes``         – reminder of output language rules
    """
    # ── 0. Enforce 3-track constraint ────────────────────────────────
    if not isinstance(tracks, list) or len(tracks) != _DEBUG_TRACK_LIMIT:
        return {
            "mode": "debug",
            "status": "error",
            "error": (
                "Debug Mode requires exactly {n} tracks; "
                "{got} provided.".format(n=_DEBUG_TRACK_LIMIT, got=len(tracks) if isinstance(tracks, list) else 0)
            ),
        }

    effective_labels = list(labels) if labels and len(labels) == _DEBUG_TRACK_LIMIT else list(_DEFAULT_LABELS)

    # ── 1. Build per-track profiles ───────────────────────────────────
    profiles: list[dict] = []
    for i, t in enumerate(tracks):
        profiles.append(_build_track_profile(t, effective_labels[i]))

    # ── 2. Compute cross-track reference values ───────────────────────
    db_values = [p["db"] for p in profiles if p["db"] is not None]
    avg_db = sum(db_values) / len(db_values) if db_values else 0.0

    tilt_values = [p["spectral_tilt"] for p in profiles if p["spectral_tilt"] is not None]
    avg_tilt = sum(tilt_values) / len(tilt_values) if tilt_values else None

    lm_values = [p["low_mid_overlap"] for p in profiles]
    avg_lm = sum(lm_values) / len(lm_values) if lm_values else 0.5

    density_values = [p["crest_factor"] for p in profiles if p["crest_factor"] is not None]
    avg_density = sum(density_values) / len(density_values) if density_values else None

    # ── 3. Per-track analysis ─────────────────────────────────────────
    per_track_results: list[dict] = []
    for p in profiles:
        issues: list[str] = []
        # Loudness check
        if p["db"] is not None:
            delta = p["db"] - avg_db
            if delta > 2.0:
                issues.append(
                    "slightly louder than the group average ({:+.1f} dB relative)".format(delta)
                )
            elif delta < -2.0:
                issues.append(
                    "slightly quieter than the group average ({:+.1f} dB relative)".format(delta)
                )

        # Low-mid density
        if p["low_mid_overlap"] >= 0.7:
            issues.append("likely contributor to low-mid density ({})".format(_LOW_MID_HZ_LABEL))

        # Masking likelihood (high lm + louder than average)
        if p["low_mid_overlap"] >= 0.6 and p["db"] is not None and (p["db"] - avg_db) > 0.5:
            issues.append(
                "elevated level combined with strong {} overlap — possible masking source".format(_LOW_MID_HZ_LABEL)
            )

        # Spectral tilt vs group
        if avg_tilt is not None and p["spectral_tilt"] is not None:
            tilt_delta = p["spectral_tilt"] - avg_tilt
            if tilt_delta < -0.2:
                issues.append("slightly darker than the other tracks")
            elif tilt_delta > 0.2:
                issues.append("slightly brighter than the other tracks")

        # Density vs group
        if avg_density is not None and p["crest_factor"] is not None:
            d_delta = p["crest_factor"] - avg_density
            if d_delta > 0.15:
                issues.append("denser than the group average (lower crest factor)")
            elif d_delta < -0.15:
                issues.append("sparser than the group average (higher crest factor)")

        # Processing state note
        if p["has_bus_processing"]:
            issues.append(
                "already has bus/mastering-style processing ({}) — "
                "fader corrections will be smaller and less predictable".format(
                    ", ".join(p["bus_proc_devices"])
                )
            )

        per_track_results.append({
            "label": p["label"],
            "name": p["name"],
            "db": p["db"],
            "low_mid_overlap_score": round(p["low_mid_overlap"], 2),
            "spectral_tilt": p["spectral_tilt"],
            "crest_factor": p["crest_factor"],
            "stereo_width": p["stereo_width"],
            "has_bus_processing": p["has_bus_processing"],
            "issues": issues if issues else ["no significant issues detected"],
        })

    # ── 4. Cross-track comparison ─────────────────────────────────────
    loudness_spread = (max(db_values) - min(db_values)) if len(db_values) >= 2 else 0.0
    tonal_spread = (max(tilt_values) - min(tilt_values)) if len(tilt_values) >= 2 else None
    density_spread = (max(density_values) - min(density_values)) if len(density_values) >= 2 else None

    cross_track = {
        "loudness_spread_db": round(loudness_spread, 1),
        "loudness_note": (
            "loudness difference is within normal range"
            if loudness_spread < 3.0
            else "notable loudness difference across tracks — consider checking relative levels"
        ),
        "tonal_note": _tonal_note(tilt_values, profiles),
        "density_note": _density_note(density_values, profiles),
        "relative_levels": [
            {
                "label": p["label"],
                "name": p["name"],
                "db": p["db"],
                "relative_to_average": round(p["db"] - avg_db, 1) if p["db"] is not None else None,
            }
            for p in profiles
        ],
    }

    # ── 5. Identify most likely problem track ─────────────────────────
    problem_track = _identify_problem_track(profiles, avg_db, avg_tilt, avg_lm)

    # ── 6. Ranked corrections ─────────────────────────────────────────
    ranked_corrections = _build_debug_corrections(profiles, avg_db, avg_lm)

    return {
        "mode": "debug",
        "track_count": 3,
        "per_track": per_track_results,
        "cross_track_comparison": cross_track,
        "most_likely_problem_track": problem_track,
        "ranked_corrections": ranked_corrections,
        "recheck_guidance": (
            "After any suggested move, re-listen to the same section and assess: "
            "perceived congestion, melodic separation, vocal clarity. "
            "Master metering can be checked as a reference but is not the primary target."
        ),
        "language_notes": {
            "use": ["likely contributor", "low-mid dense", "slightly darker than others"],
            "avoid": ["overconfident prescriptions", "aggressive multi-track cuts"],
        },
    }


def _build_track_profile(track: dict, label: str) -> dict:
    """Extract a normalised feature profile from a track dict."""
    name = track.get("name", "Unnamed")
    mixer = track.get("mixer_device") or {}
    volume_linear = mixer.get("volume")
    devices = track.get("devices") or []

    db = _db_from_linear(volume_linear) if volume_linear is not None else None
    has_bus_proc, bus_proc_devs = _detect_bus_processing(devices)
    lm_overlap = _classify_low_mid_overlap(name)

    return {
        "label": label,
        "name": name,
        "db": round(db, 1) if db is not None else None,
        "low_mid_overlap": lm_overlap,
        "spectral_tilt": track.get("spectral_tilt"),
        "crest_factor": track.get("crest_factor"),
        "stereo_width": track.get("stereo_width"),
        "lufs": track.get("lufs"),
        "has_bus_processing": has_bus_proc,
        "bus_proc_devices": bus_proc_devs,
    }


def _tonal_note(tilt_values: list[float], profiles: list[dict]) -> str:
    if len(tilt_values) < 2:
        return "spectral tilt data not available for all tracks"
    spread = max(tilt_values) - min(tilt_values)
    if spread < 0.15:
        return "tonal balance is consistent across tracks"
    darkest = min(profiles, key=lambda p: p["spectral_tilt"] if p["spectral_tilt"] is not None else 0.0)
    brightest = max(profiles, key=lambda p: p["spectral_tilt"] if p["spectral_tilt"] is not None else 0.0)
    return (
        "tonal spread detected — track {dark} is slightly darker than others, "
        "track {bright} is slightly brighter than others".format(
            dark=darkest["label"], bright=brightest["label"]
        )
    )


def _density_note(density_values: list[float], profiles: list[dict]) -> str:
    if len(density_values) < 2:
        return "density (crest factor) data not available for all tracks"
    spread = max(density_values) - min(density_values)
    if spread < 0.10:
        return "density is similar across tracks"
    densest = min(profiles, key=lambda p: p["crest_factor"] if p["crest_factor"] is not None else 1.0)
    sparsest = max(profiles, key=lambda p: p["crest_factor"] if p["crest_factor"] is not None else 0.0)
    return (
        "density imbalance detected — track {dense} is denser than others, "
        "track {sparse} is more open/sparse".format(
            dense=densest["label"], sparse=sparsest["label"]
        )
    )


def _identify_problem_track(
    profiles: list[dict],
    avg_db: float,
    avg_tilt: float | None,
    avg_lm: float,
) -> dict:
    """Score each track and return the most likely problem track."""
    scored: list[tuple[float, dict]] = []
    for p in profiles:
        score = 0.0
        reasons: list[str] = []

        # Low-mid congestion contribution
        lm_delta = p["low_mid_overlap"] - avg_lm
        if lm_delta > 0.1:
            score += lm_delta * 2.0
            reasons.append("low-mid dense ({})".format(_LOW_MID_HZ_LABEL))

        # Relative loudness
        if p["db"] is not None:
            db_delta = abs(p["db"] - avg_db)
            if db_delta > 1.5:
                score += db_delta * 0.5
                reasons.append("loudness outlier ({:+.1f} dB vs group average)".format(p["db"] - avg_db))

        # Tonal outlier
        if avg_tilt is not None and p["spectral_tilt"] is not None:
            tilt_delta = abs(p["spectral_tilt"] - avg_tilt)
            if tilt_delta > 0.2:
                score += tilt_delta
                tone_dir = "darker" if p["spectral_tilt"] < avg_tilt else "brighter"
                reasons.append("slightly {} than others".format(tone_dir))

        scored.append((score, p, reasons))

    if not scored:
        return {"name": None, "label": None, "reason": "insufficient data"}

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_p, top_reasons = scored[0]

    if top_score < 0.05:
        return {
            "name": top_p["name"],
            "label": top_p["label"],
            "reason": "no track stands out as a clear outlier — internal balance appears similar",
        }

    return {
        "name": top_p["name"],
        "label": top_p["label"],
        "score": round(top_score, 3),
        "reason": "; ".join(top_reasons) if top_reasons else "composite scoring",
    }


def _build_debug_corrections(
    profiles: list[dict],
    avg_db: float,
    avg_lm: float,
) -> list[dict]:
    """
    Build a ranked list of conservative corrective moves.
    Priorities: internal mix corrections before loudness matching.
    """
    corrections: list[dict] = []

    # Compute cross-track crest factor average from the profiles
    cf_values = [p["crest_factor"] for p in profiles if p["crest_factor"] is not None]
    avg_cf = sum(cf_values) / len(cf_values) if cf_values else None

    for p in profiles:
        is_processed = p["has_bus_processing"]
        move_size = _MOVE_PROCESSED if is_processed else _MOVE_UNPROCESSED

        reasons: list[str] = []
        priority = 0

        # Low-mid buildup
        if p["low_mid_overlap"] >= 0.7:
            reasons.append("low-mid dense ({})".format(_LOW_MID_HZ_LABEL))
            priority += 3

        # Masking + elevated level
        if p["db"] is not None and (p["db"] - avg_db) > 1.0 and p["low_mid_overlap"] >= 0.5:
            reasons.append("slightly louder than average with {} overlap".format(_LOW_MID_HZ_LABEL))
            priority += 2

        # Density imbalance (only when cross-track average is available)
        if p["crest_factor"] is not None and avg_cf is not None:
            if p["crest_factor"] < avg_cf - 0.15:
                reasons.append("denser than expected (low crest factor)")
                priority += 1

        if reasons:
            corrections.append({
                "label": p["label"],
                "track": p["name"],
                "reason": "; ".join(reasons),
                "band": _LOW_MID_HZ_LABEL if any("low-mid" in r for r in reasons) else None,
                "processing_state": (
                    "has bus/mastering-style processing ({})".format(", ".join(p["bus_proc_devices"]))
                    if is_processed else "no bus-style processing noted"
                ),
                "proposed_move": "{} fader".format(move_size),
                "expected_effect": (
                    "slightly less body congestion, more separation between layers"
                    if not is_processed
                    else "marginal improvement; processed tracks respond less predictably to raw fader moves"
                ),
                "confidence": "low" if is_processed else ("high" if priority >= 3 else "medium"),
                "priority": priority,
            })

    corrections.sort(key=lambda x: x["priority"], reverse=True)
    # Strip internal priority key from output
    for c in corrections:
        c.pop("priority", None)

    if not corrections:
        corrections.append({
            "label": None,
            "track": None,
            "reason": "no significant internal balance issues detected",
            "proposed_move": "none — re-listen and verify",
            "expected_effect": "n/a",
            "confidence": "n/a",
        })

    return corrections


# ===========================================================================
# ── WORKFLOW 2 : FINAL REVIEW MODE ──────────────────────────────────────────
# ===========================================================================

def final_review_mode(
    tracks: list[dict],
    track_names: list[str] | None = None,
    anchor_index: int | None = None,
    sequence: list[int] | None = None,
) -> dict:
    """
    Workflow 2 — Final Review Mode: album cohesion + sequencing.

    Evaluates full project cohesion and suggests track ordering after mixes
    are already stable.  Supports any number of tracks (N ≥ 2).

    Parameters
    ----------
    tracks : list[dict]
        N ≥ 2 track dicts (same format as for debug_mix_compare).
        Extended keys used when present:
          - ``lufs``          : float  (integrated LUFS)
          - ``lufs_variance`` : float  (short-term loudness variance proxy)
          - ``bpm``           : float  (tempo)
          - ``spectral_tilt`` : float  (brightness proxy)
          - ``low_mid_ratio`` : float  (200–600 Hz energy ratio 0–1)
          - ``crest_factor``  : float  (density proxy 0–1)
          - ``stereo_width``  : float  (0–1)
    track_names : list[str] | None
        Optional display names (overrides ``name`` key in each track dict).
    anchor_index : int | None
        0-based index within ``tracks`` to use as the anchor/reference.
        If None, the project median profile is used.
    sequence : list[int] | None
        Optional current sequence (0-based indices into ``tracks``).
        If provided, this is shown alongside the suggested order.

    Returns
    -------
    dict with keys:
        ``mode``                  – always "final_review"
        ``track_count``           – N
        ``project_summary``       – center/median profile
        ``per_track_metrics``     – relative metrics per track
        ``cohesion_issues``       – ranked list of flagged mismatches
        ``suggested_track_order`` – ordered list of track names
        ``transition_notes``      – explanation per adjacent pair
        ``recommendation_notes``  – philosophy summary
    """
    if not isinstance(tracks, list) or len(tracks) < 2:
        return {
            "mode": "final_review",
            "status": "error",
            "error": (
                "Final Review Mode requires at least 2 tracks; "
                "{got} provided.".format(got=len(tracks) if isinstance(tracks, list) else 0)
            ),
        }

    n = len(tracks)

    # ── 1. Build profiles for every track ────────────────────────────
    profiles: list[dict] = []
    for i, t in enumerate(tracks):
        name = (track_names[i] if track_names and i < len(track_names) else None) or t.get("name", "Track {}".format(i + 1))
        mixer = t.get("mixer_device") or {}
        volume_linear = mixer.get("volume")
        devices = t.get("devices") or []
        db = _db_from_linear(volume_linear) if volume_linear is not None else None
        has_bus_proc, bus_proc_devs = _detect_bus_processing(devices)

        profiles.append({
            "index": i,
            "name": name,
            "db": round(db, 1) if db is not None else None,
            "lufs": t.get("lufs"),
            "lufs_variance": t.get("lufs_variance"),
            "bpm": t.get("bpm"),
            "spectral_tilt": t.get("spectral_tilt"),
            "low_mid_ratio": t.get("low_mid_ratio") or _classify_low_mid_overlap(name),
            "crest_factor": t.get("crest_factor"),
            "stereo_width": t.get("stereo_width"),
            "has_bus_processing": has_bus_proc,
            "bus_proc_devices": bus_proc_devs,
        })

    # ── 2. Compute project center / median ────────────────────────────
    project_center = _compute_project_center(profiles)

    # ── 3. Determine reference profile ───────────────────────────────
    if anchor_index is not None and 0 <= anchor_index < n:
        reference = profiles[anchor_index]
        reference_label = "anchor ({})".format(reference["name"])
    else:
        reference = project_center
        reference_label = "project median"

    # ── 4. Per-track relative metrics and outlier detection ──────────
    per_track_metrics: list[dict] = []
    cohesion_issues: list[dict] = []

    for p in profiles:
        relative, flags = _compare_to_reference(p, reference)
        cohesion_status = _cohesion_status(flags)

        per_track_metrics.append({
            "name": p["name"],
            "index": p["index"],
            "relative_metrics": relative,
            "reference_used": reference_label,
            "cohesion_status": cohesion_status,
        })

        for flag in flags:
            cohesion_issues.append({
                "track": p["name"],
                "issue": flag["type"],
                "detail": flag["detail"],
                "severity": flag["severity"],
            })

    # Sort cohesion issues: fix tone/density before loudness
    _ISSUE_PRIORITY = {"tonal_outlier": 0, "density_outlier": 1, "width_outlier": 2, "loudness_outlier": 3}
    cohesion_issues.sort(key=lambda x: _ISSUE_PRIORITY.get(x["issue"], 9))

    # ── 5. Sequencing engine ──────────────────────────────────────────
    suggested_order, transition_notes = _suggest_order(profiles)

    return {
        "mode": "final_review",
        "track_count": n,
        "reference_used": reference_label,
        "project_summary": project_center,
        "per_track_metrics": per_track_metrics,
        "cohesion_issues": cohesion_issues,
        "suggested_track_order": [profiles[i]["name"] for i in suggested_order],
        "suggested_order_indices": suggested_order,
        "transition_notes": transition_notes,
        "current_sequence": (
            [profiles[i]["name"] for i in sequence if 0 <= i < n]
            if sequence else None
        ),
        "recommendation_notes": {
            "philosophy": "Fix tone and density before addressing loudness.",
            "loudness": "Do NOT force identical loudness. Intentional variation is acceptable.",
            "sequencing": "Sequencing guidance is suggestive, not strict.",
            "priority_order": ["tonal consistency", "density consistency", "loudness alignment"],
        },
    }


def _compute_project_center(profiles: list[dict]) -> dict:
    """Compute the median/average profile across all tracks."""

    def _median(values: list[float]) -> float | None:
        v = [x for x in values if x is not None]
        if not v:
            return None
        v.sort()
        mid = len(v) // 2
        return v[mid] if len(v) % 2 == 1 else (v[mid - 1] + v[mid]) / 2.0

    def _avg(values: list[float]) -> float | None:
        v = [x for x in values if x is not None]
        return sum(v) / len(v) if v else None

    return {
        "median_db": _median([p["db"] for p in profiles]),
        "median_lufs": _median([p["lufs"] for p in profiles]),
        "median_spectral_tilt": _median([p["spectral_tilt"] for p in profiles]),
        "median_low_mid_ratio": _median([p["low_mid_ratio"] for p in profiles]),
        "median_crest_factor": _median([p["crest_factor"] for p in profiles]),
        "median_stereo_width": _median([p["stereo_width"] for p in profiles]),
        "median_bpm": _median([p["bpm"] for p in profiles]),
        "track_count": len(profiles),
    }


def _compare_to_reference(track: dict, reference: dict) -> tuple[dict, list[dict]]:
    """Compare a track to the reference (anchor or project center)."""
    relative: dict = {}
    flags: list[dict] = []

    # Loudness comparison
    ref_db = reference.get("db") or reference.get("median_db")
    if track["db"] is not None and ref_db is not None:
        db_delta = track["db"] - ref_db
        relative["db_delta"] = round(db_delta, 1)
        if abs(db_delta) >= _LUFS_OUTLIER_DELTA:
            flags.append({
                "type": "loudness_outlier",
                "detail": "{:+.1f} dB vs reference".format(db_delta),
                "severity": "clear_outlier" if abs(db_delta) > 5.0 else "slight_outlier",
            })

    # Tonal comparison
    ref_tilt = reference.get("spectral_tilt") or reference.get("median_spectral_tilt")
    if track["spectral_tilt"] is not None and ref_tilt is not None:
        tilt_delta = track["spectral_tilt"] - ref_tilt
        relative["tonal_delta"] = round(tilt_delta, 3)
        if abs(tilt_delta) >= _TONAL_OUTLIER_DELTA:
            direction = "darker" if tilt_delta < 0 else "brighter"
            flags.append({
                "type": "tonal_outlier",
                "detail": "slightly {} than reference (tilt delta: {:.3f})".format(direction, tilt_delta),
                "severity": "clear_outlier" if abs(tilt_delta) > 0.4 else "slight_outlier",
            })

    # Density comparison
    ref_cf = reference.get("crest_factor") or reference.get("median_crest_factor")
    if track["crest_factor"] is not None and ref_cf is not None:
        cf_delta = track["crest_factor"] - ref_cf
        relative["density_delta"] = round(cf_delta, 3)
        if abs(cf_delta) >= _DENSITY_OUTLIER_DELTA:
            direction = "denser" if cf_delta < 0 else "more open/sparse"
            flags.append({
                "type": "density_outlier",
                "detail": "{} than reference (crest delta: {:.3f})".format(direction, cf_delta),
                "severity": "clear_outlier" if abs(cf_delta) > 0.35 else "slight_outlier",
            })

    # Width comparison
    ref_w = reference.get("stereo_width") or reference.get("median_stereo_width")
    if track["stereo_width"] is not None and ref_w is not None:
        w_delta = track["stereo_width"] - ref_w
        relative["width_delta"] = round(w_delta, 3)
        if abs(w_delta) >= _WIDTH_OUTLIER_DELTA:
            direction = "narrower" if w_delta < 0 else "wider"
            flags.append({
                "type": "width_outlier",
                "detail": "{} than reference (width delta: {:.3f})".format(direction, w_delta),
                "severity": "slight_outlier",
            })

    return relative, flags


def _cohesion_status(flags: list[dict]) -> str:
    if not flags:
        return "fits"
    if any(f["severity"] == "clear_outlier" for f in flags):
        return "clear outlier"
    return "slight outlier"


def _track_distance(a: dict, b: dict) -> float:
    """
    Compute a distance score between two tracks for sequencing.
    Lower = smoother transition; higher = more contrast.
    """
    score = 0.0
    weights = {"db": 0.25, "spectral_tilt": 0.35, "crest_factor": 0.25, "bpm": 0.15}

    # dB difference
    if a["db"] is not None and b["db"] is not None:
        score += weights["db"] * min(abs(a["db"] - b["db"]) / 6.0, 1.0)

    # Tonal difference
    if a["spectral_tilt"] is not None and b["spectral_tilt"] is not None:
        score += weights["spectral_tilt"] * min(abs(a["spectral_tilt"] - b["spectral_tilt"]) / 0.5, 1.0)

    # Density difference
    if a["crest_factor"] is not None and b["crest_factor"] is not None:
        score += weights["crest_factor"] * min(abs(a["crest_factor"] - b["crest_factor"]) / 0.5, 1.0)

    # BPM difference
    if a["bpm"] is not None and b["bpm"] is not None:
        score += weights["bpm"] * min(abs(a["bpm"] - b["bpm"]) / 40.0, 1.0)

    return score


def _describe_transition(a: dict, b: dict, distance: float) -> str:
    """Return a human-readable transition description."""
    if distance < 0.15:
        quality = "smooth"
    elif distance < 0.30:
        quality = "moderate transition"
    else:
        quality = "contrast"

    details: list[str] = []

    if a["spectral_tilt"] is not None and b["spectral_tilt"] is not None:
        tilt_d = b["spectral_tilt"] - a["spectral_tilt"]
        if abs(tilt_d) > 0.1:
            details.append("slight brightness {}".format("increase" if tilt_d > 0 else "decrease"))

    if a["crest_factor"] is not None and b["crest_factor"] is not None:
        cf_d = b["crest_factor"] - a["crest_factor"]
        if abs(cf_d) > 0.1:
            details.append("density {}".format("drop" if cf_d > 0 else "increase"))

    if a["db"] is not None and b["db"] is not None:
        db_d = b["db"] - a["db"]
        if abs(db_d) > 1.5:
            details.append("{:+.1f} dB level change".format(db_d))

    detail_str = " ({})".format(", ".join(details)) if details else ""
    return "{quality}{detail}".format(quality=quality, detail=detail_str)


def _suggest_order(profiles: list[dict]) -> tuple[list[int], list[dict]]:
    """
    Greedy nearest-neighbour sequencing: start with the track that has the
    highest density (most energetic opening), then always add the closest
    remaining track.

    Returns (ordered_indices, transition_notes).
    """
    n = len(profiles)
    if n == 1:
        return [0], []

    # Pick starting track: densest (lowest crest_factor) or first track
    cf_values = [(i, p["crest_factor"]) for i, p in enumerate(profiles) if p["crest_factor"] is not None]
    if cf_values:
        start = min(cf_values, key=lambda x: x[1])[0]
    else:
        start = 0

    ordered: list[int] = [start]
    remaining: set[int] = set(range(n)) - {start}

    while remaining:
        last = ordered[-1]
        nearest = min(remaining, key=lambda j: _track_distance(profiles[last], profiles[j]))
        ordered.append(nearest)
        remaining.remove(nearest)

    # Build transition notes
    notes: list[dict] = []
    for idx in range(len(ordered) - 1):
        a = profiles[ordered[idx]]
        b = profiles[ordered[idx + 1]]
        dist = _track_distance(a, b)
        notes.append({
            "from": a["name"],
            "to": b["name"],
            "description": "{} → {}: {}".format(a["name"], b["name"], _describe_transition(a, b, dist)),
            "distance_score": round(dist, 3),
        })

    return ordered, notes
