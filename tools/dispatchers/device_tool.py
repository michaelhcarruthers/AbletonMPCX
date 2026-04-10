"""Device dispatcher — routes device, macro, and automation workflows."""
from __future__ import annotations

from helpers import mcp

from tools.performance import (
    add_performance_fx,
    setup_fx_chain,
    list_macro_definitions,
    check_macro_readiness,
    perform_macro,
    set_macro_intensity,
    perform_macro_live,
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

# ---------------------------------------------------------------------------
# Action implementations (thin wrappers)
# ---------------------------------------------------------------------------

def _action_macro_perform(**kwargs):
    return perform_macro(**kwargs)


def _action_macro_live(**kwargs):
    return perform_macro_live(**kwargs)


def _action_macro_intensity(**kwargs):
    return set_macro_intensity(**kwargs)


def _action_macro_check(**kwargs):
    return check_macro_readiness(**kwargs)


def _action_macro_list(**kwargs):
    return list_macro_definitions()


def _action_fx_add(**kwargs):
    return add_performance_fx(**kwargs)


def _action_fx_chain_setup(**kwargs):
    return setup_fx_chain(**kwargs)


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


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTIONS = {
    "macro_perform": _action_macro_perform,
    "macro_live": _action_macro_live,
    "macro_intensity": _action_macro_intensity,
    "macro_check": _action_macro_check,
    "macro_list": _action_macro_list,
    "fx_add": _action_fx_add,
    "fx_chain_setup": _action_fx_chain_setup,
    "adjust": _action_adjust,
    "batch_set": _action_batch_set,
    "animate": _action_animate,
    "snapshot_capture": _action_snapshot_capture,
    "snapshot_apply": _action_snapshot_apply,
    "find": _action_find,
    "randomize": _action_randomize,
    "randomize_rack": _action_randomize_rack,
    "mixer_set": _action_mixer_set,
    "mixer_get": _action_mixer_get,
    "browser_tree": _action_browser_tree,
    "browser_items": _action_browser_items,
    "load_item": _action_load_item,
    "load_plugin": _action_load_plugin,
    "add_native": _action_add_native,
}


@mcp.tool()
def device_tool(action: str, **kwargs) -> dict:
    """Device, macro, and automation workflows. Actions: macro_perform, macro_live, macro_intensity, macro_check, macro_list, fx_add, fx_chain_setup, adjust, batch_set, animate, snapshot_capture, snapshot_apply, find, randomize, randomize_rack, mixer_set, mixer_get, browser_tree, browser_items, load_item, load_plugin, add_native."""
    if action not in _ACTIONS:
        return {
            "status": "error",
            "error": "Unknown action '{}'".format(action),
            "valid_actions": sorted(_ACTIONS.keys()),
        }
    try:
        return _ACTIONS[action](**kwargs)
    except TypeError as exc:
        return {"status": "error", "error": str(exc)}
