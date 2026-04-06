"""Session suggestion tools — contextual next-action suggestions."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import helpers
from helpers import (
    mcp,
    _send,
    _operation_log,
    _reference_profiles,
    _reference_profiles_lock,
    _get_memory,
)


@mcp.tool()
def suggest_next_actions() -> dict:
    """
    Analyse the current session context and suggest logical next actions.

    Looks at:
    - Current session snapshot (tracks, devices, mixer state)
    - Recent operation log
    - Project memory (notes, preferences, track roles)
    - Stored snapshots

    Returns a list of suggestions with reasoning. These are observations only —
    nothing is executed automatically.

    Returns:
        suggestions: list of {action, reason, priority ('high'|'medium'|'low')}
    """
    suggestions = []

    # 1. Snapshot suggestion — if no snapshot taken recently
    recent_snapshots = [e for e in _operation_log[-50:] if "snapshot" in e["command"]]
    if not recent_snapshots:
        suggestions.append({
            "action": "take_snapshot('before_changes')",
            "reason": "No snapshot taken in recent operations. Recommended before making changes.",
            "priority": "high",
        })

    # 2. Project memory suggestion
    if helpers._current_project_id is None:
        suggestions.append({
            "action": "set_project_id('your_project_name')",
            "reason": "No project ID set. Set one to enable persistent memory, notes, and operation history.",
            "priority": "high",
        })

    # 3. Analyse session state
    try:
        snapshot = _send("get_session_snapshot")
        tracks = snapshot.get("tracks", [])

        # Unarmed tracks with no devices
        empty_tracks = [t for t in tracks if t.get("device_count", 0) == 0]
        if empty_tracks:
            suggestions.append({
                "action": "review or delete empty tracks: {}".format([t["name"] for t in empty_tracks[:5]]),
                "reason": "{} track(s) have no devices loaded.".format(len(empty_tracks)),
                "priority": "low",
            })

        # Master track device check
        master_devices = snapshot.get("master_track", {}).get("devices", [])
        if not master_devices:
            suggestions.append({
                "action": "add_native_device(-1, 'Limiter') or add_native_device(-1, 'EQ Eight')",
                "reason": "Master track has no devices. Consider adding a limiter or EQ.",
                "priority": "medium",
            })

        # Muted tracks
        muted = [t for t in tracks if t.get("mute")]
        if muted:
            suggestions.append({
                "action": "review muted tracks: {}".format([t["name"] for t in muted[:5]]),
                "reason": "{} track(s) are currently muted.".format(len(muted)),
                "priority": "low",
            })

    except Exception as e:
        logger.warning("Could not fetch session snapshot for suggestions: %s", e)
    if _operation_log:
        recent_cmds = [e["command"] for e in _operation_log[-20:]]

        # If user added devices recently, suggest snapshot
        if any("add_native_device" in c or "load_browser_item" in c for c in recent_cmds):
            already_snapped = any("snapshot" in c for c in recent_cmds)
            if not already_snapped:
                suggestions.append({
                    "action": "take_snapshot('after_device_changes')",
                    "reason": "Devices were recently added. Snapshot recommended to capture state.",
                    "priority": "high",
                })

        # If notes were removed recently, warn
        if any("remove_notes" in c for c in recent_cmds):
            suggestions.append({
                "action": "verify clip note state with get_notes()",
                "reason": "Notes were recently removed. Verify the clip state is as expected.",
                "priority": "medium",
            })

        # Flush log suggestion
        if len(_operation_log) > 100 and helpers._current_project_id:
            suggestions.append({
                "action": "flush_operation_log()",
                "reason": "Operation log has {} entries. Flush to persist to project memory.".format(len(_operation_log)),
                "priority": "low",
            })

    # 5. Project memory patterns
    if helpers._current_project_id:
        try:
            mem = _get_memory()
            prefs = mem.get("preferences", {})

            # If preferences mention a reverb, suggest checking return tracks
            if any("reverb" in str(v).lower() for v in prefs.values()):
                try:
                    returns = _send("get_return_tracks")
                    reverb_returns = [r for r in returns if "reverb" in r["name"].lower() or "verb" in r["name"].lower()]
                    if not reverb_returns:
                        suggestions.append({
                            "action": "check return tracks — no reverb return found",
                            "reason": "Your preferences mention a reverb preference but no return track is named for reverb.",
                            "priority": "medium",
                        })
                except Exception as e:
                    logger.debug("Could not fetch return tracks for suggestion: %s", e)
        except Exception as e:
            logger.debug("Could not read project memory for suggestions: %s", e)

    # Reference profile suggestion
    with _reference_profiles_lock:
        ref_profile_default = _reference_profiles.get("default")
        has_audio_ref = "default_audio" in _reference_profiles

    if ref_profile_default is not None:
        if ref_profile_default.get("type") == "clip_feel":
            suggestions.append({
                "action": "compare_clip_feel(track_index, slot_index, reference_label='default')",
                "reason": "A clip feel reference profile exists. Use compare_clip_feel() to check how your current clips compare.",
                "priority": "low",
            })
        elif ref_profile_default.get("type") == "mix_state":
            suggestions.append({
                "action": "compare_mix_state(reference_label='default')",
                "reason": "A mix state reference profile exists. Use compare_mix_state() to check what has changed.",
                "priority": "low",
            })

    # Audio reference suggestion
    if has_audio_ref:
        suggestions.append({
            "action": "compare_audio('/path/to/your/bounce.wav', reference_label='default_audio')",
            "reason": "An audio reference profile exists. Export a bounce and compare it against your reference.",
            "priority": "low",
        })

    return {
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }
