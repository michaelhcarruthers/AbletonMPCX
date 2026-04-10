"""
tools/theory.py — Harmony and key analysis tools for AMCPX.
"""
from __future__ import annotations
from helpers import mcp, _send

# ---------------------------------------------------------------------------
# Music theory helpers
# ---------------------------------------------------------------------------

CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Intervals for each mode (semitones from root)
SCALE_INTERVALS = {
    "major":      [0, 2, 4, 5, 7, 9, 11],
    "minor":      [0, 2, 3, 5, 7, 8, 10],
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
    "phrygian":   [0, 1, 3, 5, 7, 8, 10],
    "lydian":     [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian":    [0, 1, 3, 5, 6, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}

def _pitch_class(midi_note: int) -> int:
    return midi_note % 12

def _note_name(pitch_class: int) -> str:
    return CHROMATIC[pitch_class % 12]

def _scale_pitch_classes(root: int, mode: str) -> set[int]:
    intervals = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["major"])
    return {(root + i) % 12 for i in intervals}

def _detect_key(pitch_classes: list[int]) -> tuple[str, str, float]:
    """Detect the most likely key from a list of pitch classes.
    Returns (root_name, mode, confidence_0_to_1).
    """
    if not pitch_classes:
        return ("C", "major", 0.0)

    from collections import Counter
    counts = Counter(pitch_classes)
    total = sum(counts.values())

    best_score = -1.0
    best_root = 0
    best_mode = "major"

    for mode in ["major", "minor", "dorian", "mixolydian", "phrygian"]:
        for root in range(12):
            scale = _scale_pitch_classes(root, mode)
            score = sum(counts[pc] for pc in scale) / total
            if score > best_score:
                best_score = score
                best_root = root
                best_mode = mode

    return (_note_name(best_root), best_mode, round(best_score, 3))

def _nearest_in_key(midi_note: int, root: int, mode: str) -> int:
    """Return the nearest in-key MIDI note to the given note."""
    scale = _scale_pitch_classes(root, mode)
    pc = _pitch_class(midi_note)
    if pc in scale:
        return midi_note
    # Try up and down
    for delta in range(1, 7):
        if (pc + delta) % 12 in scale:
            return midi_note + delta
        if (pc - delta) % 12 in scale:
            return midi_note - delta
    return midi_note

def _invert_chord(notes: list[int]) -> list[int]:
    """Return the first inversion of a chord (move lowest note up an octave)."""
    if len(notes) < 2:
        return notes
    sorted_notes = sorted(notes)
    return sorted_notes[1:] + [sorted_notes[0] + 12]


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

def check_key(
    track_index: int,
    slot_index: int,
    mode_hint: str | None = None,
) -> dict:
    """Analyse the MIDI notes in a clip and detect key, flag out-of-key notes, and suggest fixes.

    track_index: zero-based track index
    slot_index: zero-based Session View slot index
    mode_hint: optional mode to test against (major, minor, dorian, etc.) — if omitted, auto-detects

    Returns:
      - detected_key: root + mode with confidence
      - out_of_key_notes: list of notes with suggested in-key replacements
      - chord_stack: unique pitch classes present
      - inversion_suggestion: first inversion of the chord stack if it improves voice leading
    """
    try:
        notes_result = _send("get_notes", {"track_index": track_index, "slot_index": slot_index})
        notes = notes_result.get("notes", []) if isinstance(notes_result, dict) else notes_result
    except RuntimeError as e:
        return {"error": str(e)}

    if not notes:
        return {"error": "No notes found in clip"}

    pitch_classes = [_pitch_class(int(n["pitch"])) for n in notes]

    root_name, mode, confidence = _detect_key(pitch_classes)

    if mode_hint and mode_hint.lower() in SCALE_INTERVALS:
        # Re-score with the hinted mode
        mode = mode_hint.lower()
        from collections import Counter
        counts = Counter(pitch_classes)
        total = sum(counts.values())
        best_root = 0
        best_score = -1.0
        for root in range(12):
            scale = _scale_pitch_classes(root, mode)
            score = sum(counts[pc] for pc in scale) / total
            if score > best_score:
                best_score = score
                best_root = root
        root_name = _note_name(best_root)
        confidence = round(best_score, 3)

    root_pc = CHROMATIC.index(root_name)
    scale_pcs = _scale_pitch_classes(root_pc, mode)

    # Find out-of-key notes
    out_of_key = []
    for n in notes:
        pitch = int(n["pitch"])
        pc = _pitch_class(pitch)
        if pc not in scale_pcs:
            suggested = _nearest_in_key(pitch, root_pc, mode)
            out_of_key.append({
                "pitch": pitch,
                "note_name": f"{_note_name(pc)}{pitch // 12 - 1}",
                "position": n.get("position", 0.0),
                "suggested_pitch": suggested,
                "suggested_note_name": f"{_note_name(_pitch_class(suggested))}{suggested // 12 - 1}",
                "semitones_to_fix": suggested - pitch,
            })

    # Chord stack (unique pitch classes, sorted)
    unique_pcs = sorted(set(pitch_classes))
    chord_stack = [_note_name(pc) for pc in unique_pcs]

    # Inversion suggestion (use MIDI pitches of the chord)
    chord_pitches = sorted(set(int(n["pitch"]) for n in notes))
    inversion = _invert_chord(chord_pitches)

    return {
        "detected_key": {
            "root": root_name,
            "mode": mode,
            "key_string": f"{root_name} {mode}",
            "confidence": confidence,
        },
        "total_notes": len(notes),
        "out_of_key_count": len(out_of_key),
        "out_of_key_notes": out_of_key,
        "chord_stack": chord_stack,
        "chord_stack_pitch_classes": unique_pcs,
        "in_key_percentage": round((len(notes) - len(out_of_key)) / len(notes) * 100, 1),
        "inversion_suggestion": {
            "original": chord_pitches,
            "first_inversion": inversion,
            "note_names": [f"{_note_name(_pitch_class(p))}{p // 12 - 1}" for p in inversion],
        },
    }


def check_key_batch(
    clips: list[dict],
    mode_hint: str | None = None,
) -> dict:
    """Analyse key and flag out-of-key notes across multiple clips.

    Each entry in clips must be a dict with:
      - track_index (int)
      - slot_index (int)
      - label (str, optional): human-readable name for the clip

    mode_hint: optional mode override applied to all clips.

    Returns per-clip analysis plus an overall key consistency summary.
    """
    results = []
    all_pitch_classes = []

    for clip in clips:
        track_index = clip["track_index"]
        slot_index = clip["slot_index"]
        label = clip.get("label", f"track{track_index}_slot{slot_index}")
        analysis = check_key(track_index, slot_index, mode_hint)
        analysis["label"] = label
        results.append(analysis)
        if "chord_stack_pitch_classes" in analysis:
            all_pitch_classes.extend(analysis["chord_stack_pitch_classes"])

    # Overall key detection across all clips
    if all_pitch_classes:
        overall_root, overall_mode, overall_conf = _detect_key(all_pitch_classes)
        overall_key = f"{overall_root} {overall_mode}"
    else:
        overall_key = "unknown"
        overall_conf = 0.0

    # Key consistency: how many clips match the overall key
    matching = sum(
        1 for r in results
        if r.get("detected_key", {}).get("key_string", "") == overall_key
    )

    return {
        "overall_key": overall_key,
        "overall_confidence": overall_conf,
        "clips_analysed": len(results),
        "clips_matching_overall_key": matching,
        "key_consistency_pct": round(matching / len(results) * 100, 1) if results else 0.0,
        "results": results,
    }
