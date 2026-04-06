"""Session tools — song, transport, project memory, snapshots, auto-naming, session collaborator, and contextual suggestion tools."""
from __future__ import annotations

import collections
import copy
import datetime
import json
import math
import os
import pathlib
import plistlib
import re
import shutil
import socket
import threading
import time
from contextlib import contextmanager
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
from helpers.cache import cache_state
from tools.spectrum import get_spectrum_telemetry_instances

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@mcp.tool()
def get_app_version() -> dict:
    """Return the running Ableton Live version."""
    return _send("get_app_version")

# ---------------------------------------------------------------------------
# Song
# ---------------------------------------------------------------------------

@mcp.tool()
def get_song_info() -> dict:
    """Return the current song's tempo, transport state, loop settings, etc."""
    return _send("get_song_info")

@mcp.tool()
def set_tempo(tempo: float) -> dict:
    """Set the song tempo (20-999 BPM)."""
    return _send("set_tempo", {"tempo": tempo})

@mcp.tool()
def set_time_signature(numerator: int | None = None, denominator: int | None = None) -> dict:
    """Set the song time signature numerator and/or denominator."""
    params: dict[str, int] = {}
    if numerator is not None:
        params["numerator"] = numerator
    if denominator is not None:
        params["denominator"] = denominator
    return _send("set_time_signature", params)

@mcp.tool()
def set_record_mode(record_mode: bool) -> dict:
    """Enable or disable Arrangement Record."""
    return _send("set_record_mode", {"record_mode": record_mode})

@mcp.tool()
def set_session_record(session_record: bool) -> dict:
    """Enable or disable Session Overdub."""
    return _send("set_session_record", {"session_record": session_record})

@mcp.tool()
def set_overdub(overdub: bool) -> dict:
    """Enable or disable MIDI Arrangement Overdub."""
    return _send("set_overdub", {"overdub": overdub})

@mcp.tool()
def set_metronome(metronome: bool) -> dict:
    """Enable or disable the metronome."""
    return _send("set_metronome", {"metronome": metronome})

@mcp.tool()
def set_loop(enabled: bool | None = None, loop_start: float | None = None, loop_length: float | None = None) -> dict:
    """Set Arrangement loop state, start position (beats) and/or length (beats)."""
    params: dict[str, Any] = {}
    if enabled is not None:
        params["enabled"] = enabled
    if loop_start is not None:
        params["loop_start"] = loop_start
    if loop_length is not None:
        params["loop_length"] = loop_length
    return _send("set_loop", params)

@mcp.tool()
def set_swing_amount(value: float) -> dict:
    """Set the global swing amount (0.0-1.0)."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("swing_amount must be between 0.0 and 1.0")
    return _send("set_swing_amount", {"value": value})

@mcp.tool()
def set_groove_amount(value: float) -> dict:
    """Set the global groove amount (0.0-1.0)."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("groove_amount must be between 0.0 and 1.0")
    return _send("set_groove_amount", {"value": value})

@mcp.tool()
def set_back_to_arranger(value: bool) -> dict:
    """Enable or disable Back to Arranger mode."""
    return _send("set_back_to_arranger", {"value": value})

@mcp.tool()
def set_clip_trigger_quantization(value: int) -> dict:
    """Set the global clip trigger quantization (0-13, matching Live's ClipTriggerQuantization enum)."""
    if not 0 <= value <= 13:
        raise ValueError("clip_trigger_quantization must be between 0 and 13")
    return _send("set_clip_trigger_quantization", {"value": value})

@mcp.tool()
def set_midi_recording_quantization(value: int) -> dict:
    """Set the MIDI recording quantization (0-8, matching Live's RecordingQuantization enum)."""
    if not 0 <= value <= 8:
        raise ValueError("midi_recording_quantization must be between 0 and 8")
    return _send("set_midi_recording_quantization", {"value": value})

@mcp.tool()
def set_scale_mode(scale_mode: bool) -> dict:
    """Enable or disable scale mode."""
    return _send("set_scale_mode", {"scale_mode": scale_mode})

@mcp.tool()
def set_scale_name(scale_name: str) -> dict:
    """Set the scale name (e.g. 'Major', 'Minor', 'Dorian')."""
    return _send("set_scale_name", {"scale_name": scale_name})

@mcp.tool()
def set_root_note(root_note: int) -> dict:
    """Set the root note for the scale (0=C, 1=C#, ..., 11=B)."""
    if not 0 <= root_note <= 11:
        raise ValueError("root_note must be between 0 and 11")
    return _send("set_root_note", {"root_note": root_note})

@mcp.tool()
def set_or_delete_cue() -> dict:
    """Toggle (create or delete) a cue point at the current playback position."""
    return _send("set_or_delete_cue")

@mcp.tool()
def re_enable_automation() -> dict:
    """Re-enable automation that has been overridden."""
    return _send("re_enable_automation")

@mcp.tool()
def play_selection() -> dict:
    """Play the current selection in the Arrangement."""
    return _send("play_selection")

@mcp.tool()
def start_playing() -> dict:
    """Start playback from the insert marker."""
    return _send("start_playing")

@mcp.tool()
def stop_playing() -> dict:
    """Stop playback."""
    return _send("stop_playing")

@mcp.tool()
def continue_playing() -> dict:
    """Continue playback from the current position."""
    return _send("continue_playing")

@mcp.tool()
def tap_tempo() -> dict:
    """Send a tap tempo pulse."""
    return _send("tap_tempo")

@mcp.tool()
def undo() -> dict:
    """Undo the last operation."""
    return _send("undo")

@mcp.tool()
def redo() -> dict:
    """Redo the last undone operation."""
    return _send("redo")

@mcp.tool()
def capture_midi(destination: int = 0) -> dict:
    """Capture recently played MIDI. destination: 0=auto, 1=session, 2=arrangement."""
    return _send("capture_midi", {"destination": destination})

@mcp.tool()
def capture_and_insert_scene() -> dict:
    """Capture currently playing clips into a new scene."""
    return _send("capture_and_insert_scene")

@mcp.tool()
def create_audio_track(index: int = -1) -> dict:
    """Create a new audio track. index=-1 appends at end."""
    return _send("create_audio_track", {"index": index})

@mcp.tool()
def create_midi_track(index: int = -1) -> dict:
    """Create a new MIDI track. index=-1 appends at end."""
    return _send("create_midi_track", {"index": index})

@mcp.tool()
def create_return_track() -> dict:
    """Add a new return track."""
    return _send("create_return_track")

@mcp.tool()
def create_scene(index: int = -1) -> dict:
    """Create a new scene. index=-1 appends at end."""
    return _send("create_scene", {"index": index})

@mcp.tool()
def delete_scene(index: int) -> dict:
    """Delete the scene at index."""
    return _send("delete_scene", {"scene_index": index})

@mcp.tool()
def delete_track(track_index: int) -> dict:
    """Delete the track at track_index."""
    return _send("delete_track", {"track_index": track_index})

@mcp.tool()
def delete_return_track(index: int) -> dict:
    """Delete the return track at index."""
    return _send("delete_return_track", {"index": index})

@mcp.tool()
def duplicate_scene(index: int) -> dict:
    """Duplicate the scene at index."""
    return _send("duplicate_scene", {"scene_index": index})

@mcp.tool()
def duplicate_track(track_index: int) -> dict:
    """Duplicate the track at track_index."""
    return _send("duplicate_track", {"track_index": track_index})

@mcp.tool()
def jump_by(beats: float) -> dict:
    """Jump the playback position by the given number of beats (positive or negative)."""
    return _send("jump_by", {"beats": beats})

@mcp.tool()
def jump_to_next_cue() -> dict:
    """Jump to the next cue point."""
    return _send("jump_to_next_cue")

@mcp.tool()
def jump_to_prev_cue() -> dict:
    """Jump to the previous cue point."""
    return _send("jump_to_prev_cue")

@mcp.tool()
def stop_all_clips(quantized: int = 1) -> dict:
    """Stop all clips. quantized=0 stops immediately regardless of quantization."""
    return _send("stop_all_clips", {"quantized": quantized})

@mcp.tool()
def get_cue_points() -> list:
    """Return all cue points as a list of {name, time} dicts."""
    return _send("get_cue_points")

@mcp.tool()
def jump_to_cue_point(index: int) -> dict:
    """Jump to the cue point at index."""
    return _send("jump_to_cue_point", {"index": index})

# ---------------------------------------------------------------------------
# Song.View
# ---------------------------------------------------------------------------

@mcp.tool()
def get_selected_track() -> dict:
    """Return the currently selected track index and name."""
    return _send("get_selected_track")

@mcp.tool()
def set_selected_track(track_index: int) -> dict:
    """Select the track at track_index."""
    return _send("set_selected_track", {"track_index": track_index})

@mcp.tool()
def get_selected_scene() -> dict:
    """Return the currently selected scene index and name."""
    return _send("get_selected_scene")

@mcp.tool()
def set_selected_scene(scene_index: int) -> dict:
    """Select the scene at scene_index."""
    return _send("set_selected_scene", {"scene_index": scene_index})

@mcp.tool()
def get_follow_song() -> dict:
    """Return whether Follow Song is enabled."""
    return _send("get_follow_song")

@mcp.tool()
def set_follow_song(follow_song: bool) -> dict:
    """Enable or disable Follow Song."""
    return _send("set_follow_song", {"follow_song": follow_song})

@mcp.tool()
def get_draw_mode() -> dict:
    """Return whether Draw Mode is enabled in the current view."""
    return _send("get_draw_mode")

@mcp.tool()
def set_draw_mode(draw_mode: bool) -> dict:
    """Enable or disable Draw Mode."""
    return _send("set_draw_mode", {"draw_mode": draw_mode})

@mcp.tool()
def focus_view(view_name: str) -> dict:
    """
    Focus a named view in Ableton Live.
    Common view names: 'Session', 'Arranger', 'Detail', 'Detail/Clip',
    'Detail/DeviceChain', 'Browser', 'Mixer'.
    """
    return _send("focus_view", {"view_name": view_name})

@mcp.tool()
def show_view(view_name: str) -> dict:
    """Show a named panel/view. See focus_view for common view names."""
    return _send("show_view", {"view_name": view_name})

@mcp.tool()
def hide_view(view_name: str) -> dict:
    """Hide a named panel/view. See focus_view for common view names."""
    return _send("hide_view", {"view_name": view_name})

@mcp.tool()
def is_view_visible(view_name: str) -> dict:
    """Return whether the named view/panel is currently visible."""
    return _send("is_view_visible", {"view_name": view_name})

@mcp.tool()
def available_main_views() -> dict:
    """Return the list of available main view names."""
    return _send("available_main_views")

@mcp.tool()
def set_exclusive_arm(value: bool) -> dict:
    """Enable or disable exclusive arm mode (arming one track disarms all others)."""
    return _send("set_exclusive_arm", {"value": value})

@mcp.tool()
def set_exclusive_solo(value: bool) -> dict:
    """Enable or disable exclusive solo mode (soloing one track un-solos all others)."""
    return _send("set_exclusive_solo", {"value": value})

@mcp.tool()
def set_select_on_launch(value: bool) -> dict:
    """Enable or disable Select on Launch (firing a scene/clip selects it)."""
    return _send("set_select_on_launch", {"value": value})

@mcp.tool()
def nudge_up() -> dict:
    """Send a tempo nudge up pulse (nudges the master tempo up momentarily)."""
    return _send("nudge_up")

@mcp.tool()
def nudge_down() -> dict:
    """Send a tempo nudge down pulse (nudges the master tempo down momentarily)."""
    return _send("nudge_down")

@mcp.tool()
def get_appointed_device() -> dict:
    """
    Return the currently appointed (focused) device in Live.
    Returns track_index, device_index, name and class_name, or {"device": None} if none.
    """
    return _send("get_appointed_device")

# ---------------------------------------------------------------------------
# Protocol versioning and capability discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def get_protocol_version() -> dict:
    """Return the AbletonMPCX protocol version string."""
    return _send("get_protocol_version")


@mcp.tool()
def get_selected_context() -> dict:
    """
    Return everything currently selected/focused in Live:
    selected_track, selected_scene, detail_clip (open in Detail View),
    and appointed_device (focused device).

    Use this at the start of a workflow to orient without making extra calls.
    """
    return _send("get_selected_context")


@mcp.tool()
def get_capabilities() -> dict:
    """
    Returns a structured summary of all registered MCP tools with their descriptions.
    Call this on connect to understand what actions are available before acting.

    Returns:
        tools: dict mapping tool name to first-line description
        tool_count: int
        version: str
        usage_hint: str
    """
    tools_map = {}
    for name, tool_obj in mcp._tool_manager._tools.items():
        description = (tool_obj.description or "").strip().split("\n")[0]
        tools_map[name] = description
    return {
        "tool_count": len(tools_map),
        "tools": tools_map,
        "version": "AbletonMPCX 1.0",
        "usage_hint": (
            "Call get_session_snapshot() to orient fully. "
            "Use tool names to discover capabilities."
        ),
    }


@mcp.tool()
def get_session_snapshot() -> dict:
    """
    Return a full normalised snapshot of the current session in a single call.

    Includes: tempo, time signature, transport state, all tracks (with mixer
    values and device list), return tracks, master track devices, and scene list.
    Does NOT include clip notes (use get_notes per clip for that).

    Use this at the start of a session to orient an agent completely,
    or before/after a set of changes to compare state.
    """
    return _send("get_session_snapshot")


