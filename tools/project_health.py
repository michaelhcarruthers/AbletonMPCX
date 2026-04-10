"""Project health tools — missing plugins, missing media, cleanup, and batch audit."""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

from helpers import _send
from helpers.summarizer import summarize_health_report

_MISSING_PLUGIN_INDICATORS = ["missing", "disabled", "unknown plugin", "vst not found", "au not found"]

_PROJECT_LOAD_DELAY_SECONDS: float = 2.0  # seconds to wait after opening a set before auditing

_MAX_ISSUE_CATEGORIES = 5


def find_missing_plugins(dry_run: bool = True) -> dict:
    """Scan all tracks for missing or disabled plugin placeholders. dry_run=True by default — reports without making changes."""
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


def get_missing_media_status() -> dict:
    """Report all missing audio files in the current Live set."""
    result = _send("get_missing_media", {})
    missing = result.get("missing", [])
    total_checked = result.get("total_checked", 0)
    return {
        "missing_samples": missing,
        "total_missing": len(missing),
        "total_checked": total_checked,
        "can_search": True,
    }


def search_missing_media(search_folders: list) -> dict:
    """Attempt to relink missing audio samples by searching the given folders."""
    _send("begin_undo_step", {"name": "search_missing_media"})
    try:
        result = _send("search_missing_media", {"search_folders": search_folders})
    finally:
        _send("end_undo_step", {})
    return result


def project_health_report() -> dict:
    """Run a full health audit of the current Live set."""
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


def find_empty_tracks() -> dict:
    """Find all tracks with no clips and no devices."""
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


def find_unused_returns() -> dict:
    """Find return tracks that no track is sending to (all sends at zero or minimum)."""
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


def cleanup_session(dry_run: bool = True) -> dict:
    """Remove empty tracks and unused return tracks. dry_run=True by default — reports without making changes."""
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
                except Exception as e:
                    logger.warning("Could not delete return track %s: %s", idx, e)
            # Delete empty regular tracks in reverse index order
            for idx in sorted(empty_track_indices, reverse=True):
                try:
                    _send("delete_track", {"track_index": idx})
                    removed.append(next(c for c in candidates if c["track_index"] == idx))
                except Exception as e:
                    logger.warning("Could not delete track %s: %s", idx, e)
        finally:
            _send("end_undo_step", {})

    key = "removed" if not dry_run else "would_remove"
    return {
        key: removed if not dry_run else candidates,
        "dry_run": dry_run,
        "total_affected": len(candidates),
    }


def open_set(set_path: str) -> dict:
    """Open an Ableton Live set file (.als) on the currently running Live instance."""
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


def batch_audit_projects(set_paths: list, save_reports: bool = True) -> dict:
    """Run project_health_report() on multiple Live sets in sequence."""
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
                except Exception as e:
                    logger.warning("Could not save audit report to '%s': %s", report_path, e)

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


def save_project_audit(save_path: str | None = None) -> dict:
    """Run project_health_report() and save the result as a JSON file."""
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


def load_project_audit(audit_path: str) -> dict:
    """Load a previously saved project audit JSON and return its contents."""
    if not os.path.exists(audit_path):
        return {"error": "Audit file not found: {}".format(audit_path)}
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {"error": "Failed to read audit file: {}".format(str(exc))}


def compare_project_audits(audit_path_a: str, audit_path_b: str) -> dict:
    """Compare two saved project audits and return what changed."""
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
