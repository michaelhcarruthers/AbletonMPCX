"""Chop tools — audio clip chopping by equal slices, transients, and drum rack distribution."""
from __future__ import annotations

from typing import Any

from helpers import (
    mcp,
    _send,
)


# ---------------------------------------------------------------------------
# Equal-slice chopping
# ---------------------------------------------------------------------------

@mcp.tool()
def chop_clip_to_slots(
    track_index: int,
    slot_index: int,
    num_chops: int,
    target_track_index: int | None = None,
    start_slot_index: int | None = None,
) -> dict:
    """Divide a clip into equal slices and place each in a new clip slot.

    Reads the source clip length and creates `num_chops` equal slices,
    placing each in `(target_track_index, start_slot_index + i)`.

    Args:
        track_index: Track containing the source clip.
        slot_index: Clip slot index of the source clip.
        num_chops: Number of equal slices to create.
        target_track_index: Track to place chops in (defaults to source track).
        start_slot_index: First slot for chops (defaults to slot_index + 1 if
            same track, else 0).

    Returns:
        dict with chops_created, track_index, source_slot_index, slice_length, and chops list.
    """
    clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
    clip_length = float(clip_info.get("length", 0.0)) if isinstance(clip_info, dict) else 0.0

    if clip_length <= 0.0 or num_chops <= 0:
        return {
            "chops_created": 0,
            "track_index": track_index,
            "source_slot_index": slot_index,
            "slice_length": 0.0,
            "chops": [],
        }

    slice_length = clip_length / num_chops
    t_target = target_track_index if target_track_index is not None else track_index

    if start_slot_index is not None:
        base_slot = start_slot_index
    elif t_target == track_index:
        base_slot = slot_index + 1
    else:
        base_slot = 0

    chops = []
    _send("begin_undo_step", {"name": "chop_clip_to_slots"})
    try:
        for i in range(num_chops):
            dest_slot = base_slot + i
            start = i * slice_length
            end = start + slice_length
            _send("create_clip", {"track_index": t_target, "slot_index": dest_slot, "length": slice_length})
            _send("set_clip_loop", {
                "track_index": t_target,
                "slot_index": dest_slot,
                "loop_start": 0.0,
                "loop_end": slice_length,
            })
            _send("set_clip_markers", {
                "track_index": t_target,
                "slot_index": dest_slot,
                "start_marker": 0.0,
                "end_marker": slice_length,
            })
            chops.append({"slot_index": dest_slot, "start": start, "end": end})
    finally:
        _send("end_undo_step")

    return {
        "chops_created": len(chops),
        "track_index": t_target,
        "source_slot_index": slot_index,
        "slice_length": slice_length,
        "chops": chops,
    }


# ---------------------------------------------------------------------------
# Transient-based chopping
# ---------------------------------------------------------------------------