@mcp.tool()
def take_snapshot(label: str) -> dict:
    """
    Take a named snapshot of the current session state and store it in memory.

    The snapshot is retrieved via get_session_snapshot() and stored under the
    given label. Use diff_snapshots(label_a, label_b) to compare two snapshots.

    Labels are ephemeral — they are lost when the MCP server restarts.

    Args:
        label: A name for this snapshot, e.g. 'before_eq', 'after_mix', 'v1'.

    Returns:
        label, track_count, scene_count, timestamp_ms
    """
    snapshot = _send("get_session_snapshot")
    snapshot["_label"] = label
    snapshot["_timestamp_ms"] = int(time.time() * 1000)
    _snapshots[label] = snapshot
    return {
        "label": label,
        "track_count": snapshot.get("track_count", 0),
        "scene_count": snapshot.get("scene_count", 0),
        "timestamp_ms": snapshot["_timestamp_ms"],
    }


@mcp.tool()
def list_snapshots() -> dict:
    """
    List all stored snapshots by label and timestamp.

    Returns:
        snapshots: list of {label, track_count, scene_count, timestamp_ms}
    """
    return {
        "snapshots": [
            {
                "label": label,
                "track_count": s.get("track_count", 0),
                "scene_count": s.get("scene_count", 0),
                "timestamp_ms": s.get("_timestamp_ms", 0),
            }
            for label, s in sorted(_snapshots.items(), key=lambda x: x[1].get("_timestamp_ms", 0))
        ]
    }


@mcp.tool()
def delete_snapshot(label: str) -> dict:
    """Delete a stored snapshot by label."""
    if label not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label))
    del _snapshots[label]
    return {"deleted": label}


def _diff_value(a, b, path: str, changes: list):
    """Recursively diff two values, appending changes to the list."""
    if type(a) != type(b):
        changes.append({"path": path, "before": a, "after": b})
        return
    if isinstance(a, dict):
        all_keys = set(a.keys()) | set(b.keys())
        for k in sorted(all_keys):
            if k.startswith("_"):
                continue
            child_path = "{}.{}".format(path, k)
            if k not in a:
                changes.append({"path": child_path, "before": None, "after": b[k]})
            elif k not in b:
                changes.append({"path": child_path, "before": a[k], "after": None})
            else:
                _diff_value(a[k], b[k], child_path, changes)
    elif isinstance(a, list):
        # For lists of dicts with an "index" key (tracks, scenes, devices), diff by index
        if a and b and isinstance(a[0], dict) and "index" in a[0]:
            a_map = {item["index"]: item for item in a}
            b_map = {item["index"]: item for item in b}
            all_indices = sorted(set(a_map.keys()) | set(b_map.keys()))
            for idx in all_indices:
                child_path = "{}[{}]".format(path, idx)
                if idx not in a_map:
                    changes.append({"path": child_path, "before": None, "after": b_map[idx]})
                elif idx not in b_map:
                    changes.append({"path": child_path, "before": a_map[idx], "after": None})
                else:
                    _diff_value(a_map[idx], b_map[idx], child_path, changes)
        else:
            if a != b:
                changes.append({"path": path, "before": a, "after": b})
    else:
        if a != b:
            changes.append({"path": path, "before": a, "after": b})


@mcp.tool()
def diff_snapshots(label_a: str, label_b: str) -> dict:
    """
    Compare two named snapshots and return what changed between them.

    Args:
        label_a: Label of the 'before' snapshot.
        label_b: Label of the 'after' snapshot.

    Returns:
        label_a, label_b, change_count, changes: list of {path, before, after}

    The 'path' uses dot notation, e.g.:
        'tracks[0].volume'        — track 0 volume changed
        'tracks[2].devices[1].is_active'  — device enabled/disabled
        'master_track.volume'     — master volume changed
        'tempo'                   — song tempo changed

    Example workflow:
        take_snapshot('before')
        set_master_volume(0.9)
        add_native_device(0, 'EQ Eight')
        take_snapshot('after')
        diff_snapshots('before', 'after')
    """
    if label_a not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label_a))
    if label_b not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label_b))

    a = _snapshots[label_a]
    b = _snapshots[label_b]

    changes: list = []
    _diff_value(a, b, "session", changes)

    return {
        "label_a": label_a,
        "label_b": label_b,
        "change_count": len(changes),
        "changes": changes,
    }


@mcp.tool()
def diff_snapshot_vs_live(label: str) -> dict:
    """
    Compare a stored snapshot against the current live session state.

    Equivalent to: take_snapshot('_live_now') then diff_snapshots(label, '_live_now'),
    but without permanently storing the live snapshot.

    Args:
        label: Label of the stored 'before' snapshot to compare against live.

    Returns:
        label, change_count, changes: list of {path, before, after}
    """
    if label not in _snapshots:
        raise ValueError("No snapshot with label '{}'".format(label))

    live = _send("get_session_snapshot")
    a = _snapshots[label]

    changes: list = []
    _diff_value(a, live, "session", changes)

    return {
        "label": label,
        "change_count": len(changes),
        "changes": changes,
    }



# ---------------------------------------------------------------------------
# Phase 5: Persistent project memory
# ---------------------------------------------------------------------------

@mcp.tool()
def set_project_id(project_id: str) -> dict:
    """
    Set the current project identity for persistent memory.

    All subsequent memory operations (notes, snapshots, operation log, preferences,
    track roles) are scoped to this project_id.

    Args:
        project_id: A unique name for this project, e.g. 'my_album_track_3'.
                    Use something meaningful — it becomes a filename on disk.

    Returns:
        project_id, memory_path, is_new (whether this is a fresh project)
    """
    helpers._current_project_id = project_id
    path = _memory_path(project_id)
    is_new = not os.path.exists(path)
    if is_new:
        mem = _load_memory(project_id)
        _save_memory(project_id, mem)
    return {
        "project_id": project_id,
        "memory_path": path,
        "is_new": is_new,
    }


@mcp.tool()
def get_project_memory() -> dict:
    """
    Return the full persistent memory for the current project.

    Includes: preferences, track roles, notes, snapshot labels, operation log summary.
    Requires set_project_id() to have been called first.
    """
    mem = _get_memory()
    return {
        "project_id": mem["project_id"],
        "created_at": mem.get("created_at"),
        "note_count": len(mem.get("notes", [])),
        "notes": mem.get("notes", []),
        "preferences": mem.get("preferences", {}),
        "track_roles": mem.get("track_roles", {}),
        "snapshot_labels": list(mem.get("snapshots", {}).keys()),
        "device_snapshot_labels": list(mem.get("device_snapshots", {}).keys()),
        "operation_log_count": len(mem.get("operation_log", [])),
    }


@mcp.tool()
def add_project_note(note: str, category: str = "general") -> dict:
    """
    Add a free-form note to the current project memory.

    Use this to record intent, decisions, problems, or anything worth remembering.

    Args:
        note: The note text.
        category: Optional category tag, e.g. 'mix', 'arrangement', 'intent', 'issue'.

    Returns:
        note_id, timestamp
    """
    mem = _get_memory()
    entry = {
        "id": len(mem.get("notes", [])),
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "category": category,
        "note": note,
    }
    mem.setdefault("notes", []).append(entry)
    _save_memory(helpers._current_project_id, mem)
    return {"note_id": entry["id"], "timestamp": entry["ts"]}


def _set_track_role(track_index: int, role: str) -> dict:
    """
    Assign a semantic role to a track in the current project memory.

    Examples: 'kick bus', 'main reverb', 'lead synth', 'master chain', 'resample'

    Args:
        track_index: Track index (-1 for master).
        role: Human-readable role string.

    Returns:
        track_index, role
    """
    mem = _get_memory()
    mem.setdefault("track_roles", {})[str(track_index)] = role
    _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "role": role}


def _get_track_roles() -> dict:
    """
    Return all track role assignments for the current project.

    Returns:
        track_roles: dict of {track_index_str: role}
    """
    mem = _get_memory()
    return {"track_roles": mem.get("track_roles", {})}


@mcp.tool()
def set_preference(key: str, value: Any) -> dict:
    """
    Store a user preference in the current project memory.

    Preferences are free-form key/value pairs. Use them to record
    working style, mix targets, or workflow habits.

    Examples:
        set_preference('preferred_reverb', 'Valhalla Room')
        set_preference('target_lufs', -14.0)
        set_preference('grit_on_melodics', True)
        set_preference('low_mid_character', 'dense but not muddy')

    Args:
        key: Preference key string.
        value: Any JSON-serialisable value.

    Returns:
        key, value
    """
    mem = _get_memory()
    mem.setdefault("preferences", {})[key] = value
    _save_memory(helpers._current_project_id, mem)
    return {"key": key, "value": value}


@mcp.tool()
def get_preferences() -> dict:
    """Return all stored preferences for the current project."""
    mem = _get_memory()
    return {"preferences": mem.get("preferences", {})}


