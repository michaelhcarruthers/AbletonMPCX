"""Humanization tools — MIDI feel analysis and humanization workflows."""
from __future__ import annotations

import math

from helpers import (
    _send,
    _reference_profiles,
    _reference_profiles_lock,
    _load_reference_profiles_from_project,
)


def _std_dev(values: list) -> float:
    """Return population standard deviation of a list of numbers. Returns 0.0 for empty or single-element lists."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def humanize_notes(
    track_index: int,
    slot_index: int,
    timing_amount: float = 0.02,
    velocity_amount: float = 10.0,
    seed: int | None = None,
) -> dict:
    """Apply subtle human-feel randomisation to all notes in a MIDI clip."""
    import random

    rng = random.Random(seed)
    seed_used = seed if seed is not None else rng.randint(0, 2**31)
    rng = random.Random(seed_used)

    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    modified = []
    for note in notes:
        t_shift = rng.uniform(-timing_amount, timing_amount)
        v_shift = rng.uniform(-velocity_amount, velocity_amount)
        new_start = max(0.0, note["start_time"] + t_shift)
        new_velocity = int(max(1, min(127, note["velocity"] + v_shift)))
        modified.append({
            "pitch": note["pitch"],
            "start_time": new_start,
            "duration": note["duration"],
            "velocity": new_velocity,
            "mute": note["mute"],
        })

    # Replace all notes atomically
    _send("replace_all_notes", {
        "track_index": track_index,
        "slot_index": slot_index,
        "notes": modified,
    })

    return {
        "note_count": len(modified),
        "timing_amount": timing_amount,
        "velocity_amount": velocity_amount,
        "seed_used": seed_used,
    }


def humanize_dilla(
    track_index: int,
    slot_index: int,
    late_bias: float = 0.018,
    max_early: float = 0.005,
    max_late: float = 0.032,
    velocity_amount: float = 8.0,
    loose_subdivisions: bool = True,
    seed: int | None = None,
) -> dict:
    """Apply a J Dilla-inspired humanization to a MIDI clip."""
    import random

    rng = random.Random(seed)
    seed_used = seed if seed is not None else rng.randint(0, 2**31)
    rng = random.Random(seed_used)

    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    def is_weak_subdivision(start_time: float, grid: float = 0.25) -> bool:
        """True if the note falls on an offbeat 16th (not on a quarter or 8th)."""
        pos_in_beat = (start_time % 1.0)
        QUARTER_THRESHOLD = 0.05
        EIGHTH_THRESHOLD = 0.05
        if pos_in_beat < QUARTER_THRESHOLD or abs(pos_in_beat - 1.0) < QUARTER_THRESHOLD:
            return False  # on the quarter
        if abs(pos_in_beat - 0.5) < EIGHTH_THRESHOLD:
            return False  # on the 8th
        return True  # offbeat 16th or smaller

    modified = []
    for note in notes:
        # Timing: triangular distribution biased late
        if loose_subdivisions and is_weak_subdivision(note["start_time"]):
            actual_max_late = max_late * 1.5
            actual_late_bias = late_bias * 1.4
        else:
            actual_max_late = max_late
            actual_late_bias = late_bias

        t_shift = rng.triangular(-max_early, actual_max_late, actual_late_bias)
        new_start = max(0.0, note["start_time"] + t_shift)

        # Velocity: symmetric small nudge
        v_shift = rng.uniform(-velocity_amount, velocity_amount)
        new_velocity = int(max(1, min(127, note["velocity"] + v_shift)))

        modified.append({
            "pitch": note["pitch"],
            "start_time": new_start,
            "duration": note["duration"],
            "velocity": new_velocity,
            "mute": note["mute"],
        })

    _send("replace_all_notes", {
        "track_index": track_index,
        "slot_index": slot_index,
        "notes": modified,
    })

    return {
        "note_count": len(modified),
        "late_bias": late_bias,
        "max_early": max_early,
        "max_late": max_late,
        "velocity_amount": velocity_amount,
        "seed_used": seed_used,
    }


def analyze_clip_feel(track_index: int, slot_index: int, grid: float = 0.25) -> dict:
    """Analyse the timing and velocity feel of a MIDI clip."""
    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    if not notes:
        return {
            "note_count": 0,
            "perfectly_quantized": False,
            "timing_variance": 0.0,
            "velocity_std_dev": 0.0,
            "low_velocity_variance": False,
            "per_pitch_analysis": [],
            "robotic_flags": ["clip is empty"],
            "feel_score": 0,
        }

    # --- Timing analysis ---
    def dist_to_grid(t, g):
        return abs(t - round(t / g) * g)

    grid_distances = [dist_to_grid(n["start_time"], grid) for n in notes]
    SNAP_THRESHOLD = 0.001  # beats — within 1ms at 120bpm
    perfectly_quantized = all(d < SNAP_THRESHOLD for d in grid_distances)
    timing_variance = _std_dev(grid_distances)

    # --- Velocity analysis ---
    velocities = [n["velocity"] for n in notes]
    velocity_std_dev = _std_dev(velocities)
    low_velocity_variance = velocity_std_dev < 5.0

    # --- Per-pitch analysis ---
    from collections import defaultdict
    pitch_groups: dict = defaultdict(list)
    for n in notes:
        pitch_groups[n["pitch"]].append(n)

    per_pitch = []
    for pitch, pitch_notes in sorted(pitch_groups.items()):
        pvels = [n["velocity"] for n in pitch_notes]
        pdurs = [n["duration"] for n in pitch_notes]
        pvel_std = _std_dev(pvels)
        pdur_std = _std_dev(pdurs)
        per_pitch.append({
            "pitch": pitch,
            "note_count": len(pitch_notes),
            "velocity_std_dev": round(pvel_std, 3),
            "duration_std_dev": round(pdur_std, 4),
            "uniform_velocity": pvel_std < 3.0 and len(pitch_notes) > 1,
            "uniform_duration": pdur_std < 0.01 and len(pitch_notes) > 1,
        })

    # --- Build flags ---
    robotic_flags = []
    if perfectly_quantized:
        robotic_flags.append("all note start times are exactly on the {}-beat grid".format(grid))
    if low_velocity_variance:
        robotic_flags.append("overall velocity std dev is {:.1f} — near-uniform".format(velocity_std_dev))
    uniform_vel_pitches = [p for p in per_pitch if p["uniform_velocity"]]
    if uniform_vel_pitches:
        robotic_flags.append("pitches with identical velocities: {}".format([p["pitch"] for p in uniform_vel_pitches]))
    uniform_dur_pitches = [p for p in per_pitch if p["uniform_duration"]]
    if uniform_dur_pitches:
        robotic_flags.append("pitches with uniform note lengths: {}".format([p["pitch"] for p in uniform_dur_pitches]))

    # --- Feel score (0=human, 100=robotic) ---
    score = 0
    if perfectly_quantized:
        score += 40
    if low_velocity_variance:
        score += 30
    uniform_vel_ratio = len(uniform_vel_pitches) / max(len(per_pitch), 1)
    score += int(uniform_vel_ratio * 20)
    uniform_dur_ratio = len(uniform_dur_pitches) / max(len(per_pitch), 1)
    score += int(uniform_dur_ratio * 10)
    score = min(100, score)

    return {
        "note_count": len(notes),
        "perfectly_quantized": perfectly_quantized,
        "timing_variance": round(timing_variance, 5),
        "velocity_std_dev": round(velocity_std_dev, 3),
        "low_velocity_variance": low_velocity_variance,
        "per_pitch_analysis": per_pitch,
        "robotic_flags": robotic_flags,
        "feel_score": score,
    }


def auto_humanize_if_robotic(
    track_index: int,
    slot_index: int,
    feel_score_threshold: int = 60,
    style: str = "dilla",
    late_bias: float = 0.018,
    max_early: float = 0.005,
    max_late: float = 0.032,
    velocity_amount: float = 8.0,
    seed: int | None = None,
) -> dict:
    """Check a clip's feel score and apply humanization automatically if it is too robotic."""
    feel = analyze_clip_feel(track_index, slot_index)
    score_before = feel.get("feel_score", 0)
    flags_before = feel.get("robotic_flags", [])
    note_count = feel.get("note_count", 0)

    if score_before < feel_score_threshold:
        return {
            "applied": False,
            "feel_score_before": score_before,
            "feel_score_after": score_before,
            "robotic_flags_before": flags_before,
            "humanization_style": "none",
            "note_count": note_count,
            "reason": "feel_score {} is below threshold {}".format(score_before, feel_score_threshold),
        }

    if style == "dilla":
        humanize_dilla(
            track_index=track_index,
            slot_index=slot_index,
            late_bias=late_bias,
            max_early=max_early,
            max_late=max_late,
            velocity_amount=velocity_amount,
            seed=seed,
        )
    else:
        humanize_notes(
            track_index=track_index,
            slot_index=slot_index,
            timing_amount=max_late,
            velocity_amount=velocity_amount,
            seed=seed,
        )

    feel_after = analyze_clip_feel(track_index, slot_index)
    score_after = feel_after.get("feel_score", 0)

    return {
        "applied": True,
        "feel_score_before": score_before,
        "feel_score_after": score_after,
        "robotic_flags_before": flags_before,
        "humanization_style": style,
        "note_count": note_count,
        "reason": "feel_score {} >= threshold {}".format(score_before, feel_score_threshold),
    }


