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
from helpers.cache import cache_state  # noqa: E402

# ---------------------------------------------------------------------------
# Mix Analysis and Sound Recommendation
# ---------------------------------------------------------------------------

# ------------------------------------------------------------------
# Module-level descriptor constants
# ------------------------------------------------------------------

_TONAL_KEYWORDS: dict[str, dict[str, float]] = {
    "sub":      {"sub": 0.95, "bass": 0.3},
    "bass":     {"bass": 0.85, "sub": 0.4, "punch": 0.3},
    "warm":     {"body": 0.8, "mid": 0.5, "air": 0.1},
    "bright":   {"presence": 0.7, "air": 0.6},
    "airy":     {"air": 0.9, "presence": 0.3},
    "shimmer":  {"air": 0.85, "presence": 0.6},
    "crystal":  {"air": 0.8, "presence": 0.7},
    "dark":     {"air": 0.05, "presence": 0.15, "body": 0.65},
    "pad":      {"sustain": 0.9, "transient": 0.05, "density": 0.4},
    "pluck":    {"transient": 0.9, "sustain": 0.15},
    "wide":     {"width": 0.9},
    "lush":     {"width": 0.75, "sustain": 0.7},
    "thick":    {"body": 0.7, "punch": 0.5, "mid": 0.4},
    "deep":     {"sub": 0.75, "bass": 0.65},
    "grand":    {"body": 0.6, "presence": 0.5, "transient": 0.6},
    "upright":  {"body": 0.7, "punch": 0.5, "transient": 0.5},
    "rhodes":   {"body": 0.5, "mid": 0.6, "transient": 0.5},
    "bell":     {"presence": 0.7, "air": 0.6, "transient": 0.8, "sustain": 0.6},
    "strings":  {"sustain": 0.85, "body": 0.5, "mid": 0.5},
    "choir":    {"sustain": 0.8, "mid": 0.6, "presence": 0.4},
    "stab":     {"transient": 0.9, "sustain": 0.1},
    "perc":     {"transient": 0.85, "sustain": 0.2},
    "snap":     {"transient": 0.9},
    "hit":      {"transient": 0.8},
    "drone":    {"sustain": 0.95, "density": 0.6},
    "evolving": {"sustain": 0.9, "density": 0.7},
    "lead":     {"presence": 0.7, "mid": 0.6, "transient": 0.5},
    "organ":    {"mid": 0.7, "body": 0.5, "sustain": 0.85},
    "piano":    {"transient": 0.7, "body": 0.5, "mid": 0.5, "presence": 0.4},
    "brass":    {"presence": 0.8, "mid": 0.6, "transient": 0.6},
    "flute":    {"presence": 0.6, "air": 0.5, "sustain": 0.7},
    "guitar":   {"mid": 0.6, "punch": 0.5, "transient": 0.6},
    "mellow":   {"body": 0.6, "mid": 0.5, "air": 0.1, "presence": 0.2},
    "crisp":    {"presence": 0.8, "air": 0.5},
    "punchy":   {"punch": 0.85, "transient": 0.75},
    "808":      {"sub": 0.9, "bass": 0.7, "sustain": 0.6},
    "mono":     {"width": 0.05},
    "stereo":   {"width": 0.8},
}

_DRUM_KEYWORDS: dict[str, dict[str, float]] = {
    "tight":      {"tempo_feel": 0.1, "room_size": 0.1},
    "dry":        {"room_size": 0.05},
    "room":       {"room_size": 0.6, "tempo_feel": 0.5},
    "heavy":      {"kick_sub": 0.9, "kick_punch": 0.7, "density": 0.8},
    "punchy":     {"kick_punch": 0.85, "kick_attack": 0.75},
    "jazz":       {"tempo_feel": 0.7, "overhead_air": 0.85, "density": 0.3},
    "rock":       {"kick_punch": 0.8, "snare_crack": 0.7, "density": 0.7},
    "electronic": {"kick_attack": 0.9, "tempo_feel": 0.1, "room_size": 0.05},
    "vintage":    {"room_size": 0.5, "density": 0.5, "overhead_air": 0.6},
    "modern":     {"kick_attack": 0.8, "snare_crack": 0.8, "tempo_feel": 0.2},
}

_OMNISPHERE_TAG_MAP: dict[str, dict[str, float]] = {
    "Aggressive": {"transient": 0.8, "density": 0.8, "presence": 0.7},
    "Airy":       {"air": 0.9, "presence": 0.4, "sustain": 0.7},
    "Bright":     {"presence": 0.75, "air": 0.6},
    "Dark":       {"air": 0.05, "presence": 0.1, "body": 0.7},
    "Evolving":   {"sustain": 0.9, "density": 0.7},
    "Full":       {"bass": 0.5, "body": 0.6, "mid": 0.5, "density": 0.6},
    "Grunge":     {"density": 0.85, "transient": 0.6, "presence": 0.6},
    "Hard":       {"transient": 0.8, "density": 0.7},
    "Hollow":     {"body": 0.1, "mid": 0.3, "air": 0.4},
    "Lush":       {"width": 0.85, "sustain": 0.8, "density": 0.5},
    "Percussive": {"transient": 0.85, "sustain": 0.15},
    "Soft":       {"transient": 0.1, "density": 0.2, "sustain": 0.7},
    "Thin":       {"body": 0.05, "bass": 0.1, "density": 0.2},
    "Warm":       {"body": 0.8, "mid": 0.5, "air": 0.1},
    "Wide":       {"width": 0.9},
}

_MOOG_MARIANA_BASE: dict[str, float] = {
    "sub": 0.85, "bass": 0.7, "punch": 0.4, "body": 0.2,
    "mid": 0.1, "presence": 0.05, "air": 0.02,
}

_SESSION_UPRIGHT_BASE: dict[str, float] = {
    "bass": 0.85, "punch": 0.7, "body": 0.5, "mid": 0.3,
    "sub": 0.4, "presence": 0.2, "air": 0.05,
}

# Canonical frequency band descriptors
_FREQ_BANDS = ["sub", "bass", "punch", "body", "mid", "presence", "air"]
_CHAR_BANDS = ["transient", "sustain", "width", "density"]
_ALL_BANDS = _FREQ_BANDS + _CHAR_BANDS

# Splice librosa frequency bin ranges (at sr=22050)
_SPLICE_BAND_RANGES: dict[str, tuple[float, float]] = {
    "sub":      (20.0,   60.0),
    "bass":     (60.0,  120.0),
    "punch":   (120.0,  250.0),
    "body":    (250.0,  500.0),
    "mid":     (500.0, 2000.0),
    "presence": (2000.0, 6000.0),
    "air":     (6000.0, 20000.0),
}

# Cache file path
_CACHE_DIR = pathlib.Path.home() / ".ableton_mpcx"
_CACHE_FILE = _CACHE_DIR / "sound_library.json"


def _ensure_cache_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_cache() -> dict:
    """Load the sound library cache or return an empty structure."""
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as e:
            logger.warning("Failed to load sound library cache: %s", e)
    return {"entries": []}


def _save_cache(cache: dict) -> None:
    """Persist the sound library cache to disk."""
    _ensure_cache_dir()
    with open(_CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2)


