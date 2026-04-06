"""Natural language → parameter delta mapping (vocabulary system).

Maps human-readable intensity descriptions to normalised delta values
(0.0–1.0 range) for use with relative parameter adjustment tools.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Intensity lookup table
# ---------------------------------------------------------------------------

_INTENSITY_MAP: dict[str, float] = {
    # Very small adjustments
    "a touch": 0.02,
    "a hair": 0.02,
    "barely": 0.02,
    "tiny": 0.02,
    "tiny bit": 0.02,
    "just a touch": 0.02,
    "just a hair": 0.02,
    # Small adjustments
    "slightly": 0.05,
    "a little": 0.05,
    "a bit": 0.05,
    "gently": 0.05,
    "nudge": 0.05,
    "subtle": 0.05,
    # Medium-small adjustments
    "somewhat": 0.10,
    "a fair amount": 0.10,
    "moderately": 0.10,
    "noticeably": 0.10,
    # Medium adjustments
    "a good amount": 0.15,
    "quite a bit": 0.15,
    "significantly": 0.20,
    "a lot": 0.20,
    "much": 0.20,
    "considerably": 0.20,
    # Large adjustments
    "a great deal": 0.30,
    "substantially": 0.30,
    "dramatically": 0.30,
    "heavily": 0.30,
    # Very large adjustments
    "massively": 0.50,
    "halfway": 0.50,
    "half": 0.50,
    # Full range
    "fully": 1.0,
    "completely": 1.0,
    "all the way": 1.0,
    "maximum": 1.0,
    "max": 1.0,
}

_DEFAULT_INTENSITY = 0.05  # fallback when phrase is unrecognised


def resolve_intensity(phrase: str) -> float:
    """
    Resolve a natural language intensity phrase to a normalised delta (0.0–1.0).

    Matching is case-insensitive and strips surrounding whitespace.
    Unknown phrases fall back to the default delta of 0.05 ("a little").

    Args:
        phrase: Human-readable magnitude description such as "a little",
                "a lot", "a touch", "significantly", "halfway", etc.

    Returns:
        A float in [0.0, 1.0] representing the normalised delta to apply.
    """
    normalised = phrase.strip().lower()
    return _INTENSITY_MAP.get(normalised, _DEFAULT_INTENSITY)