def fix_groove_from_reference(
    track_index: int,
    slot_index: int,
    reference_label: str = "default",
    timing_blend: float = 0.5,
    velocity_blend: float = 0.3,
    seed: int | None = None,
) -> dict:
    """Compare a clip's feel against a stored reference and apply corrections to close the gap."""
    from tools.reference_profiles import compare_clip_feel
    with _reference_profiles_lock:
        has_label = reference_label in _reference_profiles
    if not has_label:
        _load_reference_profiles_from_project()
    with _reference_profiles_lock:
        if reference_label not in _reference_profiles:
            raise ValueError(
                "No reference feel profile '{}'. Call designate_reference_clip() first.".format(reference_label)
            )
        ref = _reference_profiles[reference_label]
    if ref.get("type") != "clip_feel":
        raise ValueError(
            "Reference '{}' is not a feel profile (type={}). "
            "Use designate_reference_clip() to create one.".format(reference_label, ref.get("type"))
        )

    comparison = compare_clip_feel(track_index, slot_index, reference_label=reference_label)
    flags = comparison.get("flags", [])
    timing_var_before = comparison.get("timing_variance", 0.0)
    vel_std_before = comparison.get("velocity_std_dev", 0.0)

    ref_timing_variance = ref.get("timing_variance", 0.0)
    ref_velocity_std = ref.get("velocity_std_dev", 0.0)

    corrections = []
    # 70% threshold: only apply timing correction when clip is significantly tighter than reference
    apply_timing = timing_var_before < ref_timing_variance * 0.7
    # 60% threshold: only apply velocity correction when clip has meaningfully less variation
    apply_velocity = vel_std_before < ref_velocity_std * 0.6

    if apply_timing:
        corrections.append("timing: clip is tighter than reference — applying late-biased loosening")
    if apply_velocity:
        corrections.append("velocity: clip has less variation than reference — widening spread")

    if not apply_timing and not apply_velocity:
        return {
            "applied": False,
            "flags_before": flags,
            "corrections_applied": [],
            "timing_variance_before": timing_var_before,
            "timing_variance_after": timing_var_before,
            "velocity_std_before": vel_std_before,
            "velocity_std_after": vel_std_before,
            "reference_label": reference_label,
            "reason": "clip feel is already within acceptable range of reference",
        }

    timing_gap = max(0.0, ref_timing_variance - timing_var_before)
    timing_amount = max(0.001, timing_gap * timing_blend)

    velocity_gap = max(0.0, ref_velocity_std - vel_std_before)
    # Scale by 10 to convert from timing standard-deviation units to MIDI velocity range (0-127)
    velocity_amount_computed = max(1.0, velocity_gap * velocity_blend * 10)

    humanize_dilla(
        track_index=track_index,
        slot_index=slot_index,
        late_bias=timing_amount * 0.6,
        max_early=timing_amount * 0.2,
        max_late=timing_amount * 1.2,
        velocity_amount=velocity_amount_computed if apply_velocity else 0.0,
        loose_subdivisions=True,
        seed=seed,
    )

    feel_after = analyze_clip_feel(track_index, slot_index)
    timing_var_after = feel_after.get("timing_variance", 0.0)
    vel_std_after = feel_after.get("velocity_std_dev", 0.0)

    return {
        "applied": True,
        "flags_before": flags,
        "corrections_applied": corrections,
        "timing_variance_before": timing_var_before,
        "timing_variance_after": timing_var_after,
        "velocity_std_before": vel_std_before,
        "velocity_std_after": vel_std_after,
        "reference_label": reference_label,
    }


def batch_auto_humanize(
    track_indices: list,
    slot_index: int,
    feel_score_threshold: int = 60,
    style: str = "dilla",
    seed: int | None = None,
) -> dict:
    """Run auto_humanize_if_robotic() across multiple tracks at the same slot index."""
    results = []
    applied_count = 0
    skipped_count = 0

    for ti in track_indices:
        try:
            result = auto_humanize_if_robotic(
                track_index=ti,
                slot_index=slot_index,
                feel_score_threshold=feel_score_threshold,
                style=style,
                seed=seed,
            )
            results.append({
                "track_index": ti,
                "applied": result["applied"],
                "feel_score_before": result["feel_score_before"],
                "feel_score_after": result["feel_score_after"],
                "note_count": result["note_count"],
                "reason": result.get("reason", ""),
            })
            if result["applied"]:
                applied_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            results.append({
                "track_index": ti,
                "applied": False,
                "error": str(e),
            })
            skipped_count += 1

    return {
        "results": results,
        "applied_count": applied_count,
        "skipped_count": skipped_count,
        "total_checked": len(track_indices),
    }
