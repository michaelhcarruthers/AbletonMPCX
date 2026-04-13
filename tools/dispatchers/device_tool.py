"""Device dispatcher — routes device, macro, and automation workflows."""
from __future__ import annotations

from helpers import mcp

from tools.performance import (
    add_performance_fx,
    perform_macro,
    set_macro_intensity,
    perform_macro_live,
    setup_performance_rack,
    get_rack_macros,
)
from tools.audit import (
    capture_device_macro_snapshot,
    apply_device_macro_snapshot,
)
from tools.devices import (
    adjust_device_parameter,
    set_device_parameters_batch,
    perform_device_parameter_moves,
    find_device_by_name,
    remove_device_by_name,
    randomize_device_parameters,
    randomize_rack_macros,
    set_mixer_snapshot,
    get_mixer_device,
    get_browser_tree,
    get_browser_items_at_path,
    load_browser_item,
    load_plugin_device,
    add_native_device,
)
from tools.staging import (
    gain_analyze,
    gain_trim_clips,
    gain_protect_headroom,
)

# ---------------------------------------------------------------------------
# Action implementations (thin wrappers)
# ---------------------------------------------------------------------------

def _action_macro_perform(**kwargs):
    return perform_macro(**kwargs)


def _action_macro_live(**kwargs):
    return perform_macro_live(**kwargs)


def _action_macro_intensity(**kwargs):
    return set_macro_intensity(**kwargs)


def _action_fx_add(**kwargs):
    return add_performance_fx(**kwargs)


def _action_setup_rack(**kwargs):
    return setup_performance_rack(**kwargs)


def _action_get_rack_macros(**kwargs):
    return get_rack_macros(**kwargs)


def _action_adjust(**kwargs):
    return adjust_device_parameter(**kwargs)


def _action_batch_set(**kwargs):
    return set_device_parameters_batch(**kwargs)


def _action_animate(**kwargs):
    return perform_device_parameter_moves(**kwargs)


def _action_snapshot_capture(**kwargs):
    return capture_device_macro_snapshot(**kwargs)


def _action_snapshot_apply(**kwargs):
    return apply_device_macro_snapshot(**kwargs)


def _action_find(**kwargs):
    return find_device_by_name(**kwargs)


def _action_remove_by_name(**kwargs):
    return remove_device_by_name(**kwargs)


def _action_randomize(**kwargs):
    return randomize_device_parameters(**kwargs)


def _action_randomize_rack(**kwargs):
    return randomize_rack_macros(**kwargs)


def _action_mixer_set(**kwargs):
    return set_mixer_snapshot(**kwargs)


def _action_mixer_get(**kwargs):
    return get_mixer_device(**kwargs)


def _action_browser_tree(**kwargs):
    return get_browser_tree(**kwargs)


def _action_browser_items(**kwargs):
    return get_browser_items_at_path(**kwargs)


def _action_load_item(**kwargs):
    return load_browser_item(**kwargs)


def _action_load_plugin(**kwargs):
    return load_plugin_device(**kwargs)


def _action_add_native(**kwargs):
    return add_native_device(**kwargs)


def _action_gain_analyze(**kwargs):
    return gain_analyze(**kwargs)


def _action_gain_trim_clips(**kwargs):
    return gain_trim_clips(**kwargs)


def _action_gain_protect_headroom(**kwargs):
    return gain_protect_headroom(**kwargs)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTIONS = {
    "macro_perform": _action_macro_perform,
    "macro_live": _action_macro_live,
    "macro_intensity": _action_macro_intensity,
    "fx_add": _action_fx_add,
    "setup_rack": _action_setup_rack,
    "get_rack_macros": _action_get_rack_macros,
    "adjust": _action_adjust,
    "batch_set": _action_batch_set,
    "animate": _action_animate,
    "snapshot_capture": _action_snapshot_capture,
    "snapshot_apply": _action_snapshot_apply,
    "find": _action_find,
    "remove_by_name": _action_remove_by_name,
    "randomize": _action_randomize,
    "randomize_rack": _action_randomize_rack,
    "mixer_set": _action_mixer_set,
    "mixer_get": _action_mixer_get,
    "browser_tree": _action_browser_tree,
    "browser_items": _action_browser_items,
    "load_item": _action_load_item,
    "load_plugin": _action_load_plugin,
    "add_native": _action_add_native,
    "gain_analyze": _action_gain_analyze,
    "gain_trim_clips": _action_gain_trim_clips,
    "gain_protect_headroom": _action_gain_protect_headroom,
}


@mcp.tool()
def device_tool(action: str, **kwargs) -> dict:
    """Device, macro, and automation workflows. Actions: macro_perform, macro_live, macro_intensity, fx_add, setup_rack, get_rack_macros, adjust, batch_set, animate, snapshot_capture, snapshot_apply, find, remove_by_name, randomize, randomize_rack, mixer_set, mixer_get, browser_tree, browser_items, load_item, load_plugin, add_native, gain_analyze, gain_trim_clips, gain_protect_headroom."""
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
