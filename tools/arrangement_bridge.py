"""Arrangement automation tools — write volume and dynamic automation
via the Remote Script (port 9877). No M4L bridge device required.
"""
from __future__ import annotations

from typing import Any

from helpers import mcp, _send


@mcp.tool()
def write_dynamic_automation(
    track_name: str,
    direction: str,
    bar_start: int,
    bar_end: int,
    curve: str = "linear",
) -> dict:
    """Ramp track volume and filter cutoff up (louder) or down (softer) across a bar range in arrangement view."""
    from helpers.preflight import get_session_state, get_track_index_by_name, get_device_index_by_name
    from helpers.timing import bar_range_to_seconds

    # --- validate curve ---
    VALID_CURVES = ("ease_in", "ease_out", "linear")
    if curve not in VALID_CURVES:
        raise ValueError(f"Invalid curve '{curve}'. Must be one of: {VALID_CURVES}")

    # --- resolve track ---
    track_index = get_track_index_by_name(track_name)
    if track_index is None:
        return {"error": f"Track '{track_name}' not found.", "applied": False}

    # --- resolve timing (all Python, no AI reasoning) ---
    session = get_session_state()
    tempo = session["tempo"]
    time_sig_num = session["time_sig_numerator"]
    start_secs, end_secs = bar_range_to_seconds(bar_start, bar_end, tempo, time_sig_num)

    # --- direction config ---
    direction_lower = direction.strip().lower()
    if direction_lower not in ("louder", "softer"):
        return {"error": f"direction must be 'louder' or 'softer', got '{direction}'", "applied": False}

    going_up = direction_lower == "louder"

    # Volume: louder = 0.5 → 0.85 range shift, softer = 0.85 → 0.5
    # These are normalised Live mixer values (0.0–1.0 maps to -inf to +6dB)
    # 0.85 ≈ 0dB, 0.5 ≈ -12dB
    volume_start = 0.5 if going_up else 0.85
    volume_end   = 0.85 if going_up else 0.5

    # Filter cutoff: louder = open up, softer = close down
    filter_start = 0.4 if going_up else 0.8
    filter_end   = 0.8 if going_up else 0.4

    # --- build automation points ---
    def make_envelope(val_start: float, val_end: float) -> list[dict]:
        """Build envelope points for a 2-point ramp with optional curve shaping."""
        if curve == "ease_in":
            mid_secs = start_secs + (end_secs - start_secs) * 0.7
            mid_val = val_start + (val_end - val_start) * 0.2
            return [
                {"time": start_secs, "value": val_start},
                {"time": mid_secs,   "value": mid_val},
                {"time": end_secs,   "value": val_end},
            ]
        elif curve == "ease_out":
            mid_secs = start_secs + (end_secs - start_secs) * 0.3
            mid_val = val_start + (val_end - val_start) * 0.8
            return [
                {"time": start_secs, "value": val_start},
                {"time": mid_secs,   "value": mid_val},
                {"time": end_secs,   "value": val_end},
            ]
        else:
            return [
                {"time": start_secs, "value": val_start},
                {"time": end_secs,   "value": val_end},
            ]

    applied_automations = []

    # --- write volume automation ---
    try:
        vol_result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "parameter_type": "volume",
            "points": make_envelope(volume_start, volume_end),
        })
        applied_automations.append("volume")
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "automations_written": [],
        }

    # --- attempt filter cutoff automation (graceful skip if no filter device) ---
    filter_result = None
    filter_device_index = get_device_index_by_name(track_index, "eq")
    if filter_device_index is None:
        filter_device_index = get_device_index_by_name(track_index, "filter")
    if filter_device_index is None:
        filter_device_index = get_device_index_by_name(track_index, "auto filter")

    if filter_device_index is not None:
        try:
            filter_result = _send("write_arrangement_automation", {
                "track_index": track_index,
                "parameter_type": "device_parameter",
                "device_index": filter_device_index,
                "parameter_index": 0,
                "points": make_envelope(filter_start, filter_end),
            })
            applied_automations.append("filter_cutoff")
        except Exception as e:
            filter_result = {"error": str(e)}

    return {
        "status": "ok",
        "direction": direction_lower,
        "automations_written": applied_automations,
    }


