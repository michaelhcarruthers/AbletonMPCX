"""Mix template tools — auto-classify tracks by role and apply genre-appropriate processing.

Provides a fully automatic, repeatable mix template system. Open any session,
run classify_tracks() to detect roles from track names, then apply_mix_template()
to apply genre-appropriate processing — no audio file exports or manual input needed.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

import helpers
from helpers import mcp, _send, _get_memory, _save_memory

# ---------------------------------------------------------------------------
# Role detection patterns
# ---------------------------------------------------------------------------

_ROLE_PATTERNS: dict[str, list[str]] = {
    "kick":   ["kick", "bd", "808", "bass drum", "bassdrum", "kik"],
    "snare":  ["snare", "snr", "clap", "rimshot", "rim"],
    "hihat":  ["hat", "hh", "hihat", "hi-hat", "cymbal", "ride", "open hat", "closed hat"],
    "perc":   ["perc", "conga", "bongo", "shaker", "tamb", "cowbell", "timbale", "cabasa", "clav"],
    "bass":   ["bass", "sub", "low end", "808 bass", "reese", "bassline"],
    "pad":    ["pad", "atmosphere", "atmos", "texture", "ambient", "drone", "wash", "strings", "chord"],
    "lead":   ["lead", "melody", "synth lead", "hook", "riff", "arp", "arpegg"],
    "vocal":  ["vox", "vocal", "voice", "voc", "singer", "lyric", "adlib", "backing vox"],
    "fx":     ["fx", "effect", "sfx", "riser", "sweep", "impact", "transition", "foley", "noise"],
    "sample": ["sample", "loop", "break", "chop", "splice"],
    "bus":    ["bus", "group", "sum", "buss", "drum bus", "mix bus", "submix"],
    "return": ["reverb", "delay", "send", "return", "aux"],
    "master": ["master", "mstr", "2bus", "2-bus", "output"],
}

# ---------------------------------------------------------------------------
# Mix template definitions
# ---------------------------------------------------------------------------

_MIX_TEMPLATES: dict[str, dict[str, list[dict]]] = {
    "house": {
        "kick": [
            {"device": "Compressor", "params": {"Threshold": 0.35, "Ratio": 0.4, "Attack Time": 0.002, "Release Time": 0.1}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "bass": [
            {"device": "Compressor", "params": {"Threshold": 0.4, "Ratio": 0.35, "Attack Time": 0.008, "Release Time": 0.15}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "hihat": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.3}},
        ],
        "snare": [
            {"device": "Compressor", "params": {"Threshold": 0.45, "Ratio": 0.35, "Attack Time": 0.005, "Release Time": 0.08}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "pad": [
            {"device": "Reverb",     "params": {"Dry/Wet": 0.25}},
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.5}},
        ],
        "lead": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.2}},
        ],
        "vocal": [
            {"device": "Compressor", "params": {"Threshold": 0.4, "Ratio": 0.4, "Attack Time": 0.005, "Release Time": 0.1}},
            {"device": "EQ Eight",   "params": {}},
            {"device": "Reverb",     "params": {"Dry/Wet": 0.18}},
        ],
        "fx": [
            {"device": "Reverb",     "params": {"Dry/Wet": 0.5}},
        ],
        "bus": [
            {"device": "Compressor", "params": {"Threshold": 0.5, "Ratio": 0.3}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "sample": [
            {"device": "EQ Eight",   "params": {}},
        ],
        "perc": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.1}},
        ],
    },
    "techno": {
        "kick": [
            {"device": "Compressor", "params": {"Threshold": 0.25, "Ratio": 0.5, "Attack Time": 0.001, "Release Time": 0.08}},
            {"device": "Saturator",  "params": {"Drive": 0.35}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "bass": [
            {"device": "Compressor", "params": {"Threshold": 0.3, "Ratio": 0.5, "Attack Time": 0.005, "Release Time": 0.1}},
            {"device": "Saturator",  "params": {"Drive": 0.25}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "hihat": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.4}},
        ],
        "snare": [
            {"device": "Compressor", "params": {"Threshold": 0.3, "Ratio": 0.5, "Attack Time": 0.003, "Release Time": 0.06}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "pad": [
            {"device": "Reverb",     "params": {"Dry/Wet": 0.15}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "lead": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Saturator",  "params": {"Drive": 0.2}},
        ],
        "vocal": [
            {"device": "Compressor", "params": {"Threshold": 0.35, "Ratio": 0.45, "Attack Time": 0.003, "Release Time": 0.08}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "fx": [
            {"device": "Reverb",     "params": {"Dry/Wet": 0.4}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "bus": [
            {"device": "Compressor", "params": {"Threshold": 0.4, "Ratio": 0.4}},
            {"device": "Saturator",  "params": {"Drive": 0.15}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "sample": [
            {"device": "EQ Eight",   "params": {}},
        ],
        "perc": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.2}},
        ],
    },
    "hiphop": {
        "kick": [
            {"device": "Compressor", "params": {"Threshold": 0.4, "Ratio": 0.35, "Attack Time": 0.005, "Release Time": 0.12}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "bass": [
            {"device": "Compressor", "params": {"Threshold": 0.45, "Ratio": 0.3, "Attack Time": 0.01, "Release Time": 0.2}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "hihat": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.0}},
        ],
        "snare": [
            {"device": "Compressor", "params": {"Threshold": 0.4, "Ratio": 0.4, "Attack Time": 0.008, "Release Time": 0.1}},
            {"device": "Reverb",     "params": {"Dry/Wet": 0.12}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "pad": [
            {"device": "Reverb",     "params": {"Dry/Wet": 0.3}},
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.3}},
        ],
        "lead": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.1}},
        ],
        "vocal": [
            {"device": "Compressor", "params": {"Threshold": 0.35, "Ratio": 0.45, "Attack Time": 0.004, "Release Time": 0.12}},
            {"device": "EQ Eight",   "params": {}},
            {"device": "Reverb",     "params": {"Dry/Wet": 0.25}},
        ],
        "fx": [
            {"device": "Reverb",     "params": {"Dry/Wet": 0.45}},
        ],
        "bus": [
            {"device": "Compressor", "params": {"Threshold": 0.5, "Ratio": 0.3}},
            {"device": "EQ Eight",   "params": {}},
        ],
        "sample": [
            {"device": "EQ Eight",   "params": {}},
        ],
        "perc": [
            {"device": "EQ Eight",   "params": {}},
            {"device": "Utility",    "params": {"Width": 1.0}},
        ],
    },
}

# Human-readable descriptions for list_mix_templates
_TEMPLATE_DESCRIPTIONS: dict[str, str] = {
    "house": (
        "House music: punchy kick/bass compression, hi-hat EQ + widening, "
        "pad reverb, vocal compression + reverb chain"
    ),
    "techno": (
        "Techno: harder compression with faster attack, saturation drive on "
        "kick/bass/lead, tight transients, minimal reverb"
    ),
    "hiphop": (
        "Hip-hop: warm bass compression, snare reverb, heavy vocal chain, "
        "sample EQ, wider stereo on pads"
    ),
}

# Roles that apply_mix_template skips (routing/master/unclassified tracks)
_SKIP_ROLES: frozenset[str] = frozenset({"unknown", "bus", "master", "return"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_role(track_name: str) -> str | None:
    """Return the first matching role for track_name, or None if no match."""
    name_lower = track_name.lower()
    for role, keywords in _ROLE_PATTERNS.items():
        for kw in keywords:
            if kw in name_lower:
                return role
    return None


def _apply_device_params(
    track_index: int,
    device_index: int,
    device_name: str,
    params: dict[str, float],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Map param names case-insensitively and apply via set_device_parameters_batch.

    Returns:
        set_count: number of parameters successfully matched and applied (or
                   would be applied in dry_run mode).
    """
    if not params:
        return {"set_count": 0}

    if dry_run:
        return {"set_count": len(params)}

    try:
        params_result = _send("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index,
        })
    except Exception as e:
        logger.debug("Could not read parameters for device %s on track %s: %s", device_name, track_index, e)
        return {"set_count": 0}

    all_params = params_result.get("parameters", []) if isinstance(params_result, dict) else []

    updates = []
    for param_name, value in params.items():
        param_lower = param_name.lower()
        for p in all_params:
            if param_lower in p.get("name", "").lower():
                updates.append({"parameter_index": p["index"], "value": value})
                break

    if not updates:
        return {"set_count": 0}

    try:
        _send("set_device_parameters_batch", {
            "track_index": track_index,
            "device_index": device_index,
            "updates": updates,
        })
        return {"set_count": len(updates)}
    except Exception as e:
        logger.debug("Could not set parameters on device %s on track %s: %s", device_name, track_index, e)
        return {"set_count": 0}


