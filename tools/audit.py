"""Audit tools — workflow primitives, project health, missing plugins and media, reference profiles, audio analysis, and the detect-correct workflow loop."""
from __future__ import annotations

import collections
import datetime
import json
import math
import os
import pathlib
import re
import threading
import time
from typing import Any

import helpers
from helpers import (
    mcp,
    _send,
    _append_operation,
    _operation_log,
    _MAX_LOG_ENTRIES,
    _snapshots,
    _reference_profiles,
    _audio_analysis_cache,
    _get_memory,
    _save_memory,
    _load_memory,
    _memory_path,
    _save_reference_profile,
    _load_reference_profiles_from_project,
)
from helpers.summarizer import summarize_health_report

# Number of distinct issue categories checked by project_health_report().
# Used as a fixed denominator for the health score so that results are
# comparable across projects of different sizes.
_MAX_ISSUE_CATEGORIES = 5

# ---------------------------------------------------------------------------
# Observer thread (background session watcher)
# ---------------------------------------------------------------------------

_suggestion_queue: collections.deque = collections.deque(maxlen=50)
_observer_thread: threading.Thread | None = None
_observer_running: bool = False
_observer_last_snapshot: dict | None = None
_observer_lock: threading.Lock = threading.Lock()
_OBSERVER_POLL_INTERVAL: float = 8.0  # seconds between polls
_observer_last_checkpoint_log_len: int = 0  # tracks Rule 5 threshold crossings
_observer_poll_count: int = 0
_observer_clip_cursor: int = 0
_observer_flagged_clips: set = set()
_OBSERVER_FEEL_EVERY_N_POLLS: int = 3
_OBSERVER_FEEL_MAX_CLIPS_PER_POLL: int = 4

# ---------------------------------------------------------------------------
# Workflow primitives (Phase 4)
# Deterministic, composable operations built on existing primitives.
# Each compiles down to explicit _send() calls — no fuzzy behaviour.
# ---------------------------------------------------------------------------


def _std_dev(values: list) -> float:
    """Return population standard deviation of a list of numbers. Returns 0.0 for empty or single-element lists."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


@mcp.tool()
def humanize_notes(
    track_index: int,
    slot_index: int,
    timing_amount: float = 0.02,
    velocity_amount: float = 10.0,
    seed: int | None = None,
) -> dict:
    """
    Apply subtle human-feel randomisation to all notes in a MIDI clip.

    Randomly offsets note start times and velocities within the given ranges.
    All changes are deterministic if a seed is provided.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        timing_amount: Max timing shift in beats (default 0.02 = ~5ms at 120bpm).
        velocity_amount: Max velocity shift in either direction (default 10).
        seed: Optional random seed for reproducibility.

    Returns:
        note_count, timing_amount, velocity_amount, seed_used
    """
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


@mcp.tool()
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
    """
    Apply a J Dilla-inspired humanization to a MIDI clip.

    Key characteristics vs generic humanize_notes:
    - Timing is biased LATE, not symmetrically randomised.
      Distribution is triangular(max_early, max_late, late_bias).
    - Weaker subdivisions (16th-note offbeats) get more timing looseness.
    - Velocities are nudged randomly but with less extreme spread than timing.

    All changes are deterministic if a seed is provided.
    Uses replace_all_notes for atomic write.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        late_bias: Mode of the triangular timing distribution in beats (default 0.018 ≈ +4ms at 120bpm).
        max_early: Maximum early shift in beats (default 0.005 ≈ 1ms).
        max_late: Maximum late shift in beats (default 0.032 ≈ 8ms).
        velocity_amount: Max velocity shift in either direction (default 8).
        loose_subdivisions: If True, 16th-note offbeats get 1.5× the timing range.
        seed: Optional random seed for reproducibility.

    Returns:
        note_count, late_bias, max_early, max_late, velocity_amount, seed_used
    """
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


@mcp.tool()
def analyze_clip_feel(track_index: int, slot_index: int, grid: float = 0.25) -> dict:
    """
    Analyse the timing and velocity feel of a MIDI clip.

    Checks for signs of robotic, over-quantized feel:
    - All note start times fall exactly on a rhythmic grid
    - Near-uniform velocities across all notes
    - Per-pitch velocity variance (e.g. every hi-hat hit the same velocity)
    - Uniform note durations per pitch

    Nothing is modified. Returns observations and a summary flag.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        grid: Grid resolution in beats to check snapping against (default 0.25 = 16th note).

    Returns:
        note_count,
        perfectly_quantized (bool): all start times are exact grid multiples,
        timing_variance (float): std dev of distance-to-nearest-grid in beats,
        velocity_std_dev (float): overall velocity standard deviation,
        low_velocity_variance (bool): velocity std dev < 5 (flag),
        per_pitch_analysis: list of {pitch, note_count, velocity_std_dev, duration_std_dev, uniform_velocity, uniform_duration},
        robotic_flags: list of human-readable flag strings,
        feel_score: int 0-100 (100 = fully robotic, 0 = very human)
    """
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


@mcp.tool()
def duplicate_clip_to_new_scene(track_index: int, slot_index: int) -> dict:
    """
    Duplicate the clip at (track_index, slot_index) into a new scene.

    Creates a new scene at the end, then recreates the clip (notes, name,
    color, length) in the corresponding slot of the new scene.

    Args:
        track_index: Track containing the source clip.
        slot_index: Source clip slot index.

    Returns:
        new_scene_index, new_slot_index
    """
    # Get current scene count to know the index of the new scene
    scenes = _send("get_scenes")
    new_scene_index = len(scenes)

    # Create new scene at end
    _send("create_scene", {"index": -1})

    # Read source clip properties
    clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
    length = clip_info.get("length", 4.0)
    clip_name = clip_info.get("name", "")
    clip_color = clip_info.get("color")

    notes_result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = notes_result.get("notes", []) if isinstance(notes_result, dict) else notes_result

    # Create a new clip in the correct slot of the new scene
    _send("create_clip", {"track_index": track_index, "slot_index": new_scene_index, "length": length})

    # Copy name, color, and notes
    if clip_name:
        _send("set_clip_name", {"track_index": track_index, "slot_index": new_scene_index, "name": clip_name})
    if clip_color is not None:
        _send("set_clip_color", {"track_index": track_index, "slot_index": new_scene_index, "color": clip_color})
    if notes:
        _send("replace_all_notes", {"track_index": track_index, "slot_index": new_scene_index, "notes": notes})

    return {
        "source_track_index": track_index,
        "source_slot_index": slot_index,
        "new_scene_index": new_scene_index,
        "new_slot_index": new_scene_index,
    }


@mcp.tool()
def create_midi_track_with_drum_rack(index: int = -1, track_name: str | None = None) -> dict:
    """
    Create a new MIDI track and immediately load a Drum Rack onto it.

    Args:
        index: Position to insert the track (-1 = end).
        track_name: Optional name to give the new track.

    Returns:
        track_index, track_name
    """
    # Create the MIDI track
    _send("create_midi_track", {"index": index})

    # Get updated track list to find the new track index
    tracks = _send("get_tracks")
    new_track_index = index if index >= 0 else len(tracks) - 1

    # Optionally rename
    if track_name:
        _send("set_track_name", {"track_index": new_track_index, "name": track_name})
    else:
        track_name = tracks[new_track_index]["name"] if new_track_index < len(tracks) else "MIDI"

    # Load Drum Rack
    _send("add_native_device", {"track_index": new_track_index, "device_name": "Drum Rack", "is_return_track": False})

    return {
        "track_index": new_track_index,
        "track_name": track_name,
    }


@mcp.tool()
def capture_device_macro_snapshot(track_index: int, device_index: int, label: str | None = None) -> dict:
    """
    Capture the current parameter values of a device as a named snapshot.

    Stores all parameter values under a label so they can be restored later
    with apply_device_macro_snapshot().

    Args:
        track_index: Track containing the device (-1 for master).
        device_index: Device index on the track.
        label: Optional label. Defaults to '{track_index}_{device_index}'.

    Returns:
        label, device_name, parameter_count
    """
    result = _send("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
        "is_return_track": False,
    })
    device_name = result.get("name", "unknown")
    parameters = result.get("parameters", [])

    snap_label = label or "device_{}_{}".format(track_index, device_index)

    # Store in the same _snapshots store under a prefixed key
    _snapshots["__device__{}".format(snap_label)] = {
        "track_index": track_index,
        "device_index": device_index,
        "device_name": device_name,
        "parameters": parameters,
        "_timestamp_ms": int(time.time() * 1000),
    }

    return {
        "label": snap_label,
        "device_name": device_name,
        "parameter_count": len(parameters),
    }


@mcp.tool()
def apply_device_macro_snapshot(label: str, track_index: int | None = None, device_index: int | None = None) -> dict:
    """
    Restore device parameter values from a previously captured snapshot.

    Args:
        label: Label used when calling capture_device_macro_snapshot().
        track_index: Override track index (uses snapshot's original if omitted).
        device_index: Override device index (uses snapshot's original if omitted).

    Returns:
        label, device_name, parameters_set, skipped
    """
    key = "__device__{}".format(label)
    if key not in _snapshots:
        raise ValueError("No device snapshot with label '{}'. Use capture_device_macro_snapshot() first.".format(label))

    snap = _snapshots[key]
    ti = track_index if track_index is not None else snap["track_index"]
    di = device_index if device_index is not None else snap["device_index"]
    parameters = snap.get("parameters", [])

    set_count = 0
    skipped = 0
    for param in parameters:
        try:
            _send("set_device_parameter", {
                "track_index": ti,
                "device_index": di,
                "parameter_index": param["index"],
                "value": param["value"],
                "is_return_track": False,
            })
            set_count += 1
        except Exception:
            skipped += 1

    return {
        "label": label,
        "device_name": snap.get("device_name", "unknown"),
        "parameters_set": set_count,
        "skipped": skipped,
    }


@mcp.tool()
def prep_track_for_resampling(track_index: int, resample_track_name: str = "Resample") -> dict:
    """
    Prepare a track for resampling by creating a new audio track routed to record it.

    Steps:
    1. Creates a new audio track named resample_track_name.
    2. Arms the new track for recording.
    3. Returns both track indices so the caller can set up routing manually if needed.

    Args:
        track_index: The source track to resample from.
        resample_track_name: Name for the new recording track.

    Returns:
        source_track_index, resample_track_index, resample_track_name
    """
    # Create the audio track
    _send("create_audio_track", {"index": -1})
    tracks = _send("get_tracks")
    resample_track_index = len(tracks) - 1

    # Name it
    _send("set_track_name", {"track_index": resample_track_index, "name": resample_track_name})

    # Arm it
    arm_succeeded = True
    try:
        _send("set_track_arm", {"track_index": resample_track_index, "arm": True})
    except Exception:
        arm_succeeded = False  # Some track types may not support arming

    return {
        "source_track_index": track_index,
        "resample_track_index": resample_track_index,
        "resample_track_name": resample_track_name,
        "arm_succeeded": arm_succeeded,
    }


@mcp.tool()
def create_arrangement_scaffold(
    sections: list[dict],
) -> dict:
    """
    Create a basic arrangement scaffold by adding named scenes for each section.

    Each section dict requires a 'name' key and optionally 'tempo' and 'color'.

    Args:
        sections: List of section dicts, e.g.:
            [
                {"name": "Intro", "tempo": 120.0, "color": 0x00FF6600},
                {"name": "Verse", "tempo": 120.0},
                {"name": "Chorus", "color": 0x00FF0000},
                {"name": "Bridge"},
                {"name": "Outro"},
            ]

    Returns:
        scenes_created: list of {name, scene_index}
    """
    existing_scenes = _send("get_scenes")
    start_index = len(existing_scenes)

    created = []
    tempo_failures = 0
    color_failures = 0
    for i, section in enumerate(sections):
        scene_index = start_index + i
        _send("create_scene", {"index": -1})
        name = section.get("name", "Section {}".format(i + 1))
        _send("set_scene_name", {"scene_index": scene_index, "name": name})
        if "tempo" in section:
            try:
                _send("set_scene_tempo", {"scene_index": scene_index, "tempo": float(section["tempo"]), "tempo_enabled": True})
            except Exception:
                tempo_failures += 1
        if "color" in section:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": int(section["color"])})
            except Exception:
                color_failures += 1
        created.append({"name": name, "scene_index": scene_index})

    return {
        "scenes_created": created,
        "count": len(created),
        "tempo_failures": tempo_failures,
        "color_failures": color_failures,
    }


# ---------------------------------------------------------------------------
# Phase 8: Reference profiles
# ---------------------------------------------------------------------------

@mcp.tool()
def designate_reference_clip(
    track_index: int,
    slot_index: int,
    label: str = "default",
) -> dict:
    """
    Analyse the feel of a MIDI clip and store it as a named reference profile.

    The profile captures timing and velocity characteristics that can later be
    compared against other clips using compare_clip_feel().

    Stored profile includes:
      - timing_variance: std dev of distance-to-nearest-16th-grid (beats)
      - lateness_bias: mean signed offset from nearest grid point (positive = late)
      - velocity_std_dev: overall velocity spread
      - velocity_mean: mean velocity
      - per_pitch: per-pitch timing and velocity stats
      - note_count
      - grid: grid resolution used (always 0.25 = 16th note)

    Args:
        track_index: Track containing the reference clip.
        slot_index: Clip slot index.
        label: Name for this reference profile (default: 'default').

    Returns:
        label, note_count, timing_variance, lateness_bias, velocity_std_dev
    """
    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    if not notes:
        raise ValueError("Reference clip at track={}, slot={} is empty.".format(track_index, slot_index))

    grid = 0.25  # 16th note

    def nearest_grid(t, g):
        return round(t / g) * g

    signed_offsets = [n["start_time"] - nearest_grid(n["start_time"], grid) for n in notes]
    abs_offsets = [abs(o) for o in signed_offsets]
    timing_variance = _std_dev(abs_offsets)
    lateness_bias = sum(signed_offsets) / len(signed_offsets)

    velocities = [n["velocity"] for n in notes]
    velocity_std_dev = _std_dev(velocities)
    velocity_mean = sum(velocities) / len(velocities)

    from collections import defaultdict
    pitch_groups: dict = defaultdict(list)
    for n in notes:
        pitch_groups[n["pitch"]].append(n)

    per_pitch = {}
    for pitch, pitch_notes in pitch_groups.items():
        pvels = [n["velocity"] for n in pitch_notes]
        poffsets = [n["start_time"] - nearest_grid(n["start_time"], grid) for n in pitch_notes]
        per_pitch[pitch] = {
            "note_count": len(pitch_notes),
            "velocity_mean": sum(pvels) / len(pvels),
            "velocity_std_dev": _std_dev(pvels),
            "lateness_bias": sum(poffsets) / len(poffsets),
            "timing_variance": _std_dev([abs(o) for o in poffsets]),
        }

    profile = {
        "type": "clip_feel",
        "label": label,
        "track_index": track_index,
        "slot_index": slot_index,
        "note_count": len(notes),
        "grid": grid,
        "timing_variance": timing_variance,
        "lateness_bias": lateness_bias,
        "velocity_std_dev": velocity_std_dev,
        "velocity_mean": velocity_mean,
        "per_pitch": per_pitch,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    _save_reference_profile(label, profile)

    return {
        "label": label,
        "note_count": len(notes),
        "timing_variance": round(timing_variance, 5),
        "lateness_bias": round(lateness_bias, 5),
        "velocity_std_dev": round(velocity_std_dev, 3),
        "velocity_mean": round(velocity_mean, 1),
    }


@mcp.tool()
def compare_clip_feel(
    track_index: int,
    slot_index: int,
    reference_label: str = "default",
) -> dict:
    """
    Compare the feel of a MIDI clip against a stored reference profile.

    Call designate_reference_clip() first to create the reference.

    Returns deltas and human-readable flags. Nothing is modified.

    Args:
        track_index: Track containing the clip to analyse.
        slot_index: Clip slot index.
        reference_label: Label of the reference profile to compare against.

    Returns:
        note_count,
        timing_variance_delta (float): target minus reference (positive = more loose)
        lateness_bias_delta (float): target minus reference (positive = target is later)
        velocity_std_dev_delta (float): target minus reference (positive = more varied)
        flags: list of human-readable observation strings
        summary: one-line summary of the main departure
        reference_label, reference_note_count
    """
    if reference_label not in _reference_profiles:
        # Try loading from project memory
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference profile '{}'. Call designate_reference_clip() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "clip_feel":
        raise ValueError("Reference '{}' is not a clip feel profile (type={}).".format(
            reference_label, ref.get("type")))

    result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
    notes = result.get("notes", [])

    if not notes:
        return {
            "note_count": 0,
            "flags": ["target clip is empty"],
            "summary": "target clip is empty",
            "reference_label": reference_label,
            "reference_note_count": ref["note_count"],
        }

    grid = ref.get("grid", 0.25)

    def nearest_grid(t, g):
        return round(t / g) * g

    signed_offsets = [n["start_time"] - nearest_grid(n["start_time"], grid) for n in notes]
    abs_offsets = [abs(o) for o in signed_offsets]
    timing_variance = _std_dev(abs_offsets)
    lateness_bias = sum(signed_offsets) / len(signed_offsets)

    velocities = [n["velocity"] for n in notes]
    velocity_std_dev = _std_dev(velocities)
    velocity_mean = sum(velocities) / len(velocities)

    tv_delta = timing_variance - ref["timing_variance"]
    lb_delta = lateness_bias - ref["lateness_bias"]
    vsd_delta = velocity_std_dev - ref["velocity_std_dev"]
    vm_delta = velocity_mean - ref["velocity_mean"]

    flags = []

    # Timing variance
    if ref["timing_variance"] > 0.001:
        ratio = timing_variance / ref["timing_variance"]
        if ratio < 0.4:
            flags.append("timing is much tighter than reference ({:.1f}x less loose)".format(1 / ratio))
        elif ratio < 0.75:
            flags.append("timing is tighter than reference ({:.1f}x less loose)".format(1 / ratio))
        elif ratio > 2.5:
            flags.append("timing is much looser than reference ({:.1f}x more loose)".format(ratio))
        elif ratio > 1.5:
            flags.append("timing is looser than reference ({:.1f}x more loose)".format(ratio))
    else:
        # Reference is near-perfectly quantized
        if timing_variance > 0.005:
            flags.append("target has timing looseness; reference is grid-locked")

    # Lateness bias
    if abs(lb_delta) > 0.004:
        direction = "later" if lb_delta > 0 else "earlier"
        flags.append("notes are {:.1f}ms {} than reference (at 120bpm)".format(
            abs(lb_delta) * 500, direction))  # 1 beat at 120bpm = 500ms

    # Velocity spread
    if ref["velocity_std_dev"] > 1.0:
        ratio = velocity_std_dev / ref["velocity_std_dev"] if ref["velocity_std_dev"] > 0 else 1.0
        if ratio < 0.5:
            flags.append("velocities are much more uniform than reference ({:.1f}x less varied)".format(1 / ratio))
        elif ratio < 0.75:
            flags.append("velocities are more uniform than reference")
        elif ratio > 2.0:
            flags.append("velocities are much more varied than reference ({:.1f}x)".format(ratio))
    else:
        if velocity_std_dev > 8.0:
            flags.append("velocities more varied than reference (reference had near-uniform velocities)")

    # Velocity mean
    if abs(vm_delta) > 8:
        direction = "louder" if vm_delta > 0 else "quieter"
        flags.append("overall velocity is {:.0f} units {} than reference".format(abs(vm_delta), direction))

    # Perfectly quantized check
    SNAP_THRESHOLD = 0.001
    target_quantized = all(abs(o) < SNAP_THRESHOLD for o in abs_offsets)
    ref_quantized = ref["timing_variance"] < SNAP_THRESHOLD
    if target_quantized and not ref_quantized:
        flags.append("target is perfectly grid-locked; reference has human feel")
    elif not target_quantized and ref_quantized:
        flags.append("target has loose timing; reference is grid-locked")

    if not flags:
        flags.append("feel is similar to reference — no major departures detected")

    # Summary: the most significant flag
    summary = flags[0] if flags else "no significant difference"

    return {
        "note_count": len(notes),
        "timing_variance": round(timing_variance, 5),
        "lateness_bias": round(lateness_bias, 5),
        "velocity_std_dev": round(velocity_std_dev, 3),
        "velocity_mean": round(velocity_mean, 1),
        "timing_variance_delta": round(tv_delta, 5),
        "lateness_bias_delta": round(lb_delta, 5),
        "velocity_std_dev_delta": round(vsd_delta, 3),
        "velocity_mean_delta": round(vm_delta, 1),
        "flags": flags,
        "summary": summary,
        "reference_label": reference_label,
        "reference_note_count": ref["note_count"],
        "reference_timing_variance": round(ref["timing_variance"], 5),
        "reference_lateness_bias": round(ref["lateness_bias"], 5),
        "reference_velocity_std_dev": round(ref["velocity_std_dev"], 3),
    }


@mcp.tool()
def designate_reference_mix_state(
    label: str = "default",
    scene_index: int | None = None,
) -> dict:
    """
    Capture the current mix state as a named reference profile.

    Stores per-track volumes, panning, sends, mute/solo state,
    device counts, and clip counts. Can optionally be scoped to the
    clips active in a particular scene.

    Use compare_mix_state() to compare a later mix state against this reference.

    Args:
        label: Name for this reference profile (default: 'default').
        scene_index: Optional scene index to annotate (no filtering applied —
                     all tracks are captured regardless).

    Returns:
        label, track_count, timestamp
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", [])

    track_profiles = []
    for t in tracks:
        track_profiles.append({
            "index": t["index"],
            "name": t["name"],
            "volume": t.get("volume", 0.0),
            "pan": t.get("pan", 0.0),
            "mute": t.get("mute", False),
            "solo": t.get("solo", False),
            "arm": t.get("arm", False),
            "sends": t.get("sends", []),
            "device_count": t.get("device_count", 0),
            "clip_count": t.get("clip_count", 0),
            "is_midi_track": t.get("is_midi_track", False),
        })

    master = snapshot.get("master_track", {})
    return_tracks = snapshot.get("return_tracks", [])

    profile = {
        "type": "mix_state",
        "label": label,
        "scene_index": scene_index,
        "track_count": len(tracks),
        "tracks": track_profiles,
        "master": {
            "volume": master.get("volume", 0.0),
            "pan": master.get("pan", 0.0),
        },
        "return_tracks": [
            {
                "index": r["index"],
                "name": r["name"],
                "volume": r.get("volume", 0.0),
                "pan": r.get("pan", 0.0),
                "mute": r.get("mute", False),
            }
            for r in return_tracks
        ],
        "tempo": snapshot.get("tempo"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    _save_reference_profile(label, profile)

    return {
        "label": label,
        "track_count": len(tracks),
        "timestamp": profile["timestamp"],
    }


@mcp.tool()
def compare_mix_state(
    reference_label: str = "default",
    scene_index: int | None = None,
) -> dict:
    """
    Compare the current mix state against a stored reference mix profile.

    Call designate_reference_mix_state() first to create the reference.

    Flags material differences in volume, panning, and send levels per track.
    Also reports section energy delta (total clip count, active track count).

    Nothing is modified.

    Args:
        reference_label: Label of the reference mix profile to compare against.
        scene_index: Optional — annotated in the result but does not filter tracks.

    Returns:
        track_count, flags, summary, per_track_deltas,
        master_volume_delta, total_clip_count_delta,
        reference_label, reference_timestamp
    """
    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference profile '{}'. Call designate_reference_mix_state() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "mix_state":
        raise ValueError("Reference '{}' is not a mix state profile (type={}).".format(
            reference_label, ref.get("type")))

    snapshot = _send("get_session_snapshot")
    curr_tracks = {t["index"]: t for t in snapshot.get("tracks", [])}
    ref_tracks = {t["index"]: t for t in ref.get("tracks", [])}

    flags = []
    per_track_deltas = []

    VOLUME_THRESHOLD = 0.05     # ~0.5 dB at unity
    PAN_THRESHOLD = 0.1
    SEND_THRESHOLD = 0.05

    for idx in sorted(set(curr_tracks.keys()) | set(ref_tracks.keys())):
        curr = curr_tracks.get(idx)
        reft = ref_tracks.get(idx)

        if curr is None:
            flags.append("track {} ('{}') existed in reference but is now gone".format(idx, reft.get("name", "?")))
            continue
        if reft is None:
            flags.append("track {} ('{}') is new since reference was taken".format(idx, curr.get("name", "?")))
            continue

        name = curr.get("name", str(idx))
        deltas = {"index": idx, "name": name, "changes": []}

        vol_delta = curr.get("volume", 0.0) - reft.get("volume", 0.0)
        if abs(vol_delta) > VOLUME_THRESHOLD:
            direction = "louder" if vol_delta > 0 else "quieter"
            deltas["changes"].append({
                "property": "volume",
                "delta": round(vol_delta, 3),
                "description": "'{}' is {:.2f} units {} than reference".format(name, abs(vol_delta), direction),
            })
            flags.append("'{}' volume is {} by {:.2f}".format(name, direction, abs(vol_delta)))

        pan_delta = curr.get("pan", 0.0) - reft.get("pan", 0.0)
        if abs(pan_delta) > PAN_THRESHOLD:
            direction = "right" if pan_delta > 0 else "left"
            deltas["changes"].append({
                "property": "pan",
                "delta": round(pan_delta, 3),
                "description": "'{}' panned {:.2f} units more {} than reference".format(name, abs(pan_delta), direction),
            })

        curr_sends = curr.get("sends", [])
        ref_sends = reft.get("sends", [])
        for si, (cs, rs) in enumerate(zip(curr_sends, ref_sends)):
            sd = cs - rs
            if abs(sd) > SEND_THRESHOLD:
                direction = "higher" if sd > 0 else "lower"
                deltas["changes"].append({
                    "property": "send_{}".format(si),
                    "delta": round(sd, 3),
                    "description": "'{}' send {} is {} by {:.2f}".format(name, si, direction, abs(sd)),
                })

        # Mute state change
        if curr.get("mute") != reft.get("mute"):
            state = "muted" if curr.get("mute") else "unmuted"
            deltas["changes"].append({
                "property": "mute",
                "delta": None,
                "description": "'{}' is now {}".format(name, state),
            })
            flags.append("'{}' is now {}".format(name, state))

        # Device count change
        cd = curr.get("device_count", 0) - reft.get("device_count", 0)
        if cd != 0:
            deltas["changes"].append({
                "property": "device_count",
                "delta": cd,
                "description": "'{}' has {} {} device(s) than reference".format(
                    name, abs(cd), "more" if cd > 0 else "fewer"),
            })

        if deltas["changes"]:
            per_track_deltas.append(deltas)

    # Master volume
    curr_master_vol = snapshot.get("master_track", {}).get("volume", 0.0)
    ref_master_vol = ref.get("master", {}).get("volume", 0.0)
    master_vol_delta = curr_master_vol - ref_master_vol
    if abs(master_vol_delta) > VOLUME_THRESHOLD:
        direction = "louder" if master_vol_delta > 0 else "quieter"
        flags.append("master volume is {} by {:.2f}".format(direction, abs(master_vol_delta)))

    # Section energy: total clip count as a rough density proxy
    curr_clip_total = sum(t.get("clip_count", 0) for t in snapshot.get("tracks", []))
    ref_clip_total = sum(t.get("clip_count", 0) for t in ref.get("tracks", []))
    clip_count_delta = curr_clip_total - ref_clip_total

    if not flags:
        flags.append("mix state is similar to reference — no material changes detected")

    summary = flags[0] if flags else "no significant difference"

    return {
        "track_count": len(curr_tracks),
        "flags": flags,
        "summary": summary,
        "per_track_deltas": per_track_deltas,
        "master_volume_delta": round(master_vol_delta, 3),
        "total_clip_count_delta": clip_count_delta,
        "reference_label": reference_label,
        "reference_timestamp": ref.get("timestamp"),
    }


@mcp.tool()
def list_reference_profiles() -> dict:
    """
    List all stored reference profiles (both in-process and persisted).

    Returns:
        profiles: list of {label, type, timestamp, note_count (if clip_feel), track_count (if mix_state)}
    """
    _load_reference_profiles_from_project()
    profiles = []
    for label, p in sorted(_reference_profiles.items()):
        entry = {
            "label": label,
            "type": p.get("type", "unknown"),
            "timestamp": p.get("timestamp"),
        }
        if p.get("type") == "clip_feel":
            entry["note_count"] = p.get("note_count")
            entry["timing_variance"] = round(p.get("timing_variance", 0.0), 5)
            entry["lateness_bias"] = round(p.get("lateness_bias", 0.0), 5)
        elif p.get("type") == "mix_state":
            entry["track_count"] = p.get("track_count")
        profiles.append(entry)
    return {"profiles": profiles, "count": len(profiles)}


@mcp.tool()
def delete_reference_profile(label: str) -> dict:
    """Delete a reference profile by label (in-process and from project memory)."""
    removed_memory = False
    if label in _reference_profiles:
        del _reference_profiles[label]
    else:
        raise ValueError("No reference profile with label '{}'.".format(label))
    if helpers._current_project_id is not None:
        try:
            mem = _get_memory()
            if label in mem.get("reference_profiles", {}):
                del mem["reference_profiles"][label]
                _save_memory(helpers._current_project_id, mem)
                removed_memory = True
        except Exception:
            pass
    return {"deleted": label, "removed_from_disk": removed_memory}


# ---------------------------------------------------------------------------
# Phase 9: Tier 2 audio analysis (requires librosa)
# ---------------------------------------------------------------------------


def _analyse_audio_file(file_path: str, duration_limit: float = 300.0) -> dict:
    """Run audio analysis and return the result dict. Used by both analyse_audio and designate_reference_audio."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        raise ImportError(
            "librosa and numpy are required for audio analysis. "
            "Install with: pip install librosa soundfile"
        )

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    y, sr = librosa.load(path, sr=None, mono=True, duration=duration_limit)
    duration = len(y) / sr

    stereo_width = None
    try:
        import soundfile as sf
        y_stereo, _ = sf.read(path, always_2d=True)
        if y_stereo.shape[1] >= 2:
            max_samples = int(duration_limit * sr)
            y_stereo = y_stereo[:max_samples]
            L = y_stereo[:, 0].astype(np.float32)
            R = y_stereo[:, 1].astype(np.float32)
            mid = (L + R) / 2.0
            side = (L - R) / 2.0
            mid_rms = float(np.sqrt(np.mean(mid ** 2)) + 1e-9)
            side_rms = float(np.sqrt(np.mean(side ** 2)) + 1e-9)
            stereo_width = round(side_rms / mid_rms, 4)
    except Exception:
        pass

    S = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)

    def band_energy(f_low, f_high):
        mask = (freqs >= f_low) & (freqs < f_high)
        return float(np.mean(S[mask, :] ** 2)) if mask.any() else 0.0

    total_energy = float(np.mean(S ** 2)) + 1e-9
    bands = {
        "low":       band_energy(20, 100) / total_energy,
        "low_mid":   band_energy(100, 500) / total_energy,
        "mid":       band_energy(500, 2000) / total_energy,
        "high_mid":  band_energy(2000, 8000) / total_energy,
        "high":      band_energy(8000, sr / 2) / total_energy,
    }
    bands = {k: round(v, 5) for k, v in bands.items()}

    rms = float(np.sqrt(np.mean(y ** 2)))
    loudness_dbfs = round(20 * np.log10(rms + 1e-9), 2)
    peak = float(np.max(np.abs(y)))
    peak_dbfs = round(20 * np.log10(peak + 1e-9), 2)
    crest_factor_db = round(peak_dbfs - loudness_dbfs, 2)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    sc_mean = round(float(np.mean(centroid)), 1)
    sc_std = round(float(np.std(centroid)), 1)

    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
    sr_mean = round(float(np.mean(rolloff)), 1)

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='time')
    transient_density = round(len(onset_frames) / duration, 3) if duration > 0 else 0.0

    hop = int(sr * 0.5)
    rms_frames = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    rms_db_frames = 20 * np.log10(rms_frames + 1e-9)
    dynamic_range = round(float(np.std(rms_db_frames)), 3)

    return {
        "file_path": path,
        "duration_seconds": round(duration, 2),
        "sample_rate": int(sr),
        "tonal_balance": bands,
        "loudness_dbfs": loudness_dbfs,
        "peak_dbfs": peak_dbfs,
        "crest_factor_db": crest_factor_db,
        "spectral_centroid_mean": sc_mean,
        "spectral_centroid_std": sc_std,
        "spectral_rolloff_mean": sr_mean,
        "transient_density_per_sec": transient_density,
        "dynamic_range": dynamic_range,
        "stereo_width": stereo_width,
    }


@mcp.tool()
def designate_reference_audio(
    file_path: str,
    label: str = "default_audio",
    duration_limit: float = 300.0,
) -> dict:
    """
    Analyse an audio file and store it as a named reference audio profile.

    Computes:
      - Tonal balance: low / low-mid / mid / high-mid / high band energy ratios
      - Integrated loudness estimate (RMS-based, in dBFS)
      - Peak level (dBFS)
      - Crest factor (peak-to-average ratio, dB)
      - Spectral centroid mean and std (brightness proxy)
      - Spectral rolloff mean (frequency below which 85% of energy sits)
      - Transient density: mean onset rate (onsets per second)
      - Dynamic range: std dev of short-term RMS across 0.5s windows
      - Stereo width estimate (if stereo file: mean absolute L-R difference / mean L+R)

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Absolute or home-relative path to audio file (WAV, AIFF, FLAC, MP3).
        label: Name for this reference profile (default: 'default_audio').
        duration_limit: Maximum seconds to analyse (default 300s = 5 min). Longer files are truncated.

    Returns:
        label, duration_seconds, sample_rate, channels,
        tonal_balance (dict of band: ratio),
        loudness_dbfs, peak_dbfs, crest_factor_db,
        spectral_centroid_mean, spectral_centroid_std,
        spectral_rolloff_mean,
        transient_density_per_sec,
        dynamic_range,
        stereo_width (float or None)
    """
    result = _analyse_audio_file(file_path, duration_limit=duration_limit)

    profile = dict(result)
    profile["type"] = "audio_analysis"
    profile["label"] = label
    profile["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_reference_profile(label, profile)
    _audio_analysis_cache[label] = profile

    return {k: v for k, v in profile.items() if k != "type"}


@mcp.tool()
def analyse_audio(
    file_path: str,
    duration_limit: float = 300.0,
) -> dict:
    """
    Analyse an audio file and return tonal, loudness, transient, and spectral metrics.

    Does NOT store the result as a reference profile. Use designate_reference_audio()
    if you want to store it for later comparison.

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Absolute or home-relative path to audio file.
        duration_limit: Maximum seconds to analyse (default 300s).

    Returns:
        Same fields as designate_reference_audio() minus the label/timestamp.
    """
    return _analyse_audio_file(file_path, duration_limit=duration_limit)


@mcp.tool()
def compare_audio(
    file_path: str,
    reference_label: str = "default_audio",
    duration_limit: float = 300.0,
) -> dict:
    """
    Analyse an audio file and compare it against a stored reference audio profile.

    Call designate_reference_audio() first to create the reference.

    Returns per-metric deltas and human-readable flags. Nothing is modified.

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Path to the audio file to analyse and compare.
        reference_label: Label of the reference audio profile.
        duration_limit: Max seconds to analyse.

    Returns:
        flags: list of human-readable observation strings
        summary: most significant departure
        deltas: dict of {metric: {target, reference, delta, delta_pct}}
        tonal_balance_deltas: dict of {band: delta}
        reference_label, reference_file_path
    """
    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference audio profile '{}'. Call designate_reference_audio() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    if ref.get("type") != "audio_analysis":
        raise ValueError("Reference '{}' is not an audio analysis profile (type={}).".format(
            reference_label, ref.get("type")))

    target = _analyse_audio_file(file_path, duration_limit=duration_limit)

    flags = []
    deltas = {}

    def compare_scalar(key, label_str, threshold, unit="", higher_is="louder", fmt=".1f"):
        t_val = target.get(key)
        r_val = ref.get(key)
        if t_val is None or r_val is None:
            return
        delta = t_val - r_val
        pct = (delta / abs(r_val) * 100) if r_val != 0 else 0.0
        deltas[key] = {
            "target": t_val,
            "reference": r_val,
            "delta": round(delta, 3),
            "delta_pct": round(pct, 1),
        }
        if abs(delta) > threshold:
            direction = higher_is if delta > 0 else ("darker" if higher_is == "brighter" else
                                                      "quieter" if higher_is == "louder" else
                                                      "lower" if higher_is == "higher" else "less")
            flags.append("{} is {} than reference (delta: {:{}}{})"
                         .format(label_str, direction, delta, fmt, unit))

    compare_scalar("loudness_dbfs",          "loudness",          1.5,  unit=" dB",   higher_is="louder",   fmt="+.1f")
    compare_scalar("peak_dbfs",              "peak level",        2.0,  unit=" dB",   higher_is="louder",   fmt="+.1f")
    compare_scalar("crest_factor_db",        "crest factor",      3.0,  unit=" dB",   higher_is="higher",   fmt="+.1f")
    compare_scalar("spectral_centroid_mean", "spectral centroid", 500,  unit=" Hz",   higher_is="brighter", fmt="+.0f")
    compare_scalar("spectral_rolloff_mean",  "spectral rolloff",  800,  unit=" Hz",   higher_is="brighter", fmt="+.0f")
    compare_scalar("transient_density_per_sec", "transient density", 0.5, unit=" onsets/s", higher_is="higher", fmt="+.2f")
    compare_scalar("dynamic_range",          "dynamic range",     2.0,  unit=" dB",   higher_is="higher",   fmt="+.1f")

    if target.get("stereo_width") is not None and ref.get("stereo_width") is not None:
        compare_scalar("stereo_width", "stereo width", 0.05, unit="", higher_is="wider", fmt="+.3f")

    tonal_deltas = {}
    ref_bands = ref.get("tonal_balance", {})
    tgt_bands = target.get("tonal_balance", {})
    tonal_threshold = 0.03

    band_descriptions = {
        "low":      "sub/low end (<100Hz)",
        "low_mid":  "low mids (100-500Hz)",
        "mid":      "mids (500Hz-2kHz)",
        "high_mid": "high mids (2-8kHz)",
        "high":     "highs (>8kHz)",
    }

    for band in ("low", "low_mid", "mid", "high_mid", "high"):
        t_b = tgt_bands.get(band, 0.0)
        r_b = ref_bands.get(band, 0.0)
        d = t_b - r_b
        tonal_deltas[band] = round(d, 5)
        if abs(d) > tonal_threshold:
            direction = "more" if d > 0 else "less"
            flags.append("{} has {} energy than reference ({:+.1f}%)".format(
                band_descriptions.get(band, band), direction, d * 100))

    if not flags:
        flags.append("no significant differences detected vs reference")

    summary = flags[0] if flags else "similar to reference"

    return {
        "flags": flags,
        "summary": summary,
        "flag_count": len(flags),
        "deltas": deltas,
        "tonal_balance_deltas": tonal_deltas,
        "target_file": target["file_path"],
        "target_duration_seconds": target["duration_seconds"],
        "reference_label": reference_label,
        "reference_file_path": ref.get("file_path", "unknown"),
    }


@mcp.tool()
def compare_audio_sections(
    file_path: str,
    reference_label: str = "default_audio",
    num_sections: int = 4,
    duration_limit: float = 300.0,
) -> dict:
    """
    Split a target audio file into N equal sections and compare each against the reference.

    Useful for detecting whether energy, brightness, and density build correctly
    across sections (intro → verse → chorus → outro) relative to the reference.

    Requires: librosa, numpy, soundfile
    Install: pip install librosa soundfile

    Args:
        file_path: Path to the audio file to analyse.
        reference_label: Label of the reference audio profile (full-song reference).
        num_sections: Number of equal sections to split the file into (default 4).
        duration_limit: Max seconds to analyse.

    Returns:
        sections: list of {section_index, start_sec, end_sec, loudness_dbfs,
                           spectral_centroid_mean, transient_density_per_sec,
                           vs_reference_loudness_delta, vs_reference_centroid_delta}
        flags: list of human-readable observations about section energy progression
        reference_label
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        raise ImportError(
            "librosa and numpy are required for audio analysis. "
            "Install with: pip install librosa soundfile"
        )

    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
    if reference_label not in _reference_profiles:
        raise ValueError(
            "No reference audio profile '{}'. Call designate_reference_audio() first.".format(reference_label)
        )

    ref = _reference_profiles[reference_label]
    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    y, sr = librosa.load(path, sr=None, mono=True, duration=duration_limit)
    total_samples = len(y)
    section_size = total_samples // num_sections

    ref_loudness = ref.get("loudness_dbfs", -18.0)
    ref_centroid = ref.get("spectral_centroid_mean", 2000.0)

    sections = []
    for i in range(num_sections):
        start = i * section_size
        end = start + section_size if i < num_sections - 1 else total_samples
        segment = y[start:end]

        seg_rms = float(np.sqrt(np.mean(segment ** 2)))
        seg_loudness = round(20 * np.log10(seg_rms + 1e-9), 2)

        seg_centroid = librosa.feature.spectral_centroid(y=segment, sr=sr)[0]
        seg_centroid_mean = round(float(np.mean(seg_centroid)), 1)

        seg_onsets = librosa.onset.onset_detect(y=segment, sr=sr, units='time')
        seg_duration = len(segment) / sr
        seg_density = round(len(seg_onsets) / seg_duration, 3) if seg_duration > 0 else 0.0

        sections.append({
            "section_index": i,
            "start_sec": round(start / sr, 2),
            "end_sec": round(end / sr, 2),
            "loudness_dbfs": seg_loudness,
            "spectral_centroid_mean": seg_centroid_mean,
            "transient_density_per_sec": seg_density,
            "vs_reference_loudness_delta": round(seg_loudness - ref_loudness, 2),
            "vs_reference_centroid_delta": round(seg_centroid_mean - ref_centroid, 1),
        })

    flags = []
    loudness_values = [s["loudness_dbfs"] for s in sections]
    centroid_values = [s["spectral_centroid_mean"] for s in sections]

    if loudness_values[-1] < loudness_values[0] - 1.0:
        flags.append("energy drops from first to last section — arrangement may not build")
    elif loudness_values[-1] > loudness_values[0] + 1.0:
        flags.append("energy builds from first to last section — good arrangement progression")

    very_quiet = [s for s in sections if s["vs_reference_loudness_delta"] < -6.0]
    if very_quiet:
        flags.append("sections {} are more than 6dB quieter than reference".format(
            [s["section_index"] for s in very_quiet]))

    if centroid_values[-1] < centroid_values[0] - 300:
        flags.append("brightness decreases across sections — track gets darker toward the end")

    loudness_range = max(loudness_values) - min(loudness_values)
    if loudness_range < 1.5:
        flags.append("section loudness variance is only {:.1f}dB — arrangement may lack dynamic contrast".format(loudness_range))

    if not flags:
        flags.append("section energy progression looks normal")

    return {
        "sections": sections,
        "flags": flags,
        "flag_count": len(flags),
        "reference_label": reference_label,
        "total_duration_seconds": round(total_samples / sr, 2),
    }


def _observer_loop():
    """Background thread: polls session state and evaluates rules."""
    global _observer_running, _observer_last_snapshot

    while _observer_running:
        try:
            snapshot = _send("get_session_snapshot", _log=False)
            with _observer_lock:
                prev = _observer_last_snapshot
            _evaluate_observer_rules(snapshot, prev)
            with _observer_lock:
                _observer_last_snapshot = snapshot
        except Exception:
            pass  # Ableton not connected — silently skip
        time.sleep(_OBSERVER_POLL_INTERVAL)


def _evaluate_observer_rules(current: dict, previous: dict | None):
    """Evaluate observation rules and push suggestions to the queue."""
    global _observer_last_checkpoint_log_len, _observer_poll_count, _observer_clip_cursor, _observer_flagged_clips
    suggestions = []

    # Rule 1: New track added with no devices
    if previous is not None:
        prev_tracks = {t["index"]: t for t in previous.get("tracks", [])}
        curr_tracks = {t["index"]: t for t in current.get("tracks", [])}
        new_indices = set(curr_tracks.keys()) - set(prev_tracks.keys())
        for idx in new_indices:
            t = curr_tracks[idx]
            if t.get("device_count", 0) == 0:
                suggestions.append({
                    "source": "observer",
                    "priority": "medium",
                    "message": f"New track \"{t['name']}\" (index {idx}) has no devices.",
                    "action": f"add_native_device({idx}, 'Simpler')  # or set_track_role({idx}, 'your role')",
                })

    # Rule 2: Master volume near ceiling
    master_vol = current.get("master_track", {}).get("volume", 0.0)
    if master_vol > 0.95:
        suggestions.append({
            "source": "observer",
            "priority": "high",
            "message": f"Master volume at {master_vol:.2f} — near ceiling.",
            "action": "set_master_volume(0.85)  # or add a Limiter",
        })

    # Rule 3: Track count changed significantly (3+ tracks added at once)
    if previous is not None:
        prev_count = previous.get("track_count", 0)
        curr_count = current.get("track_count", 0)
        if curr_count - prev_count >= 3:
            suggestions.append({
                "source": "observer",
                "priority": "low",
                "message": f"Track count jumped from {prev_count} to {curr_count}.",
                "action": "take_snapshot('after_track_changes')  # capture state",
            })

    # Rule 4: Any track soloed
    soloed = [t["name"] for t in current.get("tracks", []) if t.get("solo")]
    if soloed:
        suggestions.append({
            "source": "observer",
            "priority": "low",
            "message": f"Tracks still soloed: {soloed}",
            "action": "set_track_solo(track_index, False)  # unmute others",
        })

    # Rule 5: No snapshot taken and op count growing (fire once per 20-op threshold crossing)
    log_len = len(_operation_log)
    if log_len > 0:
        current_threshold = (log_len // 20) * 20
        if current_threshold > _observer_last_checkpoint_log_len:
            recent_snaps = [e for e in _operation_log[-30:] if "snapshot" in e["command"]]
            if not recent_snaps:
                suggestions.append({
                    "source": "observer",
                    "priority": "medium",
                    "message": f"{log_len} operations since server start, no recent snapshot.",
                    "action": "take_snapshot('checkpoint')",
                })
            # Advance threshold marker regardless, to avoid re-firing at same boundary
            _observer_last_checkpoint_log_len = current_threshold

    # Rule 6: Clip feel divergence from default reference
    if "default" in _reference_profiles:
        ref = _reference_profiles["default"]
        if ref.get("type") == "clip_feel" and ref.get("timing_variance", 0) > 0.002:
            # Only flag if reference has meaningful human feel
            for track in current.get("tracks", []):
                # We only have clip_count here, not note data — so we can only flag
                # at the track level if it has clips. The actual per-clip comparison
                # requires a get_notes call which is too expensive for the observer loop.
                # Instead, queue a softer suggestion to run compare_clip_feel manually.
                pass  # Full per-clip analysis is left to explicit compare_clip_feel() calls

    # Rule 7: Perfectly quantized / robotic feel detection (lazy rotating sampler)
    try:
        _observer_poll_count += 1

        # Detect structural change (track/clip layout changed) — clear flagged set
        if previous is not None:
            prev_layout = tuple(
                (t.get("index"), t.get("clip_count", 0))
                for t in previous.get("tracks", [])
            )
            curr_layout = tuple(
                (t.get("index"), t.get("clip_count", 0))
                for t in current.get("tracks", [])
            )
            if prev_layout != curr_layout:
                _observer_flagged_clips = set()

        if _observer_poll_count % _OBSERVER_FEEL_EVERY_N_POLLS == 0:
            # Build a flat list of (track_index, slot_index, track_name) for all MIDI clips
            midi_clips = []
            for track in current.get("tracks", []):
                ti = track.get("index")
                track_name = track.get("name", f"Track {ti}")
                clips = track.get("clips", [])
                for clip in clips:
                    if clip.get("is_midi_clip") and not clip.get("is_empty", True):
                        si = clip.get("slot_index", clip.get("index"))
                        midi_clips.append((ti, si, track_name))

            if midi_clips:
                # Rotate cursor so all clips are eventually sampled
                _observer_clip_cursor = _observer_clip_cursor % len(midi_clips)
                batch_start = _observer_clip_cursor
                sampled = []
                for i in range(len(midi_clips)):
                    idx = (batch_start + i) % len(midi_clips)
                    sampled.append(midi_clips[idx])
                    if len(sampled) >= _OBSERVER_FEEL_MAX_CLIPS_PER_POLL:
                        break
                _observer_clip_cursor = (batch_start + len(sampled)) % len(midi_clips)

                for track_index, slot_index, track_name in sampled:
                    if (track_index, slot_index) in _observer_flagged_clips:
                        continue
                    try:
                        result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index}, _log=False)
                        notes = result.get("notes", [])
                    except Exception:
                        continue

                    if len(notes) < 4:
                        continue

                    # --- Perfectly quantized check ---
                    grid = 0.25
                    SNAP_THRESHOLD = 0.001

                    def _dist_to_grid(t: float, g: float) -> float:
                        return abs(t - round(t / g) * g)

                    perfectly_quantized = all(
                        _dist_to_grid(n["start_time"], grid) < SNAP_THRESHOLD
                        for n in notes
                    )

                    # --- Uniform velocities check ---
                    velocities = [n["velocity"] for n in notes]
                    vel_mean = sum(velocities) / len(velocities)
                    vel_std = (sum((v - vel_mean) ** 2 for v in velocities) / len(velocities)) ** 0.5
                    uniform_velocities = vel_std < 3.0

                    # --- Uniform durations per pitch check ---
                    pitch_durations: dict = collections.defaultdict(list)
                    for n in notes:
                        pitch_durations[n["pitch"]].append(n["duration"])
                    uniform_dur_pitches = 0
                    for durs in pitch_durations.values():
                        if len(durs) > 1:
                            dur_mean = sum(durs) / len(durs)
                            dur_std = (sum((d - dur_mean) ** 2 for d in durs) / len(durs)) ** 0.5
                            if dur_std < 0.01:
                                uniform_dur_pitches += 1
                    uniform_durations = uniform_dur_pitches >= 2

                    flags = []
                    if perfectly_quantized:
                        flags.append("perfectly_quantized")
                    if uniform_velocities:
                        flags.append("uniform_velocities")
                    if uniform_durations:
                        flags.append("uniform_durations")

                    if flags:
                        _observer_flagged_clips.add((track_index, slot_index))
                        suggestions.append({
                            "source": "observer",
                            "type": "feel_observer",
                            "action": "humanize_notes or humanize_dilla",
                            "reason": (
                                f"Clip on track {track_name} slot {slot_index} appears perfectly "
                                f"quantized (robotic feel detected: {', '.join(flags)})"
                            ),
                            "message": (
                                f"Clip on track {track_name} slot {slot_index} appears perfectly "
                                f"quantized (robotic feel detected: {', '.join(flags)})"
                            ),
                            "priority": "high" if perfectly_quantized else "medium",
                            "track_index": track_index,
                            "slot_index": slot_index,
                            "flags": flags,
                        })
    except Exception:
        pass  # Rule 7 errors never break the observer loop

    # Push all to queue (deduplicate by message)
    with _observer_lock:
        existing_messages = {s["message"] for s in _suggestion_queue}
        for s in suggestions:
            if s["message"] not in existing_messages:
                _suggestion_queue.append(s)


def _start_observer():
    """Start the background observer thread."""
    global _observer_thread, _observer_running
    if _observer_thread is not None and _observer_thread.is_alive():
        return  # already running
    _observer_running = True
    _observer_thread = threading.Thread(
        target=_observer_loop,
        name="AbletonMPCX-Observer",
        daemon=True,
    )
    _observer_thread.start()


def _stop_observer():
    """Stop the background observer thread."""
    global _observer_running
    _observer_running = False


@mcp.tool()
def get_pending_suggestions(max_items: int = 10) -> dict:
    """
    Return and clear pending suggestions from the background observer.

    The observer thread watches the session state and queues suggestions
    when it detects state changes matching known rules (new tracks without
    devices, volume ceiling, solo tracks left on, etc.).

    Call this after every tool interaction to surface proactive observations.
    Returns an empty list if nothing has been detected.

    Args:
        max_items: Maximum number of suggestions to return (default 10).

    Returns:
        suggestions: list of {source, priority, message, action}
        queue_length_before: how many were queued before this call
    """
    with _observer_lock:
        before = len(_suggestion_queue)
        items = []
        for _ in range(min(max_items, len(_suggestion_queue))):
            if _suggestion_queue:
                items.append(_suggestion_queue.popleft())
    return {
        "suggestions": items,
        "queue_length_before": before,
    }


@mcp.tool()
def observer_status() -> dict:
    """
    Return the current status of the background observer thread.

    Returns:
        running, poll_interval_seconds, queue_length, last_snapshot_track_count
    """
    with _observer_lock:
        queue_len = len(_suggestion_queue)
        last_snap = _observer_last_snapshot
    return {
        "running": _observer_running and (_observer_thread is not None and _observer_thread.is_alive()),
        "poll_interval_seconds": _OBSERVER_POLL_INTERVAL,
        "queue_length": queue_len,
        "last_snapshot_track_count": last_snap.get("track_count", 0) if last_snap else None,
        "last_snapshot_tempo": last_snap.get("tempo") if last_snap else None,
    }


# ---------------------------------------------------------------------------
# Workflow loop — detect → correct
# ---------------------------------------------------------------------------

@mcp.tool()
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
    """
    Check a clip's feel score and apply humanization automatically if it is too robotic.

    Calls analyze_clip_feel() internally. If feel_score >= feel_score_threshold,
    applies humanize_dilla() (style='dilla') or humanize_notes() (style='generic').
    If the clip already feels human, nothing is modified.

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        feel_score_threshold: Apply if feel_score >= this (0=human, 100=robotic). Default 60.
        style: 'dilla' for biased-late humanization, 'generic' for symmetric.
        late_bias: Passed to humanize_dilla (ignored for style='generic').
        max_early: Passed to humanize_dilla (ignored for style='generic').
        max_late: Passed to humanize_dilla. Also used as timing_amount for 'generic'.
        velocity_amount: Max velocity shift for either style.
        seed: Optional random seed.

    Returns:
        applied (bool), feel_score_before, feel_score_after,
        robotic_flags_before, humanization_style, note_count, reason
    """
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


@mcp.tool()
def fix_groove_from_reference(
    track_index: int,
    slot_index: int,
    reference_label: str = "default",
    timing_blend: float = 0.5,
    velocity_blend: float = 0.3,
    seed: int | None = None,
) -> dict:
    """
    Compare a clip's feel against a stored reference and apply corrections to close the gap.

    Calls compare_clip_feel() internally. If the clip is measurably tighter or more
    uniform than the reference, applies targeted humanize_dilla() to bring it closer.
    The correction is conservative by default (timing_blend=0.5).

    Requires a feel profile created with designate_reference_clip().

    Args:
        track_index: Track containing the clip.
        slot_index: Clip slot index.
        reference_label: Label of the stored feel reference profile.
        timing_blend: 0.0=no timing change, 1.0=fully match reference timing spread.
        velocity_blend: 0.0=no velocity change, 1.0=fully match reference velocity spread.
        seed: Optional random seed.

    Returns:
        applied (bool), flags_before, corrections_applied,
        timing_variance_before, timing_variance_after,
        velocity_std_before, velocity_std_after, reference_label
    """
    if reference_label not in _reference_profiles:
        _load_reference_profiles_from_project()
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


@mcp.tool()
def batch_auto_humanize(
    track_indices: list,
    slot_index: int,
    feel_score_threshold: int = 60,
    style: str = "dilla",
    seed: int | None = None,
) -> dict:
    """
    Run auto_humanize_if_robotic() across multiple tracks at the same slot index.

    Useful for checking all clips in a scene row and humanizing any that are too robotic.

    Args:
        track_indices: List of track indices to check.
        slot_index: Clip slot index to check on each track.
        feel_score_threshold: Apply humanization if feel_score >= this value. Default 60.
        style: 'dilla' or 'generic'.
        seed: Optional random seed (same seed applied to each clip for reproducibility).

    Returns:
        results: list of per-track {track_index, applied, feel_score_before, feel_score_after, note_count}
        applied_count, skipped_count, total_checked
    """
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




# ---------------------------------------------------------------------------
# Project audit tools
# ---------------------------------------------------------------------------

_MISSING_PLUGIN_INDICATORS = ["missing", "disabled", "unknown plugin", "vst not found", "au not found"]


@mcp.tool()
def find_missing_plugins(dry_run: bool = True) -> dict:
    """
    Scan all tracks for missing or disabled plugin placeholders.

    A "missing plugin" is a device whose name contains indicators like
    "Missing", "Disabled", "Unknown Plugin", "VST Not Found", or "AU Not Found"
    (case-insensitive), or whose ``is_active`` field is False, or whose
    ``has_error`` field is True.

    Args:
        dry_run: If True (default), report what would be deleted without
                 making any changes. Set to False to actually delete them.

    Returns:
        missing: list of {track_index, track_name, device_index, device_name, reason}
        deleted: list of same shape (populated only when dry_run=False)
        dry_run: bool echo
        total_found: int
        total_deleted: int
    """
    tracks = _send("get_tracks", {})
    missing = []
    for track in tracks:
        track_index = track["index"]
        track_name = track["name"]
        devices = _send("get_devices", {"track_index": track_index, "is_return_track": False})
        for device in devices:
            device_index = device["index"]
            device_name = device.get("name", "")
            reason = None
            name_lower = device_name.lower()
            for indicator in _MISSING_PLUGIN_INDICATORS:
                if indicator in name_lower:
                    reason = "name contains '{}'".format(indicator)
                    break
            if reason is None and device.get("is_active") is False:
                reason = "is_active=False"
            if reason is None and device.get("has_error") is True:
                reason = "has_error=True"
            if reason is not None:
                missing.append({
                    "track_index": track_index,
                    "track_name": track_name,
                    "device_index": device_index,
                    "device_name": device_name,
                    "reason": reason,
                })

    deleted = []
    if not dry_run and missing:
        _send("begin_undo_step", {"name": "delete_missing_plugins"})
        try:
            # Delete in reverse order to preserve indices
            for entry in reversed(missing):
                _send("delete_device", {
                    "track_index": entry["track_index"],
                    "device_index": entry["device_index"],
                    "is_return_track": False,
                })
                deleted.append(entry)
        finally:
            _send("end_undo_step", {})

    return {
        "missing": missing,
        "deleted": deleted,
        "dry_run": dry_run,
        "total_found": len(missing),
        "total_deleted": len(deleted),
    }


@mcp.tool()
def get_missing_media_status() -> dict:
    """
    Report all missing audio files in the current Live set.

    Calls the Remote Script to inspect clip sample references across
    all tracks and return which samples are missing/offline.

    Returns:
        missing_samples: list of {track_index, track_name, clip_index, clip_name, sample_path, status}
        total_missing: int
        total_checked: int
        can_search: bool  -- whether search_missing_media() is supported
    """
    result = _send("get_missing_media", {})
    missing = result.get("missing", [])
    total_checked = result.get("total_checked", 0)
    return {
        "missing_samples": missing,
        "total_missing": len(missing),
        "total_checked": total_checked,
        "can_search": True,
    }


@mcp.tool()
def search_missing_media(search_folders: list) -> dict:
    """
    Attempt to relink missing audio samples by searching the given folders.

    For each missing sample, searches the provided folders for a file with
    a matching name and relinks it if found.

    Args:
        search_folders: List of absolute folder paths to search (e.g.
                        ["/Users/me/Music/Samples", "/Volumes/Drive/Samples"])

    Returns:
        relinked: list of {sample_name, old_path, new_path, track_index, clip_index}
        still_missing: list of {sample_name, original_path, track_index, clip_index}
        relinked_count: int
        still_missing_count: int
        searched_folders: list of folders actually searched
    """
    _send("begin_undo_step", {"name": "search_missing_media"})
    try:
        result = _send("search_missing_media", {"search_folders": search_folders})
    finally:
        _send("end_undo_step", {})
    return result


@mcp.tool()
def project_health_report() -> dict:
    """
    Run a full health audit of the current Live set.

    Combines missing plugin detection, missing media status, and session
    structure checks into a single report with a human-readable summary.

    Returns:
        set_name: str
        track_count: int
        missing_plugins: list (same as find_missing_plugins())
        missing_media: list (same as get_missing_media_status())
        empty_tracks: list of {track_index, track_name}
        unnamed_tracks: list of {track_index, track_name}
        armed_tracks: list of {track_index, track_name}
        issues: list of human-readable issue strings
        health_score: float  -- 0.0 (broken) to 1.0 (clean)
        recommendations: list of str
    """
    # Gather data
    plugin_report = find_missing_plugins(dry_run=True)
    media_report = get_missing_media_status()
    tracks = _send("get_tracks", {})

    try:
        song_info = _send("get_song_info", {})
        set_name = song_info.get("name", "")
    except Exception:
        set_name = ""

    track_count = len(tracks)
    empty_tracks = []
    unnamed_tracks = []
    armed_tracks = []

    _default_name_pattern = re.compile(
        r"^(Audio|MIDI|1-Audio|1-MIDI)\s*\d*$|^\d+$", re.IGNORECASE
    )

    for track in tracks:
        track_index = track["index"]
        track_name = track["name"]
        if track.get("clip_count", 0) == 0 and track.get("device_count", 0) == 0:
            empty_tracks.append({"track_index": track_index, "track_name": track_name})
        if not track_name or _default_name_pattern.match(track_name.strip()):
            unnamed_tracks.append({"track_index": track_index, "track_name": track_name})
        if track.get("arm"):
            armed_tracks.append({"track_index": track_index, "track_name": track_name})

    # Build issue list
    issues = []
    missing_plugins = plugin_report["missing"]
    missing_media = media_report["missing_samples"]

    if missing_plugins:
        issues.append("{} missing/disabled plugin(s) found".format(len(missing_plugins)))
    if missing_media:
        issues.append("{} missing audio file(s) found".format(len(missing_media)))
    if empty_tracks:
        issues.append("{} empty track(s) (no clips or devices)".format(len(empty_tracks)))
    if unnamed_tracks:
        issues.append("{} track(s) with default/unnamed labels".format(len(unnamed_tracks)))
    if armed_tracks:
        issues.append("{} track(s) currently armed for recording".format(len(armed_tracks)))

    # Health score: 1.0 - (issues / _MAX_ISSUE_CATEGORIES)
    # Using a fixed denominator (5 possible issue categories) makes the score
    # consistent across projects regardless of track count.
    health_score = max(0.0, 1.0 - (len(issues) / _MAX_ISSUE_CATEGORIES))

    # Recommendations
    recommendations = []
    if missing_plugins:
        recommendations.append(
            "{} missing plugin(s) found — run find_missing_plugins(dry_run=False) to remove them".format(
                len(missing_plugins)
            )
        )
    if missing_media:
        recommendations.append(
            "{} missing audio file(s) — run search_missing_media([...]) with your sample folder paths to relink them".format(
                len(missing_media)
            )
        )
    if empty_tracks:
        recommendations.append(
            "{} empty track(s) found — consider removing them to clean up the session".format(
                len(empty_tracks)
            )
        )
    if unnamed_tracks:
        recommendations.append(
            "{} track(s) with default names — consider renaming for better organisation".format(
                len(unnamed_tracks)
            )
        )
    if armed_tracks:
        recommendations.append(
            "{} track(s) are armed — disarm before saving if not intentional".format(
                len(armed_tracks)
            )
        )
    if not issues:
        recommendations.append("No issues found — project looks healthy!")

    return {
        "set_name": set_name,
        "track_count": track_count,
        "missing_plugins": missing_plugins,
        "missing_media": missing_media,
        "empty_tracks": empty_tracks,
        "unnamed_tracks": unnamed_tracks,
        "armed_tracks": armed_tracks,
        "issues": issues,
        "health_score": health_score,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Cleanup tools
# ---------------------------------------------------------------------------

@mcp.tool()
def find_empty_tracks() -> dict:
    """
    Find all tracks with no clips and no devices.

    Returns:
        empty_tracks: list of {track_index, track_name, type}
        total_empty: int
        suggestion: str
    """
    tracks = _send("get_tracks", {})
    empty_tracks = []
    for track in tracks:
        if track.get("clip_count", 0) == 0 and track.get("device_count", 0) == 0:
            is_midi = track.get("is_midi_track", False)
            empty_tracks.append({
                "track_index": track.get("index", track.get("track_index", 0)),
                "track_name": track.get("name", ""),
                "type": "midi" if is_midi else "audio",
            })

    suggestion = (
        "Run cleanup_session(dry_run=False) to remove {} empty track(s).".format(len(empty_tracks))
        if empty_tracks
        else "No empty tracks found."
    )

    return {
        "empty_tracks": empty_tracks,
        "total_empty": len(empty_tracks),
        "suggestion": suggestion,
    }


@mcp.tool()
def find_unused_returns() -> dict:
    """
    Find return tracks that no track is sending to (all sends at zero or minimum).

    Returns:
        unused_returns: list of {track_index, track_name}
        total_unused: int
        suggestion: str
    """
    try:
        return_tracks = _send("get_return_tracks", {})
    except Exception:
        return_tracks = []

    try:
        tracks = _send("get_tracks", {})
    except Exception:
        tracks = []

    # For each return track determine if any regular track has a non-zero send to it
    return_count = len(return_tracks)
    send_totals = [0.0] * return_count

    for track in tracks:
        sends = track.get("sends", [])
        for send_idx, send_value in enumerate(sends):
            if send_idx < return_count:
                send_totals[send_idx] += float(send_value or 0.0)

    unused_returns = []
    for idx, rt in enumerate(return_tracks):
        if send_totals[idx] <= 0.0:
            unused_returns.append({
                "track_index": rt.get("index", rt.get("track_index", idx)),
                "track_name": rt.get("name", "Return {}".format(idx + 1)),
            })

    suggestion = (
        "Run cleanup_session(dry_run=False) to remove {} unused return track(s).".format(len(unused_returns))
        if unused_returns
        else "No unused return tracks found."
    )

    return {
        "unused_returns": unused_returns,
        "total_unused": len(unused_returns),
        "suggestion": suggestion,
    }


@mcp.tool()
def cleanup_session(dry_run: bool = True) -> dict:
    """
    Remove empty tracks and unused return tracks.

    Args:
        dry_run: If True (default), report what would be removed. Set False to execute.

    Returns:
        would_remove / removed: list of {track_index, track_name, reason}
        dry_run: bool
        total_affected: int
    """
    empty_result = find_empty_tracks()
    unused_result = find_unused_returns()

    candidates = []
    for t in empty_result["empty_tracks"]:
        candidates.append({
            "track_index": t["track_index"],
            "track_name": t["track_name"],
            "reason": "empty track (no clips, no devices)",
        })
    for r in unused_result["unused_returns"]:
        candidates.append({
            "track_index": r["track_index"],
            "track_name": r["track_name"],
            "reason": "unused return track (all sends at zero)",
        })

    removed = []
    if not dry_run and candidates:
        # Separate regular tracks from return tracks, delete returns first by name
        empty_track_indices = {t["track_index"] for t in empty_result["empty_tracks"]}
        unused_return_indices = {r["track_index"] for r in unused_result["unused_returns"]}

        _send("begin_undo_step", {"name": "cleanup_session"})
        try:
            # Delete return tracks in reverse index order
            # Note: delete_return_track uses 'index', while delete_track uses 'track_index' — both match the existing MCP API
            for idx in sorted(unused_return_indices, reverse=True):
                try:
                    _send("delete_return_track", {"index": idx})
                    removed.append(next(c for c in candidates if c["track_index"] == idx))
                except Exception:
                    pass
            # Delete empty regular tracks in reverse index order
            for idx in sorted(empty_track_indices, reverse=True):
                try:
                    _send("delete_track", {"track_index": idx})
                    removed.append(next(c for c in candidates if c["track_index"] == idx))
                except Exception:
                    pass
        finally:
            _send("end_undo_step", {})

    key = "removed" if not dry_run else "would_remove"
    return {
        key: removed if not dry_run else candidates,
        "dry_run": dry_run,
        "total_affected": len(candidates),
    }


# ---------------------------------------------------------------------------
# Batch project audit tools
# ---------------------------------------------------------------------------

_PROJECT_LOAD_DELAY_SECONDS: float = 2.0  # seconds to wait after opening a set before auditing

@mcp.tool()
def open_set(set_path: str) -> dict:
    """
    Open an Ableton Live set file (.als) on the currently running Live instance.

    Args:
        set_path: Absolute path to the .als file

    Returns:
        success: bool
        set_name: str
        set_path: str
        error: str or None
    """
    set_path = str(set_path)
    set_name = os.path.splitext(os.path.basename(set_path))[0]

    try:
        _send("open_set", {"set_path": set_path})
        return {
            "success": True,
            "set_name": set_name,
            "set_path": set_path,
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "set_name": set_name,
            "set_path": set_path,
            "error": str(exc),
        }


@mcp.tool()
def batch_audit_projects(set_paths: list, save_reports: bool = True) -> dict:
    """
    Run project_health_report() on multiple Live sets in sequence.

    Opens each set, runs the health report, optionally saves a JSON report
    next to each .als file, then moves to the next.

    Args:
        set_paths: List of absolute paths to .als files
        save_reports: If True, save a {set_name}_audit.json next to each .als file

    Returns:
        results: list of {set_path, set_name, health_score, missing_plugins,
                          missing_media, issues, report_saved_to}
        total_sets: int
        completed: int
        failed: list of {set_path, error}
        summary: str  -- human readable e.g. "8/10 sets healthy, 2 have missing plugins"
    """
    results = []
    failed = []
    healthy_count = 0
    sets_with_missing_plugins = 0

    for path in set_paths:
        path = str(path)
        set_name = os.path.splitext(os.path.basename(path))[0]

        try:
            open_result = open_set(path)
            if not open_result["success"]:
                raise RuntimeError(open_result["error"] or "open_set returned failure")

            # Give Live a moment to finish loading
            time.sleep(_PROJECT_LOAD_DELAY_SECONDS)

            report = project_health_report()
            report_saved_to = None

            if save_reports:
                report_path = os.path.join(
                    os.path.dirname(path),
                    "{}_audit.json".format(set_name),
                )
                try:
                    with open(report_path, "w", encoding="utf-8") as f:
                        json.dump(report, f, indent=2)
                    report_saved_to = report_path
                except Exception:
                    pass

            entry = {
                "set_path": path,
                "set_name": set_name,
                "health_score": report.get("health_score", 0.0),
                "missing_plugins": report.get("missing_plugins", []),
                "missing_media": report.get("missing_media", []),
                "issues": report.get("issues", []),
                "report_saved_to": report_saved_to,
            }
            results.append(entry)

            if report.get("health_score", 0.0) >= 1.0:
                healthy_count += 1
            if report.get("missing_plugins"):
                sets_with_missing_plugins += 1

        except Exception as exc:
            failed.append({"set_path": path, "error": str(exc)})

    total = len(set_paths)
    completed = len(results)

    if sets_with_missing_plugins:
        summary = "{}/{} sets healthy, {} have missing plugins".format(
            healthy_count, total, sets_with_missing_plugins
        )
    elif failed:
        summary = "{}/{} sets audited successfully, {} failed to open".format(
            completed, total, len(failed)
        )
    else:
        summary = "{}/{} sets healthy".format(healthy_count, total)

    return {
        "results": results,
        "total_sets": total,
        "completed": completed,
        "failed": failed,
        "summary": summary,
    }

# ---------------------------------------------------------------------------
# M — Per-project cached audit JSON files
# ---------------------------------------------------------------------------

@mcp.tool()
def save_project_audit(save_path: str | None = None) -> dict:
    """Run project_health_report() and save the result as a JSON file.

    Args:
        save_path: Where to save.  If None, saves next to the current .als file
                   as ``{project_name}_audit_{date}.json``.

    Returns:
        saved_to: str
        health_score: int or float
        summary: str
        timestamp: str
    """
    report = project_health_report()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if save_path is None:
        set_name = report.get("set_name") or "project"
        safe_name = re.sub(r"[^\w\-]", "_", set_name)
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        filename = "{}_audit_{}.json".format(safe_name, date_str)
        save_path = os.path.join(os.path.expanduser("~/.ableton_mpcx/audits"), filename)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    report["_saved_at"] = timestamp
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    summary = summarize_health_report(report)
    return {
        "saved_to": save_path,
        "health_score": report.get("health_score"),
        "summary": summary,
        "timestamp": timestamp,
    }


@mcp.tool()
def load_project_audit(audit_path: str) -> dict:
    """Load a previously saved project audit JSON and return its contents.

    Args:
        audit_path: Path to the ``_audit.json`` file.

    Returns:
        The audit data dict, or an error dict if the file is not found.
    """
    if not os.path.exists(audit_path):
        return {"error": "Audit file not found: {}".format(audit_path)}
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {"error": "Failed to read audit file: {}".format(str(exc))}


@mcp.tool()
def compare_project_audits(audit_path_a: str, audit_path_b: str) -> dict:
    """Compare two saved project audits and return what changed.

    Useful for tracking project health over time or comparing two versions.

    Returns:
        health_score_change: int
        new_issues: list of str
        resolved_issues: list of str
        unchanged_issues: list of str
        summary: str
    """
    a = load_project_audit(audit_path_a)
    if "error" in a:
        return {"error": "Audit A: {}".format(a["error"])}
    b = load_project_audit(audit_path_b)
    if "error" in b:
        return {"error": "Audit B: {}".format(b["error"])}

    score_a = a.get("health_score", 0)
    score_b = b.get("health_score", 0)
    health_score_change = int(score_b) - int(score_a)

    issues_a = set(str(i) for i in a.get("issues", []))
    issues_b = set(str(i) for i in b.get("issues", []))

    new_issues = sorted(issues_b - issues_a)
    resolved_issues = sorted(issues_a - issues_b)
    unchanged_issues = sorted(issues_a & issues_b)

    direction = "improved" if health_score_change > 0 else ("worsened" if health_score_change < 0 else "unchanged")
    summary = (
        "Health score {} from {} to {} ({:+d}). "
        "{} new issue(s), {} resolved, {} unchanged.".format(
            direction, score_a, score_b, health_score_change,
            len(new_issues), len(resolved_issues), len(unchanged_issues),
        )
    )

    return {
        "health_score_change": health_score_change,
        "new_issues": new_issues,
        "resolved_issues": resolved_issues,
        "unchanged_issues": unchanged_issues,
        "summary": summary,
    }

