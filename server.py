"""
AbletonMPCX MCP Server — entry point.

Starts the FastMCP server and imports all domain tool modules so that every
@mcp.tool() decorator registers against the shared ``mcp`` instance.
"""
from helpers import mcp  # noqa: F401 — creates the FastMCP instance

# Import all tool modules so their @mcp.tool() decorators fire
import tools.session      # noqa: F401  (also imports session_snapshots, session_suggestions, session_recording)
import tools.tracks       # noqa: F401
import tools.clips        # noqa: F401
import tools.devices      # noqa: F401
import tools.audit        # noqa: F401
import tools.performance  # noqa: F401
import tools.diagnostics  # noqa: F401
import tools.analysis             # noqa: F401
import tools.arrangement_bridge   # noqa: F401

# Start the background observer thread (defined in tools.audit)
from tools.audit import _start_observer
_start_observer()

if __name__ == "__main__":
    mcp.run()