# ---------------------------------------------------------------------------
# Track role tools (public MCP tools)
# ---------------------------------------------------------------------------

def set_track_role(track_index: int, role: str) -> dict:
    """Assign a semantic role to a track in project memory."""
    mem = _get_memory()
    mem.setdefault("track_roles", {})[str(track_index)] = role
    _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "role": role}


def get_track_roles() -> dict:
    """Return all stored track role assignments for the current project."""
    mem = _get_memory()
    return {"track_roles": mem.get("track_roles", {})}


def validate_track_roles() -> dict:
    """Validate stored track roles against the current session."""
    mem = _get_memory()
    stored_roles = mem.get("track_roles", {})

    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []
    valid_indices = {str(t.get("index", t.get("track_index", -1))) for t in tracks}

    stale: list[dict] = []
    valid: list[dict] = []
    role_counts: dict[str, int] = {}

    for idx_str, role in stored_roles.items():
        role_counts[role] = role_counts.get(role, 0) + 1
        if idx_str in valid_indices:
            valid.append({"track_index": int(idx_str), "role": role})
        else:
            stale.append({"track_index": int(idx_str), "role": role})

    return {
        "valid_roles": len(valid),
        "stale_roles": len(stale),
        "stale": stale,
        "valid": valid,
        "role_distribution": role_counts,
    }


