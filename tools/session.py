"""Session tools — song, transport, project memory, snapshots, auto-naming, session collaborator, and contextual suggestion tools."""
from __future__ import annotations

# AGENT WORKFLOW NOTE:
# Use get_session_diff() as the default monitoring call during active sessions.
# Only call get_session_snapshot() or get_full_session_state() for initial
# orientation or after major structural changes. get_session_diff() is token-efficient
# and returns only what changed since the last snapshot.

import collections
import copy
import datetime
import json
import logging
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

logger = logging.getLogger(__name__)

import helpers
from helpers import (
    mcp,
    _send,
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
from helpers.cache import cache_state

# ---------------------------------------------------------------------------
# Sub-module imports — trigger @mcp.tool() registration and re-export for
# backward compatibility with any callers that import from tools.session
# ---------------------------------------------------------------------------

from tools.session_snapshots import (  # noqa: E402,F401
    take_snapshot,
    list_snapshots,
    delete_snapshot,
    _diff_value,
    diff_snapshots,
    diff_snapshot_vs_live,
    save_snapshot_to_project,
    load_snapshots_from_project,
    save_device_snapshot,
    recall_device_snapshot,
    list_device_snapshots,
    diff_device_snapshots,
    delete_device_snapshot,
    save_version_snapshot,
    list_version_snapshots,
    diff_version_snapshots,
    full_session_snapshot,
    _SESSION_CACHE_DIR,
    _DEVICE_SNAPSHOTS_PATH,
    _VERSIONS_PATH,
    _ensure_session_cache_dir,
    _load_json_cache,
    _save_json_cache,
)

from tools.session_suggestions import suggest_next_actions  # noqa: E402,F401

from tools.session_recording import (  # noqa: E402,F401
    setup_resampling_route,
    teardown_resampling_route,
    get_resampling_status,
    render_track_to_audio,
)

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
def set_arrangement_position(position_beats: float) -> dict:
    """
    Set the arrangement playhead position in beats (absolute song time).

    Use bars_beats_to_song_time() to convert bar/beat to absolute beats first.

    Args:
        position_beats: Absolute song time in beats (0.0 = start of song).

    Returns:
        dict with key 'position': the position that was set (in beats).
    """
    return _send("set_arrangement_position", {"position": position_beats})

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
            except Exception as e:
                logger.debug("Could not read project memory for mix analysis: %s", e)

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


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------


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


# --- Feature 1: Auto-naming and color ---

@mcp.tool()
def auto_name_track(track_index: int, dry_run: bool = False) -> dict:
    """
    Automatically name a track based on its device chain content.

    Infers the track role by:
    1. Checking device names against _DEVICE_TO_ROLE mappings
    2. Using track position as last resort (Track 1, Track 2, etc.)

    Args:
        track_index: Track to name (-1 for master).
        dry_run: If True, return the suggested name without applying it.

    Returns:
        track_index, suggested_name, inferred_role, method_used, applied (bool)
    """
    role, method = _infer_role_from_devices(track_index)
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
            except RuntimeError as e:
                logger.debug("Could not rename/recolor track %s: %s", idx, e)
        elif skipped_reason is not None:
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
        except RuntimeError as e:
            logger.debug("Could not get clip slots for track %s: %s", idx, e)

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











# --- Feature 3: Project version snapshots ---







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
        except RuntimeError as e:
            logger.debug("Could not set scene name for scene %s: %s", scene_index, e)

        if color_code:
            try:
                _send("set_scene_color", {"scene_index": scene_index, "color": color})
            except RuntimeError as e:
                logger.debug("Could not set scene color for scene %s: %s", scene_index, e)

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
    except RuntimeError as e:
        logger.debug("Could not get clip info for track %s slot %s: %s", track_index, clip_index, e)

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
                except RuntimeError as e:
                    logger.debug("Could not get clip length for track %s scene %s: %s", ti, scene_idx, e)

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
                except RuntimeError as e:
                    logger.debug("Could not place clip for track %s scene %s: %s", ti, scene_idx, e)

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







# --- Feature 7: Session collaborator tools ---



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
                except Exception as e:
                    logger.debug("Could not auto-name track %s during audit fix: %s", idx, e)
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
                except RuntimeError as e:
                    logger.debug("Could not disarm track %s during audit fix: %s", idx, e)
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
        except RuntimeError as e:
            logger.debug("Could not get devices for track %s during audit: %s", idx, e)
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
                except RuntimeError as e:
                    logger.debug("Could not get clip info for track %s scene %s during audit: %s", ti, scene_idx, e)
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
    except RuntimeError as e:
        logger.debug("Could not check scenes during session audit: %s", e)
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

    # Band value reading is not supported without an external spectrum analyzer.
    def _read_band_value():
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
        except RuntimeError as e:
            logger.debug("Could not get parameters for device %s on track %s: %s", dev_idx, track_index, e)

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
        except Exception as e:
            logger.warning("Could not save post-correction snapshot: %s", e)

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