@mcp.tool()
def write_arrangement_volume_automation(
    track_index: int,
    start_beat: float,
    end_beat: float,
    start_value: float,
    end_value: float,
    curve: str = "linear",
) -> dict:
    """Write volume automation to a track in arrangement view.

    Uses the Remote Script (port 9877) — does NOT require the M4L bridge device.

    track_index: zero-based track index
    start_beat: song position in beats where ramp starts (beat 0 = bar 1)
    end_beat: song position in beats where ramp ends
    start_value: normalised volume at start (0.0 = silence, 0.85 ≈ 0dB, 1.0 = +6dB)
    end_value: normalised volume at end
    curve: 'linear' (default), 'ease_in', or 'ease_out'
    """
    VALID_CURVES = ("linear", "ease_in", "ease_out")
    if curve not in VALID_CURVES:
        return {"error": f"curve must be one of {VALID_CURVES}", "applied": False}

    duration = end_beat - start_beat
    if duration <= 0:
        return {"error": "end_beat must be greater than start_beat", "applied": False}

    if curve == "ease_in":
        mid_beat = start_beat + duration * 0.7
        mid_val = start_value + (end_value - start_value) * 0.2
        points = [
            {"time": start_beat, "value": start_value},
            {"time": mid_beat, "value": mid_val},
            {"time": end_beat, "value": end_value},
        ]
    elif curve == "ease_out":
        mid_beat = start_beat + duration * 0.3
        mid_val = start_value + (end_value - start_value) * 0.8
        points = [
            {"time": start_beat, "value": start_value},
            {"time": mid_beat, "value": mid_val},
            {"time": end_beat, "value": end_value},
        ]
    else:
        points = [
            {"time": start_beat, "value": start_value},
            {"time": end_beat, "value": end_value},
        ]

    try:
        result = _send("write_arrangement_automation", {
            "track_index": track_index,
            "parameter_type": "volume",
            "points": points,
        })
    except RuntimeError as e:
        return {"error": str(e), "applied": False}
    return {
        "status": "ok",
        "track_index": track_index,
        "start_beat": start_beat,
        "end_beat": end_beat,
        "start_value": start_value,
        "end_value": end_value,
        "curve": curve,
        "points_written": len(points),
        "result": result,
    }