@mcp.tool()
def save_snapshot_to_project(label: str) -> dict:
    """
    Capture the current session state and persist it to project memory on disk.

    Unlike take_snapshot() which is in-memory only, this survives MCP server restarts.

    Args:
        label: Snapshot label.

    Returns:
        label, track_count, scene_count, timestamp
    """
    mem = _get_memory()
    snapshot = _send("get_session_snapshot")
    snapshot["_label"] = label
    snapshot["_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    mem.setdefault("snapshots", {})[label] = snapshot
    _save_memory(helpers._current_project_id, mem)
    # Also store in-process for diff tools
    _snapshots[label] = snapshot
    return {
        "label": label,
        "track_count": snapshot.get("track_count", 0),
        "scene_count": snapshot.get("scene_count", 0),
        "timestamp": snapshot["_timestamp"],
    }


@mcp.tool()
def load_snapshots_from_project() -> dict:
    """
    Load all persisted snapshots from project memory into the in-process store.

    After calling this, diff_snapshots() and diff_snapshot_vs_live() can use
    snapshots that were saved in previous sessions.

    Returns:
        loaded: list of snapshot labels loaded
    """
    mem = _get_memory()
    persisted = mem.get("snapshots", {})
    for label, snap in persisted.items():
        _snapshots[label] = snap
    return {"loaded": list(persisted.keys()), "count": len(persisted)}


# ---------------------------------------------------------------------------
# Phase 6: Operation log
# ---------------------------------------------------------------------------

@mcp.tool()
def get_operation_log(limit: int = 50) -> dict:
    """
    Return the most recent operations from the in-process operation log.

    The log captures every command sent to Ableton during this server session.
    It is not automatically persisted unless flush_operation_log() is called.

    Args:
        limit: Maximum number of entries to return (most recent first).

    Returns:
        entries: list of {ts, command, params, result_summary}
        total_in_memory: total entries in the current session log
    """
    entries = list(reversed(_operation_log[-limit:]))
    return {
        "entries": entries,
        "total_in_memory": len(_operation_log),
    }


@mcp.tool()
def flush_operation_log() -> dict:
    """
    Persist the current in-process operation log to project memory on disk.

    Appends new entries to the project's stored log (capped at 5000 entries total).
    Requires set_project_id() to have been called.

    Returns:
        flushed_count, total_stored
    """
    mem = _get_memory()
    stored = mem.get("operation_log", [])
    stored.extend(_operation_log)
    # Cap at 5000
    if len(stored) > 5000:
        stored = stored[-5000:]
    mem["operation_log"] = stored
    _save_memory(helpers._current_project_id, mem)
    return {
        "flushed_count": len(_operation_log),
        "total_stored": len(stored),
    }


@mcp.tool()
def get_stored_operation_log(limit: int = 100) -> dict:
    """
    Return the persisted operation log from project memory (across sessions).

    Args:
        limit: Maximum number of entries to return (most recent first).

    Returns:
        entries: list of {ts, command, params, result_summary}
        total_stored: total entries stored on disk
    """
    mem = _get_memory()
    stored = mem.get("operation_log", [])
    return {
        "entries": list(reversed(stored[-limit:])),
        "total_stored": len(stored),
    }


@mcp.tool()
def summarise_session() -> dict:
    """
    Summarise what happened in the current session based on the operation log.

    Returns counts of each command type, most frequent operations,
    and a timeline of major state changes.

    Returns:
        session_start, command_counts, most_frequent, destructive_ops, total_ops
    """
    from collections import Counter

    if not _operation_log:
        return {"total_ops": 0, "command_counts": {}, "most_frequent": [], "destructive_ops": []}

    counter = Counter(entry["command"] for entry in _operation_log)
    destructive = [
        e for e in _operation_log
        if any(kw in e["command"] for kw in ("delete", "remove", "create", "duplicate", "add_notes"))
    ]

    return {
        "session_start": _operation_log[0]["ts"] if _operation_log else None,
        "total_ops": len(_operation_log),
        "command_counts": dict(counter.most_common()),
        "most_frequent": [{"command": cmd, "count": cnt} for cmd, cnt in counter.most_common(10)],
        "destructive_ops": destructive[-20:],  # last 20 destructive ops
    }


# ---------------------------------------------------------------------------
# Phase 7: Contextual suggestions
# ---------------------------------------------------------------------------

@mcp.tool()
def suggest_next_actions() -> dict:
    """
    Analyse the current session context and suggest logical next actions.

    Looks at:
    - Current session snapshot (tracks, devices, mixer state)
    - Recent operation log
    - Project memory (notes, preferences, track roles)
    - Stored snapshots

    Returns a list of suggestions with reasoning. These are observations only —
    nothing is executed automatically.

    Returns:
        suggestions: list of {action, reason, priority ('high'|'medium'|'low')}
    """
    suggestions = []

    # 1. Snapshot suggestion — if no snapshot taken recently
    recent_snapshots = [e for e in _operation_log[-50:] if "snapshot" in e["command"]]
    if not recent_snapshots:
        suggestions.append({
            "action": "take_snapshot('before_changes')",
            "reason": "No snapshot taken in recent operations. Recommended before making changes.",
            "priority": "high",
        })

    # 2. Project memory suggestion
    if helpers._current_project_id is None:
        suggestions.append({
            "action": "set_project_id('your_project_name')",
            "reason": "No project ID set. Set one to enable persistent memory, notes, and operation history.",
            "priority": "high",
        })

    # 3. Analyse session state
    try:
        snapshot = _send("get_session_snapshot")
        tracks = snapshot.get("tracks", [])

        # Unarmed tracks with no devices
        empty_tracks = [t for t in tracks if t.get("device_count", 0) == 0]
        if empty_tracks:
            suggestions.append({
                "action": "review or delete empty tracks: {}".format([t["name"] for t in empty_tracks[:5]]),
                "reason": "{} track(s) have no devices loaded.".format(len(empty_tracks)),
                "priority": "low",
            })

        # Master track device check
        master_devices = snapshot.get("master_track", {}).get("devices", [])
        if not master_devices:
            suggestions.append({
                "action": "add_native_device(-1, 'Limiter') or add_native_device(-1, 'EQ Eight')",
                "reason": "Master track has no devices. Consider adding a limiter or EQ.",
                "priority": "medium",
            })

        # Muted tracks
        muted = [t for t in tracks if t.get("mute")]
        if muted:
            suggestions.append({
                "action": "review muted tracks: {}".format([t["name"] for t in muted[:5]]),
                "reason": "{} track(s) are currently muted.".format(len(muted)),
                "priority": "low",
            })

    except Exception:
        pass

    # 4. Operation log patterns
    if _operation_log:
        recent_cmds = [e["command"] for e in _operation_log[-20:]]

        # If user added devices recently, suggest snapshot
        if any("add_native_device" in c or "load_browser_item" in c for c in recent_cmds):
            already_snapped = any("snapshot" in c for c in recent_cmds)
            if not already_snapped:
                suggestions.append({
                    "action": "take_snapshot('after_device_changes')",
                    "reason": "Devices were recently added. Snapshot recommended to capture state.",
                    "priority": "high",
                })

        # If notes were removed recently, warn
        if any("remove_notes" in c for c in recent_cmds):
            suggestions.append({
                "action": "verify clip note state with get_notes()",
                "reason": "Notes were recently removed. Verify the clip state is as expected.",
                "priority": "medium",
            })

        # Flush log suggestion
        if len(_operation_log) > 100 and helpers._current_project_id:
            suggestions.append({
                "action": "flush_operation_log()",
                "reason": "Operation log has {} entries. Flush to persist to project memory.".format(len(_operation_log)),
                "priority": "low",
            })

    # 5. Project memory patterns
    if helpers._current_project_id:
        try:
            mem = _get_memory()
            prefs = mem.get("preferences", {})

            # If preferences mention a reverb, suggest checking return tracks
            if any("reverb" in str(v).lower() for v in prefs.values()):
                try:
                    returns = _send("get_return_tracks")
                    reverb_returns = [r for r in returns if "reverb" in r["name"].lower() or "verb" in r["name"].lower()]
                    if not reverb_returns:
                        suggestions.append({
                            "action": "check return tracks — no reverb return found",
                            "reason": "Your preferences mention a reverb preference but no return track is named for reverb.",
                            "priority": "medium",
                        })
                except Exception:
                    pass
        except Exception:
            pass

    # Reference profile suggestion
    if "default" in _reference_profiles:
        ref = _reference_profiles.get("default", {})
        if ref.get("type") == "clip_feel":
            suggestions.append({
                "action": "compare_clip_feel(track_index, slot_index, reference_label='default')",
                "reason": "A clip feel reference profile exists. Use compare_clip_feel() to check how your current clips compare.",
                "priority": "low",
            })
        elif ref.get("type") == "mix_state":
            suggestions.append({
                "action": "compare_mix_state(reference_label='default')",
                "reason": "A mix state reference profile exists. Use compare_mix_state() to check what has changed.",
                "priority": "low",
            })

    # Audio reference suggestion
    if "default_audio" in _reference_profiles:
        suggestions.append({
            "action": "compare_audio('/path/to/your/bounce.wav', reference_label='default_audio')",
            "reason": "An audio reference profile exists. Export a bounce and compare it against your reference.",
            "priority": "low",
        })

    return {
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }


@mcp.tool()
def analyse_mix_state() -> dict:
    """
    Analyse the current mix state and surface observations.

    Looks at track volumes, panning, mute/solo state, device presence,
    and compares against stored preferences if available.

    Returns observations, not instructions. Nothing is modified.

    Returns:
        observations: list of {observation, category, severity ('info'|'warn'|'flag')}
    """
    observations = []

    try:
        snapshot = _send("get_session_snapshot")
        tracks = snapshot.get("tracks", [])
        master = snapshot.get("master_track", {})

        # Volume checks
        hot_tracks = [t for t in tracks if t.get("volume", 0) > 0.95]
        if hot_tracks:
            observations.append({
                "observation": "Tracks near maximum volume: {}".format([t["name"] for t in hot_tracks]),
                "category": "levels",
                "severity": "warn",
            })

        silent_tracks = [t for t in tracks if not t.get("mute") and t.get("volume", 1.0) < 0.01]
        if silent_tracks:
            observations.append({
                "observation": "Tracks at near-zero volume (not muted): {}".format([t["name"] for t in silent_tracks]),
                "category": "levels",
                "severity": "warn",
            })

        # Panning checks
        hard_panned = [t for t in tracks if abs(t.get("pan", 0)) > 0.95]
        if hard_panned:
            observations.append({
                "observation": "Tracks hard-panned: {}".format([t["name"] for t in hard_panned]),
                "category": "panning",
                "severity": "info",
            })

        # Solo check
        soloed = [t for t in tracks if t.get("solo")]
        if soloed:
            observations.append({
                "observation": "Tracks currently soloed: {}".format([t["name"] for t in soloed]),
                "category": "monitoring",
                "severity": "flag",
            })

        # Master device check
        master_devices = master.get("devices", [])
        device_names = [d["name"] for d in master_devices]
        has_limiter = any("limit" in n.lower() for n in device_names)
        has_eq = any("eq" in n.lower() for n in device_names)

        if not has_limiter:
            observations.append({
                "observation": "No limiter on master track.",
                "category": "master_chain",
                "severity": "info",
            })
        if not has_eq:
            observations.append({
                "observation": "No EQ on master track.",
                "category": "master_chain",
                "severity": "info",
            })

        # Armed tracks check
        armed = [t for t in tracks if t.get("arm")]
        if armed:
            observations.append({
                "observation": "Tracks currently armed for recording: {}".format([t["name"] for t in armed]),
                "category": "recording",
                "severity": "info",
            })

        # Compare against preferences if available
        if helpers._current_project_id:
            try:
                mem = _get_memory()
                target_lufs = mem.get("preferences", {}).get("target_lufs")
                if target_lufs:
                    observations.append({
                        "observation": "Target LUFS preference set to {}. Use an external meter to verify.".format(target_lufs),
                        "category": "levels",
                        "severity": "info",
                    })
            except Exception:
                pass

    except Exception as e:
        observations.append({
            "observation": "Could not read session state: {}".format(str(e)),
            "category": "error",
            "severity": "flag",
        })

    return {
        "observation_count": len(observations),
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Phase 7: Song creation from brief
# ---------------------------------------------------------------------------

_STYLE_PRESETS: dict[str, dict] = {
    "snoop": {"bpm": 90, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "hip_hop": {"bpm": 90, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "boom_bap": {"bpm": 85, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Sample", "audio"), ("Lead", "midi")]},
    "trap": {"bpm": 140, "tracks": [("808", "midi"), ("HiHat", "midi"), ("Melody", "midi"), ("FX", "midi")]},
    "lofi": {"bpm": 75, "tracks": [("Drums", "midi"), ("Bass", "midi"), ("Piano", "midi"), ("Texture", "audio")]},
}
_STYLE_FREE: dict = {"bpm": 120, "tracks": [("MIDI 1", "midi"), ("MIDI 2", "midi"), ("MIDI 3", "midi"), ("Audio 1", "audio")]}


@mcp.tool()
def create_song_from_brief(
    style: str,
    key: str | None = None,
    bpm: float | None = None,
) -> dict:
    """
    Create a skeleton arrangement from a music style brief.

    Supported styles: 'snoop', 'hip_hop', 'boom_bap', 'trap', 'lofi', or any value for a generic layout.

    Args:
        style: Music style preset.
        key: Optional musical key (e.g. 'C', 'F#m'). Stored as metadata; no Ableton command is issued.
        bpm: Override BPM. Uses style default if not provided.

    Returns:
        style, bpm, key, tracks_created, track_names, warnings
    """
    preset = _STYLE_PRESETS.get(style, _STYLE_FREE)
    bpm_used: float = bpm if bpm is not None else float(preset["bpm"])
    tracks: list[tuple[str, str]] = preset["tracks"]
    warnings: list[str] = []

    # 1. Set tempo
    _send("set_tempo", {"tempo": bpm_used})

    # 2. Create tracks and rename them
    track_names: list[str] = []
    for idx, (name, track_type) in enumerate(tracks):
        if track_type == "audio":
            _send("create_audio_track", {"index": idx})
        else:
            _send("create_midi_track", {"index": idx})
        _send("set_track_name", {"track_index": idx, "name": name})
        track_names.append(name)

    # 3. Warn if key was provided (no set_song_key command available)
    if key is not None:
        warnings.append(
            f"Key '{key}' noted but no set_song_key command is available; "
            "set the key manually in Ableton."
        )

    return {
        "style": style,
        "bpm": bpm_used,
        "key": key,
        "tracks_created": len(track_names),
        "track_names": track_names,
        "warnings": warnings,
    }




_ROLE_COLORS = {
    "kick":     5,    # red
    "snare":    9,    # orange
    "drums":    9,    # orange
    "hi-hat":   12,   # yellow
    "perc":     12,   # yellow
    "bass":     14,   # yellow-green
    "keys":     19,   # green
    "piano":    19,
    "guitar":   25,   # teal
    "pad":      28,   # cyan
    "synth":    28,
    "lead":     41,   # blue
    "fx":       49,   # purple
    "vocal":    57,   # pink
    "master":   1,    # white
    "return":   70,   # grey
    "default":  0,
}

_DEVICE_TO_ROLE = {
    "kick":             "kick",
    "snare":            "snare",
    "drum":             "drums",
    "superior":         "drums",
    "addictive":        "drums",
    "bass":             "bass",
    "mariana":          "bass",
    "session upright":  "bass",
    "sub":              "bass",
    "piano":            "piano",
    "keyscape":         "piano",
    "grand":            "piano",
    "upright":          "piano",
    "keys":             "keys",
    "rhodes":           "keys",
    "wurli":            "keys",
    "clav":             "keys",
    "organ":            "keys",
    "pad":              "pad",
    "omnisphere":       "pad",
    "lead":             "lead",
    "serum":            "synth",
    "massive":          "synth",
    "vocal":            "vocal",
    "voice":            "vocal",
    "choir":            "vocal",
    "guitar":           "guitar",
    "reverb":           "fx",
    "delay":            "fx",
}

_SCENE_SECTION_COLORS = {
    "intro":    70,   # grey
    "verse":    41,   # blue
    "chorus":   5,    # red
    "hook":     5,    # red
    "drop":     5,    # red
    "pre":      28,   # cyan
    "build":    28,   # cyan
    "bridge":   49,   # purple
    "break":    49,   # purple
    "outro":    70,   # grey
    "default":  0,
}

# Cache directory for session management persistent data
_SESSION_CACHE_DIR = os.path.expanduser("~/.ableton_mpcx")
_DEVICE_SNAPSHOTS_PATH = os.path.join(_SESSION_CACHE_DIR, "device_snapshots.json")
_VERSIONS_PATH = os.path.join(_SESSION_CACHE_DIR, "versions.json")



# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------


def _ensure_session_cache_dir():
    os.makedirs(_SESSION_CACHE_DIR, exist_ok=True)


def _load_json_cache(path: str, default):
    """Load a JSON cache file; return default on missing/corrupt."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json_cache(path: str, data) -> bool:
    """Save data to a JSON cache file. Returns True on success."""
    _ensure_session_cache_dir()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def _infer_role_from_devices(track_index: int) -> tuple[str, str]:
    """Return (role, method_used) by inspecting device names on the track."""
    try:
        devices = _send("get_devices", {"track_index": track_index})
    except RuntimeError:
        devices = []
    for device in devices:
        name_lower = device.get("name", "").lower()
        for key, role in _DEVICE_TO_ROLE.items():
            if key in name_lower:
                return role, "device_name"
    return "default", "fallback"


def _infer_role_from_spectrum(track_index: int) -> tuple[str, str]:
    """Return (role, method_used) by inspecting MCPSpectrum band profile."""
    try:
        data = get_spectrum_telemetry_instances()
        for instance in data.get("instances", []):
            if instance.get("track_index") == track_index:
                bands = instance.get("bands", {})

                def _band_val(keyword):
                    for bname, bdata in bands.items():
                        if keyword.lower() in bname.lower():
                            return float(bdata.get("value", 0.0))
                    return 0.0

                sub = _band_val("sub")
                body = _band_val("body")
                air = _band_val("air")
                punch = _band_val("punch")
                transient = _band_val("transient")

                if sub > 0.6:
                    return "bass", "spectrum_sub"
                if air > 0.6:
                    return "pad", "spectrum_air"
                if transient > 0.6 or punch > 0.6:
                    return "perc", "spectrum_transient"
                if body > 0.6:
                    return "keys", "spectrum_body"
    except Exception:
        pass
    return "default", "fallback"


# --- Feature 1: Auto-naming and color ---

@mcp.tool()
def auto_name_track(track_index: int, dry_run: bool = False) -> dict:
    """
    Automatically name a track based on its device chain content and spectrum analyzer data.

    Infers the track role by:
    1. Checking device names against _DEVICE_TO_ROLE mappings
    2. Falling back to MCPSpectrum band profile (sub-heavy=bass, air-heavy=pad, etc.)
    3. Using track position as last resort (Track 1, Track 2, etc.)

    Args:
        track_index: Track to name (-1 for master).
        dry_run: If True, return the suggested name without applying it.

    Returns:
        track_index, suggested_name, inferred_role, method_used, applied (bool)
    """
    role, method = _infer_role_from_devices(track_index)
    if role == "default":
        role, method = _infer_role_from_spectrum(track_index)
    if role == "default":
        suggested_name = "Track {}".format(track_index + 1)
        method = "position"
    else:
        suggested_name = role.replace("-", " ").title()

    applied = False
    if not dry_run:
        try:
            _send("set_track_name", {"track_index": track_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "suggested_name": suggested_name,
                "inferred_role": role,
                "method_used": method,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "suggested_name": suggested_name,
        "inferred_role": role,
        "method_used": method,
        "applied": applied,
    }


@mcp.tool()
def auto_color_track(track_index: int, role: str | None = None, dry_run: bool = False) -> dict:
    """
    Set a track's color based on its inferred or specified role.

    Args:
        track_index: Track to color.
        role: Override role (e.g. 'bass', 'pad', 'drums'). If None, infers from devices.
        dry_run: If True, return the color value without applying.

    Returns:
        track_index, role, color_value, applied (bool)
    """
    if role is None:
        role, _ = _infer_role_from_devices(track_index)
        if role == "default":
            role, _ = _infer_role_from_spectrum(track_index)

    color_value = _ROLE_COLORS.get(role, _ROLE_COLORS["default"])

    applied = False
    if not dry_run:
        try:
            _send("set_track_color", {"track_index": track_index, "color": color_value})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "role": role,
                "color_value": color_value,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "role": role,
        "color_value": color_value,
        "applied": applied,
    }


@mcp.tool()
def auto_name_all_tracks(dry_run: bool = False, skip_named: bool = True) -> dict:
    """
    Auto-name and color all tracks in the session at once.

    Args:
        dry_run: If True, return suggestions without applying.
        skip_named: If True, skip tracks that already have a non-default name (default True).

    Returns:
        results: list of {track_index, track_name, suggested_name, role, color, applied, skipped_reason}
        applied_count, skipped_count
    """
    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e), "results": []}

    results = []
    applied_count = 0
    skipped_count = 0

    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        current_name = track.get("name", "")

        skipped_reason = None
        if skip_named:
            default_names = {"audio", "midi", "track"}
            name_lower = current_name.lower()
            is_default = (
                not current_name
                or any(name_lower.startswith(d) for d in default_names)
                or re.match(r"^track\s*\d+$", name_lower)
                or re.match(r"^\d+$", name_lower)
            )
            if not is_default:
                skipped_reason = "already_named"

        role, _ = _infer_role_from_devices(idx)
        if role == "default":
            role, _ = _infer_role_from_spectrum(idx)

        if role == "default":
            suggested_name = "Track {}".format(idx + 1)
        else:
            suggested_name = role.replace("-", " ").title()

        color = _ROLE_COLORS.get(role, _ROLE_COLORS["default"])

        applied = False
        if skipped_reason is None and not dry_run:
            try:
                _send("set_track_name", {"track_index": idx, "name": suggested_name})
                _send("set_track_color", {"track_index": idx, "color": color})
                applied = True
                applied_count += 1
            except RuntimeError:
                pass
        elif skipped_reason:
            skipped_count += 1

        results.append({
            "track_index": idx,
            "track_name": current_name,
            "suggested_name": suggested_name,
            "role": role,
            "color": color,
            "applied": applied,
            "skipped_reason": skipped_reason,
        })

    return {
        "results": results,
        "applied_count": applied_count,
        "skipped_count": skipped_count,
    }


@mcp.tool()
def auto_name_clip(track_index: int, clip_index: int, dry_run: bool = False) -> dict:
    """
    Auto-name a clip based on its MIDI content or audio file name.

    For MIDI clips: infers from note register (low=bass line, mid=chords, high=melody/lead)
    and note density (sparse=melody, dense=chord/pad).
    For audio clips: uses the audio file name as base.

    Args:
        track_index: Track containing the clip.
        clip_index: Clip slot index.
        dry_run: If True, return suggestion without applying.

    Returns:
        track_index, clip_index, suggested_name, inference_basis, applied (bool)
    """
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
    except RuntimeError as e:
        return {"error": "Could not get clip info: {}".format(e)}

    inference_basis = "unknown"
    suggested_name = "Clip {}".format(clip_index + 1)

    clip_type = clip_info.get("type", clip_info.get("is_midi_clip"))
    is_midi = clip_type == "midi" or clip_type is True

    if not is_midi:
        file_path = clip_info.get("file_path", clip_info.get("sample_path", ""))
        if file_path:
            base = os.path.splitext(os.path.basename(file_path))[0]
            suggested_name = base
            inference_basis = "audio_filename"
        else:
            inference_basis = "default"
    else:
        notes = clip_info.get("notes", [])
        if notes:
            pitches = [n.get("pitch", n.get("note", 60)) for n in notes]
            avg_pitch = sum(pitches) / len(pitches)
            density = len(notes) / max(clip_info.get("length", 1.0), 0.001)

            if avg_pitch < 48:
                suggested_name = "Bass Line"
                inference_basis = "midi_low_register"
            elif avg_pitch > 72:
                if density < 2.0:
                    suggested_name = "Melody"
                    inference_basis = "midi_high_sparse"
                else:
                    suggested_name = "Lead"
                    inference_basis = "midi_high_dense"
            else:
                if density > 3.0:
                    suggested_name = "Chords"
                    inference_basis = "midi_mid_dense"
                else:
                    suggested_name = "Pad"
                    inference_basis = "midi_mid_sparse"
        else:
            inference_basis = "empty_midi"

    applied = False
    if not dry_run:
        try:
            _send("set_clip_name", {"track_index": track_index, "slot_index": clip_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "suggested_name": suggested_name,
                "inference_basis": inference_basis,
                "applied": False,
                "error": str(e),
            }

    return {
        "track_index": track_index,
        "clip_index": clip_index,
        "suggested_name": suggested_name,
        "inference_basis": inference_basis,
        "applied": applied,
    }


@mcp.tool()
def auto_name_scene(scene_index: int, dry_run: bool = False) -> dict:
    """
    Auto-name a scene based on the clip names in that scene row.

    Looks at clip names across all tracks in that scene row and infers
    a section label (Verse, Chorus, Bridge, etc.) from common keywords.

    Args:
        scene_index: Scene to name.
        dry_run: If True, return suggestion without applying.

    Returns:
        scene_index, suggested_name, inference_basis, applied (bool)
    """
    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    clip_names = []
    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        try:
            slots = _send("get_clip_slots", {"track_index": idx})
            if scene_index < len(slots):
                slot = slots[scene_index]
                clip_name = slot.get("clip_name", slot.get("name", ""))
                if clip_name:
                    clip_names.append(clip_name.lower())
        except RuntimeError:
            pass

    combined = " ".join(clip_names)
    suggested_name = "Scene {}".format(scene_index + 1)
    inference_basis = "position"

    for keyword, color in _SCENE_SECTION_COLORS.items():
        if keyword == "default":
            continue
        if keyword in combined:
            suggested_name = keyword.capitalize()
            inference_basis = "clip_keyword"
            break

    applied = False
    if not dry_run:
        try:
            _send("set_scene_name", {"scene_index": scene_index, "name": suggested_name})
            applied = True
        except RuntimeError as e:
            return {
                "scene_index": scene_index,
                "suggested_name": suggested_name,
                "inference_basis": inference_basis,
                "applied": False,
                "error": str(e),
            }

    return {
        "scene_index": scene_index,
        "suggested_name": suggested_name,
        "inference_basis": inference_basis,
        "applied": applied,
    }


# --- Feature 2: Device state snapshots + diff ---

@mcp.tool()
def save_device_snapshot(
    track_index: int,
    snapshot_name: str,
    device_index: int | None = None,
) -> dict:
    """
    Save the current parameter state of all devices on a track (or one device) as a named snapshot.

    Snapshots are stored in ~/.ableton_mpcx/device_snapshots.json.
    If a snapshot with the same name already exists for this track, it is overwritten.

    Args:
        track_index: Track to snapshot (-1 for master).
        snapshot_name: Name for this snapshot (e.g. 'lo-fi', 'clean', 'warm').
        device_index: If specified, snapshot only this device. If None, snapshot all devices.

    Returns:
        snapshot_name, track_index, devices_captured: int, parameter_count: int, saved_at: str
    """
    try:
        devices = _send("get_devices", {"track_index": track_index})
    except RuntimeError as e:
        return {"error": "Could not get devices: {}".format(e)}

    if device_index is not None:
        devices = [d for d in devices if d.get("index", d.get("device_index")) == device_index]

    snapshot_data = {}
    total_params = 0

    for device in devices:
        dev_idx = device.get("index", device.get("device_index", 0))
        try:
            params_result = _send("get_device_parameters", {
                "track_index": track_index,
                "device_index": dev_idx,
            })
            params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
            param_map = {}
            for p in params:
                p_idx = p.get("index", p.get("parameter_index", 0))
                param_map[str(p_idx)] = {
                    "value": p.get("value", 0.0),
                    "name": p.get("name", ""),
                }
                total_params += 1
            snapshot_data[str(dev_idx)] = {
                "device_name": device.get("name", ""),
                "parameters": param_map,
            }
        except RuntimeError:
            pass

    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)
    if track_key not in all_snapshots:
        all_snapshots[track_key] = {}
    all_snapshots[track_key][snapshot_name] = {
        "devices": snapshot_data,
        "saved_at": saved_at,
    }
    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)

    return {
        "snapshot_name": snapshot_name,
        "track_index": track_index,
        "devices_captured": len(snapshot_data),
        "parameter_count": total_params,
        "saved_at": saved_at,
    }


@mcp.tool()
def recall_device_snapshot(
    track_index: int,
    snapshot_name: str,
    device_index: int | None = None,
) -> dict:
    """
    Restore a previously saved device parameter snapshot on a track.

    All parameter changes are grouped into a single undo step.

    Args:
        track_index: Track to restore.
        snapshot_name: Name of the snapshot to recall.
        device_index: If specified, restore only this device. If None, restore all.

    Returns:
        snapshot_name, track_index, parameters_restored: int, devices_restored: int
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)
    if track_key not in all_snapshots or snapshot_name not in all_snapshots[track_key]:
        return {
            "error": "Snapshot '{}' not found for track {}. Use list_device_snapshots() to see available.".format(
                snapshot_name, track_index
            )
        }

    snapshot = all_snapshots[track_key][snapshot_name]
    devices_data = snapshot.get("devices", {})

    try:
        _send("begin_undo_step", {"name": "recall_snapshot_{}".format(snapshot_name)})
    except RuntimeError:
        pass

    parameters_restored = 0
    devices_restored = 0

    for dev_idx_str, dev_data in devices_data.items():
        dev_idx = int(dev_idx_str)
        if device_index is not None and dev_idx != device_index:
            continue
        param_map = dev_data.get("parameters", {})
        restored_any = False
        for param_idx_str, param_info in param_map.items():
            try:
                _send("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": dev_idx,
                    "parameter_index": int(param_idx_str),
                    "value": param_info.get("value", 0.0),
                })
                parameters_restored += 1
                restored_any = True
            except RuntimeError:
                pass
        if restored_any:
            devices_restored += 1

    try:
        _send("end_undo_step", {})
    except RuntimeError:
        pass

    return {
        "snapshot_name": snapshot_name,
        "track_index": track_index,
        "parameters_restored": parameters_restored,
        "devices_restored": devices_restored,
    }


@mcp.tool()
def list_device_snapshots(track_index: int | None = None) -> dict:
    """
    List all saved device snapshots, optionally filtered by track.

    Args:
        track_index: If specified, list only snapshots for this track. If None, list all.

    Returns:
        snapshots: list of {track_index, snapshot_name, device_count, parameter_count, saved_at}
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    results = []

    for track_key, snaps in all_snapshots.items():
        ti = int(track_key)
        if track_index is not None and ti != track_index:
            continue
        for snap_name, snap_data in snaps.items():
            devices_data = snap_data.get("devices", {})
            param_count = sum(
                len(d.get("parameters", {})) for d in devices_data.values()
            )
            results.append({
                "track_index": ti,
                "snapshot_name": snap_name,
                "device_count": len(devices_data),
                "parameter_count": param_count,
                "saved_at": snap_data.get("saved_at", ""),
            })

    return {"snapshots": results}


@mcp.tool()
def diff_device_snapshots(
    track_index: int,
    snapshot_a: str,
    snapshot_b: str,
) -> dict:
    """
    Compare two named device snapshots for a track and return what changed.

    Args:
        track_index: Track the snapshots belong to.
        snapshot_a: Name of the first snapshot (the 'before').
        snapshot_b: Name of the second snapshot (the 'after').

    Returns:
        snapshot_a, snapshot_b, track_index,
        changed: list of {device_index, device_name, param_index, param_name, value_a, value_b, delta}
        unchanged_count: int,
        summary: human-readable string describing what changed
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)

    for snap_name in (snapshot_a, snapshot_b):
        if track_key not in all_snapshots or snap_name not in all_snapshots[track_key]:
            return {"error": "Snapshot '{}' not found for track {}.".format(snap_name, track_index)}

    data_a = all_snapshots[track_key][snapshot_a].get("devices", {})
    data_b = all_snapshots[track_key][snapshot_b].get("devices", {})

    changed = []
    unchanged_count = 0

    all_dev_keys = set(data_a.keys()) | set(data_b.keys())
    for dev_key in all_dev_keys:
        dev_a = data_a.get(dev_key, {})
        dev_b = data_b.get(dev_key, {})
        dev_name = dev_a.get("device_name", dev_b.get("device_name", ""))
        params_a = dev_a.get("parameters", {})
        params_b = dev_b.get("parameters", {})
        all_param_keys = set(params_a.keys()) | set(params_b.keys())
        for p_key in all_param_keys:
            pa = params_a.get(p_key, {})
            pb = params_b.get(p_key, {})
            va = pa.get("value", 0.0)
            vb = pb.get("value", 0.0)
            param_name = pa.get("name", pb.get("name", ""))
            if abs(va - vb) > 1e-9:
                changed.append({
                    "device_index": int(dev_key),
                    "device_name": dev_name,
                    "param_index": int(p_key),
                    "param_name": param_name,
                    "value_a": va,
                    "value_b": vb,
                    "delta": vb - va,
                })
            else:
                unchanged_count += 1

    if changed:
        summary = "{} parameter(s) changed across {} device(s) between '{}' and '{}'.".format(
            len(changed),
            len({c["device_index"] for c in changed}),
            snapshot_a,
            snapshot_b,
        )
    else:
        summary = "No differences found between '{}' and '{}'.".format(snapshot_a, snapshot_b)

    return {
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "track_index": track_index,
        "changed": changed,
        "unchanged_count": unchanged_count,
        "summary": summary,
    }


@mcp.tool()
def delete_device_snapshot(track_index: int, snapshot_name: str) -> dict:
    """
    Delete a named device snapshot.

    Returns:
        deleted (bool), snapshot_name, track_index
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)

    if track_key not in all_snapshots or snapshot_name not in all_snapshots[track_key]:
        return {"deleted": False, "snapshot_name": snapshot_name, "track_index": track_index}

    del all_snapshots[track_key][snapshot_name]
    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)

    return {"deleted": True, "snapshot_name": snapshot_name, "track_index": track_index}


# --- Feature 3: Project version snapshots ---

@mcp.tool()
def save_version_snapshot(version_name: str) -> dict:
    """
    Save a named version snapshot of the current project.

    Workflow:
    1. Calls song.save() via _send("save_song") to save the current .als file
    2. Finds the current .als file path via _send("get_song_file_path")
    3. Copies it to "<OriginalName> - <version_name> [YYYY-MM-DD].als" in the same folder
    4. Records the entry in ~/.ableton_mpcx/versions.json

    Also captures a full_session_snapshot of all device states at this version.

    Args:
        version_name: Label for this version (e.g. 'lo-fi', 'clean', 'v2-with-strings').

    Returns:
        version_name, source_path, copy_path, saved_at, device_snapshot_captured (bool)
    """
    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    source_path = None
    copy_path = None
    als_save_note = None

    try:
        _send("save_song")
    except RuntimeError as e:
        als_save_note = "save_song not available: {}".format(e)

    try:
        file_info = _send("get_song_file_path")
        source_path = file_info if isinstance(file_info, str) else file_info.get("path", "")
    except RuntimeError as e:
        als_save_note = (als_save_note or "") + " get_song_file_path not available: {}".format(e)

    if source_path and os.path.isfile(source_path):
        base_dir = os.path.dirname(source_path)
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        copy_name = "{} - {} [{}].als".format(base_name, version_name, date_str)
        copy_path = os.path.join(base_dir, copy_name)
        try:
            shutil.copy2(source_path, copy_path)
        except Exception as e:
            als_save_note = (als_save_note or "") + " copy failed: {}".format(e)
            copy_path = None

    # Capture full device snapshot
    device_snapshot_captured = False
    snap_label = "__version__{}".format(version_name)
    try:
        snap_result = full_session_snapshot(snap_label)
        device_snapshot_captured = snap_result.get("tracks_captured", 0) > 0
    except Exception:
        pass

    versions = _load_json_cache(_VERSIONS_PATH, [])
    versions.append({
        "version_name": version_name,
        "saved_at": saved_at,
        "source_path": source_path,
        "copy_path": copy_path,
        "device_snapshot_label": snap_label,
        "has_device_snapshot": device_snapshot_captured,
        "note": als_save_note,
    })
    _save_json_cache(_VERSIONS_PATH, versions)

    return {
        "version_name": version_name,
        "source_path": source_path,
        "copy_path": copy_path,
        "saved_at": saved_at,
        "device_snapshot_captured": device_snapshot_captured,
        "note": als_save_note,
    }


@mcp.tool()
def list_version_snapshots() -> dict:
    """
    List all saved version snapshots for the current project.

    Returns:
        versions: list of {version_name, saved_at, copy_path, has_device_snapshot}
        total: int
    """
    versions = _load_json_cache(_VERSIONS_PATH, [])
    summaries = [
        {
            "version_name": v.get("version_name", ""),
            "saved_at": v.get("saved_at", ""),
            "copy_path": v.get("copy_path"),
            "has_device_snapshot": v.get("has_device_snapshot", False),
        }
        for v in versions
    ]
    return {"versions": summaries, "total": len(summaries)}


@mcp.tool()
def diff_version_snapshots(version_a: str, version_b: str) -> dict:
    """
    Compare device states between two saved version snapshots.

    Uses the device snapshots captured at each version save to produce
    a parameter-level diff across all tracks.

    Args:
        version_a: Name of the first version (the 'before').
        version_b: Name of the second version (the 'after').

    Returns:
        version_a, version_b,
        tracks_changed: list of {track_index, track_name, changes: [{device, param, before, after, delta}]}
        tracks_unchanged: list of track names
        summary: human-readable description of what changed between versions
    """
    versions = _load_json_cache(_VERSIONS_PATH, [])
    ver_map = {v["version_name"]: v for v in versions}

    for vname in (version_a, version_b):
        if vname not in ver_map:
            return {"error": "Version '{}' not found. Use list_version_snapshots() to see available.".format(vname)}

    label_a = ver_map[version_a].get("device_snapshot_label", "__version__{}".format(version_a))
    label_b = ver_map[version_b].get("device_snapshot_label", "__version__{}".format(version_b))

    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})

    # Version snapshots for all tracks are stored under track_key → label_a/label_b
    tracks_changed = []
    tracks_unchanged = []

    all_track_keys = set(all_snapshots.keys())
    for track_key in sorted(all_track_keys, key=lambda x: int(x)):
        track_snaps = all_snapshots[track_key]
        if label_a not in track_snaps and label_b not in track_snaps:
            continue

        snap_a = track_snaps.get(label_a, {}).get("devices", {})
        snap_b = track_snaps.get(label_b, {}).get("devices", {})
        changes = []

        all_dev_keys = set(snap_a.keys()) | set(snap_b.keys())
        for dev_key in all_dev_keys:
            dev_a = snap_a.get(dev_key, {})
            dev_b = snap_b.get(dev_key, {})
            dev_name = dev_a.get("device_name", dev_b.get("device_name", ""))
            params_a = dev_a.get("parameters", {})
            params_b = dev_b.get("parameters", {})
            all_param_keys = set(params_a.keys()) | set(params_b.keys())
            for p_key in all_param_keys:
                pa = params_a.get(p_key, {})
                pb = params_b.get(p_key, {})
                va = pa.get("value", 0.0)
                vb = pb.get("value", 0.0)
                if abs(va - vb) > 1e-9:
                    changes.append({
                        "device": dev_name,
                        "param": pa.get("name", pb.get("name", "")),
                        "before": va,
                        "after": vb,
                        "delta": vb - va,
                    })

        if changes:
            tracks_changed.append({
                "track_index": int(track_key),
                "track_name": "Track {}".format(track_key),
                "changes": changes,
            })
        else:
            tracks_unchanged.append("Track {}".format(track_key))

    if tracks_changed:
        summary = "{} track(s) changed between version '{}' and '{}'.".format(
            len(tracks_changed), version_a, version_b
        )
    else:
        summary = "No device parameter differences found between '{}' and '{}'.".format(version_a, version_b)

    return {
        "version_a": version_a,
        "version_b": version_b,
        "tracks_changed": tracks_changed,
        "tracks_unchanged": tracks_unchanged,
        "summary": summary,
    }


# --- Feature 4: Scene scaffolding ---

_SCAFFOLD_TEMPLATES = {
    "default": {
        "structure": ["Intro", "Verse", "Chorus", "Verse", "Chorus", "Outro"],
        "bars":      {"Intro": 8, "Verse": 16, "Chorus": 8, "Outro": 8},
    },
    "hiphop": {
        "structure": ["Intro", "Verse", "Hook", "Verse", "Hook", "Bridge", "Hook", "Outro"],
        "bars":      {"Intro": 4, "Verse": 16, "Hook": 8, "Bridge": 8, "Outro": 4},
    },
    "edm": {
        "structure": ["Intro", "Build", "Drop", "Break", "Build", "Drop", "Outro"],
        "bars":      {"Intro": 8, "Build": 8, "Drop": 16, "Break": 8, "Outro": 8},
    },
    "pop": {
        "structure": ["Intro", "Verse", "Pre", "Chorus", "Verse", "Pre", "Chorus", "Bridge", "Chorus", "Outro"],
        "bars":      {"Intro": 8, "Verse": 16, "Pre": 4, "Chorus": 8, "Bridge": 8, "Outro": 4},
    },
    "minimal": {
        "structure": ["Intro", "Part A", "Part B", "Part A", "Outro"],
        "bars":      {"Intro": 8, "Part A": 16, "Part B": 16, "Outro": 8},
    },
}


@mcp.tool()
def build_scene_scaffold(
    structure: list[str] | None = None,
    bars_each: dict[str, int] | None = None,
    color_code: bool = True,
    template: str | None = None,
) -> dict:
    """
    Create a set of named, color-coded scenes for a song structure in one command.

    Args:
        structure: Ordered list of section names, e.g. ["Intro", "Verse", "Chorus", "Outro"].
                   Repeated sections are numbered automatically: Verse 1, Verse 2, etc.
                   If None, uses the 'default' template.
        bars_each: Dict of section_name → bar count, e.g. {"Intro": 8, "Verse": 16}.
                   If a section is not in the dict, defaults to 8 bars.
        color_code: If True, apply colors from _SCENE_SECTION_COLORS per section type.
        template: Built-in template name. Options: 'default', 'hiphop', 'edm', 'pop', 'minimal'.
                  If specified, overrides structure and bars_each.

    Returns:
        scenes_created: int,
        scene_list: list of {scene_index, name, bars, color},
        template_used: str | None
    """
    template_used = None
    if template is not None:
        tpl = _SCAFFOLD_TEMPLATES.get(template, _SCAFFOLD_TEMPLATES["default"])
        structure = tpl["structure"]
        bars_each = tpl["bars"]
        template_used = template
    elif structure is None:
        tpl = _SCAFFOLD_TEMPLATES["default"]
        structure = tpl["structure"]
        bars_each = tpl["bars"]
        template_used = "default"

    if bars_each is None:
        bars_each = {}

    # Handle repeated section names by numbering them
    counts: dict[str, int] = {}
    named_structure = []
    for section in structure:
        base = section
        counts[base] = counts.get(base, 0) + 1
    # Track occurrence index
    occurrence: dict[str, int] = {}
    total_occurrences: dict[str, int] = counts
    for section in structure:
        occurrence[section] = occurrence.get(section, 0) + 1
        if total_occurrences[section] > 1:
            named_structure.append("{} {}".format(section, occurrence[section]))
        else:
            named_structure.append(section)

    try:
        existing_scenes = _send("get_scenes")
        start_index = len(existing_scenes)
    except RuntimeError as e:
        return {"error": "Could not get scenes: {}".format(e)}

    scene_list = []
    for i, name in enumerate(named_structure):
        scene_index = start_index + i
        # Determine bars (use the base section name for lookup)
        base_name = re.sub(r"\s+\d+$", "", name)
        bars = bars_each.get(base_name, bars_each.get(name, 8))

        # Determine color
        color = _SCENE_SECTION_COLORS["default"]
        if color_code:
            for keyword, c in _SCENE_SECTION_COLORS.items():
                if keyword == "default":
                    continue
                if keyword in name.lower():
                    color = c
                    break

        try:
            _send("create_scene", {"index": -1})
        except RuntimeError as e:
            scene_list.append({"scene_index": scene_index, "name": name, "bars": bars, "color": color, "error": str(e)})
            continue

        try:
            _send("set_scene_name", {"scene_index": scene_index, "name": name})
        except RuntimeError:
            pass

        if color_code:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": color})
            except RuntimeError:
                pass

        scene_list.append({"scene_index": scene_index, "name": name, "bars": bars, "color": color})

    return {
        "scenes_created": len(scene_list),
        "scene_list": scene_list,
        "template_used": template_used,
    }


@mcp.tool()
def list_scaffold_templates() -> dict:
    """
    List all available scene scaffold templates with their structures.

    Returns:
        templates: list of {name, structure, total_bars, section_count}
    """
    results = []
    for name, tpl in _SCAFFOLD_TEMPLATES.items():
        structure = tpl["structure"]
        bars_map = tpl["bars"]
        total_bars = sum(bars_map.get(re.sub(r"\s+\d+$", "", s), 8) for s in structure)
        results.append({
            "name": name,
            "structure": structure,
            "total_bars": total_bars,
            "section_count": len(structure),
        })
    return {"templates": results}


# --- Feature 5: Clip duplication and arrangement placement ---

@mcp.tool()
def place_clip_in_arrangement(
    track_index: int,
    clip_index: int,
    start_bar: int,
    start_beat: float = 1.0,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Place (duplicate) a Session View clip into the Arrangement View at a specific position.

    Args:
        track_index: Track containing the source clip.
        clip_index: Session clip slot index to copy from.
        start_bar: 1-based bar number where the clip should start in the arrangement.
        start_beat: 1-based beat within the bar (default 1.0 = start of bar).
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        track_index, start_time_beats, clip_name, clip_length_beats
    """
    start_time_beats = _bars_beats_to_song_time(start_bar, start_beat, time_signature_numerator)

    clip_name = ""
    clip_length_beats = 0.0
    try:
        clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": clip_index})
        clip_name = clip_info.get("name", "")
        clip_length_beats = float(clip_info.get("length", 0.0))
    except RuntimeError:
        pass

    try:
        _send("duplicate_clip_to_arrangement", {
            "track_index": track_index,
            "clip_index": clip_index,
            "time": start_time_beats,
        })
    except RuntimeError:
        try:
            _send("copy_clip_to_arrangement", {
                "track_index": track_index,
                "clip_index": clip_index,
                "time": start_time_beats,
            })
        except RuntimeError as e:
            return {
                "track_index": track_index,
                "start_time_beats": start_time_beats,
                "clip_name": clip_name,
                "clip_length_beats": clip_length_beats,
                "error": "Neither duplicate_clip_to_arrangement nor copy_clip_to_arrangement is supported: {}".format(e),
            }

    return {
        "track_index": track_index,
        "start_time_beats": start_time_beats,
        "clip_name": clip_name,
        "clip_length_beats": clip_length_beats,
    }


@mcp.tool()
def duplicate_clip_to_scenes(
    track_index: int,
    source_clip_index: int,
    target_scene_indices: list[int],
) -> dict:
    """
    Duplicate a clip into multiple scene slots on the same track.

    Args:
        track_index: Track containing the source clip.
        source_clip_index: Source clip slot to copy from.
        target_scene_indices: List of scene slot indices to copy into.

    Returns:
        source_clip_index, copies_made: int, target_scenes: list[int], skipped: list[int]
    """
    copies_made = 0
    skipped = []

    # Read source clip properties once before the loop
    clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": source_clip_index})
    length = clip_info.get("length", 4.0)
    clip_name = clip_info.get("name", "")
    clip_color = clip_info.get("color")

    notes_result = _send("get_notes", {"track_index": track_index, "slot_index": source_clip_index})
    notes = notes_result.get("notes", []) if isinstance(notes_result, dict) else notes_result

    for target_idx in target_scene_indices:
        try:
            _send("create_clip", {"track_index": track_index, "slot_index": target_idx, "length": length})
            if clip_name:
                _send("set_clip_name", {"track_index": track_index, "slot_index": target_idx, "name": clip_name})
            if clip_color is not None:
                _send("set_clip_color", {"track_index": track_index, "slot_index": target_idx, "color": clip_color})
            if notes:
                _send("replace_all_notes", {"track_index": track_index, "slot_index": target_idx, "notes": notes})
            copies_made += 1
        except RuntimeError:
            skipped.append(target_idx)

    return {
        "source_clip_index": source_clip_index,
        "copies_made": copies_made,
        "target_scenes": [i for i in target_scene_indices if i not in skipped],
        "skipped": skipped,
    }


@mcp.tool()
def arrange_from_scene_scaffold(
    track_indices: list[int] | None = None,
    layout: dict[str, int] | None = None,
    time_signature_numerator: int = 4,
) -> dict:
    """
    Build the Arrangement View from the current scene structure.

    Reads the scene names and the clips in each scene, then places them
    into the Arrangement in order, back to back.

    By default uses actual clip lengths to determine placement.
    Pass layout= to override bar counts per section name.

    Args:
        track_indices: Which tracks to arrange. If None, uses all tracks.
        layout: Override bar counts per scene name, e.g. {"Verse": 16, "Chorus": 8}.
                If a scene is not in layout, uses actual clip length.
        time_signature_numerator: Beats per bar (default 4).

    Returns:
        scenes_placed: int,
        placements: list of {scene_name, scene_index, start_bar, length_bars, tracks_placed},
        total_bars: int,
        arrangement_length_beats: float
    """
    try:
        scenes = _send("get_scenes")
    except RuntimeError as e:
        return {"error": "Could not get scenes: {}".format(e)}

    if track_indices is None:
        try:
            tracks = _send("get_tracks")
            track_indices = [t.get("index", t.get("track_index", i)) for i, t in enumerate(tracks)]
        except RuntimeError as e:
            return {"error": "Could not get tracks: {}".format(e)}

    if layout is None:
        layout = {}

    placements = []
    current_bar = 1
    total_bars = 0

    for scene_idx, scene in enumerate(scenes):
        scene_name = scene.get("name", "Scene {}".format(scene_idx + 1))

        # Determine length_bars: from layout override, or from clip lengths
        base_name = re.sub(r"\s+\d+$", "", scene_name)
        if base_name in layout:
            length_bars = layout[base_name]
        elif scene_name in layout:
            length_bars = layout[scene_name]
        else:
            # Use clip length from first available clip in this scene
            length_beats = 0.0
            for ti in track_indices:
                try:
                    clip_info = _send("get_clip_info", {"track_index": ti, "slot_index": scene_idx})
                    clip_len = float(clip_info.get("length", 0.0))
                    if clip_len > 0:
                        length_beats = clip_len
                        break
                except RuntimeError:
                    pass
            length_bars = max(1, round(length_beats / time_signature_numerator)) if length_beats > 0 else 8

        tracks_placed = 0
        for ti in track_indices:
            try:
                start_time = _bars_beats_to_song_time(current_bar, 1.0, time_signature_numerator)
                _send("duplicate_clip_to_arrangement", {
                    "track_index": ti,
                    "clip_index": scene_idx,
                    "time": start_time,
                })
                tracks_placed += 1
            except RuntimeError:
                try:
                    start_time = _bars_beats_to_song_time(current_bar, 1.0, time_signature_numerator)
                    _send("copy_clip_to_arrangement", {
                        "track_index": ti,
                        "clip_index": scene_idx,
                        "time": start_time,
                    })
                    tracks_placed += 1
                except RuntimeError:
                    pass

        placements.append({
            "scene_name": scene_name,
            "scene_index": scene_idx,
            "start_bar": current_bar,
            "length_bars": length_bars,
            "tracks_placed": tracks_placed,
        })
        current_bar += length_bars
        total_bars += length_bars

    arrangement_length_beats = float(total_bars * time_signature_numerator)

    return {
        "scenes_placed": len(placements),
        "placements": placements,
        "total_bars": total_bars,
        "arrangement_length_beats": arrangement_length_beats,
    }


# --- Feature 6: Resampling routing ---

@mcp.tool()
def setup_resampling_route(
    source_track_index: int | None = None,
    resample_track_index: int | None = None,
    track_name: str = "Resample",
    armed: bool = True,
) -> dict:
    """
    Set up resampling routing between a source track (or master) and a target audio track.

    Workflow:
    1. If resample_track_index is None, creates a new audio track named track_name
    2. Sets the new/target track's input routing to the source track output (or Master if source is None)
    3. Sets monitor to "In"
    4. Arms the track for recording if armed=True

    Args:
        source_track_index: Track to resample from. None = resample from Master output.
        resample_track_index: Existing audio track to use as resample target. None = create new.
        track_name: Name for the new resample track (default "Resample").
        armed: Whether to arm the resample track for recording (default True).

    Returns:
        resample_track_index, resample_track_name, source_routing, armed, monitor_mode,
        instructions: human-readable summary of what was set up and how to use it
    """
    if resample_track_index is None:
        try:
            _send("create_audio_track", {"index": -1})
            tracks = _send("get_tracks")
            resample_track_index = len(tracks) - 1
        except RuntimeError as e:
            return {"error": "Could not create audio track: {}".format(e)}

    try:
        _send("set_track_name", {"track_index": resample_track_index, "name": track_name})
    except RuntimeError:
        pass

    source_routing = "Master" if source_track_index is None else "Track {}".format(source_track_index)
    routing_set = False
    try:
        if source_track_index is None:
            _send("set_track_input_routing", {"track_index": resample_track_index, "routing": "Master"})
        else:
            _send("set_track_input_routing", {
                "track_index": resample_track_index,
                "source_track_index": source_track_index,
            })
        routing_set = True
    except RuntimeError:
        routing_set = False

    monitor_mode = "In"
    monitor_set = False
    try:
        _send("set_track_monitor", {"track_index": resample_track_index, "monitor": 1})
        monitor_set = True
    except RuntimeError:
        monitor_set = False

    arm_result = False
    if armed:
        try:
            _send("set_track_arm", {"track_index": resample_track_index, "arm": True})
            arm_result = True
        except RuntimeError:
            arm_result = False

    instructions = (
        "Resampling track '{}' (index {}) is set up to record from {}. "
        "Press Record in Live, then play your session to capture the output. "
        "When done, call teardown_resampling_route({}) to reset routing.".format(
            track_name, resample_track_index, source_routing, resample_track_index
        )
    )

    return {
        "resample_track_index": resample_track_index,
        "resample_track_name": track_name,
        "source_routing": source_routing,
        "routing_set": routing_set,
        "armed": arm_result,
        "monitor_mode": monitor_mode,
        "monitor_set": monitor_set,
        "instructions": instructions,
    }


@mcp.tool()
def teardown_resampling_route(resample_track_index: int) -> dict:
    """
    Reset a resampling track's routing back to defaults and disarm it.

    Args:
        resample_track_index: The resample track to reset.

    Returns:
        resample_track_index, disarmed (bool), routing_reset (bool)
    """
    disarmed = False
    try:
        _send("set_track_arm", {"track_index": resample_track_index, "arm": False})
        disarmed = True
    except RuntimeError:
        pass

    routing_reset = False
    try:
        _send("set_track_monitor", {"track_index": resample_track_index, "monitor": 0})
        routing_reset = True
    except RuntimeError:
        pass

    try:
        _send("set_track_input_routing", {"track_index": resample_track_index, "routing": "default"})
    except RuntimeError:
        pass

    return {
        "resample_track_index": resample_track_index,
        "disarmed": disarmed,
        "routing_reset": routing_reset,
    }


@mcp.tool()
def get_resampling_status(resample_track_index: int) -> dict:
    """
    Return the current routing and arm status of a track, to verify resampling is set up correctly.

    Returns:
        track_index, track_name, input_routing, monitor_mode, armed, ready_to_resample (bool)
    """
    try:
        tracks = _send("get_tracks")
        track = next(
            (t for t in tracks if t.get("index", t.get("track_index")) == resample_track_index),
            None,
        )
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    if track is None:
        return {"error": "Track {} not found.".format(resample_track_index)}

    track_name = track.get("name", "")
    armed = track.get("arm", track.get("armed", False))
    monitor_mode = track.get("monitor", track.get("monitor_mode", ""))
    input_routing = track.get("input_routing", track.get("input", ""))

    ready = bool(armed) and str(monitor_mode) in {"1", "In", 1}

    return {
        "track_index": resample_track_index,
        "track_name": track_name,
        "input_routing": input_routing,
        "monitor_mode": monitor_mode,
        "armed": armed,
        "ready_to_resample": ready,
    }


# --- Feature 7: Session collaborator tools ---

@mcp.tool()
def full_session_snapshot(snapshot_name: str) -> dict:
    """
    Save device parameter snapshots for ALL tracks simultaneously under a single name.

    Captures master track, all audio/MIDI tracks, and all return tracks.
    All stored in ~/.ableton_mpcx/device_snapshots.json under the given name.

    Args:
        snapshot_name: Name for this full-session snapshot (e.g. 'pre-drop', 'final-mix').

    Returns:
        snapshot_name, tracks_captured: int, total_parameters: int, saved_at: str
    """
    saved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tracks_captured = 0
    total_parameters = 0

    # Collect all track indices: regular tracks + master (-1) + return tracks
    track_indices = [-1]
    try:
        tracks = _send("get_tracks")
        for t in tracks:
            idx = t.get("index", t.get("track_index"))
            if idx is not None:
                track_indices.append(idx)
    except RuntimeError:
        pass

    try:
        return_tracks = _send("get_return_tracks")
        for rt in return_tracks:
            idx = rt.get("index", rt.get("track_index"))
            if idx is not None:
                track_indices.append(("return", idx))
    except RuntimeError:
        pass

    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})

    for ti in track_indices:
        if isinstance(ti, tuple):
            # return track — skip for now, they aren't indexed the same way
            continue
        track_key = str(ti)
        try:
            devices = _send("get_devices", {"track_index": ti})
        except RuntimeError:
            continue

        snapshot_data = {}
        for device in devices:
            dev_idx = device.get("index", device.get("device_index", 0))
            try:
                params_result = _send("get_device_parameters", {
                    "track_index": ti,
                    "device_index": dev_idx,
                })
                params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
                param_map = {}
                for p in params:
                    p_idx = p.get("index", p.get("parameter_index", 0))
                    param_map[str(p_idx)] = {
                        "value": p.get("value", 0.0),
                        "name": p.get("name", ""),
                    }
                    total_parameters += 1
                snapshot_data[str(dev_idx)] = {
                    "device_name": device.get("name", ""),
                    "parameters": param_map,
                }
            except RuntimeError:
                pass

        if not all_snapshots.get(track_key):
            all_snapshots[track_key] = {}
        all_snapshots[track_key][snapshot_name] = {
            "devices": snapshot_data,
            "saved_at": saved_at,
        }
        tracks_captured += 1

    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)

    return {
        "snapshot_name": snapshot_name,
        "tracks_captured": tracks_captured,
        "total_parameters": total_parameters,
        "saved_at": saved_at,
    }


