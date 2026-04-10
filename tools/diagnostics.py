"""Diagnostics tools — mix balance analysis, AU preset scanning, Splice library scanning, preset recommendations, and sound library stats."""
from __future__ import annotations

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
import subprocess
import tempfile
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
    _reference_profiles,
    _audio_analysis_cache,
    _get_memory,
    _save_memory,
    _load_memory,
    _memory_path,
    _save_reference_profile,
    _load_reference_profiles_from_project,
)
from helpers.summarizer import summarize_session

from tools.sound_library import (  # noqa: F401
    _TONAL_KEYWORDS,
    _DRUM_KEYWORDS,
    _OMNISPHERE_TAG_MAP,
    _MOOG_MARIANA_BASE,
    _SESSION_UPRIGHT_BASE,
    _FREQ_BANDS,
    _CHAR_BANDS,
    _ALL_BANDS,
    _SPLICE_BAND_RANGES,
    _CACHE_DIR,
    _CACHE_FILE,
    _ensure_cache_dir,
    _load_cache,
    _save_cache,
    _infer_descriptors_from_name,
    _infer_drum_descriptors_from_name,
    _detect_plugin_from_path,
    _is_drum_plugin,
    _parse_aupreset,
    _parse_prt_omni,
    _apply_omnisphere_tags,
    scan_au_presets,
    scan_splice_library,
    recommend_presets,
    audit_preset,
    get_sound_library_stats,
)
from tools.screenshot import take_screenshot  # noqa: F401
from tools.mix_analysis import analyze_mix_balance  # noqa: F401

# ---------------------------------------------------------------------------
# J — Diagnostic tools per question
# ---------------------------------------------------------------------------

def _db_from_linear(linear: float) -> float:
    """Convert linear gain (0.0–1.0 nominal) to dB."""
    if linear <= 0:
        return -math.inf
    return 20.0 * math.log10(max(linear, 1e-10))


@mcp.tool()
def diagnose_track(track_index: int) -> dict:
    """Run a full diagnostic on a single track and return structured findings."""
    tracks = _send("get_tracks")
    if not isinstance(tracks, list) or track_index >= len(tracks):
        return {
            "track_name": "",
            "track_index": track_index,
            "warnings": ["Track index {} not found".format(track_index)],
            "info": [],
            "recommendations": [],
            "health_score": 0,
        }

    track = tracks[track_index]
    track_name = track.get("name", "Unnamed")
    warnings: list[str] = []
    info: list[str] = []
    recommendations: list[str] = []
    penalty = 0

    # Volume check
    mixer = track.get("mixer_device", {}) or {}
    volume = mixer.get("volume")
    if volume is not None:
        db = _db_from_linear(volume)
        if db > 0:
            warnings.append("Volume is above 0 dBFS ({:+.1f} dB) — may clip".format(db))
            penalty += 15
        elif db < -40:
            warnings.append("Volume is very low ({:+.1f} dB)".format(db))
            penalty += 5
        else:
            info.append("Volume: {:+.1f} dB".format(db))

    # Pan check
    pan = mixer.get("panning")
    if pan is not None:
        if abs(pan) > 0.9:
            direction = "left" if pan < 0 else "right"
            warnings.append("Pan is hard {} ({:.2f})".format(direction, pan))
            penalty += 5
        else:
            info.append("Pan: {:.2f}".format(pan))

    # Device chain
    devices = track.get("devices", [])
    disabled_devices: list[str] = []
    for d in devices:
        if not d.get("is_active", True):
            disabled_devices.append(d.get("name", "?"))
    if disabled_devices:
        warnings.append("Disabled device(s): {}".format(", ".join(disabled_devices)))
        penalty += 10
    if not devices:
        info.append("No devices on this track")

    # Sends check
    sends = mixer.get("sends", [])
    for i, s in enumerate(sends):
        send_val = s if isinstance(s, (int, float)) else s.get("value", 0) if isinstance(s, dict) else 0
        if send_val > 0.9:
            warnings.append("Send {} is very high ({:.2f})".format(i, send_val))
            penalty += 5

    # Clips
    clip_slots = track.get("clip_slots", [])
    short_clips: list[int] = []
    for i, slot in enumerate(clip_slots):
        if isinstance(slot, dict) and slot.get("has_clip"):
            length = slot.get("clip", {}).get("length", slot.get("length"))
            if length is not None and length < 0.25:
                short_clips.append(i)
    if short_clips:
        warnings.append("Very short clip(s) at slot(s): {}".format(short_clips))
        penalty += 5

    if not warnings:
        info.append("No issues found")
    else:
        recommendations.append("Review the flagged warnings above")

    health_score = max(0, 100 - penalty)
    return {
        "track_name": track_name,
        "track_index": track_index,
        "warnings": warnings,
        "info": info,
        "recommendations": recommendations,
        "health_score": health_score,
    }


