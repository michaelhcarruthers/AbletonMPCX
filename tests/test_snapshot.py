"""Basic unit tests for session snapshot tools using MockTransport.

These tests exercise the snapshot logic without requiring a live Ableton
connection. They demonstrate the MockTransport pattern introduced in
helpers/transport.py.
"""
import sys
import os

# Ensure the repo root (where helpers/ and tools/ live) is on the path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest

from helpers.transport import MockTransport
from helpers import set_transport, _snapshots, _snapshots_lock
from tools.session_snapshots import (
    take_snapshot,
    list_snapshots,
    delete_snapshot,
    diff_snapshots,
    diff_snapshot_vs_live,
)


@pytest.fixture(autouse=True)
def mock_transport():
    """Set up a MockTransport before each test and tear it down afterwards."""
    mock = MockTransport()
    # Default session snapshot response used by most tools
    mock.responses["get_session_snapshot"] = {
        "track_count": 3,
        "scene_count": 4,
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.85},
            {"index": 1, "name": "Bass", "volume": 0.75},
            {"index": 2, "name": "Lead", "volume": 0.70},
        ],
        "tempo": 120.0,
    }
    set_transport(mock)

    # Clear in-process snapshot store before each test
    with _snapshots_lock:
        _snapshots.clear()

    yield mock

    # Restore default (socket) transport and clear snapshots after each test
    set_transport(None)
    with _snapshots_lock:
        _snapshots.clear()


# ---------------------------------------------------------------------------
# take_snapshot
# ---------------------------------------------------------------------------

def test_take_snapshot_returns_label_and_counts(mock_transport):
    result = take_snapshot("before")
    assert result["label"] == "before"
    assert result["track_count"] == 3
    assert result["scene_count"] == 4
    assert "timestamp_ms" in result


def test_take_snapshot_stores_in_memory(mock_transport):
    take_snapshot("v1")
    with _snapshots_lock:
        assert "v1" in _snapshots


def test_take_snapshot_calls_get_session_snapshot(mock_transport):
    take_snapshot("check")
    assert any(cmd == "get_session_snapshot" for cmd, _ in mock_transport.calls)


# ---------------------------------------------------------------------------
# list_snapshots
# ---------------------------------------------------------------------------

def test_list_snapshots_empty(mock_transport):
    result = list_snapshots()
    assert result["snapshots"] == []


def test_list_snapshots_after_take(mock_transport):
    take_snapshot("a")
    take_snapshot("b")
    result = list_snapshots()
    labels = [s["label"] for s in result["snapshots"]]
    assert "a" in labels
    assert "b" in labels


# ---------------------------------------------------------------------------
# delete_snapshot
# ---------------------------------------------------------------------------

def test_delete_snapshot_removes_label(mock_transport):
    take_snapshot("to_delete")
    result = delete_snapshot("to_delete")
    assert result["deleted"] == "to_delete"
    with _snapshots_lock:
        assert "to_delete" not in _snapshots


def test_delete_snapshot_raises_on_missing(mock_transport):
    with pytest.raises(ValueError, match="No snapshot with label"):
        delete_snapshot("nonexistent")


# ---------------------------------------------------------------------------
# diff_snapshots
# ---------------------------------------------------------------------------

def test_diff_snapshots_no_changes(mock_transport):
    take_snapshot("s1")
    take_snapshot("s2")
    result = diff_snapshots("s1", "s2")
    assert result["change_count"] == 0
    assert result["changes"] == []


def test_diff_snapshots_detects_volume_change(mock_transport):
    take_snapshot("before")

    # Change the mock response so 'after' has a different volume
    mock_transport.responses["get_session_snapshot"] = {
        "track_count": 3,
        "scene_count": 4,
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.50},  # changed
            {"index": 1, "name": "Bass", "volume": 0.75},
            {"index": 2, "name": "Lead", "volume": 0.70},
        ],
        "tempo": 120.0,
    }
    take_snapshot("after")

    result = diff_snapshots("before", "after")
    assert result["change_count"] > 0
    paths = [c["path"] for c in result["changes"]]
    assert any("volume" in p for p in paths)


def test_diff_snapshots_raises_on_missing_label(mock_transport):
    take_snapshot("only_one")
    with pytest.raises(ValueError):
        diff_snapshots("only_one", "missing")


# ---------------------------------------------------------------------------
# diff_snapshot_vs_live
# ---------------------------------------------------------------------------

def test_diff_snapshot_vs_live_no_changes(mock_transport):
    take_snapshot("live_check")
    result = diff_snapshot_vs_live("live_check")
    assert result["label"] == "live_check"
    assert result["change_count"] == 0


def test_diff_snapshot_vs_live_raises_on_missing_label(mock_transport):
    with pytest.raises(ValueError, match="No snapshot with label"):
        diff_snapshot_vs_live("ghost")