@mcp.tool()
def mix_section(
    bar_start: int,
    bar_end: int,
    tracks: list[dict],
    curve: str = "ease_in_out",
    transition_bars: float = 0.5,
    time_signature_numerator: int | None = None,
) -> dict:
    """Write volume automation for multiple tracks across a bar range in one call.

    Use this to reshape the mix balance for a section — push drums back, bring pad
    forward, fade bass down — all in one tool call instead of one per track.

    bar_start: first bar of the section (1-indexed)
    bar_end: last bar of the section (exclusive — automation ends at the start of this bar)
    tracks: list of track mix specs, each dict with:
      - track_index (int): zero-based track index
      - volume (float): target normalised volume for the section body (0.0–1.0)
                        0.85 ≈ 0dB, 0.70 ≈ -3dB, 0.50 ≈ -12dB, 0.0 = silence
      - start_volume (float, optional): volume at bar_start (defaults to current fader value)
      - end_volume (float, optional): volume at bar_end (defaults to same as volume)
      - per_bar (list[dict], optional): fine-grained per-bar level map:
            [{"bar": 5, "volume": 0.6}, {"bar": 6, "volume": 0.4}, ...]
            When provided, overrides volume/start_volume/end_volume for this track
            and writes one automation point per listed bar instead of a simple ramp.

    curve: shape of the volume ramp — "linear", "ease_in", "ease_out", "ease_in_out" (default)
    transition_bars: how many bars to ramp in/out at section boundaries (default 0.5)
    time_signature_numerator: override the time signature numerator (default: read from song)

    Returns a summary of what was written and any errors per track.

    Volume reference:
      1.0  = +6 dB (boost)
      0.85 = 0 dB  (unity, default fader position)
      0.70 = -3 dB
      0.60 = -6 dB
      0.50 = -12 dB
      0.35 = -18 dB
      0.0  = silence
    """
    from tools.session import _get_time_sig_numerator, _bars_beats_to_song_time

    VALID_CURVES = ("linear", "ease_in", "ease_out", "ease_in_out")
    if curve not in VALID_CURVES:
        raise ValueError("curve must be one of {}".format(VALID_CURVES))

    tsn = _get_time_sig_numerator(time_signature_numerator)

    # Get current track volumes for defaults
    try:
        tracks_info = _send("get_tracks", {"slim": False})
        if isinstance(tracks_info, list):
            current_volumes = {t["index"]: t.get("volume", 0.85) for t in tracks_info}
        else:
            current_volumes = {}
    except Exception:
        current_volumes = {}

    # Build the batch writes list
    writes = []
    track_results = []

    for spec in tracks:
        track_index = int(spec["track_index"])
        current_vol = current_volumes.get(track_index, 0.85)

        per_bar = spec.get("per_bar")

        if per_bar:
            # Per-bar mode: write one automation point at the start of each specified bar
            points = []
            for entry in per_bar:
                bar = int(entry["bar"])
                vol = max(0.0, min(1.0, float(entry["volume"])))
                beat_time = _bars_beats_to_song_time(bar, 1.0, tsn)
                points.append({"time": beat_time, "value": vol})
            # Sort by time to be safe
            points.sort(key=lambda p: p["time"])
        else:
            # Simple ramp mode
            target_vol = max(0.0, min(1.0, float(spec["volume"])))
            start_vol = max(0.0, min(1.0, float(spec.get("start_volume", current_vol))))
            end_vol = max(0.0, min(1.0, float(spec.get("end_volume", target_vol))))

            # Convert bars to beats
            start_beat = _bars_beats_to_song_time(bar_start, 1.0, tsn)
            body_beat = _bars_beats_to_song_time(bar_start, 1.0 + transition_bars * tsn, tsn)
            end_beat = _bars_beats_to_song_time(bar_end, 1.0, tsn)
            fade_out_beat = max(body_beat, end_beat - transition_bars * tsn)

            if curve == "ease_in_out":
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": body_beat, "value": target_vol},
                    {"time": fade_out_beat, "value": target_vol},
                    {"time": end_beat, "value": end_vol},
                ]
            elif curve == "ease_in":
                mid_beat = start_beat + (end_beat - start_beat) * 0.7
                mid_val = start_vol + (target_vol - start_vol) * 0.2
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": mid_beat, "value": mid_val},
                    {"time": end_beat, "value": end_vol},
                ]
            elif curve == "ease_out":
                mid_beat = start_beat + (end_beat - start_beat) * 0.3
                mid_val = start_vol + (target_vol - start_vol) * 0.8
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": mid_beat, "value": mid_val},
                    {"time": end_beat, "value": end_vol},
                ]
            else:  # linear
                points = [
                    {"time": start_beat, "value": start_vol},
                    {"time": end_beat, "value": end_vol},
                ]

            # Deduplicate consecutive identical points to keep automation tidy
            deduped = [points[0]]
            for pt in points[1:]:
                if pt["time"] != deduped[-1]["time"]:
                    deduped.append(pt)
            points = deduped

        writes.append({
            "track_index": track_index,
            "parameter_type": "volume",
            "points": points,
            "clear_range": True,
        })
        track_results.append({"track_index": track_index, "points": len(points)})

    # Send as batch
    try:
        result = _send("write_arrangement_automation_batch", {"writes": writes})
        writes_applied = result.get("writes_applied", len(writes))
        batch_errors = result.get("errors", [])
    except Exception as e:
        # Fallback: send individually if batch command not yet available
        writes_applied = 0
        batch_errors = []
        for write in writes:
            try:
                _send("write_arrangement_automation", write)
                writes_applied += 1
            except Exception as we:
                batch_errors.append({"track_index": write["track_index"], "error": str(we)})

    return {
        "status": "ok",
        "bar_start": bar_start,
        "bar_end": bar_end,
        "tracks_written": writes_applied,
        "tracks_requested": len(writes),
        "track_results": track_results,
        "errors": batch_errors,
        "curve": curve,
    }


