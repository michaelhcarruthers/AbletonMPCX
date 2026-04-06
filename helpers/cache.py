"""Sound-library and session-JSON cache helpers.

The concrete cache helpers (_ensure_cache_dir, _load_cache, _save_cache,
_ensure_session_cache_dir, _load_json_cache, _save_json_cache) are defined
inline in tools/diagnostics.py and tools/session.py where they are used.
This module exists as a home for any shared cache utilities extracted in
future PRs.
"""

# ---------------------------------------------------------------------------
# State diff cache (H)
# Tracks previous Ableton session state and returns only what changed.
# Used to reduce token cost when polling session state repeatedly.
# ---------------------------------------------------------------------------

import time

_state_cache: dict = {}
_cache_timestamps: dict = {}


def compute_diff(previous: dict, current: dict) -> dict:
    """Return only the keys that changed between previous and current state dicts.

    Recursively diffs nested dicts.

    Returns a dict with:
        changed: dict of {key: {"from": old_val, "to": new_val}}
        added: dict of new keys and their values
        removed: list of removed keys
        unchanged_count: int
    """
    changed: dict = {}
    added: dict = {}
    removed: list = []
    unchanged_count = 0

    if previous == current:
        return {
            "changed": changed,
            "added": added,
            "removed": removed,
            "unchanged_count": len(current),
        }

    all_keys = set(previous) | set(current)
    for key in all_keys:
        if key not in previous:
            added[key] = current[key]
        elif key not in current:
            removed.append(key)
        else:
            prev_val = previous[key]
            curr_val = current[key]
            if isinstance(prev_val, dict) and isinstance(curr_val, dict):
                nested = compute_diff(prev_val, curr_val)
                if nested["changed"] or nested["added"] or nested["removed"]:
                    changed[key] = nested
                else:
                    unchanged_count += 1
            elif prev_val != curr_val:
                changed[key] = {"from": prev_val, "to": curr_val}
            else:
                unchanged_count += 1

    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "unchanged_count": unchanged_count,
    }


def cache_state(key: str, state: dict) -> dict:
    """Cache a state snapshot under *key*.

    Returns a diff from the previous cached state.
    If no previous state exists, returns ``{"first_snapshot": True, "state": state}``.
    """
    previous = _state_cache.get(key)
    _state_cache[key] = state
    _cache_timestamps[key] = time.time()

    if previous is None:
        return {"first_snapshot": True, "state": state}

    return compute_diff(previous, state)

