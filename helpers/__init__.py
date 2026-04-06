"""Shared helpers — MCP instance, low-level socket transport, and operation log."""
from __future__ import annotations

import collections
import datetime
import json
import math
import os
import pathlib
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

# --- Connection settings ---
ABLETON_HOST = "localhost"
ABLETON_PORT = 9877

mcp = FastMCP("AbletonMPCX")


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
# Operation log
# ---------------------------------------------------------------------------

_operation_log: list[dict] = []
_MAX_LOG_ENTRIES = 1000


def _append_operation(command: str, params: dict, result: Any):
    """Append an operation to the in-process log."""
    global _operation_log
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": command,
        "params": params,
        "result_summary": str(result)[:200] if result is not None else None,
    }
    _operation_log.append(entry)
    if len(_operation_log) > _MAX_LOG_ENTRIES:
        _operation_log = _operation_log[-_MAX_LOG_ENTRIES:]


# ---------------------------------------------------------------------------
# High-level send helpers
# ---------------------------------------------------------------------------

def _send(command: str, params: dict[str, Any] | None = None, _log: bool = True) -> Any:
    payload = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
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


def _send_logged(command: str, params: dict[str, Any] | None = None) -> Any:
    """Like _send but appends to the operation log. Kept for compatibility; _send now logs by default."""
    return _send(command, params)
