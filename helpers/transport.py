"""Transport abstraction for mockable testing of MCP tool functions.

This module defines a ``Transport`` protocol and a ``MockTransport`` class that
can be used in unit tests to exercise tool logic without a live Ableton connection.

Usage in tests::

    from helpers.transport import MockTransport
    from helpers import set_transport

    mock = MockTransport()
    mock.responses["get_session_snapshot"] = {"tracks": [], "track_count": 0, "scene_count": 2}
    set_transport(mock)

    # Now call your tool functions — they will use mock.send() instead of the real socket
    from tools.session_snapshots import take_snapshot
    result = take_snapshot("before")
    assert result["label"] == "before"
    assert ("get_session_snapshot", {}) in mock.calls
"""
from __future__ import annotations

from typing import Any, Protocol


class Transport(Protocol):
    """Protocol for objects that can send commands to Ableton Live."""

    def send(self, command: str, params: dict | None = None) -> Any:
        """Send a command and return the response."""
        ...


class MockTransport:
    """In-memory transport that records calls and returns pre-configured responses.

    Use this in unit tests to exercise tool logic without a live Ableton
    connection.

    Attributes:
        calls: List of ``(command, params)`` tuples recorded in order.
        responses: Dict mapping command name → return value.  Any command not
            present in ``responses`` returns ``None``.

    Example::

        mock = MockTransport()
        mock.responses["get_tracks"] = [{"index": 0, "name": "Kick", "volume": 0.85}]
        set_transport(mock)
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.responses: dict[str, Any] = {}

    def send(self, command: str, params: dict | None = None) -> Any:
        """Record the call and return the configured response (or None)."""
        self.calls.append((command, params or {}))
        return self.responses.get(command)

    def reset(self) -> None:
        """Clear recorded calls (keep configured responses)."""
        self.calls.clear()
