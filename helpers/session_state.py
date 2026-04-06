"""Per-session AI handoff helpers.

Writes/reads ``session_state.json`` at the repo root so that a new AI session
can call ``get_session_summary()`` (or read the file directly) and immediately
know where the project stands without needing the full conversation history.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

# Resolve repo root relative to this file (helpers/ is one level down)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE_PATH = os.path.join(_REPO_ROOT, "session_state.json")


def save_session_state(
    completed: list[str] | None = None,
    in_progress: str | None = None,
    notes: str = "",
    current_structure: str | None = None,
    tool_count: int | None = None,
    next_up: str | None = None,
) -> dict[str, Any]:
    """Write current session state to ``session_state.json``.

    ``last_updated`` is always set to today's date on every save.

    Args:
        completed:         List of completed PR/milestone strings (appended to any
                           previously stored list when provided).
        in_progress:       Short description of what is currently being worked on
                           (scratchpad field; not shown in ``get_session_summary``).
        notes:             Free-form notes to persist across the session boundary.
        current_structure: One-line description of the current module layout.
        tool_count:        Total number of registered MCP tools.
        next_up:           Short description of the next planned work item.

    Returns:
        The state dict that was written.
    """
    state = load_session_state()
    state["last_updated"] = date.today().isoformat()

    if completed:
        existing: list[str] = state.get("completed_prs", [])
        for item in completed:
            if item not in existing:
                existing.append(item)
        state["completed_prs"] = existing

    if in_progress is not None:
        state["in_progress"] = in_progress

    if notes:
        state["notes"] = notes

    if current_structure is not None:
        state["current_structure"] = current_structure

    if tool_count is not None:
        state["tool_count"] = tool_count

    if next_up is not None:
        state["next_up"] = next_up

    with open(_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)

    return state


def load_session_state() -> dict[str, Any]:
    """Read and return the current ``session_state.json``.

    Returns an empty dict skeleton if the file does not exist.
    """
    if os.path.exists(_STATE_PATH):
        try:
            with open(_STATE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {
        "last_updated": date.today().isoformat(),
        "completed_prs": [],
        "current_structure": "",
        "tool_count": 0,
        "next_up": "",
        "notes": "",
    }


def get_session_summary() -> str:
    """Return a compact one-paragraph string suitable for pasting into a new AI session.

    Example output::

        AbletonMPCX | last updated 2026-04-06 | 264 tools
        Completed: #17-#35, #36, #41, #44, #45, #47, #48
        Structure: tools/ + helpers/ module layout, server.py = 24 lines
        Next: A-N build queue (core tools, mix intelligence, performance optimisation)
        Notes: (none)
    """
    state = load_session_state()
    completed = ", ".join(state.get("completed_prs", [])) or "(none)"
    return (
        "AbletonMPCX | last updated {last_updated} | {tool_count} tools\n"
        "Completed: {completed}\n"
        "Structure: {current_structure}\n"
        "Next: {next_up}\n"
        "Notes: {notes}"
    ).format(
        last_updated=state.get("last_updated", "unknown"),
        tool_count=state.get("tool_count", "unknown"),
        completed=completed,
        current_structure=state.get("current_structure", "unknown"),
        next_up=state.get("next_up", "unknown"),
        notes=state.get("notes") or "(none)",
    )
