"""
Pre-compute bar/beat/second conversions locally before calling Live.
Eliminates AI reasoning about time and reduces token usage.
"""
from __future__ import annotations


def bars_to_seconds(bar: int, tempo: float, time_sig_numerator: int = 4) -> float:
    """Convert a 1-based bar number to a position in seconds."""
    if tempo <= 0:
        raise ValueError(f"tempo must be positive, got {tempo}")
    beats = (bar - 1) * time_sig_numerator
    return beats * (60.0 / tempo)


def seconds_to_bars(seconds: float, tempo: float, time_sig_numerator: int = 4) -> float:
    """Convert a position in seconds back to a (fractional) bar number."""
    if tempo <= 0:
        raise ValueError(f"tempo must be positive, got {tempo}")
    if time_sig_numerator <= 0:
        raise ValueError(f"time_sig_numerator must be positive, got {time_sig_numerator}")
    beats = seconds / (60.0 / tempo)
    return (beats / time_sig_numerator) + 1


def bar_range_to_seconds(
    bar_start: int,
    bar_end: int,
    tempo: float,
    time_sig_numerator: int = 4,
) -> tuple[float, float]:
    """Return (start_seconds, end_seconds) for a bar range."""
    return (
        bars_to_seconds(bar_start, tempo, time_sig_numerator),
        bars_to_seconds(bar_end, tempo, time_sig_numerator),
    )


def beats_to_seconds(beats: float, tempo: float) -> float:
    """Convert a beat count to seconds."""
    if tempo <= 0:
        raise ValueError(f"tempo must be positive, got {tempo}")
    return beats * (60.0 / tempo)


def seconds_to_beats(seconds: float, tempo: float) -> float:
    """Convert seconds to beats."""
    if tempo <= 0:
        raise ValueError(f"tempo must be positive, got {tempo}")
    return seconds / (60.0 / tempo)
