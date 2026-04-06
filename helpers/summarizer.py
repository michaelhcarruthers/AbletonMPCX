"""Compact output formatters for MCP tool responses.

Summarizer helpers are defined inline in the tool modules that produce them.
This module exists as a dedicated home for any shared formatting utilities
extracted in future PRs.
"""

# ---------------------------------------------------------------------------
# Compact summarizers (I)
# Reduce verbose Ableton state dumps to token-efficient summaries.
# ---------------------------------------------------------------------------

from __future__ import annotations
import math


def _db(linear: float) -> str:
    """Convert a linear gain value (0.0–1.0 nominal) to a dB string."""
    if linear <= 0:
        return "-inf dB"
    db = 20.0 * math.log10(max(linear, 1e-10))
    return "{:+.0f}dB".format(db)


def summarize_track(track: dict) -> str:
    """Convert a full track dict to a compact single-line string.

    Example output::

        [2] Kick (Audio) | Vol:-3dB | Armed | 4 devices | 12 clips
    """
    idx = track.get("index", track.get("track_index", "?"))
    name = track.get("name", "Unnamed")
    kind = track.get("type", track.get("track_type", ""))
    volume = track.get("volume", track.get("mixer_device", {}).get("volume") if isinstance(track.get("mixer_device"), dict) else None)
    vol_str = " | Vol:{}".format(_db(volume)) if volume is not None else ""
    armed = track.get("arm", False)
    arm_str = " | Armed" if armed else ""
    devices = track.get("devices", [])
    device_count = len(devices) if isinstance(devices, list) else 0
    dev_str = " | {} device{}".format(device_count, "s" if device_count != 1 else "") if device_count else ""
    clips = track.get("clip_slots", track.get("clips", []))
    clip_count = sum(1 for c in clips if c) if isinstance(clips, list) else 0
    clip_str = " | {} clip{}".format(clip_count, "s" if clip_count != 1 else "") if clip_count else ""
    type_str = " ({})".format(kind) if kind else ""
    return "[{}] {}{}{}{}{}{}".format(idx, name, type_str, vol_str, arm_str, dev_str, clip_str)


def summarize_device(device: dict) -> str:
    """Convert a full device dict to a compact string.

    Example output::

        Compressor | Threshold:-18dB Ratio:4:1 Attack:10ms
    """
    name = device.get("name", "Unknown")
    params = device.get("parameters", [])
    param_parts: list[str] = []
    for p in params[:5]:
        pname = p.get("name", "")
        pval = p.get("value")
        if pname and pval is not None:
            param_parts.append("{}:{}".format(pname, pval))
    param_str = " | " + " ".join(param_parts) if param_parts else ""
    return "{}{}".format(name, param_str)


def summarize_session(session: dict) -> str:
    """Convert full session state to a compact multi-line summary.

    Returns up to ~10 lines regardless of session size.
    """
    lines: list[str] = []

    # Header line
    tempo = session.get("tempo")
    ts_num = session.get("time_signature_numerator", session.get("numerator"))
    ts_den = session.get("time_signature_denominator", session.get("denominator"))
    header_parts: list[str] = []
    if tempo is not None:
        header_parts.append("{} BPM".format(tempo))
    if ts_num and ts_den:
        header_parts.append("{}/{}".format(ts_num, ts_den))
    if header_parts:
        lines.append("Session: " + " | ".join(header_parts))

    tracks = session.get("tracks", [])
    if tracks:
        lines.append("Tracks: {}".format(len(tracks)))
        for t in tracks[:8]:
            lines.append("  " + summarize_track(t))
        if len(tracks) > 8:
            lines.append("  … and {} more track(s)".format(len(tracks) - 8))

    return "\n".join(lines)


def summarize_health_report(report: dict) -> str:
    """Convert a project_health_report dict to a 3-line human-readable summary.

    Example output::

        Score: 87/100 | 2 missing plugins | 0 missing media | 14 tracks OK
        Issues: high CPU on track 3; unnamed track at index 7
        Recommendations: Freeze track 3; rename unnamed tracks
    """
    score = report.get("health_score", "?")
    missing_plugins = report.get("missing_plugins", [])
    missing_media = report.get("missing_media", [])
    track_count = report.get("track_count", "?")
    line1 = "Score: {}/100 | {} missing plugin{} | {} missing media | {} tracks".format(
        score,
        len(missing_plugins), "s" if len(missing_plugins) != 1 else "",
        len(missing_media),
        track_count,
    )
    issues = report.get("issues", [])
    line2 = "Issues: " + ("; ".join(str(i) for i in issues[:3]) if issues else "none")
    recs = report.get("recommendations", [])
    line3 = "Recommendations: " + ("; ".join(str(r) for r in recs[:3]) if recs else "none")
    return "\n".join([line1, line2, line3])
