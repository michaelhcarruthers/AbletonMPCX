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


# ---------------------------------------------------------------------------
# N — Device and parameter alias registry
# Natural language → Ableton device/parameter name resolution
# ---------------------------------------------------------------------------

# Device name aliases — natural language → Ableton device name
DEVICE_ALIASES: dict[str, str] = {
    "compressor": "Compressor",
    "comp": "Compressor",
    "eq": "EQ Eight",
    "equalizer": "EQ Eight",
    "reverb": "Reverb",
    "verb": "Reverb",
    "delay": "Echo",
    "echo": "Echo",
    "chorus": "Chorus-Ensemble",
    "flanger": "Flanger",
    "phaser": "Phaser-Flanger",
    "limiter": "Limiter",
    "gate": "Gate",
    "saturator": "Saturator",
    "sat": "Saturator",
    "overdrive": "Overdrive",
    "redux": "Redux",
    "vinyl": "Vinyl Distortion",
    "auto filter": "Auto Filter",
    "filter": "Auto Filter",
    "arp": "Arpeggiator",
    "chord": "Chord",
    "pitch": "Pitch",
}

# Parameter name aliases — natural language → parameter name fragment
PARAMETER_ALIASES: dict[str, str] = {
    "volume": "Volume",
    "vol": "Volume",
    "gain": "Gain",
    "threshold": "Threshold",
    "thresh": "Threshold",
    "ratio": "Ratio",
    "attack": "Attack",
    "release": "Release",
    "rel": "Release",
    "dry wet": "Dry/Wet",
    "mix": "Dry/Wet",
    "wet": "Dry/Wet",
    "dry": "Dry/Wet",
    "freq": "Frequency",
    "frequency": "Frequency",
    "resonance": "Resonance",
    "res": "Resonance",
    "feedback": "Feedback",
    "time": "Time",
    "size": "Room Size",
    "room": "Room Size",
    "decay": "Decay Time",
}


def resolve_device_name(name: str) -> str:
    """Resolve a natural language device name to Ableton's exact name.

    Returns the original *name* unchanged if no alias is registered.
    """
    return DEVICE_ALIASES.get(name.lower().strip(), name)


def resolve_parameter_name(name: str) -> str:
    """Resolve a natural language parameter name to Ableton's parameter name fragment.

    Returns the original *name* unchanged if no alias is registered.
    """
    return PARAMETER_ALIASES.get(name.lower().strip(), name)