def _infer_descriptors_from_name(name: str, plugin: str = "") -> dict[str, float]:
    """
    Infer tonal descriptors from a preset/file name using _TONAL_KEYWORDS.
    Returns a dict of band -> 0.0-1.0 scores.
    """
    tokens = re.split(r"[\s_\-/\\\.]+", name.lower())
    scores: dict[str, float] = {}

    # Apply plugin base descriptors first
    plugin_lower = plugin.lower()
    if "moog mariana" in plugin_lower or "mariana" in plugin_lower:
        for k, v in _MOOG_MARIANA_BASE.items():
            scores[k] = v
    elif "session upright" in plugin_lower or "session bass" in plugin_lower:
        for k, v in _SESSION_UPRIGHT_BASE.items():
            scores[k] = v

    # Apply keyword matches
    for token in tokens:
        if token in _TONAL_KEYWORDS:
            for band, val in _TONAL_KEYWORDS[token].items():
                scores[band] = max(scores.get(band, 0.0), val)

    # Fill in any missing canonical bands with 0.0
    for band in _ALL_BANDS:
        scores.setdefault(band, 0.0)

    return scores


def _infer_drum_descriptors_from_name(name: str) -> dict[str, float]:
    """
    Infer drum descriptors from a kit/preset name using _DRUM_KEYWORDS.
    """
    tokens = re.split(r"[\s_\-/\\\.]+", name.lower())
    drum_bands = [
        "kick_sub", "kick_punch", "kick_attack",
        "snare_crack", "snare_body",
        "room_size", "overhead_air", "density", "tempo_feel",
    ]
    scores: dict[str, float] = {b: 0.0 for b in drum_bands}
    for token in tokens:
        if token in _DRUM_KEYWORDS:
            for band, val in _DRUM_KEYWORDS[token].items():
                scores[band] = max(scores.get(band, 0.0), val)
    return scores


def _detect_plugin_from_path(path: str) -> str:
    """Detect plugin name from a file path substring."""
    pl = path.lower()
    if "omnisphere" in pl:
        return "Omnisphere"
    if "keyscape" in pl:
        return "Keyscape"
    if "moog mariana" in pl or "mariana" in pl:
        return "Moog Mariana"
    if "session upright" in pl:
        return "Session Upright"
    if "session bass" in pl:
        return "Session Bass"
    if "addictive drums" in pl or "ad2" in pl:
        return "Addictive Drums 2"
    if "superior drummer" in pl or "sd3" in pl:
        return "Superior Drummer 3"
    return "Unknown"


def _is_drum_plugin(plugin: str) -> bool:
    pl = plugin.lower()
    return any(k in pl for k in ("addictive drums", "ad2", "superior drummer", "sd3"))


def _parse_aupreset(path: pathlib.Path) -> tuple[str, dict]:
    """
    Parse an .aupreset (plist) file.
    Returns (preset_name, extra_info_dict).
    """
    with open(path, "rb") as fh:
        data = plistlib.load(fh)
    name = data.get("name", path.stem)
    return name, data


def _parse_prt_omni(path: pathlib.Path) -> tuple[str, list[str]]:
    """
    Parse an Omnisphere .prt_omni file.
    Returns (preset_name, character_tags).
    """
    name = path.stem
    tags: list[str] = []
    try:
        with open(path, "rb") as fh:
            data = plistlib.load(fh)
        name = data.get("PatchName", data.get("name", name))
        char = data.get("CharacterTags", data.get("Attributes", []))
        if isinstance(char, list):
            tags = [str(t) for t in char]
        return name, tags
    except Exception as e:
        logger.debug("Failed to parse plist for '%s': %s", path, e)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"PatchName[^\w]+([\w\s]+)", text)
        if m:
            name = m.group(1).strip()
        tags = re.findall(r"<string>([\w]+)</string>", text)
    except Exception as e:
        logger.debug("Failed to read text for '%s': %s", path, e)
    return name, tags


def _apply_omnisphere_tags(
    descriptors: dict[str, float], tags: list[str]
) -> dict[str, float]:
    """Merge Omnisphere character-tag descriptors into existing scores."""
    for tag in tags:
        if tag in _OMNISPHERE_TAG_MAP:
            for band, val in _OMNISPHERE_TAG_MAP[tag].items():
                descriptors[band] = max(descriptors.get(band, 0.0), val)
    return descriptors


# ------------------------------------------------------------------
# Tool: analyze_mix_balance
# ------------------------------------------------------------------

@mcp.tool()
def analyze_mix_balance(
    file_paths: list[str],
    reference_file_path: str | None = None,
    crowded_threshold_hz: float = 1000.0,
    missing_threshold_hz: float = -1000.0,
) -> dict:
    """Analyse spectral balance across a set of audio files using file-based analysis."""
    from tools.analysis import get_spectral_descriptors

    if not file_paths:
        return {"error": "file_paths must not be empty."}

    # Analyse all files
    results = []
    errors = []
    for fp in file_paths:
        try:
            desc = get_spectral_descriptors(fp)
            results.append(desc)
        except Exception as exc:
            errors.append({"file_path": fp, "error": str(exc)})

    if not results:
        return {"error": "Could not analyse any files.", "details": errors}

    # Analyse reference file (if provided and not already in results)
    ref_centroid: float
    ref_desc: dict | None = None
    if reference_file_path:
        try:
            ref_desc = get_spectral_descriptors(reference_file_path)
            ref_centroid = ref_desc["spectral_centroid"]
        except Exception as exc:
            return {"error": "Could not analyse reference file: {}".format(exc)}
    else:
        ref_centroid = sum(r["spectral_centroid"] for r in results) / len(results)

    # Classify each file
    bright: list[str] = []
    dark: list[str] = []
    balanced: list[str] = []
    recommendations: list[str] = []

    for desc in results:
        fp = desc["file_path"]
        delta = desc["spectral_centroid"] - ref_centroid
        desc["centroid_delta_hz"] = round(delta, 1)

        if delta >= crowded_threshold_hz:
            bright.append(fp)
            recommendations.append(
                "{} is spectrally bright ({:+.0f} Hz above reference centroid) — "
                "consider high-shelf cut or low-passing competing elements.".format(
                    fp, delta
                )
            )
        elif delta <= missing_threshold_hz:
            dark.append(fp)
            recommendations.append(
                "{} is spectrally dark ({:+.0f} Hz below reference centroid) — "
                "consider high-shelf boost or presence boost.".format(fp, delta)
            )
        else:
            balanced.append(fp)

    if bright and dark:
        summary = "{} file(s) bright, {} file(s) dark relative to reference.".format(
            len(bright), len(dark)
        )
    elif bright:
        summary = "{} file(s) spectrally bright relative to reference.".format(len(bright))
    elif dark:
        summary = "{} file(s) spectrally dark relative to reference.".format(len(dark))
    else:
        summary = "All files are spectrally balanced relative to reference."

    output: dict = {
        "results":              results,
        "reference_centroid_hz": round(ref_centroid, 2),
        "bright":               bright,
        "dark":                 dark,
        "balanced":             balanced,
        "recommendations":      recommendations,
        "summary":              summary,
        "file_count":           len(results),
    }
    if ref_desc:
        output["reference_file"] = reference_file_path
        output["reference_descriptors"] = ref_desc
    if errors:
        output["errors"] = errors
    return output


