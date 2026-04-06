"""
Natural language → parameter delta mapping.
Used by adjust_device_parameter and any tool accepting magnitude descriptions.
"""

# How much to move a parameter (0.0–1.0 normalised scale)
INTENSITY_DELTAS = {
    # Small adjustments
    "a touch": 0.02,
    "a hair": 0.02,
    "slightly": 0.03,
    "a little": 0.05,
    "a bit": 0.05,
    "subtly": 0.05,
    # Medium adjustments
    "some": 0.10,
    "a fair amount": 0.10,
    "noticeably": 0.12,
    "more": 0.10,
    "quite a bit": 0.15,
    # Large adjustments
    "a lot": 0.20,
    "a good amount": 0.20,
    "significantly": 0.20,
    "heavily": 0.25,
    "a ton": 0.35,
    "drenched": 0.40,
    # Absolute
    "halfway": 0.5,
    "all the way": 1.0,
    "fully": 1.0,
    "off": 0.0,
}

# Time/speed descriptions (in seconds)
TIME_DESCRIPTIONS = {
    "instantly": 0.0,
    "very fast": 0.1,
    "fast": 0.25,
    "quick": 0.25,
    "normal": 1.0,
    "slow": 2.0,
    "gradually": 3.0,
    "very slow": 5.0,
    "gently": 3.0,
}

# Musical feel descriptions (maps to intensity delta)
MUSICAL_DESCRIPTIONS = {
    "subtle": 0.05,
    "tasteful": 0.08,
    "musical": 0.10,
    "noticeable": 0.12,
    "heavy": 0.25,
    "extreme": 0.40,
}


def resolve_intensity(word: str) -> float:
    """
    Resolve a natural language intensity word to a normalised delta (0.0–1.0).
    Returns 0.10 (medium) if word not recognised.
    """
    word = word.lower().strip()
    return (
        INTENSITY_DELTAS.get(word)
        or MUSICAL_DESCRIPTIONS.get(word)
        or 0.10
    )


def resolve_time(word: str) -> float:
    """
    Resolve a natural language time description to seconds.
    Returns 1.0 (normal) if word not recognised.
    """
    return TIME_DESCRIPTIONS.get(word.lower().strip(), 1.0)
