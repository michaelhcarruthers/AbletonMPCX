"""Shared helpers — MCP instance, low-level socket transport, and operation log."""
from __future__ import annotations

import collections
import copy
import datetime
import json
import logging
import math
import os
import pathlib
import urllib.parse
import urllib.request
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

from mcp.server.fastmcp import FastMCP


def _detect_ngrok_host() -> str | None:
    """Return the active ngrok public hostname, or None if not available.

    Checks the ``NGROK_HOST`` env-var first (manual override).  Falls back to
    querying the local ngrok introspection API at ``http://127.0.0.1:4040/api/tunnels``
    and extracting the hostname from the first ``https://`` tunnel found.
    """
    try:
        manual = os.environ.get("NGROK_HOST", "").strip()
        if manual:
            return manual
        req = urllib.request.urlopen(
            "http://127.0.0.1:4040/api/tunnels", timeout=1.5
        )
        data = json.loads(req.read().decode("utf-8"))
        for tunnel in data.get("tunnels", []):
            public_url = tunnel.get("public_url", "")
            if public_url.startswith("https://"):
                return urllib.parse.urlparse(public_url).hostname
    except Exception:
        pass
    return None


try:
    from mcp.server.transport_security import TransportSecuritySettings
    _allowed_hosts = ["localhost", "127.0.0.1"]
    _detected_host = _detect_ngrok_host()
    if _detected_host:
        _allowed_hosts.append(_detected_host)
        logger.info("AMCPX ngrok host: %s", _detected_host)
    else:
        logger.debug("ngrok not detected; allowed_hosts: %s", _allowed_hosts)
    _transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=_allowed_hosts,
    )
    mcp = FastMCP("AbletonMPCX", transport_security=_transport_security)
except (ImportError, TypeError):
    # Older FastMCP versions without transport_security support
    mcp = FastMCP("AbletonMPCX")

# --- Connection settings ---
ABLETON_HOST = "localhost"
ABLETON_PORT = 9877


# ---------------------------------------------------------------------------
# Low-level socket helpers
# ---------------------------------------------------------------------------

@contextmanager
def _ableton_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15.0)
    try:
        sock.connect((ABLETON_HOST, ABLETON_PORT))
        yield sock
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _recv_exactly(sock, n: int) -> bytes | None:
    """Read exactly n bytes from sock. Returns None if connection closes early."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return None
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# Operation log (shared across modules)
# ---------------------------------------------------------------------------

_operation_log: list[dict] = []
_MAX_LOG_ENTRIES = 1000


def _append_operation(command: str, params: dict, result: Any):
    """Append an operation to the in-process log."""
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": command,
        "params": params,
        "result_summary": str(result)[:200] if result is not None else None,
    }
    _operation_log.append(entry)
    if len(_operation_log) > _MAX_LOG_ENTRIES:
        del _operation_log[:-_MAX_LOG_ENTRIES]


# ---------------------------------------------------------------------------
# Transport abstraction (mockable for unit tests)
# ---------------------------------------------------------------------------

# The active transport — None means use the default socket-based Ableton transport.
_active_transport: Any = None


def set_transport(transport: Any) -> None:
    """Replace the internal transport used by ``_send``.

    Pass a :class:`helpers.transport.MockTransport` instance (or any object
    with a compatible ``send(command, params)`` method) to run tools without
    a live Ableton connection.

    Pass ``None`` to restore the default socket transport.

    Args:
        transport: An object implementing ``send(command, params) -> Any``,
            or ``None`` to restore the socket transport.
    """
    global _active_transport
    _active_transport = transport


# ---------------------------------------------------------------------------
# High-level send helpers
# ---------------------------------------------------------------------------

def _send(command: str, params: dict[str, Any] | None = None, _log: bool = True, _silent: bool = False) -> Any:
    if _active_transport is not None:
        result = _active_transport.send(command, params or {})
        if _log:
            _append_operation(command, params or {}, result)
        return result
    payload = json.dumps({"command": command, "params": params or {}, "silent": _silent}).encode("utf-8")
    with _ableton_socket() as sock:
        sock.sendall(len(payload).to_bytes(4, "big") + payload)
        header = _recv_exactly(sock, 4)
        if not header:
            raise RuntimeError("Connection closed before response header")
        msg_len = int.from_bytes(header, "big")
        if msg_len > 10 * 1024 * 1024:
            raise RuntimeError("Response too large: {} bytes".format(msg_len))
        data = _recv_exactly(sock, msg_len)
        if data is None:
            raise RuntimeError("Connection closed before response body")
    response = json.loads(data.decode("utf-8"))
    if response.get("status") == "error":
        raise RuntimeError(response["error"])
    result = response.get("result")
    if _log:
        _append_operation(command, params or {}, result)
    return result


def _send_silent(command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a read-only command that must not create Ableton undo entries.

    Sets ``silent=True`` in the JSON payload so the Remote Script wraps the
    dispatched call in ``song.begin_undo_step`` / ``song.end_undo_step``.
    Live silently drops undo steps that contain no mutations, so read-only
    calls (including ``clip.get_notes`` which Live internally marks as
    mutating) produce zero net undo entries.
    """
    return _send(command, params, _log=False, _silent=True)


