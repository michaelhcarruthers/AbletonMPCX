"""
AbletonMPCX MCP Server — entry point.

Starts the FastMCP server and imports all domain tool modules so that every
@mcp.tool() decorator registers against the shared ``mcp`` instance.

Set AMCPX_TOOL_GROUPS in .env to load only specific groups, e.g.:
    AMCPX_TOOL_GROUPS=base,session,mixer,clips,arrangement,devices

If AMCPX_TOOL_GROUPS is not set, all dispatcher modules are loaded along
with the implementation modules they depend on.

Run modes:
    # stdio (Claude Desktop) — auto-detected when stdin is not a TTY
    python server.py

    # HTTP (ChatGPT Desktop) — auto-detected when run from a terminal
    python server.py
    # Connect ChatGPT Desktop to: http://localhost:8081/mcp

    # Force a specific transport
    python server.py --transport stdio
    python server.py --transport http
"""
from __future__ import annotations

import importlib
import logging
import os

from dotenv import load_dotenv
load_dotenv(override=False)

from helpers import mcp  # noqa: F401 — creates the FastMCP instance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Selective tool module loading based on AMCPX_TOOL_GROUPS env var
# ---------------------------------------------------------------------------

# Implementation modules — must be loaded before dispatcher modules so that
# internal functions are already defined when dispatchers import them.
_IMPL_MODULES = [
    "tools.theory",
    "tools.session",
    "tools.session_snapshots",
    "tools.session_suggestions",
    "tools.session_recording",
    "tools.tracks",
    "tools.clips",
    "tools.devices",
    "tools.staging",
    "tools.morph",
    "tools.reference",
    "tools.audit",
    "tools.performance",
    "tools.diagnostics",
    "tools.arrangement_bridge",
    "tools.observer_bridge",
    "tools.realtime_analyzer",
    "tools.mix_templates",
    "tools.spectrum",
    "tools.analysis",
]

# Dispatcher modules — thin routing layer loaded after implementation modules.
_DISPATCHER_MODULES = [
    "tools.dispatchers.arrangement_tool",
    "tools.dispatchers.device_tool",
    "tools.dispatchers.analysis_tool",
    "tools.dispatchers.render_tool",
    "tools.dispatchers.project_tool",
]

# Combined list for backward-compatible "load everything" mode
_ALL_MODULES = _IMPL_MODULES + _DISPATCHER_MODULES

_groups_env = os.environ.get("AMCPX_TOOL_GROUPS", "").strip()

if not _groups_env:
    # No filter — load implementation modules then dispatcher modules
    _modules_to_load = _ALL_MODULES
else:
    from tool_groups import TOOL_GROUP_MODULES

    requested_groups = [g.strip() for g in _groups_env.split(",") if g.strip()]

    # Always include base
    groups_to_load = list(dict.fromkeys(["base"] + requested_groups))

    _modules_to_load_list: list[str] = []
    for group in groups_to_load:
        for mod in TOOL_GROUP_MODULES.get(group, []):
            if mod not in _modules_to_load_list:
                _modules_to_load_list.append(mod)
    _modules_to_load = _modules_to_load_list

    logger.info("AMCPX_TOOL_GROUPS=%s → loading modules: %s", _groups_env, _modules_to_load)

for _mod in _modules_to_load:
    importlib.import_module(_mod)

# Start the background observer thread (defined in tools.audit) only if audit is loaded
if "tools.audit" in _modules_to_load:
    from tools.audit import _start_observer
    _start_observer()

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="AMCPX MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="Transport mode: stdio (Claude Desktop) or http (ChatGPT Desktop). Auto-detected if not set.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind when using HTTP transport. Default: 0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="Port to bind when using HTTP transport. Default: 8081",
    )
    args = parser.parse_args()

    # Auto-detect transport if not explicitly set:
    # Claude Desktop spawns server.py as a subprocess with a non-TTY stdin → stdio
    # Running manually from a terminal → http (for ChatGPT Desktop)
    if args.transport is None:
        args.transport = "stdio" if not sys.stdin.isatty() else "http"

    logger.info("AMCPX transport: %s", args.transport)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            path="/mcp",
        )
