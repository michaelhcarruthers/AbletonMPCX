"""Device and parameter alias registry — resolve natural language names to Ableton names."""

from __future__ import annotations

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