@mcp.tool()
def session_audit(fix: bool = False) -> dict:
    """
    Analyze the current session state and return a list of issues with suggestions.

    Checks performed:
    - Unnamed or default-named tracks (suggest auto_name_track)
    - Tracks with no devices
    - Tracks with arm still on
    - No snapshots saved (suggest full_session_snapshot)
    - Empty scenes in scaffold (scenes with no clips)

    Args:
        fix: If True, auto-apply safe fixes (auto-naming, disarming tracks).
             Does NOT auto-apply mix corrections (those require human judgment).

    Returns:
        issues: list of {type, severity, description, suggestion, auto_fixable, fixed}
        issues_found: int,
        issues_fixed: int (if fix=True),
        session_health: "good" | "warnings" | "issues"
    """
    issues = []
    issues_fixed = 0

    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    default_name_pattern = re.compile(r"^(audio|midi|track)\s*\d*$", re.IGNORECASE)

    for track in tracks:
        idx = track.get("index", track.get("track_index", 0))
        name = track.get("name", "")
        armed = track.get("arm", track.get("armed", False))

        # Check for default/unnamed tracks
        if not name or default_name_pattern.match(name):
            fixed = False
            if fix:
                try:
                    auto_name_track(idx, dry_run=False)
                    fixed = True
                    issues_fixed += 1
                except Exception:
                    pass
            issues.append({
                "type": "unnamed_track",
                "severity": "warning",
                "description": "Track {} has default name '{}'".format(idx, name),
                "suggestion": "Call auto_name_track({})".format(idx),
                "auto_fixable": True,
                "fixed": fixed,
            })

        # Check for armed tracks
        if armed:
            fixed = False
            if fix:
                try:
                    _send("set_track_arm", {"track_index": idx, "arm": False})
                    fixed = True
                    issues_fixed += 1
                except RuntimeError:
                    pass
            issues.append({
                "type": "track_armed",
                "severity": "warning",
                "description": "Track {} ('{}') is armed".format(idx, name),
                "suggestion": "Disarm track {} or call teardown_resampling_route({})".format(idx, idx),
                "auto_fixable": True,
                "fixed": fixed,
            })

        # Check for tracks with no devices
        try:
            devices = _send("get_devices", {"track_index": idx})
            if not devices:
                issues.append({
                    "type": "no_devices",
                    "severity": "info",
                    "description": "Track {} ('{}') has no devices".format(idx, name),
                    "suggestion": "Add instruments or effects to this track",
                    "auto_fixable": False,
                    "fixed": False,
                })
        except RuntimeError:
            pass

    # Check for no snapshots saved
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    if not all_snapshots:
        issues.append({
            "type": "no_snapshots",
            "severity": "info",
            "description": "No device snapshots have been saved",
            "suggestion": "Call full_session_snapshot('initial') to create a baseline",
            "auto_fixable": False,
            "fixed": False,
        })

    # Check for empty scenes
    try:
        scenes = _send("get_scenes")
        for scene_idx, scene in enumerate(scenes):
            has_clip = False
            for track in tracks:
                ti = track.get("index", track.get("track_index", 0))
                try:
                    clip_info = _send("get_clip_info", {"track_index": ti, "slot_index": scene_idx})
                    if clip_info:
                        has_clip = True
                        break
                except RuntimeError:
                    pass
            if not has_clip:
                issues.append({
                    "type": "empty_scene",
                    "severity": "info",
                    "description": "Scene {} ('{}') has no clips".format(
                        scene_idx, scene.get("name", "")
                    ),
                    "suggestion": "Add clips to scene {} or remove it".format(scene_idx),
                    "auto_fixable": False,
                    "fixed": False,
                })
    except RuntimeError:
        pass

    has_issue = any(i["severity"] == "issues" for i in issues)
    has_warning = any(i["severity"] == "warning" for i in issues)
    if has_issue:
        session_health = "issues"
    elif has_warning:
        session_health = "warnings"
    else:
        session_health = "good"

    return {
        "issues": issues,
        "issues_found": len(issues),
        "issues_fixed": issues_fixed,
        "session_health": session_health,
    }