@mcp.tool()
def chop_clip_on_transients(
    track_index: int,
    slot_index: int,
    file_path: str,
    target_track_index: int | None = None,
    start_slot_index: int | None = None,
    sensitivity: float = 0.5,
) -> dict:
    """Divide a clip at detected transient onsets and place each slice in a new clip slot.

    Uses librosa to detect onset times in the audio file, then creates one
    new clip per onset-to-onset region.

    Args:
        track_index: Track containing the source clip.
        slot_index: Clip slot index of the source clip.
        file_path: Absolute path to the audio file to analyse.
        target_track_index: Track to place chops in (defaults to source track).
        start_slot_index: First slot index for chops.
        sensitivity: 0.0–1.0, higher = fewer onsets (default 0.5).
            Maps to librosa delta: `delta = 0.07 + (1.0 - sensitivity) * 0.2`.

    Returns:
        dict with chops_created, onset_count, file_path, sensitivity, and chops list.

    Raises:
        ImportError: If librosa is not installed.
    """
    try:
        import librosa  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "librosa is required for transient-based chopping. "
            "Install it with: pip install librosa soundfile"
        ) from exc

    clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": slot_index})
    clip_length = float(clip_info.get("length", 0.0)) if isinstance(clip_info, dict) else 0.0

    y, sr = librosa.load(file_path, sr=None, mono=True)
    delta = 0.07 + (1.0 - max(0.0, min(1.0, sensitivity))) * 0.2
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, delta=delta)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()

    # Trim to onsets that fit within the clip
    if clip_length > 0.0:
        onset_times = [t for t in onset_times if t < clip_length]

    t_target = target_track_index if target_track_index is not None else track_index
    if start_slot_index is not None:
        base_slot = start_slot_index
    elif t_target == track_index:
        base_slot = slot_index + 1
    else:
        base_slot = 0

    boundaries = onset_times + ([clip_length] if clip_length > 0.0 else [])
    chops = []
    _send("begin_undo_step", {"name": "chop_clip_on_transients"})
    try:
        for i in range(len(boundaries) - 1):
            start_sec = boundaries[i]
            end_sec = boundaries[i + 1]
            length = end_sec - start_sec
            if length <= 0.0:
                continue
            dest_slot = base_slot + i
            _send("create_clip", {"track_index": t_target, "slot_index": dest_slot, "length": length})
            _send("set_clip_loop", {
                "track_index": t_target,
                "slot_index": dest_slot,
                "loop_start": 0.0,
                "loop_end": length,
            })
            _send("set_clip_markers", {
                "track_index": t_target,
                "slot_index": dest_slot,
                "start_marker": 0.0,
                "end_marker": length,
            })
            chops.append({"slot_index": dest_slot, "start_sec": start_sec, "end_sec": end_sec})
    finally:
        _send("end_undo_step")

    return {
        "chops_created": len(chops),
        "onset_count": len(onset_times),
        "file_path": file_path,
        "sensitivity": sensitivity,
        "chops": chops,
    }


# ---------------------------------------------------------------------------
# Drum rack distribution
# ---------------------------------------------------------------------------

@mcp.tool()
def distribute_chops_to_drum_rack(
    track_index: int,
    slot_indices: list[int],
    drum_rack_track_index: int,
    drum_rack_device_index: int,
    start_pad_note: int = 36,
) -> dict:
    """Map a list of clip chops to drum rack pads via MIDI clips.

    For each slot index, creates a new scene, creates a MIDI clip in the
    drum rack track, and inserts a single note at the corresponding pad pitch
    (`start_pad_note + i`).

    Args:
        track_index: Track holding the source chop clips.
        slot_indices: List of slot indices to map (one per pad).
        drum_rack_track_index: Track index containing the drum rack.
        drum_rack_device_index: Device index of the drum rack (for reference).
        start_pad_note: MIDI note number for the first pad (default 36 = C1).

    Returns:
        dict with pads_mapped, start_pad_note, and drum_rack_track_index.
    """
    pads_mapped = 0
    for i, si in enumerate(slot_indices):
        note = start_pad_note + i
        # Create a new scene for this chop
        try:
            _send("create_scene", {"scene_index": -1})
        except Exception:
            pass
        scene_index = i  # best-effort: use chop index as scene index

        clip_length = 1.0
        try:
            clip_info = _send("get_clip_info", {"track_index": track_index, "slot_index": si})
            if isinstance(clip_info, dict):
                clip_length = float(clip_info.get("length", 1.0))
        except Exception:
            pass

        try:
            _send("create_clip", {
                "track_index": drum_rack_track_index,
                "slot_index": scene_index,
                "length": clip_length,
            })
            _send("replace_all_notes", {
                "track_index": drum_rack_track_index,
                "slot_index": scene_index,
                "notes": [{"pitch": note, "start_time": 0.0, "duration": clip_length * 0.9, "velocity": 100, "mute": False}],
            })
            pads_mapped += 1
        except Exception:
            pass

    return {
        "pads_mapped": pads_mapped,
        "start_pad_note": start_pad_note,
        "drum_rack_track_index": drum_rack_track_index,
    }
