"""Unit tests for session_recording sidechain and arrangement dump tools.

Uses MockTransport so no live Ableton connection is required.
"""
import sys
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest

from helpers.transport import MockTransport
from helpers import set_transport
from tools.session_recording import (
    setup_sidechain_route,
    teardown_sidechain_route,
    dump_session_to_arrangement,
)

_TRACKS = [
    {"index": 0, "name": "Kick"},
    {"index": 1, "name": "Bass"},
    {"index": 2, "name": "Lead"},
]

_SONG_INFO = {"tempo": 120.0, "time_signature_numerator": 4}


@pytest.fixture(autouse=True)
def mock_transport():
    mock = MockTransport()
    mock.responses["get_tracks"] = _TRACKS
    mock.responses["get_song_info"] = _SONG_INFO
    mock.responses["setup_resampling_route"] = {
        "dest_track_index": 1,
        "source_track_name": "Kick",
        "confirmed_arm": True,
    }
    mock.responses["teardown_resampling_route"] = {
        "dest_track_index": 1,
        "confirmed_arm": False,
    }
    mock.responses["get_clip_info"] = {"length": 16.0, "name": "clip"}
    mock.responses["set_track_arm"] = None
    mock.responses["set_arrangement_position"] = None
    mock.responses["set_record_mode"] = None
    mock.responses["stop_all_clips"] = None
    mock.responses["fire_clip_slot"] = None
    mock.responses["start_playing"] = None
    mock.responses["set_device_parameter"] = None
    set_transport(mock)
    yield mock
    set_transport(None)


# ---------------------------------------------------------------------------
# setup_sidechain_route
# ---------------------------------------------------------------------------

def test_setup_sidechain_route_basic(mock_transport):
    result = setup_sidechain_route(source_track_index=0, dest_track_index=1)
    assert result["source_track_index"] == 0
    assert result["source_track_name"] == "Kick"
    assert result["dest_track_index"] == 1
    assert result["parameter_set"] is False
    assert "instructions" in result


def test_setup_sidechain_route_calls_get_tracks(mock_transport):
    setup_sidechain_route(source_track_index=0, dest_track_index=1)
    assert any(cmd == "get_tracks" for cmd, _ in mock_transport.calls)


def test_setup_sidechain_route_calls_setup_resampling_route(mock_transport):
    setup_sidechain_route(source_track_index=0, dest_track_index=1)
    assert any(cmd == "setup_resampling_route" for cmd, _ in mock_transport.calls)


def test_setup_sidechain_route_passes_source_name(mock_transport):
    setup_sidechain_route(source_track_index=0, dest_track_index=1)
    for cmd, params in mock_transport.calls:
        if cmd == "setup_resampling_route":
            assert params["source_track_name"] == "Kick"
            assert params["dest_track_index"] == 1
            break
    else:
        pytest.fail("setup_resampling_route not called")


def test_setup_sidechain_route_sets_parameter_when_all_provided(mock_transport):
    result = setup_sidechain_route(
        source_track_index=0,
        dest_track_index=1,
        dest_device_index=0,
        sidechain_amount_param_index=0,
        sidechain_amount=0.8,
    )
    assert result["parameter_set"] is True
    param_calls = [(cmd, params) for cmd, params in mock_transport.calls if cmd == "set_device_parameter"]
    assert len(param_calls) == 1
    _, p = param_calls[0]
    assert p["track_index"] == 1
    assert p["device_index"] == 0
    assert p["parameter_index"] == 0
    assert abs(p["value"] - 0.8) < 1e-6


def test_setup_sidechain_route_skips_parameter_when_partial(mock_transport):
    # Only dest_device_index provided — no parameter call expected
    result = setup_sidechain_route(
        source_track_index=0,
        dest_track_index=1,
        dest_device_index=0,
    )
    assert result["parameter_set"] is False
    assert not any(cmd == "set_device_parameter" for cmd, _ in mock_transport.calls)


def test_setup_sidechain_route_source_not_found(mock_transport):
    result = setup_sidechain_route(source_track_index=99, dest_track_index=1)
    assert "error" in result
    assert "99" in result["error"]


def test_setup_sidechain_route_routing_error(mock_transport):
    def raising_send(command, params=None):
        if command == "setup_resampling_route":
            raise RuntimeError("routing failed")
        return mock_transport.responses.get(command)

    mock_transport.send = raising_send
    result = setup_sidechain_route(source_track_index=0, dest_track_index=1)
    assert "error" in result


# ---------------------------------------------------------------------------
# teardown_sidechain_route
# ---------------------------------------------------------------------------

