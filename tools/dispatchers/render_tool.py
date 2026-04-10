"""Render dispatcher — routes resampling, bounce, and recording workflows."""
from __future__ import annotations

from helpers import mcp

from tools.session_recording import (
    setup_resampling_route,
    teardown_resampling_route,
    get_resampling_status,
    render_track_to_audio,
    setup_sidechain_route,
    teardown_sidechain_route,
    dump_session_to_arrangement,
)
from tools.audit import prep_track_for_resampling

# ---------------------------------------------------------------------------
# Action implementations (thin wrappers)
# ---------------------------------------------------------------------------

def _action_setup(**kwargs):
    return setup_resampling_route(**kwargs)


def _action_teardown(**kwargs):
    return teardown_resampling_route(**kwargs)


def _action_status(**kwargs):
    return get_resampling_status(**kwargs)


def _action_render(**kwargs):
    return render_track_to_audio(**kwargs)


def _action_prep(**kwargs):
    return prep_track_for_resampling(**kwargs)


def _action_sidechain_setup(**kwargs):
    return setup_sidechain_route(**kwargs)


def _action_sidechain_teardown(**kwargs):
    return teardown_sidechain_route(**kwargs)


def _action_dump_to_arrangement(**kwargs):
    return dump_session_to_arrangement(**kwargs)


def _action_bounce(**kwargs):
    """Orchestration: setup resampling route then render track to audio."""
    setup_kwargs = {
        k: kwargs[k]
        for k in ("source_track_index", "resample_track_index", "track_name", "armed")
        if k in kwargs
    }
    render_kwargs = {
        k: kwargs[k]
        for k in (
            "source_track_index",
            "start_bar",
            "end_bar",
            "use_resampling",
            "post_fx",
            "ensure_full_length",
            "new_track_name",
            "target_track_index",
        )
        if k in kwargs
    }
    setup_result = setup_resampling_route(**setup_kwargs)
    if isinstance(setup_result, dict) and setup_result.get("status") == "error":
        return setup_result
    render_result = render_track_to_audio(**render_kwargs)
    return {"setup": setup_result, "render": render_result}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTIONS = {
    "setup": _action_setup,
    "teardown": _action_teardown,
    "status": _action_status,
    "render": _action_render,
    "prep": _action_prep,
    "sidechain_setup": _action_sidechain_setup,
    "sidechain_teardown": _action_sidechain_teardown,
    "dump_to_arrangement": _action_dump_to_arrangement,
    "bounce": _action_bounce,
}


@mcp.tool()
def render_tool(action: str, **kwargs) -> dict:
    """Resampling, bounce, and recording workflows. Actions: setup, teardown, status, render, prep, sidechain_setup, sidechain_teardown, dump_to_arrangement, bounce."""
    if action not in _ACTIONS:
        return {
            "status": "error",
            "error": f"Unknown action '{action}'",
            "valid_actions": sorted(_ACTIONS.keys()),
        }
    try:
        return _ACTIONS[action](**kwargs)
    except TypeError as exc:
        return {"status": "error", "error": str(exc)}
