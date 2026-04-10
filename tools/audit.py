"""Audit tools — workflow primitives, project health, missing plugins and media, reference profiles, audio analysis, and the detect-correct workflow loop."""
from __future__ import annotations

import collections
import datetime
import json
import logging
import math
import os
import pathlib
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

import helpers
from helpers import (
    mcp,
    _send,
    _send_silent,
    _append_operation,
    _operation_log,
    _MAX_LOG_ENTRIES,
    _snapshots,
    _snapshots_lock,
    _reference_profiles,
    _reference_profiles_lock,
    _audio_analysis_cache,
    _audio_analysis_cache_lock,
    _get_memory,
    _save_memory,
    _load_memory,
    _memory_path,
    _save_reference_profile,
    _load_reference_profiles_from_project,
)
from tools.humanization import (  # noqa: F401
    humanize_notes,
    humanize_dilla,
    analyze_clip_feel,
    auto_humanize_if_robotic,
    fix_groove_from_reference,
    batch_auto_humanize,
)
from tools.audio_analysis import (  # noqa: F401
    _analyse_audio_file,
    analyse_audio,
)
from tools.reference_profiles import (  # noqa: F401
    designate_reference_clip,
    compare_clip_feel,
    designate_reference_mix_state,
    compare_mix_state,
    designate_reference_audio,
    compare_audio,
    compare_audio_sections,
    list_reference_profiles,
    delete_reference_profile,
)
from tools.project_health import (  # noqa: F401
    find_missing_plugins,
    get_missing_media_status,
    search_missing_media,
    project_health_report,
    find_empty_tracks,
    find_unused_returns,
    cleanup_session,
    open_set,
    batch_audit_projects,
    save_project_audit,
    load_project_audit,
    compare_project_audits,
)

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


def duplicate_clip_to_new_scene(track_index: int, slot_index: int) -> dict:
    """Duplicate the clip at (track_index, slot_index) into a new scene."""
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


def create_midi_track_with_drum_rack(index: int = -1, track_name: str | None = None) -> dict:
    """Create a new MIDI track and immediately load a Drum Rack onto it."""
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


def capture_device_macro_snapshot(track_index: int, device_index: int, label: str | None = None) -> dict:
    """Capture the current parameter values of a device as a named snapshot."""
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


def apply_device_macro_snapshot(label: str, track_index: int | None = None, device_index: int | None = None) -> dict:
    """Restore device parameter values from a previously captured snapshot."""
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
        except Exception as e:
            logger.debug("Could not set parameter %s on device %s track %s: %s", param.get("index"), di, ti, e)
            skipped += 1

    return {
        "label": label,
        "device_name": snap.get("device_name", "unknown"),
        "parameters_set": set_count,
        "skipped": skipped,
    }


def prep_track_for_resampling(track_index: int, resample_track_name: str = "Resample") -> dict:
    """Prepare a track for resampling by creating a new audio track routed to record it."""
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
    except Exception as e:
        logger.debug("Could not arm resampling track %s: %s", resample_track_index, e)
        arm_succeeded = False  # Some track types may not support arming

    return {
        "source_track_index": track_index,
        "resample_track_index": resample_track_index,
        "resample_track_name": resample_track_name,
        "arm_succeeded": arm_succeeded,
    }


def create_arrangement_scaffold(
    sections: list[dict],
) -> dict:
    """Create a basic arrangement scaffold by adding named scenes for each section."""
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
            except Exception as e:
                logger.debug("Could not set tempo for scene %s: %s", scene_index, e)
                tempo_failures += 1
        if "color" in section:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": int(section["color"])})
            except Exception as e:
                logger.debug("Could not set color for scene %s: %s", scene_index, e)
                color_failures += 1
        created.append({"name": name, "scene_index": scene_index})

    return {
        "scenes_created": created,
        "count": len(created),
        "tempo_failures": tempo_failures,
        "color_failures": color_failures,
    }


def _observer_loop():
    """Background thread: polls session state and evaluates rules."""
    global _observer_running, _observer_last_snapshot

    while _observer_running:
        try:
            snapshot = _send_silent("get_session_snapshot")
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
    with _reference_profiles_lock:
        default_ref = _reference_profiles.get("default")
    if default_ref is not None:
        if default_ref.get("type") == "clip_feel" and default_ref.get("timing_variance", 0) > 0.002:
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
                        result = _send_silent("get_notes", {"track_index": track_index, "slot_index": slot_index})
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


def get_pending_suggestions(max_items: int = 10) -> dict:
    """Return and clear pending suggestions from the background observer."""
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


def observer_status() -> dict:
    """Return the current status of the background observer thread."""
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