def clear_track_role(track_index: int) -> dict:
    """Remove the stored role for a specific track."""
    mem = _get_memory()
    removed = mem.get("track_roles", {}).pop(str(track_index), None)
    _save_memory(helpers._current_project_id, mem)
    return {"track_index": track_index, "removed_role": removed}


# ---------------------------------------------------------------------------
# classify_tracks
# ---------------------------------------------------------------------------

@mcp.tool()
def classify_tracks(overwrite: bool = False) -> dict:
    """Auto-detect track roles from track names using keyword pattern matching."""
    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []

    mem = _get_memory()
    existing_roles: dict[str, str] = mem.get("track_roles", {})

    classified = 0
    already_had_role = 0
    unmatched = 0
    roles_assigned: dict[str, str] = {}

    for track in tracks:
        track_index = track.get("index", track.get("track_index", 0))
        track_name = track.get("name", "")

        # Skip tracks that already have a role when overwrite=False
        if not overwrite and str(track_index) in existing_roles:
            already_had_role += 1
            roles_assigned[track_name] = existing_roles[str(track_index)]
            continue

        matched_role = _detect_role(track_name)
        if matched_role is None:
            matched_role = "unknown"
            unmatched += 1
        else:
            classified += 1

        set_track_role(track_index, matched_role)
        roles_assigned[track_name] = matched_role

    return {
        "classified": classified,
        "already_had_role": already_had_role,
        "unmatched": unmatched,
        "total": len(tracks),
        "roles_assigned": roles_assigned,
    }


# ---------------------------------------------------------------------------
# list_mix_templates
# ---------------------------------------------------------------------------

@mcp.tool()
def list_mix_templates() -> dict:
    """Return all available mix template names with a summary of what each does."""
    templates = {}
    for name, role_map in _MIX_TEMPLATES.items():
        templates[name] = {
            "description": _TEMPLATE_DESCRIPTIONS.get(name, ""),
            "roles_covered": sorted(role_map.keys()),
        }
    return {
        "templates": templates,
        "available_names": sorted(_MIX_TEMPLATES.keys()),
    }


# ---------------------------------------------------------------------------
# preview_mix_template
# ---------------------------------------------------------------------------

def preview_mix_template(template_name: str) -> dict:
    """Show what apply_mix_template would do without touching anything."""
    return apply_mix_template(template_name, dry_run=True)


# ---------------------------------------------------------------------------
# apply_mix_template
# ---------------------------------------------------------------------------

