"""Session snapshot tools — in-memory session snapshots, device parameter snapshots, and version snapshots."""
from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import time
from typing import Any

logger = logging.getLogger(__name__)

import helpers
from helpers import (
    mcp,
    _send,
    _snapshots,
    _snapshots_lock,
    _get_memory,
    _save_memory,
)

# ---------------------------------------------------------------------------
# Session-management cache paths (shared with session.py coordinator)
# ---------------------------------------------------------------------------

_SESSION_CACHE_DIR = os.path.expanduser("~/.ableton_mpcx")
_DEVICE_SNAPSHOTS_PATH = os.path.join(_SESSION_CACHE_DIR, "device_snapshots.json")
_VERSIONS_PATH = os.path.join(_SESSION_CACHE_DIR, "versions.json")


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


# ---------------------------------------------------------------------------
# In-memory session snapshots
# ---------------------------------------------------------------------------

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
    with _snapshots_lock:
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
    with _snapshots_lock:
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
    with _snapshots_lock:
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
    with _snapshots_lock:
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
    with _snapshots_lock:
        if label not in _snapshots:
            raise ValueError("No snapshot with label '{}'".format(label))
        a = _snapshots[label]

    live = _send("get_session_snapshot")

    changes: list = []
    _diff_value(a, live, "session", changes)

    return {
        "label": label,
        "change_count": len(changes),
        "changes": changes,
    }


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
    with _snapshots_lock:
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
    with _snapshots_lock:
        for label, snap in persisted.items():
            _snapshots[label] = snap
    return {"loaded": list(persisted.keys()), "count": len(persisted)}


# ---------------------------------------------------------------------------
# Device parameter snapshots
# ---------------------------------------------------------------------------

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
        except RuntimeError as e:
            logger.debug("Could not get parameters for device %s on track %s: %s", dev_idx, track_index, e)

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
    except RuntimeError as e:
        logger.debug("Could not begin undo step for snapshot recall: %s", e)

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
            except RuntimeError as e:
                logger.debug("Could not restore parameter %s on device %s: %s", param_idx_str, dev_idx, e)
        if restored_any:
            devices_restored += 1

    try:
        _send("end_undo_step", {})
    except RuntimeError as e:
        logger.debug("Could not end undo step for snapshot recall: %s", e)

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
        track_index: Filter to a specific track. None = list all tracks.

    Returns:
        snapshots: list of {track_index, snapshot_name, device_count, parameter_count, saved_at}
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    results = []
    for track_key, track_snaps in all_snapshots.items():
        if track_index is not None and int(track_key) != track_index:
            continue
        for snap_name, snap_data in track_snaps.items():
            devices_data = snap_data.get("devices", {})
            total_params = sum(len(d.get("parameters", {})) for d in devices_data.values())
            results.append({
                "track_index": int(track_key),
                "snapshot_name": snap_name,
                "device_count": len(devices_data),
                "parameter_count": total_params,
                "saved_at": snap_data.get("saved_at", ""),
            })
    return {"snapshots": results, "count": len(results)}


@mcp.tool()
def diff_device_snapshots(
    track_index: int,
    snapshot_a: str,
    snapshot_b: str,
    device_index: int | None = None,
) -> dict:
    """
    Compare two device snapshots for a track and return parameter differences.

    Args:
        track_index: Track to compare.
        snapshot_a: Name of the 'before' snapshot.
        snapshot_b: Name of the 'after' snapshot.
        device_index: Optional — compare only this device.

    Returns:
        snapshot_a, snapshot_b, track_index,
        changes: list of {device_index, device_name, parameter_index, parameter_name, before, after, delta}
    """
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)

    for snap_name in (snapshot_a, snapshot_b):
        if track_key not in all_snapshots or snap_name not in all_snapshots[track_key]:
            return {"error": "Snapshot '{}' not found for track {}.".format(snap_name, track_index)}

    data_a = all_snapshots[track_key][snapshot_a].get("devices", {})
    data_b = all_snapshots[track_key][snapshot_b].get("devices", {})

    all_dev_keys = set(data_a.keys()) | set(data_b.keys())
    if device_index is not None:
        all_dev_keys = {k for k in all_dev_keys if int(k) == device_index}

    changes = []
    for dev_key in sorted(all_dev_keys, key=int):
        dev_a = data_a.get(dev_key, {})
        dev_b = data_b.get(dev_key, {})
        dev_name = dev_a.get("device_name", dev_b.get("device_name", ""))
        params_a = dev_a.get("parameters", {})
        params_b = dev_b.get("parameters", {})
        all_param_keys = set(params_a.keys()) | set(params_b.keys())
        for p_key in sorted(all_param_keys, key=int):
            pa = params_a.get(p_key, {})
            pb = params_b.get(p_key, {})
            va = pa.get("value", 0.0)
            vb = pb.get("value", 0.0)
            if abs(va - vb) > 1e-9:
                changes.append({
                    "device_index": int(dev_key),
                    "device_name": dev_name,
                    "parameter_index": int(p_key),
                    "parameter_name": pa.get("name", pb.get("name", "")),
                    "before": va,
                    "after": vb,
                    "delta": vb - va,
                })

    return {
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "track_index": track_index,
        "change_count": len(changes),
        "changes": changes,
    }


@mcp.tool()
def delete_device_snapshot(track_index: int, snapshot_name: str) -> dict:
    """Delete a saved device snapshot."""
    all_snapshots = _load_json_cache(_DEVICE_SNAPSHOTS_PATH, {})
    track_key = str(track_index)
    if track_key not in all_snapshots or snapshot_name not in all_snapshots[track_key]:
        return {"error": "Snapshot '{}' not found for track {}.".format(snapshot_name, track_index)}
    del all_snapshots[track_key][snapshot_name]
    _save_json_cache(_DEVICE_SNAPSHOTS_PATH, all_snapshots)
    return {"deleted": snapshot_name, "track_index": track_index}


# ---------------------------------------------------------------------------
# Version snapshots
# ---------------------------------------------------------------------------

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
    except Exception as e:
        logger.warning("Could not capture device snapshot for version '%s': %s", version_name, e)

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


# ---------------------------------------------------------------------------
# Full session snapshot (all tracks + devices)
# ---------------------------------------------------------------------------

@mcp.tool()
def full_session_snapshot(snapshot_name: str) -> dict:
    """
    Capture a full device-parameter snapshot of every track in the session.

    Iterates all regular tracks, the master track, and return tracks, reading
    every device's full parameter state. The snapshot is saved to
    ~/.ableton_mpcx/device_snapshots.json under the given name.

    Use diff_device_snapshots() or diff_version_snapshots() to compare later.

    Args:
        snapshot_name: Name for this snapshot (e.g. 'initial', 'before_mastering').

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
    except RuntimeError as e:
        logger.debug("Could not get tracks for full session snapshot: %s", e)

    try:
        return_tracks = _send("get_return_tracks")
        for rt in return_tracks:
            idx = rt.get("index", rt.get("track_index"))
            if idx is not None:
                track_indices.append(("return", idx))
    except RuntimeError as e:
        logger.debug("Could not get return tracks for full session snapshot: %s", e)

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
            except RuntimeError as e:
                logger.debug("Could not get parameters for device %s on track %s: %s", dev_idx, ti, e)

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
