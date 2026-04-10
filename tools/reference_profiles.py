"""Reference profile tools — store and compare clip feel, mix state, and audio references."""
from __future__ import annotations

import datetime
import logging
import os

logger = logging.getLogger(__name__)

import helpers
from helpers import (
    _send,
    _reference_profiles,
    _reference_profiles_lock,
    _audio_analysis_cache,
    _audio_analysis_cache_lock,
    _get_memory,
    _save_memory,
    _save_reference_profile,
    _load_reference_profiles_from_project,
)
from tools.audio_analysis import _analyse_audio_file
from tools.humanization import _std_dev


def designate_reference_clip(
    track_index: int,
    slot_index: int,
    label: str = "default",
) -> dict:
    """Analyse the feel of a MIDI clip and store it as a named reference profile."""
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


def compare_clip_feel(
    track_index: int,
    slot_index: int,
    reference_label: str = "default",
) -> dict:
    """Compare the feel of a MIDI clip against a stored reference profile."""
    with _reference_profiles_lock:
        has_label = reference_label in _reference_profiles
    if not has_label:
        # Try loading from project memory
        _load_reference_profiles_from_project()
    with _reference_profiles_lock:
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


def designate_reference_mix_state(
    label: str = "default",
    scene_index: int | None = None,
) -> dict:
    """Capture the current mix state as a named reference profile."""
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


def compare_mix_state(
    reference_label: str = "default",
    scene_index: int | None = None,
) -> dict:
    """Compare the current mix state against a stored reference mix profile."""
    with _reference_profiles_lock:
        has_label = reference_label in _reference_profiles
    if not has_label:
        _load_reference_profiles_from_project()
    with _reference_profiles_lock:
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


def designate_reference_audio(
    file_path: str,
    label: str = "default_audio",
    duration_limit: float = 300.0,
) -> dict:
    """Analyse an audio file and store it as a named reference audio profile."""
    result = _analyse_audio_file(file_path, duration_limit=duration_limit)

    profile = dict(result)
    profile["type"] = "audio_analysis"
    profile["label"] = label
    profile["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_reference_profile(label, profile)
    with _audio_analysis_cache_lock:
        _audio_analysis_cache[label] = profile

    return {k: v for k, v in profile.items() if k != "type"}


def compare_audio(
    file_path: str,
    reference_label: str = "default_audio",
    duration_limit: float = 300.0,
) -> dict:
    """Analyse an audio file and compare it against a stored reference audio profile."""
    with _reference_profiles_lock:
        has_label = reference_label in _reference_profiles
    if not has_label:
        _load_reference_profiles_from_project()
    with _reference_profiles_lock:
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


def compare_audio_sections(
    file_path: str,
    reference_label: str = "default_audio",
    num_sections: int = 4,
    duration_limit: float = 300.0,
) -> dict:
    """Split a target audio file into N equal sections and compare each against the reference."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        raise ImportError(
            "librosa and numpy are required for audio analysis. "
            "Install with: pip install librosa soundfile"
        )

    with _reference_profiles_lock:
        has_label = reference_label in _reference_profiles
    if not has_label:
        _load_reference_profiles_from_project()
    with _reference_profiles_lock:
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


def list_reference_profiles() -> dict:
    """List all stored reference profiles (both in-process and persisted)."""
    _load_reference_profiles_from_project()
    profiles = []
    with _reference_profiles_lock:
        items = sorted(_reference_profiles.items())
    for label, p in items:
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


def delete_reference_profile(label: str) -> dict:
    """Delete a reference profile by label (in-process and from project memory)."""
    removed_memory = False
    with _reference_profiles_lock:
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
        except Exception as e:
            logger.warning("Failed to delete memory reference profile '%s': %s", label, e)
    return {"deleted": label, "removed_from_disk": removed_memory}
