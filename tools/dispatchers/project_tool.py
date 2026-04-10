"""Project dispatcher — routes project health, audit, snapshot, and memory workflows."""
from __future__ import annotations

from helpers import mcp

from tools.audit import (
    project_health_report,
    cleanup_session,
    find_empty_tracks,
    find_unused_returns,
    find_missing_plugins,
    get_missing_media_status,
    search_missing_media,
    batch_audit_projects,
    save_project_audit,
    load_project_audit,
    compare_project_audits,
    observer_status,
)
from tools.session import (
    session_audit,
    get_session_diff,
    get_session_state,
    get_session_health,
    get_project_memory,
    add_project_note,
    set_project_id,
    set_preference,
    get_preferences,
    get_operation_log,
    flush_operation_log,
    get_stored_operation_log,
    summarise_session,
    get_protocol_version,
)
from tools.session_snapshots import (
    take_snapshot,
    list_snapshots,
    delete_snapshot,
    diff_snapshots,
    full_session_snapshot,
)

# ---------------------------------------------------------------------------
# Action implementations (thin wrappers)
# ---------------------------------------------------------------------------

def _action_health(**kwargs):
    return project_health_report()


def _action_audit(**kwargs):
    return session_audit(**kwargs)


def _action_cleanup(**kwargs):
    return cleanup_session(**kwargs)


def _action_find_empty(**kwargs):
    return find_empty_tracks()


def _action_find_unused_returns(**kwargs):
    return find_unused_returns()


def _action_find_missing_plugins(**kwargs):
    return find_missing_plugins(**kwargs)


def _action_find_missing_media(**kwargs):
    return get_missing_media_status()


def _action_search_missing_media(**kwargs):
    return search_missing_media(**kwargs)


def _action_snapshot_take(**kwargs):
    return take_snapshot(**kwargs)


def _action_snapshot_list(**kwargs):
    return list_snapshots()


def _action_snapshot_delete(**kwargs):
    return delete_snapshot(**kwargs)


def _action_snapshot_diff(**kwargs):
    return diff_snapshots(**kwargs)


def _action_snapshot_full(**kwargs):
    return full_session_snapshot(**kwargs)


def _action_diff(**kwargs):
    return get_session_diff()


def _action_state(**kwargs):
    return get_session_state(**kwargs)


def _action_state_health(**kwargs):
    return get_session_health()


def _action_memory_get(**kwargs):
    return get_project_memory()


def _action_memory_note(**kwargs):
    return add_project_note(**kwargs)


def _action_memory_set_id(**kwargs):
    return set_project_id(**kwargs)


def _action_preference_set(**kwargs):
    return set_preference(**kwargs)


def _action_preference_get(**kwargs):
    return get_preferences()


def _action_operation_log(**kwargs):
    return get_operation_log(**kwargs)


def _action_operation_log_flush(**kwargs):
    return flush_operation_log()


def _action_operation_log_stored(**kwargs):
    return get_stored_operation_log(**kwargs)


def _action_summarise(**kwargs):
    return summarise_session()


def _action_observer_status(**kwargs):
    return observer_status()


def _action_batch_audit(**kwargs):
    return batch_audit_projects(**kwargs)


def _action_save_audit(**kwargs):
    return save_project_audit(**kwargs)


def _action_load_audit(**kwargs):
    return load_project_audit(**kwargs)


def _action_compare_audits(**kwargs):
    return compare_project_audits(**kwargs)


def _action_ping(**kwargs):
    return get_protocol_version()


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTIONS = {
    "health": _action_health,
    "audit": _action_audit,
    "cleanup": _action_cleanup,
    "find_empty": _action_find_empty,
    "find_unused_returns": _action_find_unused_returns,
    "find_missing_plugins": _action_find_missing_plugins,
    "find_missing_media": _action_find_missing_media,
    "search_missing_media": _action_search_missing_media,
    "snapshot_take": _action_snapshot_take,
    "snapshot_list": _action_snapshot_list,
    "snapshot_delete": _action_snapshot_delete,
    "snapshot_diff": _action_snapshot_diff,
    "snapshot_full": _action_snapshot_full,
    "diff": _action_diff,
    "state": _action_state,
    "state_health": _action_state_health,
    "memory_get": _action_memory_get,
    "memory_note": _action_memory_note,
    "memory_set_id": _action_memory_set_id,
    "preference_set": _action_preference_set,
    "preference_get": _action_preference_get,
    "operation_log": _action_operation_log,
    "operation_log_flush": _action_operation_log_flush,
    "operation_log_stored": _action_operation_log_stored,
    "summarise": _action_summarise,
    "observer_status": _action_observer_status,
    "batch_audit": _action_batch_audit,
    "save_audit": _action_save_audit,
    "load_audit": _action_load_audit,
    "compare_audits": _action_compare_audits,
    "ping": _action_ping,
}


@mcp.tool()
def project_tool(action: str, **kwargs) -> dict:
    """Project health, audit, snapshot, and memory workflows. Actions: health, audit, cleanup, find_empty, find_unused_returns, find_missing_plugins, find_missing_media, search_missing_media, snapshot_take, snapshot_list, snapshot_delete, snapshot_diff, snapshot_full, diff, state, state_health, memory_get, memory_note, memory_set_id, preference_set, preference_get, operation_log, operation_log_flush, operation_log_stored, summarise, observer_status, batch_audit, save_audit, load_audit, compare_audits, ping."""
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