@mcp.tool()
def analyze_section_levels(
    bar: int,
    track_indices: list[int] | None = None,
    time_signature_numerator: int | None = None,
) -> dict:
    """Read the current volume (fader or automation) for all tracks at a specific bar.

    Returns per-track volume levels at the given bar position so Claude can assess
    the current mix balance before deciding what to change.

    bar: 1-indexed bar number to sample levels at
    track_indices: optional list of track indices to check (default: all tracks)
    time_signature_numerator: override time sig numerator (default: read from song)

    Returns per-track volumes with dB equivalents and a balance summary.

    Volume → dB reference (Live's mixer scale):
      1.0  → +6 dB
      0.85 → 0 dB  (unity)
      0.70 → -3 dB
      0.50 → -12 dB
      0.35 → -18 dB
    """
    import math
    from tools.session import _get_time_sig_numerator, _bars_beats_to_song_time

    tsn = _get_time_sig_numerator(time_signature_numerator)
    beat_position = _bars_beats_to_song_time(bar, 1.0, tsn)

    # Get all tracks
    try:
        all_tracks = _send("get_tracks", {"slim": False})
        if not isinstance(all_tracks, list):
            return {"error": "Could not get tracks"}
    except Exception as e:
        return {"error": str(e)}

    if track_indices is not None:
        track_filter = set(track_indices)
        all_tracks = [t for t in all_tracks if (t.get("index") if "index" in t else t.get("track_index")) in track_filter]

    def _track_idx(t: dict) -> int:
        """Return a consistent track index from a track dict (handles both key names)."""
        return t.get("index") if "index" in t else t.get("track_index", 0)

    def vol_to_db(v: float) -> float:
        """Approximate dB from Live's normalised mixer value."""
        if v <= 0.0:
            return -float("inf")
        # Live uses a roughly piecewise curve; approximate:
        # 0.85 ≈ 0dB, linear above, logarithmic below
        if v >= 0.85:
            return round((v - 0.85) / 0.15 * 6.0, 1)
        else:
            return round(20.0 * math.log10(v / 0.85), 1)

    # Try to read automation value at beat_position; fall back to fader value
    levels = []
    for t in all_tracks:
        t_idx = _track_idx(t)
        t_name = t.get("name", "Track {}".format(t_idx))
        fader_vol = float(t.get("volume", 0.85))

        # Attempt to read automation at this beat position
        auto_vol = None
        try:
            auto_result = _send("get_automation_value_at", {
                "track_index": t_idx,
                "parameter_type": "volume",
                "beat_position": beat_position,
            })
            if isinstance(auto_result, dict) and "value" in auto_result:
                auto_vol = float(auto_result["value"])
        except Exception:
            pass  # command may not exist — fall back to fader

        effective_vol = auto_vol if auto_vol is not None else fader_vol
        source = "automation" if auto_vol is not None else "fader"

        levels.append({
            "track_index": t_idx,
            "track_name": t_name,
            "volume": round(effective_vol, 4),
            "volume_db": vol_to_db(effective_vol),
            "source": source,
            "muted": bool(t.get("mute", False)),
        })

    # Sort by volume descending (loudest first)
    levels.sort(key=lambda x: x["volume"], reverse=True)

    # Build a quick balance summary
    active = [l for l in levels if not l["muted"] and l["volume"] > 0.01]
    if active:
        loudest = active[0]
        quietest = active[-1]
        dynamic_range_db = loudest["volume_db"] - quietest["volume_db"]
        summary = "Loudest: {} ({} dB). Quietest: {} ({} dB). Range: {:.1f} dB.".format(
            loudest["track_name"], loudest["volume_db"],
            quietest["track_name"], quietest["volume_db"],
            dynamic_range_db,
        )
    else:
        summary = "No active tracks at bar {}.".format(bar)

    return {
        "bar": bar,
        "beat_position": beat_position,
        "levels": levels,
        "track_count": len(levels),
        "summary": summary,
    }