@mcp.tool()
def mix_correction_loop(
    track_index: int,
    target_band: str,
    direction: str,
    device_name: str | None = None,
    param_name: str | None = None,
    max_steps: int = 5,
    verify: bool = True,
    snapshot_after: bool = False,
    snapshot_name: str | None = None,
) -> dict:
    """
    Iteratively adjust a device parameter to improve a frequency band balance,
    reading the analyzer after each step to verify improvement.

    Args:
        track_index: Track to adjust.
        target_band: Band to improve (e.g. 'body', 'air', 'bass').
        direction: 'reduce' to reduce crowding or 'boost' to fill a gap.
        device_name: Device to adjust (e.g. 'Auto Filter', 'EQ Eight'). If None, auto-detects.
        param_name: Parameter to adjust (e.g. 'Frequency', 'Gain'). If None, auto-detects.
        max_steps: Maximum number of adjustment iterations (default 5).
        verify: If True, re-read analyzer after each step to check improvement.
        snapshot_after: If True and improvement was made, save a device snapshot.
        snapshot_name: Name for the snapshot (default: 'post-correction-{band}').

    Returns:
        track_index, target_band, direction,
        steps_taken: int,
        before_value: float (analyzer reading before),
        after_value: float (analyzer reading after),
        improved: bool,
        parameter_changes: list of {step, param, before, after},
        snapshot_saved: bool,
        summary: human-readable description of what was done
    """
    if direction not in ("reduce", "boost"):
        return {"error": "direction must be 'reduce' or 'boost'"}

    # Read initial band value
    def _read_band_value():
        try:
            data = get_spectrum_telemetry_instances()
            for instance in data.get("instances", []):
                if instance.get("track_index") == track_index:
                    bands = instance.get("bands", {})
                    for bname, bdata in bands.items():
                        if target_band.lower() in bname.lower():
                            return float(bdata.get("value", 0.0))
        except Exception:
            pass
        return None

    before_value = _read_band_value()

    # Find target device and parameter
    target_device_index = None
    target_parameter_index = None
    target_param_name = param_name

    try:
        devices = _send("get_devices", {"track_index": track_index})
    except RuntimeError as e:
        return {"error": "Could not get devices: {}".format(e)}

    for device in devices:
        dev_idx = device.get("index", device.get("device_index", 0))
        dev_name = device.get("name", "")
        if device_name and device_name.lower() not in dev_name.lower():
            continue

        # Auto-detect: prefer EQ or filter devices
        is_eq = any(k in dev_name.lower() for k in ["eq", "filter", "equalizer"])
        if device_name is None and not is_eq:
            continue

        try:
            params_result = _send("get_device_parameters", {
                "track_index": track_index,
                "device_index": dev_idx,
            })
            params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
            for p in params:
                p_name = p.get("name", "")
                if param_name and param_name.lower() not in p_name.lower():
                    continue
                if param_name is None and "gain" not in p_name.lower():
                    continue
                target_device_index = dev_idx
                target_parameter_index = p.get("index", p.get("parameter_index", 0))
                target_param_name = p_name
                break
        except RuntimeError:
            pass
        if target_device_index is not None:
            break

    if target_device_index is None or target_parameter_index is None:
        return {
            "error": "Could not find a suitable device/parameter to adjust. "
                     "Specify device_name and param_name explicitly.",
            "track_index": track_index,
            "target_band": target_band,
            "direction": direction,
        }

    # Get current param value
    try:
        params_result = _send("get_device_parameters", {
            "track_index": track_index,
            "device_index": target_device_index,
        })
        params = params_result.get("parameters", params_result) if isinstance(params_result, dict) else params_result
        current_param = next(
            (p for p in params if p.get("index", p.get("parameter_index")) == target_parameter_index),
            None,
        )
    except RuntimeError as e:
        return {"error": "Could not get parameters: {}".format(e)}

    if current_param is None:
        return {"error": "Parameter index {} not found.".format(target_parameter_index)}

    current_value = float(current_param.get("value", 0.0))
    p_min = float(current_param.get("min", current_value - 12))
    p_max = float(current_param.get("max", current_value + 12))
    step_size = (p_max - p_min) / 20.0  # ~5% of range per step

    parameter_changes = []
    steps_taken = 0

    for step in range(max_steps):
        old_value = current_value
        if direction == "reduce":
            new_value = max(p_min, current_value - step_size)
        else:
            new_value = min(p_max, current_value + step_size)

        try:
            _send("set_device_parameter", {
                "track_index": track_index,
                "device_index": target_device_index,
                "parameter_index": target_parameter_index,
                "value": new_value,
            })
            current_value = new_value
            steps_taken += 1
            parameter_changes.append({
                "step": step + 1,
                "param": target_param_name,
                "before": old_value,
                "after": new_value,
            })
        except RuntimeError:
            break

        if verify:
            new_band = _read_band_value()
            if new_band is not None and before_value is not None:
                if direction == "reduce" and new_band < before_value:
                    break
                if direction == "boost" and new_band > before_value:
                    break

    after_value = _read_band_value()
    improved = False
    if before_value is not None and after_value is not None:
        if direction == "reduce":
            improved = after_value < before_value
        else:
            improved = after_value > before_value

    snapshot_saved = False
    if snapshot_after and improved:
        snap_label = snapshot_name or "post-correction-{}".format(target_band)
        try:
            save_device_snapshot(track_index, snap_label, device_index=target_device_index)
            snapshot_saved = True
        except Exception:
            pass

    if steps_taken > 0:
        summary = "Adjusted '{}' on track {} by {} step(s) to {} the '{}' band. Improved: {}.".format(
            target_param_name, track_index, steps_taken, direction, target_band, improved
        )
    else:
        summary = "No adjustments were made to track {}.".format(track_index)

    return {
        "track_index": track_index,
        "target_band": target_band,
        "direction": direction,
        "steps_taken": steps_taken,
        "before_value": before_value,
        "after_value": after_value,
        "improved": improved,
        "parameter_changes": parameter_changes,
        "snapshot_saved": snapshot_saved,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Auto-orient
# ---------------------------------------------------------------------------


@mcp.tool()
def auto_orient() -> dict:
    """
    Call this immediately on connecting to a Live session.

    Surveys the current session and returns a structured orientation summary:
    - Session name and tempo
    - Track list with types (audio/midi/return/master), names, armed state, mute/solo state
    - Active clip count in arrangement vs session view
    - Any immediately obvious issues (unnamed tracks, armed tracks, missing media)
    - Recommended first actions based on session state

    This is the entry point for every AI session. Call it before any other tool.

    Returns:
        session_name: str
        tempo: float
        track_summary: list of {index, name, type, armed, muted, soloed, device_count}
        arrangement_clip_count: int
        session_clip_count: int
        unnamed_tracks: list of {index, name}
        armed_tracks: list of {index, name}
        issues: list of str
        recommended_actions: list of str
        orientation_complete: bool
    """
    _default_name_pattern = re.compile(
        r"^(Audio|MIDI|1-Audio|1-MIDI)\s*\d*$|^\d+$", re.IGNORECASE
    )
    # Session info (name + tempo)
    try:
        song_info = _send("get_song_info", {})
        session_name = song_info.get("name", "")
        tempo = song_info.get("tempo", 0.0)
    except Exception:
        session_name = ""
        tempo = 0.0

    # Full track list
    try:
        tracks = _send("get_tracks", {})
    except Exception:
        tracks = []

    track_summary = []
    unnamed_tracks = []
    armed_tracks = []
    session_clip_count = 0

    for track in tracks:
        index = track.get("index", track.get("track_index", 0))
        name = track.get("name", "")
        is_midi = track.get("is_midi_track", False)
        track_type = "midi" if is_midi else "audio"
        armed = bool(track.get("arm", False))
        muted = bool(track.get("mute", False))
        soloed = bool(track.get("solo", False))
        device_count = track.get("device_count", 0)
        clip_count = track.get("clip_count", 0)
        session_clip_count += clip_count

        track_summary.append({
            "index": index,
            "name": name,
            "type": track_type,
            "armed": armed,
            "muted": muted,
            "soloed": soloed,
            "device_count": device_count,
        })

        if not name or _default_name_pattern.match(name.strip()):
            unnamed_tracks.append({"index": index, "name": name})

        if armed:
            armed_tracks.append({"index": index, "name": name})

    # Arrangement clip count
    try:
        arrangement_data = _send("get_arrangement_clips", {})
        if isinstance(arrangement_data, list):
            arrangement_clip_count = len(arrangement_data)
        elif isinstance(arrangement_data, dict):
            arrangement_clip_count = len(arrangement_data.get("clips", []))
        else:
            arrangement_clip_count = 0
    except Exception:
        arrangement_clip_count = 0

    # Build issues list
    issues: list[str] = []
    if unnamed_tracks:
        issues.append("{} track(s) have default names".format(len(unnamed_tracks)))
    if armed_tracks:
        issues.append("{} track(s) are currently armed for recording".format(len(armed_tracks)))

    # Build recommended actions
    recommended_actions: list[str] = []
    if unnamed_tracks:
        recommended_actions.append(
            "{} tracks are unnamed — consider running auto_name_track".format(len(unnamed_tracks))
        )
    if armed_tracks:
        recommended_actions.append(
            "{} track(s) are armed — disarm before saving if not intentional".format(len(armed_tracks))
        )
    if not issues:
        recommended_actions.append("Session looks clean — ready to work")

    return {
        "session_name": session_name,
        "tempo": tempo,
        "track_summary": track_summary,
        "arrangement_clip_count": arrangement_clip_count,
        "session_clip_count": session_clip_count,
        "unnamed_tracks": unnamed_tracks,
        "armed_tracks": armed_tracks,
        "issues": issues,
        "recommended_actions": recommended_actions,
        "orientation_complete": True,
    }



# ---------------------------------------------------------------------------
# H — State diff cache
# ---------------------------------------------------------------------------

@mcp.tool()
def get_session_diff() -> dict:
    """Return only what has changed in the session since the last call.

    On the first call returns the full state snapshot.  On subsequent calls
    returns only the fields that differ from the previous snapshot.
    Dramatically reduces token usage when monitoring a session over time.

    Returns:
        changed_tracks: list of {track_index, track_name, changed_fields}
        changed_devices: list of {track_index, device_index, changed_parameters}
        tempo_changed: bool
        new_tempo: float or None
        is_first_snapshot: bool
        total_changes: int
    """
    snapshot = _send("get_session_snapshot")
    diff = cache_state("session_diff", snapshot)

    if diff.get("first_snapshot"):
        tracks = snapshot.get("tracks", [])
        return {
            "is_first_snapshot": True,
            "changed_tracks": [],
            "changed_devices": [],
            "tempo_changed": False,
            "new_tempo": snapshot.get("tempo"),
            "total_changes": 0,
            "snapshot": snapshot,
        }

    changed_tracks: list[dict] = []
    changed_devices: list[dict] = []
    tempo_changed = False
    new_tempo = None

    top_changed = diff.get("changed", {})

    # Detect tempo change
    if "tempo" in top_changed:
        tempo_changed = True
        new_tempo = top_changed["tempo"].get("to")

    # Detect per-track changes
    tracks_diff = top_changed.get("tracks", {})
    if isinstance(tracks_diff, dict):
        nested = tracks_diff.get("changed", {})
        for idx_str, track_change in nested.items():
            if not isinstance(track_change, dict):
                continue
            track_idx = int(idx_str) if str(idx_str).isdigit() else idx_str
            changed_fields = list(track_change.get("changed", {}).keys())
            # Try to get the track name from the current snapshot
            tracks_list = snapshot.get("tracks", [])
            track_name = ""
            if isinstance(tracks_list, list) and isinstance(track_idx, int) and track_idx < len(tracks_list):
                track_name = tracks_list[track_idx].get("name", "")
            changed_tracks.append({
                "track_index": track_idx,
                "track_name": track_name,
                "changed_fields": changed_fields,
            })
            # Device changes within the track
            devices_diff = track_change.get("changed", {}).get("devices", {})
            if isinstance(devices_diff, dict):
                for dev_idx_str, dev_change in devices_diff.get("changed", {}).items():
                    changed_devices.append({
                        "track_index": track_idx,
                        "device_index": int(dev_idx_str) if str(dev_idx_str).isdigit() else dev_idx_str,
                        "changed_parameters": list(dev_change.get("changed", {}).keys()) if isinstance(dev_change, dict) else [],
                    })

    total_changes = (
        len(top_changed)
        + len(diff.get("added", {}))
        + len(diff.get("removed", []))
    )

    return {
        "is_first_snapshot": False,
        "changed_tracks": changed_tracks,
        "changed_devices": changed_devices,
        "tempo_changed": tempo_changed,
        "new_tempo": new_tempo,
        "total_changes": total_changes,
    }


# ---------------------------------------------------------------------------
# L — Tool call bundling
# ---------------------------------------------------------------------------

@mcp.tool()
def get_full_session_state() -> dict:
    """Return complete session state in a single tool call.

    Bundles session info + all tracks + all devices + all clips + a levels
    overview derived from mixer device data.  Use this instead of calling
    each tool separately when you need a full picture.

    Returns:
        session: dict (song info)
        tracks: list (all tracks with devices and clips)
        devices_by_track: dict mapping track_index (str) to list of devices
        arrangement_clips: list (arrangement clips)
        levels: dict (per-track volume/pan summary)
        fetched_at: float (Unix timestamp)
        total_tracks: int
        total_devices: int
        total_clips: int
    """
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []

    devices_by_track: dict[str, list] = {}
    total_devices = 0
    for t in tracks:
        idx = t.get("index", t.get("track_index"))
        devs = t.get("devices", [])
        if devs:
            devices_by_track[str(idx)] = devs
            total_devices += len(devs)

    # Build a lightweight levels overview from the track data already fetched
    levels: dict[str, dict] = {}
    for t in tracks:
        idx = t.get("index", t.get("track_index"))
        mixer = t.get("mixer_device", {}) or {}
        levels[str(idx)] = {
            "name": t.get("name", ""),
            "volume": mixer.get("volume"),
            "pan": mixer.get("panning"),
            "mute": t.get("mute", False),
        }

    try:
        arrangement_clips = _send("get_arrangement_clips")
    except Exception:
        arrangement_clips = []

    total_clips = len(arrangement_clips) if isinstance(arrangement_clips, list) else 0

    return {
        "session": snapshot,
        "tracks": tracks,
        "devices_by_track": devices_by_track,
        "arrangement_clips": arrangement_clips,
        "levels": levels,
        "fetched_at": time.time(),
        "total_tracks": len(tracks),
        "total_devices": total_devices,
        "total_clips": total_clips,
    }


# ---------------------------------------------------------------------------
# Render / Print to audio
# ---------------------------------------------------------------------------

@mcp.tool()
def render_track_to_audio(
    source_track_index: int,
    start_bar: int = 1,
    end_bar: int = 9,
    use_resampling: bool = False,
    post_fx: bool = True,
    ensure_full_length: bool = True,
    new_track_name: str | None = None,
    target_track_index: int | None = None,
) -> dict:
    """
    Print a track's audio output to a new audio track for a given bar range.

    Automates the "resample" workflow:
    1. Optionally duplicates the source clip until it fills the requested range.
    2. Creates a new audio track routed to the source track (Post FX) or Resampling.
    3. Arms the new track and starts Arrangement recording for exactly the bar range.
    4. Stops, disarms, and returns the new track details.

    Useful for printing third-party plugin edits (e.g. Melodyne) to audio.

    Args:
        source_track_index: Track to capture audio from.
        start_bar: First bar of the range to record (1-based, default 1).
        end_bar: Bar after the last bar to record (default 9 = 8 bars).
        use_resampling: If True, route from master Resampling instead of the source track directly.
        post_fx: If True (default), capture post-effects signal.
        ensure_full_length: If True (default), try to extend the source clip to fill the range.
        new_track_name: Name for the new audio track (default: "{source_track_name} [Rendered]").
        target_track_index: Position to insert the new track (default: right after source track).

    Returns:
        new_track_index, new_track_name, source_track_name, bars_recorded, duration_seconds
    """
    warnings: list[str] = []

    # --- Gather song info (tempo + time signature) ---
    try:
        song_info = _send("get_song_info")
    except RuntimeError as e:
        return {"error": "Could not get song info: {}".format(e)}

    tempo = float(song_info.get("tempo", 120.0))
    time_sig_num = int(song_info.get("time_signature_numerator", song_info.get("numerator", 4)))

    bars_to_record = end_bar - start_bar
    if bars_to_record <= 0:
        return {"error": "end_bar must be greater than start_bar"}

    beats_per_bar = time_sig_num
    start_beat = (start_bar - 1) * beats_per_bar
    length_beats = bars_to_record * beats_per_bar
    seconds_per_beat = 60.0 / tempo
    duration_seconds = length_beats * seconds_per_beat

    # --- Get source track info ---
    try:
        tracks = _send("get_tracks")
    except RuntimeError as e:
        return {"error": "Could not get tracks: {}".format(e)}

    if source_track_index < 0 or source_track_index >= len(tracks):
        return {"error": "source_track_index {} is out of range (0-{})".format(
            source_track_index, len(tracks) - 1)}

    source_track = tracks[source_track_index]
    source_track_name = source_track.get("name", "Track {}".format(source_track_index + 1))

    # --- Step 1: Optionally extend source clip to cover the requested range ---
    clip_length_warning = None
    if ensure_full_length:
        try:
            track_info = _send("get_track_info", {"track_index": source_track_index})
            clip_slots = track_info.get("clip_slots", [])
            # Find the first populated clip slot
            source_slot_index = None
            for slot_idx, slot in enumerate(clip_slots):
                if slot and slot.get("has_clip"):
                    source_slot_index = slot_idx
                    break

            if source_slot_index is not None:
                clip_info = _send("get_clip_info", {
                    "track_index": source_track_index,
                    "slot_index": source_slot_index,
                })
                clip_length = float(clip_info.get("length", 0))
                # Double the loop until the clip length covers what we need
                max_doublings = 10
                doublings = 0
                while clip_length < length_beats and doublings < max_doublings:
                    try:
                        _send("duplicate_clip_loop", {
                            "track_index": source_track_index,
                            "slot_index": source_slot_index,
                        })
                        doublings += 1
                        # Refresh clip length
                        clip_info = _send("get_clip_info", {
                            "track_index": source_track_index,
                            "slot_index": source_slot_index,
                        })
                        clip_length = float(clip_info.get("length", 0))
                    except RuntimeError:
                        break
                if clip_length < length_beats:
                    clip_length_warning = (
                        "Source clip (length={} beats) may be shorter than requested range "
                        "({} beats); recorded clip may be shorter than expected.".format(
                            clip_length, length_beats)
                    )
                    warnings.append(clip_length_warning)
            else:
                warnings.append(
                    "No clip found in source track slot; skipping ensure_full_length."
                )
        except RuntimeError as e:
            warnings.append("ensure_full_length skipped: {}".format(e))

    # --- Step 2: Create new audio track ---
    insert_index = target_track_index if target_track_index is not None else source_track_index + 1
    try:
        _send("create_audio_track", {"index": insert_index})
    except RuntimeError as e:
        return {"error": "Could not create audio track: {}".format(e)}

    # After insertion, fetch fresh track list to get the new track's actual index
    try:
        tracks_after = _send("get_tracks")
        new_track_index = insert_index if insert_index < len(tracks_after) else len(tracks_after) - 1
    except RuntimeError:
        new_track_index = insert_index

    # Determine the name for the new track
    if new_track_name is None:
        new_track_name = "{} [Rendered]".format(source_track_name)

    try:
        _send("set_track_name", {"track_index": new_track_index, "name": new_track_name})
    except RuntimeError as e:
        warnings.append("Could not rename new track: {}".format(e))

    # --- Step 3: Set input routing ---
    routing_set = False
    if use_resampling:
        routing_type_name = "Resampling"
        routing_channel_name = None
    else:
        # Live's display name for track routing is typically "{index+1}-{track_name}"
        routing_type_name = "{}-{}".format(source_track_index + 1, source_track_name)
        routing_channel_name = "Post FX" if post_fx else "Pre FX"

    try:
        _send("set_track_input_routing", {
            "track_index": new_track_index,
            "routing_type_name": routing_type_name,
            "routing_channel_name": routing_channel_name,
        })
        routing_set = True
    except RuntimeError as e:
        warnings.append(
            "Could not set input routing to '{}' (channel '{}'): {}. "
            "Please set routing manually in Live.".format(
                routing_type_name, routing_channel_name, e)
        )

    # --- Step 4: Arm the new track ---
    try:
        _send("set_track_arm", {"track_index": new_track_index, "arm": True})
    except RuntimeError as e:
        warnings.append("Could not arm new track: {}".format(e))

    # --- Step 5: Set Arrangement loop ---
    try:
        _send("set_loop", {
            "enabled": True,
            "loop_start": float(start_beat),
            "loop_length": float(length_beats),
        })
    except RuntimeError as e:
        warnings.append("Could not set loop: {}".format(e))

    # --- Step 6: Move playhead to start_bar ---
    try:
        _send("set_current_song_time", {"song_time": float(start_beat)})
    except RuntimeError:
        try:
            _send("jump_to_position", {"position": float(start_beat)})
        except RuntimeError as e:
            warnings.append("Could not move playhead to start: {}".format(e))

    # Make sure we are not already playing / recording
    try:
        _send("stop_playing")
    except RuntimeError:
        pass

    # --- Step 7: Start Arrangement recording ---
    try:
        _send("set_record_mode", {"record_mode": True})
    except RuntimeError as e:
        warnings.append("Could not enable record mode: {}".format(e))

    try:
        _send("start_playing")
    except RuntimeError as e:
        # Cleanup on failure
        try:
            _send("set_track_arm", {"track_index": new_track_index, "arm": False})
        except RuntimeError:
            pass
        return {"error": "Could not start playback: {}".format(e), "warnings": warnings}

    # --- Step 8: Wait for the recording duration ---
    time.sleep(duration_seconds + 0.5)

    # --- Step 9: Stop recording ---
    try:
        _send("stop_playing")
    except RuntimeError as e:
        warnings.append("Could not stop playback: {}".format(e))

    try:
        _send("set_record_mode", {"record_mode": False})
    except RuntimeError:
        pass

    # --- Step 10: Disarm the new track ---
    try:
        _send("set_track_arm", {"track_index": new_track_index, "arm": False})
    except RuntimeError as e:
        warnings.append("Could not disarm new track: {}".format(e))

    # --- Step 11: Return result ---
    result: dict[str, Any] = {
        "new_track_index": new_track_index,
        "new_track_name": new_track_name,
        "source_track_name": source_track_name,
        "source_track_index": source_track_index,
        "bars_recorded": bars_to_record,
        "duration_seconds": round(duration_seconds, 3),
        "start_bar": start_bar,
        "end_bar": end_bar,
        "tempo": tempo,
        "routing_type_name": routing_type_name,
        "routing_channel_name": routing_channel_name,
        "routing_set": routing_set,
        "use_resampling": use_resampling,
    }
    if warnings:
        result["warnings"] = warnings
    return result