def test_teardown_sidechain_route_basic(mock_transport):
    result = teardown_sidechain_route(dest_track_index=1)
    assert result["dest_track_index"] == 1
    assert "teardown_result" in result


def test_teardown_sidechain_route_calls_teardown_resampling_route(mock_transport):
    teardown_sidechain_route(dest_track_index=1)
    assert any(cmd == "teardown_resampling_route" for cmd, _ in mock_transport.calls)
    for cmd, params in mock_transport.calls:
        if cmd == "teardown_resampling_route":
            assert params["dest_track_index"] == 1
            break


def test_teardown_sidechain_route_error(mock_transport):
    def raising_send(command, params=None):
        if command == "teardown_resampling_route":
            raise RuntimeError("teardown failed")
        return mock_transport.responses.get(command)

    mock_transport.send = raising_send
    result = teardown_sidechain_route(dest_track_index=1)
    assert "error" in result


# ---------------------------------------------------------------------------
# dump_session_to_arrangement
# ---------------------------------------------------------------------------

def test_dump_session_returns_recording_started(mock_transport):
    result = dump_session_to_arrangement(slot_index=0, track_indices=[0, 1])
    assert result["status"] == "recording_started"


def test_dump_session_reports_correct_tracks(mock_transport):
    result = dump_session_to_arrangement(slot_index=0, track_indices=[0, 2])
    assert result["tracks_firing"] == [0, 2]
    assert result["track_count"] == 2


def test_dump_session_calculates_duration(mock_transport):
    # clip length = 16 beats, tempo = 120 bpm → 8 seconds
    result = dump_session_to_arrangement(slot_index=0, track_indices=[0])
    assert result["stop_after_beats"] == 16.0
    assert abs(result["duration_seconds"] - 8.0) < 0.1


def test_dump_session_uses_override_beats(mock_transport):
    result = dump_session_to_arrangement(slot_index=0, track_indices=[0], stop_after_beats=32.0)
    assert result["stop_after_beats"] == 32.0


def test_dump_session_fires_all_target_clips(mock_transport):
    dump_session_to_arrangement(slot_index=0, track_indices=[0, 1, 2])
    fire_calls = [(cmd, params) for cmd, params in mock_transport.calls if cmd == "fire_clip_slot"]
    fired_tracks = {p["track_index"] for _, p in fire_calls}
    assert fired_tracks == {0, 1, 2}


def test_dump_session_calls_record_mode(mock_transport):
    dump_session_to_arrangement(slot_index=0, track_indices=[0])
    record_calls = [(cmd, params) for cmd, params in mock_transport.calls if cmd == "set_record_mode"]
    assert any(p.get("record_mode") is True for _, p in record_calls)


def test_dump_session_calls_start_playing(mock_transport):
    dump_session_to_arrangement(slot_index=0, track_indices=[0])
    assert any(cmd == "start_playing" for cmd, _ in mock_transport.calls)


def test_dump_session_auto_detects_tracks_with_clips(mock_transport):
    # All 3 tracks have clips (get_clip_info returns success for all)
    result = dump_session_to_arrangement(slot_index=0)
    assert result["track_count"] == 3
    assert set(result["tracks_firing"]) == {0, 1, 2}


def test_dump_session_no_clips_returns_error(mock_transport):
    # Make get_clip_info always raise — no clips anywhere
    def raising_send(command, params=None):
        if command == "get_clip_info":
            raise RuntimeError("no clip")
        return mock_transport.responses.get(command)

    mock_transport.send = raising_send
    result = dump_session_to_arrangement(slot_index=0)
    assert "error" in result


def test_dump_session_fallback_stop_when_no_clip_length(mock_transport):
    # get_clip_info succeeds but returns zero length
    mock_transport.responses["get_clip_info"] = {"length": 0.0}
    result = dump_session_to_arrangement(
        slot_index=0,
        track_indices=[0],
        time_signature_numerator=4,
    )
    # fallback = 4 * 8 = 32 beats
    assert result["stop_after_beats"] == 32.0


def test_dump_session_contains_note_field(mock_transport):
    result = dump_session_to_arrangement(slot_index=0, track_indices=[0])
    assert "note" in result
    assert "bar 1" in result["note"]


def test_dump_session_slot_index_passed_to_fire(mock_transport):
    dump_session_to_arrangement(slot_index=2, track_indices=[0])
    fire_calls = [(cmd, params) for cmd, params in mock_transport.calls if cmd == "fire_clip_slot"]
    assert all(p["slot_index"] == 2 for _, p in fire_calls)