@mcp.tool()
def apply_mix_template(
    template_name: str,
    dry_run: bool = True,
    skip_existing_devices: bool = True,
) -> dict:
    """Apply a genre mix template to all tracks based on their stored roles."""
    if template_name not in _MIX_TEMPLATES:
        raise ValueError(
            "Unknown template '{}'. Available: {}".format(
                template_name, sorted(_MIX_TEMPLATES.keys())
            )
        )

    template = _MIX_TEMPLATES[template_name]

    mem = _get_memory()
    stored_roles: dict[str, str] = mem.get("track_roles", {})

    snapshot = _send("get_session_snapshot")
    tracks = snapshot.get("tracks", []) if isinstance(snapshot, dict) else []

    tracks_processed = 0
    tracks_skipped = 0
    total_devices_added = 0
    total_parameters_set = 0
    per_track: list[dict] = []

    for track in tracks:
        track_index = track.get("index", track.get("track_index", 0))
        track_name = track.get("name", "")
        role = stored_roles.get(str(track_index), "unknown")

        # Skip special/unclassified roles and roles not in this template
        if role in _SKIP_ROLES or role not in template:
            tracks_skipped += 1
            per_track.append({
                "track_index": track_index,
                "track_name": track_name,
                "role": role,
                "actions_taken": [],
                "actions_skipped": [
                    {"reason": "role '{}' not in template or excluded".format(role)}
                ],
            })
            continue

        steps = template[role]
        actions_taken: list[dict] = []
        actions_skipped: list[dict] = []

        if not dry_run:
            _send("begin_undo_step", {
                "name": "apply_mix_template: {} on {}".format(template_name, track_name)
            })

        try:
            # Fetch current devices (read op — OK in dry_run)
            existing_devices: list[dict] = []
            try:
                result = _send("get_devices", {"track_index": track_index, "is_return_track": False})
                existing_devices = result if isinstance(result, list) else []
            except Exception as e:
                logger.debug("Could not get devices for track %s: %s", track_index, e)

            for step in steps:
                device_name: str = step["device"]
                params: dict[str, float] = step.get("params", {})

                # Check if a matching device already exists on the track
                existing_device: dict | None = None
                for d in existing_devices:
                    if device_name.lower() in d.get("name", "").lower():
                        existing_device = d
                        break

                if existing_device is not None and skip_existing_devices:
                    # Device exists — skip adding, but still apply params if defined
                    if params:
                        dev_idx = existing_device.get("index", existing_device.get("device_index", 0))
                        param_result = _apply_device_params(
                            track_index, dev_idx, device_name, params, dry_run
                        )
                        total_parameters_set += param_result["set_count"]
                        actions_taken.append({
                            "action": "set_params_on_existing",
                            "device": device_name,
                            "params_set": param_result["set_count"],
                            "dry_run": dry_run,
                        })
                    else:
                        actions_skipped.append({
                            "device": device_name,
                            "reason": "already present (skip_existing_devices=True)",
                        })
                    continue

                # Device not present (or skip_existing_devices=False) — add it
                if not dry_run:
                    try:
                        _send("add_native_device", {
                            "track_index": track_index,
                            "device_name": device_name,
                        })
                        # Re-fetch devices so we have the correct index for the new device
                        updated = _send("get_devices", {"track_index": track_index, "is_return_track": False})
                        existing_devices = updated if isinstance(updated, list) else existing_devices

                        # Find the device we just added (last match by name)
                        new_device_index = len(existing_devices) - 1
                        for d in reversed(existing_devices):
                            if device_name.lower() in d.get("name", "").lower():
                                new_device_index = d.get("index", d.get("device_index", new_device_index))
                                break

                        total_devices_added += 1
                        actions_taken.append({"action": "add_device", "device": device_name})

                        # Apply params to the newly added device
                        if params:
                            param_result = _apply_device_params(
                                track_index, new_device_index, device_name, params, dry_run=False
                            )
                            total_parameters_set += param_result["set_count"]
                            actions_taken.append({
                                "action": "set_params",
                                "device": device_name,
                                "params_set": param_result["set_count"],
                            })
                    except Exception as e:
                        actions_skipped.append({
                            "device": device_name,
                            "reason": "add failed: {}".format(str(e)),
                        })
                else:
                    # dry_run — record planned actions without executing
                    total_devices_added += 1
                    actions_taken.append({"action": "add_device", "device": device_name, "dry_run": True})
                    if params:
                        total_parameters_set += len(params)
                        actions_taken.append({
                            "action": "set_params",
                            "device": device_name,
                            "params_set": len(params),
                            "dry_run": True,
                        })

        finally:
            if not dry_run:
                _send("end_undo_step", {})

        tracks_processed += 1
        per_track.append({
            "track_index": track_index,
            "track_name": track_name,
            "role": role,
            "actions_taken": actions_taken,
            "actions_skipped": actions_skipped,
        })

    return {
        "template_name": template_name,
        "dry_run": dry_run,
        "tracks_processed": tracks_processed,
        "tracks_skipped": tracks_skipped,
        "devices_added": total_devices_added,
        "parameters_set": total_parameters_set,
        "per_track": per_track,
    }