@mcp.tool()
def diagnose_mix() -> dict:
    """Run a diagnostic across the entire mix and return structured findings."""
    tracks = _send("get_tracks")
    if not isinstance(tracks, list):
        return {
            "warnings": [],
            "info": ["Could not retrieve tracks"],
            "recommendations": [],
            "overall_health": 0,
            "tracks_checked": 0,
        }

    warnings: list[dict] = []
    info: list[str] = []
    recommendations: list[str] = []
    penalty = 0

    for t in tracks:
        idx = t.get("index", t.get("track_index", "?"))
        name = t.get("name", "Unnamed")
        mixer = t.get("mixer_device", {}) or {}
        volume = mixer.get("volume")

        # Clipping/near-clipping
        if volume is not None:
            db = _db_from_linear(volume)
            if db > 0:
                warnings.append({"track_index": idx, "track_name": name, "warning": "Volume above 0 dBFS ({:+.1f} dB)".format(db)})
                penalty += 10
            elif db > -1.0:
                warnings.append({"track_index": idx, "track_name": name, "warning": "Near-clipping ({:+.1f} dB)".format(db)})
                penalty += 5

        # No devices
        devices = t.get("devices", [])
        if not devices:
            warnings.append({"track_index": idx, "track_name": name, "warning": "No devices on track"})
            penalty += 3

    # Master bus
    try:
        master = _send("get_mixer_device", {"track_index": -1})
        master_vol = master.get("volume") if isinstance(master, dict) else None
        if master_vol is not None:
            db = _db_from_linear(master_vol)
            if db > 0:
                warnings.append({"track_index": -1, "track_name": "Master", "warning": "Master bus above 0 dBFS ({:+.1f} dB)".format(db)})
                penalty += 20
            else:
                info.append("Master bus: {:+.1f} dB".format(db))
    except Exception as e:
        logger.warning("Could not complete mix health check: %s", e)
    else:
        recommendations.append("Address clipping tracks first, then review devices and routing")

    overall_health = max(0, 100 - penalty)
    return {
        "warnings": warnings,
        "info": info,
        "recommendations": recommendations,
        "overall_health": overall_health,
        "tracks_checked": len(tracks),
    }


# ---------------------------------------------------------------------------
# Latency report
# ---------------------------------------------------------------------------

_DEVICE_LATENCY_THRESHOLD_MS: float = 5.0   # flag individual devices above this
_TRACK_LATENCY_THRESHOLD_MS: float = 10.0   # flag tracks with total chain above this
_TOTAL_PDC_THRESHOLD_MS: float = 50.0       # suggest freezing when total load exceeds this

@mcp.tool()
def get_latency_report() -> dict:
    """Report per-device and per-track latency from Ableton's LOM."""
    raw = _send("get_latency_report")

    sample_rate = raw.get("sample_rate", 44100)
    tracks = raw.get("tracks", [])

    # Find the track with the highest total latency
    highest_latency_track = None
    highest_track_ms = 0.0
    for t in tracks:
        total_ms = t.get("total_latency_ms", 0.0)
        if total_ms > highest_track_ms:
            highest_track_ms = total_ms
            highest_latency_track = t.get("track_name")

    # Find the device with the highest individual latency
    highest_latency_device = None
    highest_device_ms = 0.0
    highest_device_track = None
    for t in tracks:
        for d in t.get("devices", []):
            dev_ms = d.get("latency_ms", 0.0)
            if dev_ms > highest_device_ms:
                highest_device_ms = dev_ms
                highest_latency_device = d.get("device_name")
                highest_device_track = t.get("track_name")

    # Sum all device latencies across all tracks
    total_pdc_load_ms = round(
        sum(d.get("latency_ms", 0.0) for t in tracks for d in t.get("devices", [])),
        4,
    )

    # Build recommendations
    recommendations: list[str] = []
    all_zero = total_pdc_load_ms == 0.0

    if all_zero:
        recommendations.append(
            "All device latencies are 0. Either no latency-introducing plugins are loaded, "
            "or device.latency_in_samples is not supported on this Live version."
        )
    else:
        for t in tracks:
            for d in t.get("devices", []):
                if d.get("latency_ms", 0.0) > _DEVICE_LATENCY_THRESHOLD_MS:
                    recommendations.append(
                        "{} on '{}' is reporting {:.1f} ms latency — consider checking PDC settings "
                        "or replacing with a lower-latency alternative.".format(
                            d.get("device_name", "Unknown device"),
                            t.get("track_name", "Unknown track"),
                            d.get("latency_ms", 0.0),
                        )
                    )
        for t in tracks:
            if t.get("total_latency_ms", 0.0) > _TRACK_LATENCY_THRESHOLD_MS:
                recommendations.append(
                    "Track '{}' has a total chain latency of {:.1f} ms — review PDC settings "
                    "and consider reducing the device chain length.".format(
                        t.get("track_name", "Unknown track"),
                        t.get("total_latency_ms", 0.0),
                    )
                )
        if total_pdc_load_ms > _TOTAL_PDC_THRESHOLD_MS:
            recommendations.append(
                "Total PDC load across all tracks is {:.1f} ms. Consider freezing high-latency "
                "tracks to reduce processing overhead.".format(total_pdc_load_ms)
            )

    return {
        "sample_rate": sample_rate,
        "tracks": tracks,
        "highest_latency_track": highest_latency_track,
        "highest_latency_device": highest_latency_device,
        "total_pdc_load_ms": total_pdc_load_ms,
        "recommendations": recommendations,
    }

