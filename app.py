"""
AMCPX MCP Server — entry point for ChatGPT Desktop.

Registers all tool modules against the shared FastMCP instance and serves
the MCP endpoint at /mcp via FastMCP's built-in streamable-http transport.

Running:
    # 1. Copy and fill .env
    cp .env.example .env

    # 2. Start the server
    python app.py

    # ChatGPT Desktop — connect to: http://localhost:8080/mcp
"""
from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv(override=False)

# ---------------------------------------------------------------------------
# Import the MCP instance and register all tool modules
# ---------------------------------------------------------------------------
from helpers import mcp  # noqa: F401 — creates the FastMCP instance

import tools.theory              # noqa: F401
import tools.session             # noqa: F401
import tools.session_snapshots   # noqa: F401
import tools.session_suggestions # noqa: F401
import tools.session_recording   # noqa: F401
import tools.tracks              # noqa: F401
import tools.clips_core          # noqa: F401
import tools.clips_playback      # noqa: F401
import tools.clips_envelopes     # noqa: F401
import tools.clips_notes         # noqa: F401
import tools.clips_arrangement   # noqa: F401
import tools.devices             # noqa: F401
import tools.staging             # noqa: F401
import tools.morph               # noqa: F401
import tools.reference           # noqa: F401
import tools.audit               # noqa: F401
import tools.performance         # noqa: F401
import tools.diagnostics         # noqa: F401
import tools.arrangement_bridge  # noqa: F401
import tools.observer_bridge     # noqa: F401
import tools.realtime_analyzer   # noqa: F401
import tools.mix_templates       # noqa: F401
import tools.spectrum            # noqa: F401
# import tools.analysis          # noqa: F401  # disabled: requires exported audio files
import tools.dispatchers.arrangement_tool  # noqa: F401
import tools.dispatchers.device_tool       # noqa: F401
import tools.dispatchers.analysis_tool     # noqa: F401
import tools.dispatchers.render_tool       # noqa: F401
import tools.dispatchers.project_tool      # noqa: F401

# Start the background observer thread (defined in tools.audit)
from tools.audit import _start_observer
_start_observer()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="streamable-http")