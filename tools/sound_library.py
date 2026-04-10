"""Sound library tools — AU preset scanning, Splice library scanning, and preset recommendations."""
from __future__ import annotations

import collections
import datetime
import json
import logging
import math
import os
import pathlib
import plistlib
import re
import threading

logger = logging.getLogger(__name__)

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
