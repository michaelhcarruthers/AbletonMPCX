"""Session recording tools — resampling route setup and arrangement recording."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

from helpers import (
    mcp,
    _send,
)


# ---------------------------------------------------------------------------
# Resampling routing
# ---------------------------------------------------------------------------

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
    except RuntimeError as e:
        logger.debug("Could not set resample track name: %s", e)

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
    except RuntimeError as e:
        logger.debug("Could not disarm resampling track %s: %s", resample_track_index, e)

    routing_reset = False
    try:
        _send("set_track_monitor", {"track_index": resample_track_index, "monitor": 0})
        routing_reset = True
    except RuntimeError as e:
        logger.debug("Could not reset monitor mode for resampling track %s: %s", resample_track_index, e)

    try:
        _send("set_track_input_routing", {"track_index": resample_track_index, "routing": "default"})
    except RuntimeError as e:
        logger.debug("Could not reset input routing for resampling track %s: %s", resample_track_index, e)

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


# ---------------------------------------------------------------------------
# Arrangement recording / render to audio
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
    4. Returns immediately; a background thread stops recording after the bar range elapses.

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
        status ("recording_started"), new_track_index, new_track_name, source_track_name,
        bars_recorded, duration_seconds, note (stop time description)
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
                # Double the loop until the clip length covers what we need.
                # Cap at 10 doublings to prevent runaway loops.
                max_doublings = 10
                doublings = 0
                while clip_length < length_beats and doublings < max_doublings:
                    try:
                        _send("duplicate_clip_loop", {
                            "track_index": source_track_index,
                            "slot_index": source_slot_index,
                        })
                        doublings += 1
                        clip_info = _send("get_clip_info", {
                            "track_index": source_track_index,
                            "slot_index": source_slot_index,
                        })
                        clip_length = float(clip_info.get("length", 0))
                    except RuntimeError:
                        break
                if clip_length < length_beats:
                    warnings.append(
                        "Source clip (length={} beats) may be shorter than requested range "
                        "({} beats); recorded clip may be shorter than expected.".format(
                            clip_length, length_beats)
                    )
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
    except RuntimeError as e:
        logger.debug("Could not stop playing before recording: %s", e)

    # --- Step 7: Start Arrangement recording ---
    try:
        _send("set_record_mode", {"record_mode": True})
    except RuntimeError as e:
        warnings.append("Could not enable record mode: {}".format(e))

    # Jump playhead to start of render range
    try:
        _send("set_arrangement_position", {"position": float(start_beat)})
    except RuntimeError as e:
        warnings.append("Could not set arrangement position: {}".format(e))

    try:
        _send("start_playing")
    except RuntimeError as e:
        # Cleanup on failure
        try:
            _send("set_track_arm", {"track_index": new_track_index, "arm": False})
        except RuntimeError as e2:
            logger.debug("Could not disarm track during recording cleanup: %s", e2)
        return {"error": "Could not start playback: {}".format(e), "warnings": warnings}

    # --- Step 8: Launch background thread to stop recording after duration ---

    def _stop_recording_after_delay():
        time.sleep(duration_seconds + 0.5)
        try:
            _send("stop_playing")
        except RuntimeError as e:
            logger.warning("Could not stop playback after recording: %s", e)
        try:
            _send("set_record_mode", {"record_mode": False})
        except RuntimeError as e:
            logger.debug("Could not disable record mode after recording: %s", e)
        try:
            _send("set_track_arm", {"track_index": new_track_index, "arm": False})
        except RuntimeError as e:
            logger.warning("Could not disarm new track after recording: %s", e)

    _t = threading.Thread(target=_stop_recording_after_delay, daemon=True)
    _t.start()

    # --- Step 9–11: Return immediately; recording will stop automatically ---
    result: dict[str, Any] = {
        "status": "recording_started",
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
        "note": "Recording will stop automatically after {:.1f} seconds.".format(duration_seconds + 0.5),
    }
    if warnings:
        result["warnings"] = warnings
    return result