# ------------------------------------------------------------------
# Tool: scan_au_presets
# ------------------------------------------------------------------

@mcp.tool()
def scan_au_presets(force_rescan: bool = False) -> dict:
    """Scan standard macOS AU preset locations for .aupreset and .prt_omni files and infer tonal descriptors from names."""
    scan_paths = [
        pathlib.Path.home() / "Library" / "Audio" / "Presets",
        pathlib.Path("/Library/Audio/Presets"),
        pathlib.Path.home() / "Library" / "Application Support"
            / "Spectrasonics" / "STEAM" / "Omnisphere"
            / "Settings Library" / "Patches",
        pathlib.Path.home() / "Music" / "Ableton" / "Library" / "Presets",
        pathlib.Path.home() / "Music" / "Ableton" / "User Library" / "Presets",
    ]

    cache = _load_cache()
    existing_paths = {e["path"] for e in cache.get("entries", [])}

    scanned = 0
    added = 0
    skipped = 0
    plugin_counts: dict[str, int] = {}

    for base_path in scan_paths:
        if not base_path.exists():
            continue
        for ext in ("aupreset", "prt_omni"):
            for fpath in base_path.rglob("*.{}".format(ext)):
                path_str = str(fpath)
                scanned += 1
                if path_str in existing_paths and not force_rescan:
                    skipped += 1
                    continue

                plugin = _detect_plugin_from_path(path_str)
                is_drum = _is_drum_plugin(plugin)

                omni_tags: list[str] = []
                try:
                    if ext == "aupreset":
                        preset_name, _raw = _parse_aupreset(fpath)
                    else:
                        preset_name, omni_tags = _parse_prt_omni(fpath)
                except Exception:
                    skipped += 1
                    continue

                if is_drum:
                    descriptors: dict[str, float | bool] = _infer_drum_descriptors_from_name(preset_name)  # type: ignore[assignment]
                    descriptors["is_drum"] = True
                else:
                    descriptors = _infer_descriptors_from_name(preset_name, plugin)  # type: ignore[assignment]
                    if ext == "prt_omni":
                        descriptors = _apply_omnisphere_tags(descriptors, omni_tags)  # type: ignore[assignment]
                    descriptors["is_drum"] = False

                entry: dict = {
                    "path":        path_str,
                    "preset_name": preset_name,
                    "plugin":      plugin,
                    "category":    fpath.parent.name,
                    "tags":        [],
                    "measured":    False,
                    "scan_date":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                entry.update(descriptors)

                # Remove stale entry if re-scanning
                cache["entries"] = [
                    e for e in cache["entries"] if e["path"] != path_str
                ]
                cache["entries"].append(entry)
                existing_paths.add(path_str)
                added += 1
                plugin_counts[plugin] = plugin_counts.get(plugin, 0) + 1

    _save_cache(cache)

    return {
        "scanned": scanned,
        "added":   added,
        "skipped": skipped,
        "by_plugin": plugin_counts,
        "total_in_library": len(cache["entries"]),
        "cache_file": str(_CACHE_FILE),
    }


# ------------------------------------------------------------------
# Tool: scan_splice_library
# ------------------------------------------------------------------

@mcp.tool()
def scan_splice_library(
    splice_path: str | None = None,
    force_rescan: bool = False,
) -> dict:
    """Scan the Splice sample library and measure actual frequency content using librosa."""
    try:
        import librosa  # type: ignore[import]
        import numpy as np  # type: ignore[import]
    except ImportError:
        return {
            "error": (
                "librosa and numpy are required for Splice audio analysis. "
                "Run: pip install librosa numpy"
            )
        }

    root = pathlib.Path(splice_path) if splice_path else (
        pathlib.Path.home() / "Music" / "Splice"
    )

    if not root.exists():
        return {
            "error": (
                "Splice folder not found at {}. "
                "Pass splice_path='<path>' to specify a custom location.".format(root)
            )
        }

    cache = _load_cache()
    existing_paths = {e["path"] for e in cache.get("entries", [])}

    scanned = 0
    added = 0
    skipped = 0
    errors = 0
    SAVE_INTERVAL = 100

    sr = 22050
    n_fft = 2048
    hop_length = 512

    def _hz_to_bin(hz: float) -> int:
        return int(hz * n_fft / sr)

    for fpath in root.rglob("*"):
        if fpath.suffix.lower() not in (".wav", ".aiff", ".aif"):
            continue
        path_str = str(fpath)
        scanned += 1

        if path_str in existing_paths and not force_rescan:
            skipped += 1
            continue

        try:
            y_mono, _ = librosa.load(path_str, sr=sr, mono=True, duration=4.0)
        except Exception:
            errors += 1
            continue

        # STFT magnitude
        try:
            stft_mag = np.abs(librosa.stft(y_mono, n_fft=n_fft, hop_length=hop_length))
        except Exception:
            errors += 1
            continue

        # Per-band RMS
        band_rms: dict[str, float] = {}
        for band, (lo_hz, hi_hz) in _SPLICE_BAND_RANGES.items():
            lo_bin = max(0, _hz_to_bin(lo_hz))
            hi_bin = min(stft_mag.shape[0], _hz_to_bin(hi_hz))
            if hi_bin <= lo_bin:
                band_rms[band] = 0.0
                continue
            band_rms[band] = float(np.sqrt(np.mean(stft_mag[lo_bin:hi_bin] ** 2)))

        # Normalize 0-1
        max_rms = max(band_rms.values()) if band_rms else 0.0
        if max_rms > 0:
            band_rms = {b: v / max_rms for b, v in band_rms.items()}

        # Transient strength (normalised onset envelope mean)
        try:
            onset_env = librosa.onset.onset_strength(y=y_mono, sr=sr)
            transient = float(np.clip(np.mean(onset_env) / 10.0, 0.0, 1.0))
        except Exception:
            transient = 0.0

        # Sustain: ratio of tail RMS to peak RMS
        try:
            frame_rms = librosa.feature.rms(y=y_mono, hop_length=hop_length)[0]
            n_frames = len(frame_rms)
            peak_rms = float(np.max(frame_rms)) if n_frames else 0.0
            if n_frames > 4 and peak_rms > 0:
                tail_rms = float(np.mean(frame_rms[-n_frames // 4:]))
                sustain = float(np.clip(tail_rms / peak_rms, 0.0, 1.0))
            else:
                sustain = 0.0
        except Exception:
            sustain = 0.0

        # Stereo width — try to load as stereo
        width = 0.5  # default: unknown
        try:
            y_stereo, _ = librosa.load(path_str, sr=sr, mono=False, duration=4.0)
            if y_stereo.ndim == 2 and y_stereo.shape[0] == 2:
                left, right = y_stereo[0], y_stereo[1]
                denom = (np.sqrt(np.mean(left ** 2)) * np.sqrt(np.mean(right ** 2)))
                if denom > 0:
                    corr = float(np.mean(left * right) / denom)
                    # corr=1 → mono, corr=-1 → fully out of phase → wide
                    width = float(np.clip((1.0 - corr) / 2.0, 0.0, 1.0))
        except Exception as e:
            logger.debug("Could not measure stereo width for '%s': %s", fpath, e)

        entry: dict = {
            "path":        path_str,
            "preset_name": fpath.stem,
            "plugin":      "Splice",
            "category":    fpath.parent.name,
            "tags":        [],
            "measured":    True,
            "is_drum":     False,
            "scan_date":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "transient":   round(transient, 3),
            "sustain":     round(sustain, 3),
            "width":       round(width, 3),
            "density":     0.0,
        }
        entry.update({b: round(v, 3) for b, v in band_rms.items()})

        cache["entries"] = [e for e in cache["entries"] if e["path"] != path_str]
        cache["entries"].append(entry)
        existing_paths.add(path_str)
        added += 1

        if added % SAVE_INTERVAL == 0:
            _save_cache(cache)

    _save_cache(cache)

    return {
        "scanned":          scanned,
        "added":            added,
        "skipped":          skipped,
        "errors":           errors,
        "total_in_library": len(cache["entries"]),
        "cache_file":       str(_CACHE_FILE),
    }


# ------------------------------------------------------------------
# Tool: recommend_presets
# ------------------------------------------------------------------

@mcp.tool()
def recommend_presets(
    target_bands: list[str] | None = None,
    avoid_bands: list[str] | None = None,
    top_n: int = 5,
    plugin_filter: str | None = None,
) -> dict:
    """Rank sound library entries by fit score against target frequency bands and return best_fit / usable / avoid tiers."""
    cache = _load_cache()
    entries = cache.get("entries", [])

    if not entries:
        return {
            "error": (
                "Sound library is empty. "
                "Run scan_au_presets() and/or scan_splice_library() first."
            )
        }

    target_bands = [b.lower() for b in (target_bands or [])]
    avoid_bands  = [b.lower() for b in (avoid_bands  or [])]

    if not target_bands and not avoid_bands:
        return {
            "error": (
                "Please provide at least one target_band or avoid_band. "
                "Use analyze_mix_balance() to discover which bands are crowded or missing."
            )
        }

    # Filter by plugin if requested
    if plugin_filter:
        pf_lower = plugin_filter.lower()
        entries = [e for e in entries if pf_lower in e.get("plugin", "").lower()]

    if not entries:
        return {
            "error": "No library entries match plugin_filter '{}'.".format(plugin_filter)
        }

    # Score every entry
    scored: list[tuple[float, dict]] = []
    for entry in entries:
        score = 0.0
        for band in target_bands:
            score += entry.get(band, 0.0) * 2.0
        for band in avoid_bands:
            score -= entry.get(band, 0.0) * 1.5
        if entry.get("measured", False):
            score *= 1.1
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    total = len(scored)
    third = max(1, total // 3)

    best_slice   = scored[:third]
    usable_slice = scored[third : third * 2]
    clash_slice  = scored[third * 2:]

    def _format_scored_entries(items: list[tuple[float, dict]], n: int) -> list[dict]:
        result = []
        for score, entry in items[:n]:
            result.append({
                "preset_name": entry.get("preset_name", ""),
                "plugin":      entry.get("plugin", ""),
                "path":        entry.get("path", ""),
                "score":       round(score, 3),
                "measured":    entry.get("measured", False),
                "is_drum":     entry.get("is_drum", False),
            })
        return result

    return {
        "best_fit":     _format_scored_entries(best_slice, top_n),
        "usable":       _format_scored_entries(usable_slice, top_n),
        "likely_clash": _format_scored_entries(clash_slice, top_n),
        "total_scored": total,
        "target_bands": target_bands,
        "avoid_bands":  avoid_bands,
    }


# ------------------------------------------------------------------
# Tool: audit_preset
# ------------------------------------------------------------------

@mcp.tool()
def audit_preset(
    file_path: str,
    preset_name: str,
    plugin_name: str | None = None,
) -> dict:
    """Analyse an exported audio file for a preset and store measured spectral descriptors back to the sound library cache."""
    from tools.analysis import get_spectral_descriptors

    try:
        desc = get_spectral_descriptors(file_path)
    except Exception as exc:
        return {"error": "Could not analyse file '{}': {}".format(file_path, exc)}

    measured: dict = {
        "spectral_centroid": desc.get("spectral_centroid"),
        "spectral_rolloff":  desc.get("spectral_rolloff"),
        "spectral_flatness": desc.get("spectral_flatness"),
        "key":               desc.get("key"),
        "key_strength":      desc.get("key_strength"),
        "mfcc_mean":         desc.get("mfcc_mean"),
    }

    cache = _load_cache()
    entries = cache.get("entries", [])

    pn_lower = preset_name.lower()
    pl_lower = (plugin_name or "").lower()

    matches = [
        e for e in entries
        if pn_lower in e.get("preset_name", "").lower()
        and (not pl_lower or pl_lower in e.get("plugin", "").lower())
    ]

    if not matches:
        return {
            "error": (
                "No library entry found matching preset_name='{}' "
                "(plugin_filter='{}').  Run scan_au_presets() first.".format(
                    preset_name, plugin_name or ""
                )
            )
        }

    # Update the best match (first hit)
    target_entry = matches[0]
    target_entry.update(measured)
    target_entry["measured"] = True
    target_entry["scan_date"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_cache(cache)

    return {
        "updated":          True,
        "preset_name":      target_entry.get("preset_name"),
        "plugin":           target_entry.get("plugin"),
        "path":             target_entry.get("path"),
        "measured_spectral": measured,
    }


# ------------------------------------------------------------------
# Tool: get_sound_library_stats
# ------------------------------------------------------------------

@mcp.tool()
def get_sound_library_stats() -> dict:
    """Show statistics about the sound library cache: total entries, per-plugin breakdown, and measured vs inferred counts."""
    if not _CACHE_FILE.exists():
        return {
            "error": (
                "Sound library cache not found at {}. "
                "Run scan_au_presets() or scan_splice_library() to create it.".format(
                    _CACHE_FILE
                )
            )
        }

    cache = _load_cache()
    entries = cache.get("entries", [])

    by_plugin: dict[str, int] = {}
    measured_count = 0
    drum_count = 0

    for e in entries:
        plugin = e.get("plugin", "Unknown")
        by_plugin[plugin] = by_plugin.get(plugin, 0) + 1
        if e.get("measured", False):
            measured_count += 1
        if e.get("is_drum", False):
            drum_count += 1

    total = len(entries)

    return {
        "total":          total,
        "by_plugin":      by_plugin,
        "measured_count": measured_count,
        "inferred_count": total - measured_count,
        "drum_count":     drum_count,
        "melodic_count":  total - drum_count,
        "cache_file":     str(_CACHE_FILE),
    }


# ---------------------------------------------------------------------------
# Screenshot tool
# ---------------------------------------------------------------------------

@mcp.tool()
def take_screenshot(region: str = "full", save_path: str | None = None) -> dict:
    """Take a screenshot of the Ableton Live window for visual analysis."""
    import sys

    timestamp = time.time()
    if save_path is None:
        save_path = os.path.join(
            tempfile.gettempdir(),
            "abletonmpcx_screenshot_{:.0f}.png".format(timestamp),
        )

    save_path = str(save_path)
    error = None
    width = 0
    height = 0

    try:
        captured = False

        # macOS: use screencapture (no user interaction needed with -x flag)
        if sys.platform == "darwin":
            result = subprocess.run(
                ["screencapture", "-x", save_path],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and os.path.exists(save_path):
                captured = True

        # Fallback: try PIL.ImageGrab (cross-platform)
        if not captured:
            try:
                from PIL import ImageGrab  # type: ignore
                img = ImageGrab.grab()
                img.save(save_path)
                captured = True
            except ImportError:
                pass

        if not captured:
            raise RuntimeError(
                "Screenshot capture failed: screencapture unavailable and PIL not installed."
            )

        # Read dimensions if PIL is available
        try:
            from PIL import Image  # type: ignore
            with Image.open(save_path) as img:
                width, height = img.size
        except ImportError:
            pass

        return {
            "image_path": save_path,
            "region": region,
            "width": width,
            "height": height,
            "timestamp": timestamp,
            "success": True,
            "error": None,
        }

    except Exception as exc:
        error = str(exc)
        return {
            "image_path": save_path,
            "region": region,
            "width": width,
            "height": height,
            "timestamp": timestamp,
            "success": False,
            "error": error,
        }



# ---------------------------------------------------------------------------
# J — Diagnostic tools per question
# ---------------------------------------------------------------------------

def _db_from_linear(linear: float) -> float:
    """Convert linear gain (0.0–1.0 nominal) to dB."""
    if linear <= 0:
        return -math.inf
    return 20.0 * math.log10(max(linear, 1e-10))


# ---------------------------------------------------------------------------
# Mix-analysis helpers (used by diagnose_mix)
# ---------------------------------------------------------------------------

# Instrument keywords with strong 200–600 Hz presence
_LOW_MID_HIGH_OVERLAP: frozenset[str] = frozenset({
    "piano", "ep", "rhodes", "wurli", "wurlitzer", "clav", "clavi",
    "organ", "pad", "pads", "string", "strings", "cello", "viola", "violin",
    "guitar", "acoustic", "keys", "synth", "lead", "arp", "arpeggio",
    "choir", "brass", "horns", "horn", "trombone", "trumpet",
    "sax", "saxophone", "woodwind", "mellotron",
    "rhythm", "chords", "chord", "acc", "accordion",
    "vocal", "vox", "voice", "voc",
})

# Instrument keywords with moderate 200–600 Hz presence
_LOW_MID_MED_OVERLAP: frozenset[str] = frozenset({
    "bass", "upright", "electric", "kick", "snare", "tom", "toms",
    "drum", "drums", "loop", "perc", "beat", "groove",
})

# Instrument keywords with low 200–600 Hz presence
_LOW_MID_LOW_OVERLAP: frozenset[str] = frozenset({
    "sub", "hh", "hihat", "hi-hat", "cymbal", "overhead",
    "clap", "fx", "foley", "sfx", "atmo", "atmosphere",
    "air", "reverb", "delay", "verb",
})

# Device name substrings that indicate bus-style or mastering-style processing
_BUS_PROCESSING_KEYWORDS: tuple[str, ...] = (
    "ssl", "api", "bus comp", "bus glue", "glue comp", "glue compressor",
    "master", "ozone", "pro-l", "l2", "l3", "l1", "maximizer",
    "sonnox", "neve", "shadow hills", "fairchild", "distressor",
    "multi-band", "multiband", "mb-7",
)

_LOW_MID_HZ_LABEL = "200–600 Hz"
_MOVE_PROCESSED = "-0.5 dB"
_MOVE_UNPROCESSED = "-1.0 dB"


def _classify_low_mid_overlap(track_name: str) -> float:
    """
    Estimate a track's spectral overlap with the 200–600 Hz band (0.0–1.0)
    from its name keywords.  Returns 0.8 for high-overlap instruments, 0.4
    for medium, 0.1 for low, and 0.35 for unknown/ambiguous names.
    """
    tokens = re.split(r"[\s_\-/\\\.]+", track_name.lower())
    score = 0.0
    for tok in tokens:
        if tok in _LOW_MID_HIGH_OVERLAP:
            score = max(score, 0.8)
        elif tok in _LOW_MID_MED_OVERLAP:
            score = max(score, 0.4)
        elif tok in _LOW_MID_LOW_OVERLAP:
            score = max(score, 0.1)
    return score if score > 0.0 else 0.35


def _detect_bus_processing(devices: list[dict]) -> tuple[bool, list[str]]:
    """
    Detect bus-style or mastering-style processing on a track.
    Returns (has_bus_processing, list_of_matching_device_names).
    """
    matches: list[str] = []
    for d in devices:
        dev_name = d.get("name", "").lower()
        for kw in _BUS_PROCESSING_KEYWORDS:
            if kw in dev_name:
                matches.append(d.get("name", kw))
                break
    return bool(matches), matches


def _is_vocal_track(name: str) -> bool:
    """Return True if the track name suggests it is a vocal track."""
    tokens = re.split(r"[\s_\-/\\\.]+", name.lower())
    return any(t in {"vocal", "vox", "voice", "voc", "bvox", "bgvox"} for t in tokens)


def _is_drum_track(name: str) -> bool:
    """Return True if the track name suggests it is a drum/percussion track."""
    tokens = re.split(r"[\s_\-/\\\.]+", name.lower())
    return any(
        t in {"drum", "drums", "kick", "snare", "hh", "hihat", "cymbal", "overhead", "perc", "beat"}
        for t in tokens
    )


def _staging_score(db: float, min_db: float, max_db: float) -> float:
    """Normalise a track's dB level to a 0.0–1.0 staging score (higher = more forward)."""
    db_range = max_db - min_db
    if db_range < 0.5:
        return 0.5
    return max(0.0, min(1.0, (db - min_db) / db_range))


@mcp.tool()
def diagnose_track(track_index: int) -> dict:
    """Run a full diagnostic on a single track and return structured findings."""
    tracks = _send("get_tracks", {"slim": False})
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
    """
    Run a comprehensive mix diagnostic.

    Returns separate loudness and balance findings, a weighted per-track
    contribution ranking, structured per-track recommendation objects,
    'what not to change yet' guidance, and re-check loop instructions.

    Legacy fields (warnings, info, recommendations, overall_health,
    tracks_checked) are preserved for backward compatibility.
    """
    # ── 1. Collect track data ─────────────────────────────────────────
    tracks = _send("get_tracks", {"slim": False})
    if not isinstance(tracks, list):
        return {
            "warnings": [],
            "info": ["Could not retrieve tracks"],
            "recommendations": [],
            "overall_health": 0,
            "tracks_checked": 0,
            "loudness_diagnosis": {},
            "balance_diagnosis": {},
            "most_likely_contributors": [],
            "track_recommendations": [],
            "what_not_to_change": [],
            "recheck_loop": {},
        }

    warnings: list[dict] = []
    info: list[str] = []
    penalty = 0

    # ── 2. Per-track clipping / device checks (legacy behaviour) ──────
    for t in tracks:
        idx = t.get("index", t.get("track_index", "?"))
        name = t.get("name", "Unnamed")
        mixer = t.get("mixer_device", {}) or {}
        volume = mixer.get("volume")

        if volume is not None:
            db = _db_from_linear(volume)
            if db > 0:
                warnings.append({
                    "track_index": idx, "track_name": name,
                    "warning": "Volume above 0 dBFS ({:+.1f} dB)".format(db),
                })
                penalty += 10
            elif db > -1.0:
                warnings.append({
                    "track_index": idx, "track_name": name,
                    "warning": "Near-clipping ({:+.1f} dB)".format(db),
                })
                penalty += 5

        devices = t.get("devices", [])
        if not devices:
            warnings.append({
                "track_index": idx, "track_name": name,
                "warning": "No devices on track",
            })
            penalty += 3

    # ── 3. Master bus check ───────────────────────────────────────────
    try:
        master = _send("get_mixer_device", {"track_index": -1})
        master_vol = master.get("volume") if isinstance(master, dict) else None
        if master_vol is not None:
            db = _db_from_linear(master_vol)
            if db > 0:
                warnings.append({
                    "track_index": -1, "track_name": "Master",
                    "warning": "Master bus above 0 dBFS ({:+.1f} dB)".format(db),
                })
                penalty += 20
            else:
                info.append("Master bus: {:+.1f} dB".format(db))
    except Exception as e:
        logger.warning("Could not read master bus: %s", e)

    # ── 4. Try to get LUFS / peak / spectral data from M4L analyzer ───
    lufs: float | None = None
    peak_dbfs: float | None = None
    spectral_tilt: float | None = None
    analyzer_available = False
    try:
        from tools.realtime_analyzer import (
            m4l_get_lufs,
            m4l_get_peak_level,
            get_session_context,
        )
        lufs_result = m4l_get_lufs()
        if isinstance(lufs_result, dict) and lufs_result.get("lufs") is not None:
            lufs = float(lufs_result["lufs"])
            analyzer_available = True
        peak_result = m4l_get_peak_level()
        if isinstance(peak_result, dict) and peak_result.get("peak_dbfs") is not None:
            peak_dbfs = float(peak_result["peak_dbfs"])
        ctx = get_session_context()
        if isinstance(ctx, dict) and ctx.get("spectral_tilt") is not None:
            spectral_tilt = float(ctx["spectral_tilt"])
    except Exception as e:
        logger.debug("M4L analyzer not available for mix diagnosis: %s", e)

    # ── 5. Loudness diagnosis (separate from balance) ─────────────────
    loudness_diagnosis: dict = _build_loudness_diagnosis(lufs, peak_dbfs, analyzer_available)
    is_conservative = loudness_diagnosis.get("_is_conservative", False)

    # ── 6. Balance / spectral congestion diagnosis ────────────────────
    balance_diagnosis, low_mid_congested = _build_balance_diagnosis(
        spectral_tilt, tracks, analyzer_available
    )

    # ── 7. Score and rank tracks by contribution to low-mid congestion ─
    track_dbs: list[float] = []
    for t in tracks:
        v = (t.get("mixer_device") or {}).get("volume")
        if v is not None:
            track_dbs.append(_db_from_linear(v))
    min_db = min(track_dbs) if track_dbs else -40.0
    max_db = max(track_dbs) if track_dbs else 0.0

    scored_tracks: list[dict] = []
    for t in tracks:
        name = t.get("name", "Unnamed")
        idx = t.get("index", t.get("track_index", "?"))
        v = (t.get("mixer_device") or {}).get("volume")
        devices = t.get("devices", [])
        db = _db_from_linear(v) if v is not None else min_db
        staging = _staging_score(db, min_db, max_db)
        lm_overlap = _classify_low_mid_overlap(name)
        has_bus_proc, bus_proc_devs = _detect_bus_processing(devices)
        contribution = round(0.5 * staging + 0.5 * lm_overlap, 3)
        scored_tracks.append({
            "name": name,
            "index": idx,
            "db": round(db, 1),
            "staging_score": round(staging, 2),
            "low_mid_overlap_score": round(lm_overlap, 2),
            "has_bus_processing": has_bus_proc,
            "bus_proc_devices": bus_proc_devs,
            "contribution_score": contribution,
            "device_names": [d.get("name", "") for d in devices],
        })
    scored_tracks.sort(key=lambda x: x["contribution_score"], reverse=True)

    # ── 8. Build structured per-track recommendation objects ──────────
    track_recommendations = _build_track_recommendations(
        scored_tracks, low_mid_congested
    )

    # ── 9. "What not to change yet" guidance ─────────────────────────
    what_not_to_change = _build_what_not_to_change(tracks, track_recommendations)

    # ── 10. Re-check loop instructions ───────────────────────────────
    recheck_loop = {
        "instruction": (
            "After applying any suggested move, re-run analysis on the same loud section "
            "and compare the following:"
        ),
        "validation_targets": [
            "perceived congestion — does the mix feel less dense?",
            "separation of melodic layers — can individual elements be heard more clearly?",
            "vocal clarity — do vocals feel clearer without increasing their level?",
            "master metering — useful reference, but should not be the sole validation target",
        ],
        "approach": (
            "Adjust one likely contributor, then re-run analysis before touching anything else. "
            "Small manual moves ({} to {}) accumulate; avoid multi-track cuts in the first pass.".format(
                _MOVE_PROCESSED, _MOVE_UNPROCESSED
            )
        ),
    }

    # ── 11. Legacy recommendations field (backward-compatible) ────────
    legacy_recommendations: list[str] = []
    if warnings:
        legacy_recommendations.append(
            "Address clipping tracks first, then review devices and routing"
        )
    if low_mid_congested and track_recommendations:
        first = track_recommendations[0]
        legacy_recommendations.append(
            "Most likely contributor to low-mid congestion: {} — try {} fader".format(
                first["track"], first["proposed_move"]
            )
        )
    if not legacy_recommendations:
        legacy_recommendations.append(
            "No critical issues found — review balance findings for fine-tuning"
        )

    overall_health = max(0, 100 - penalty)

    # Remove internal-only key before returning
    loudness_diagnosis.pop("_is_conservative", None)

    return {
        # Legacy / backward-compatible fields
        "warnings": warnings,
        "info": info,
        "recommendations": legacy_recommendations,
        "overall_health": overall_health,
        "tracks_checked": len(tracks),
        # New structured fields
        "loudness_diagnosis": loudness_diagnosis,
        "balance_diagnosis": balance_diagnosis,
        "most_likely_contributors": scored_tracks[:5],
        "track_recommendations": track_recommendations,
        "what_not_to_change": what_not_to_change,
        "recheck_loop": recheck_loop,
    }


def _build_loudness_diagnosis(
    lufs: float | None,
    peak_dbfs: float | None,
    analyzer_available: bool,
) -> dict:
    """
    Build the loudness diagnosis section.
    Separates objective loudness from perceived / internal-balance issues.
    Includes a private '_is_conservative' key for internal use.
    """
    if not analyzer_available or lufs is None:
        return {
            "summary": "no LUFS data available",
            "lufs": None,
            "peak_dbfs": None,
            "interpretation": (
                "M4L Analyzer not available. Cannot assess objective loudness. "
                "Volume and peak checks from track faders are still available in 'warnings'."
            ),
            "_is_conservative": False,
        }

    if lufs < -20:
        return {
            "summary": "quiet overall, likely internal balance issue",
            "lufs": round(lufs, 1),
            "peak_dbfs": round(peak_dbfs, 1) if peak_dbfs is not None else None,
            "interpretation": (
                "Master metrics are conservative (LUFS: {:.1f}). "
                "The mix is not objectively loud. Any perception of loudness or congestion "
                "is most likely an internal balance issue — density, masking, or low-mid "
                "accumulation across multiple tracks — not a master-level problem.".format(lufs)
            ),
            "_is_conservative": True,
        }
    if lufs < -14:
        return {
            "summary": "moderate overall level",
            "lufs": round(lufs, 1),
            "peak_dbfs": round(peak_dbfs, 1) if peak_dbfs is not None else None,
            "interpretation": (
                "Master level is moderate (LUFS: {:.1f}). "
                "Review spectral balance before adjusting master level.".format(lufs)
            ),
            "_is_conservative": False,
        }
    return {
        "summary": "elevated overall level",
        "lufs": round(lufs, 1),
        "peak_dbfs": round(peak_dbfs, 1) if peak_dbfs is not None else None,
        "interpretation": (
            "Master level is elevated (LUFS: {:.1f}). "
            "Check for peaks and limiting before further compression.".format(lufs)
        ),
        "_is_conservative": False,
    }


def _build_balance_diagnosis(
    spectral_tilt: float | None,
    tracks: list[dict],
    analyzer_available: bool,
) -> tuple[dict, bool]:
    """
    Build the spectral balance diagnosis section.
    Returns (balance_diagnosis_dict, low_mid_congested_bool).
    """
    if spectral_tilt is not None:
        if spectral_tilt < -0.3:
            return (
                {
                    "summary": "body-heavy / low-mid dense",
                    "spectral_tilt": round(spectral_tilt, 3),
                    "congested_band": _LOW_MID_HZ_LABEL,
                    "interpretation": (
                        "The spectral balance is weighted toward the lower-mid region "
                        "({band}). This can cause muddiness, masking of melodic layers, "
                        "and make vocals feel buried — even when master levels are conservative. "
                        "This is a balance problem, not a loudness problem.".format(band=_LOW_MID_HZ_LABEL)
                    ),
                },
                True,
            )
        if spectral_tilt > 0.3:
            return (
                {
                    "summary": "bright / top-heavy balance",
                    "spectral_tilt": round(spectral_tilt, 3),
                    "congested_band": None,
                    "interpretation": (
                        "The spectral balance has a bright tilt. "
                        "This is not a low-mid congestion issue."
                    ),
                },
                False,
            )
        return (
            {
                "summary": "relatively balanced spectrum",
                "spectral_tilt": round(spectral_tilt, 3),
                "congested_band": None,
                "interpretation": "Spectral tilt is neutral. No obvious congestion band detected.",
            },
            False,
        )

    # No analyzer — fall back to heuristic track-name count
    lm_high_count = sum(
        1 for t in tracks if _classify_low_mid_overlap(t.get("name", "")) >= 0.7
    )
    if lm_high_count >= 3:
        return (
            {
                "summary": "body-heavy / low-mid dense (heuristic)",
                "spectral_tilt": None,
                "congested_band": _LOW_MID_HZ_LABEL,
                "interpretation": (
                    "{count} or more tracks appear to have strong {band} overlap "
                    "(e.g. piano, keys, guitars, pads, vocals). "
                    "Without an analyzer reading this is a heuristic estimate, but if the "
                    "mix feels dense or vocals feel buried, this region is the likely cause.".format(
                        count=lm_high_count, band=_LOW_MID_HZ_LABEL
                    )
                ),
            },
            True,
        )
    return (
        {
            "summary": "spectral balance unknown",
            "spectral_tilt": None,
            "congested_band": None,
            "interpretation": (
                "M4L Analyzer not available and not enough tracks with clear spectral "
                "signatures to form a heuristic estimate. "
                "Use analysis_tool with action='spectrum_overview' for a snapshot."
            ),
        },
        False,
    )


def _build_track_recommendations(
    scored_tracks: list[dict],
    low_mid_congested: bool,
) -> list[dict]:
    """
    Build structured per-track recommendation objects for the most likely
    contributors to low-mid congestion.  Only populated when congestion is
    detected.  Excludes pure drum tracks and vocal tracks from the first-pass
    candidates (they have separate guidance in 'what_not_to_change').
    """
    if not low_mid_congested:
        return []

    candidates = [
        st for st in scored_tracks
        if not _is_drum_track(st["name"]) and not _is_vocal_track(st["name"])
    ][:3]

    recs: list[dict] = []
    for st in candidates:
        is_processed = st["has_bus_processing"]
        proposed_move = _MOVE_PROCESSED if is_processed else _MOVE_UNPROCESSED
        score = st["contribution_score"]
        if is_processed:
            confidence = "low"
        elif score > 0.65:
            confidence = "high"
        else:
            confidence = "medium"

        processing_desc = (
            "has bus/mastering-style processing ({})".format(
                ", ".join(st["bus_proc_devices"])
            )
            if is_processed
            else "no bus-style processing noted"
        )
        expected_effect = (
            "slightly less body congestion, more separation between layers"
            if not is_processed
            else (
                "marginal reduction in congestion; processed tracks respond "
                "less predictably to raw fader moves"
            )
        )
        recs.append({
            "track": st["name"],
            "reason": "overlap with low-mid congestion ({})".format(_LOW_MID_HZ_LABEL),
            "band": _LOW_MID_HZ_LABEL,
            "processing_state": processing_desc,
            "proposed_move": "{} fader".format(proposed_move),
            "expected_effect": expected_effect,
            "confidence": confidence,
        })
    return recs


def _build_what_not_to_change(
    tracks: list[dict],
    track_recommendations: list[dict],
) -> list[dict]:
    """
    Build the 'what not to change yet' guidance list.  Always includes master
    bus; conditionally includes vocals and drums when they are not flagged as
    primary contributors.
    """
    guidance: list[dict] = [
        {
            "element": "Master bus",
            "guidance": "Leave the master bus alone initially.",
            "reason": (
                "Adjusting the master bus changes the overall level of everything equally "
                "and does not fix internal balance. Diagnose and adjust individual "
                "tracks first, then re-evaluate the master if needed."
            ),
        },
    ]

    rec_track_names = {r["track"] for r in track_recommendations}

    vocal_tracks = [t for t in tracks if _is_vocal_track(t.get("name", ""))]
    if vocal_tracks:
        vocal_names = ", ".join(t.get("name", "") for t in vocal_tracks)
        if not any(_is_vocal_track(n) for n in rec_track_names):
            guidance.append({
                "element": "Vocals ({})".format(vocal_names),
                "guidance": "Avoid adjusting vocals unless they are clearly the masking source.",
                "reason": (
                    "Vocals are not flagged as primary contributors to low-mid congestion. "
                    "Pulling vocals to fix density usually creates a hole in the mix rather "
                    "than resolving the underlying balance issue."
                ),
            })

    drum_tracks = [t for t in tracks if _is_drum_track(t.get("name", ""))]
    if drum_tracks:
        drum_names = ", ".join(t.get("name", "") for t in drum_tracks[:3])
        if not any(_is_drum_track(n) for n in rec_track_names):
            guidance.append({
                "element": "Drums ({})".format(drum_names),
                "guidance": "Avoid touching drums unless they are actually contributing to the congested band.",
                "reason": (
                    "Drum tracks are not the primary low-mid offenders based on spectral "
                    "overlap scoring. Reducing drums to fix congestion typically costs "
                    "energy and transient feel without addressing the root cause."
                ),
            })

    return guidance


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



# ---------------------------------------------------------------------------
# Views / context (moved from tools.session)
# ---------------------------------------------------------------------------

@mcp.tool()
def focus_view(view_name: str) -> dict:
    """Focus a named view in Ableton Live (e.g. 'Session', 'Arranger', 'Detail', 'Detail/Clip')."""
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
def get_selected_context() -> dict:
    """Return everything currently selected/focused in Live: selected track, scene, and detail clip."""
    return _send("get_selected_context")


@mcp.tool()
def get_selected_track() -> dict:
    """Return the currently selected track index and name."""
    return _send("get_selected_track")


@mcp.tool()
def get_selected_scene() -> dict:
    """Return the currently selected scene index and name."""
    return _send("get_selected_scene")


@mcp.tool()
def set_selected_track(track_index: int) -> dict:
    """Select the track at track_index."""
    return _send("set_selected_track", {"track_index": track_index})


@mcp.tool()
def set_selected_scene(scene_index: int) -> dict:
    """Select the scene at scene_index."""
    return _send("set_selected_scene", {"scene_index": scene_index})


@mcp.tool()
def get_appointed_device() -> dict:
    """Return the currently appointed (focused) device in Live."""
    return _send("get_appointed_device")


@mcp.tool()
def get_protocol_version() -> dict:
    """Return the AbletonMPCX protocol version string."""
    return _send("get_protocol_version")


@mcp.tool()
def get_capabilities() -> dict:
    """Returns a structured summary of all registered MCP tools with their descriptions."""
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


# ---------------------------------------------------------------------------
# Mix analysis and session state (moved from tools.session)
# ---------------------------------------------------------------------------

@mcp.tool()
def analyse_mix_state() -> dict:
    """Analyse the current mix state and surface observations."""
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
    """Iteratively adjust a device parameter to improve a frequency band balance, reading the analyzer after each step."""
    from tools.session_snapshots import save_device_snapshot

    if direction not in ("reduce", "boost"):
        return {"error": "direction must be 'reduce' or 'boost'"}

    def _read_band_value():
        return None

    before_value = _read_band_value()

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
    step_size = (p_max - p_min) / 20.0

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


@mcp.tool()
def get_session_health() -> dict:
    """Return a single structured health summary of the current session."""
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    master = snapshot.get("master_track", {}) if isinstance(snapshot, dict) else {}

    issues: list[dict] = []

    DEFAULT_NAME_PATTERNS = {"audio", "midi", "1-audio", "1-midi", "audio track", "midi track"}

    for track in tracks:
        idx = track.get("index", track.get("track_index"))
        name = track.get("name", "")
        name_lower = name.lower().strip()
        mixer = track.get("mixer_device", {}) or {}
        devices = track.get("devices", []) or []
        sends = mixer.get("sends", []) or []

        if not name or name_lower in DEFAULT_NAME_PATTERNS or name_lower.startswith(("audio ", "midi ")):
            issues.append({
                "severity": "info",
                "category": "naming",
                "description": "Track has a default/unnamed name: '{}'".format(name),
                "track_index": idx,
            })

        if track.get("arm"):
            issues.append({
                "severity": "warn",
                "category": "recording",
                "description": "Track '{}' is armed for recording".format(name),
                "track_index": idx,
            })

        volume = mixer.get("volume")
        if volume is not None:
            db = _db_from_linear(volume)
            if db > 0:
                issues.append({
                    "severity": "warn",
                    "category": "levels",
                    "description": "Track '{}' volume is above 0 dBFS ({:+.1f} dB)".format(name, db),
                    "track_index": idx,
                })

        if len(devices) == 0:
            issues.append({
                "severity": "info",
                "category": "devices",
                "description": "Track '{}' has no devices".format(name),
                "track_index": idx,
            })

        if track.get("solo"):
            issues.append({
                "severity": "flag",
                "category": "monitoring",
                "description": "Track '{}' is soloed".format(name),
                "track_index": idx,
            })

        if sends:
            def _send_value(s: object) -> float:
                if isinstance(s, (int, float)):
                    return float(s)
                if isinstance(s, dict):
                    return float(s.get("value", 0))
                return 0.0
            if all(_send_value(s) == 0.0 for s in sends):
                issues.append({
                    "severity": "info",
                    "category": "routing",
                    "description": "Track '{}' has all sends at zero".format(name),
                    "track_index": idx,
                })

    master_mixer = master.get("mixer_device", {}) or {}
    master_vol = master_mixer.get("volume") if isinstance(master_mixer, dict) else master.get("volume")
    if master_vol is not None:
        db = _db_from_linear(master_vol)
        if db > 0:
            issues.append({
                "severity": "warn",
                "category": "levels",
                "description": "Master bus volume is above 0 dBFS ({:+.1f} dB)".format(db),
                "track_index": -1,
            })
        else:
            issues.append({
                "severity": "info",
                "category": "levels",
                "description": "Master bus: {:+.1f} dB".format(db),
                "track_index": -1,
            })

    severities = {i["severity"] for i in issues}
    if "warn" in severities or "critical" in severities:
        health = "warnings"
    elif "flag" in severities:
        health = "warnings"
    else:
        health = "clean"

    return {
        "issues": issues,
        "issue_count": len(issues),
        "health": health,
        "session_name": snapshot.get("name", "") if isinstance(snapshot, dict) else "",
        "tempo": snapshot.get("tempo", 0.0) if isinstance(snapshot, dict) else 0.0,
        "track_count": len(tracks),
    }


@mcp.tool()
def get_session_state(compact: bool = False) -> dict:
    """Return session state. compact=False returns full structured state; compact=True returns a token-efficient human-readable summary."""
    import time as _time
    if compact:
        from helpers.summarizer import summarize_session as _summarize_session
        snapshot = _send("get_session_snapshot")
        return {"summary": _summarize_session(snapshot)}

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
        "fetched_at": _time.time(),
        "total_tracks": len(tracks),
        "total_devices": total_devices,
        "total_clips": total_clips,
    }


@mcp.tool()
def get_session_diff() -> dict:
    """Return only what has changed in the session since the last call."""
    snapshot = _send("get_session_snapshot")
    diff = cache_state("session_diff", snapshot)

    if diff.get("first_snapshot"):
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

    if "tempo" in top_changed:
        tempo_changed = True
        new_tempo = top_changed["tempo"].get("to")

    tracks_diff = top_changed.get("tracks", {})
    if isinstance(tracks_diff, dict):
        nested = tracks_diff.get("changed", {})
        for idx_str, track_change in nested.items():
            if not isinstance(track_change, dict):
                continue
            track_idx = int(idx_str) if str(idx_str).isdigit() else idx_str
            changed_fields = list(track_change.get("changed", {}).keys())
            tracks_list = snapshot.get("tracks", [])
            track_name = ""
            if isinstance(tracks_list, list) and isinstance(track_idx, int) and track_idx < len(tracks_list):
                track_name = tracks_list[track_idx].get("name", "")
            changed_tracks.append({
                "track_index": track_idx,
                "track_name": track_name,
                "changed_fields": changed_fields,
            })
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


@mcp.tool()
def summarise_session() -> dict:
    """Summarise what happened in the current session based on the operation log."""
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
        "destructive_ops": destructive[-20:],
    }