# ---------------------------------------------------------------------------
# Shared in-process state (used across multiple tool modules)
# ---------------------------------------------------------------------------

# Snapshot store (ephemeral, cleared on restart)
_snapshots: dict[str, dict] = {}
_snapshots_lock = threading.Lock()

# Reference profile store (also persisted to project memory)
_reference_profiles: dict[str, dict] = {}
_reference_profiles_lock = threading.Lock()

# Audio analysis cache (in-process)
_audio_analysis_cache: dict[str, dict] = {}
_audio_analysis_cache_lock = threading.Lock()

# Persistent project memory settings
_MEMORY_DIR = os.path.expanduser("~/.ableton_mpcx/projects")
_current_project_id: str | None = None


# ---------------------------------------------------------------------------
# Persistent project memory helpers (shared by session and audit modules)
# ---------------------------------------------------------------------------

def _memory_path(project_id: str) -> str:
    safe = project_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
    os.makedirs(_MEMORY_DIR, exist_ok=True)
    return os.path.join(_MEMORY_DIR, "{}.json".format(safe))


def _load_memory(project_id: str) -> dict:
    path = _memory_path(project_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load memory for project '%s': %s", project_id, e)
    return {
        "project_id": project_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "snapshots": {},
        "operation_log": [],
        "preferences": {},
        "track_roles": {},
        "notes": [],
        "device_snapshots": {},
        "reference_profiles": {},
    }


def _save_memory(project_id: str, memory: dict):
    path = _memory_path(project_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save memory for project '%s': %s", project_id, e)


def _get_memory() -> dict:
    if _current_project_id is None:
        raise RuntimeError("No project loaded. Call set_project_id() first.")
    return _load_memory(_current_project_id)


def _save_reference_profile(label: str, profile: dict):
    """Store a reference profile in-process and persist to project memory if a project is loaded."""
    with _reference_profiles_lock:
        _reference_profiles[label] = profile
    if _current_project_id is not None:
        try:
            mem = _get_memory()
            mem.setdefault("reference_profiles", {})[label] = profile
            _save_memory(_current_project_id, mem)
        except Exception as e:
            logger.warning("Failed to persist reference profile '%s': %s", label, e)


def _load_reference_profiles_from_project():
    """Load all persisted reference profiles into the in-process store."""
    if _current_project_id is None:
        return
    try:
        mem = _get_memory()
        with _reference_profiles_lock:
            for label, profile in mem.get("reference_profiles", {}).items():
                _reference_profiles[label] = profile
    except Exception as e:
        logger.warning("Failed to load reference profiles from project: %s", e)


from helpers.timing import bars_to_seconds, bar_range_to_seconds, beats_to_seconds, seconds_to_beats, seconds_to_bars
from helpers.preflight import get_session_state, invalidate_session_cache, get_track_index_by_name, get_device_index_by_name, get_device_parameter_value
