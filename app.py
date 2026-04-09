"""
AMCPX Chat UI — FastAPI backend.

Serves the browser chat interface and proxies requests to the OpenAI API,
executing AMCPX tool calls by importing the existing tool modules directly.

Running:
    # 1. Copy and fill in your key
    cp .env.example .env

    # 2. Start the server
    python app.py

    # 3. Open browser
    #    http://localhost:8080
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

# ---------------------------------------------------------------------------
# Import the MCP instance and register all tool modules (same as server.py)
# ---------------------------------------------------------------------------
from helpers import mcp  # noqa: F401 — creates the FastMCP instance

import tools.session             # noqa: F401
import tools.tracks              # noqa: F401
import tools.clips               # noqa: F401
import tools.devices             # noqa: F401
import tools.performance         # noqa: F401
import tools.diagnostics         # noqa: F401
# import tools.analysis            # noqa: F401  # disabled: requires exported audio files
import tools.realtime_analyzer   # noqa: F401
import tools.arrangement_bridge  # noqa: F401
import tools.observer_bridge     # noqa: F401
import tools.audit               # noqa: F401
import tools.mix_templates       # noqa: F401
import tools.theory              # noqa: F401

# Start the background observer thread (defined in tools.audit)
from tools.audit import _start_observer
_start_observer()

# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------
from openai import OpenAI

_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

# ---------------------------------------------------------------------------
# Tool definitions — group-based routing to stay under OpenAI's 128-tool cap
# ---------------------------------------------------------------------------

_all_tools_cache: list | None = None


async def _get_all_tools_cached():
    global _all_tools_cache
    if _all_tools_cache is None:
        _all_tools_cache = await mcp.list_tools()
    return _all_tools_cache


def _tools_to_openai_format(tools_list) -> list[dict]:
    definitions = []
    for tool in tools_list:
        schema = dict(tool.inputSchema)
        schema.pop("title", None)
        definitions.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": schema,
            },
        })
    return definitions


async def _get_tool_definitions_for_groups(groups: list[str]) -> list[dict]:
    from tool_groups import TOOL_GROUPS
    all_tools = await _get_all_tools_cached()
    seen: set[str] = set()
    filtered: list = []
    for group in groups:
        prefixes = TOOL_GROUPS.get(group, [])
        for t in all_tools:
            if t.name not in seen and any(t.name == p or t.name.startswith(p) for p in prefixes):
                filtered.append(t)
                seen.add(t.name)
    if not filtered:
        filtered = all_tools[:120]
    filtered = filtered[:128]  # stay under OpenAI's 128-tool cap
    return _tools_to_openai_format(filtered)


def _group_selector_tool() -> list[dict]:
    from tool_groups import TOOL_GROUPS
    return [
        {
            "type": "function",
            "function": {
                "name": "select_tool_group",
                "description": (
                    "Select 1 or 2 tool groups that best match the user's request. "
                    "Pick 2 only if the task clearly spans both (e.g. mixer + arrangement). "
                    "Otherwise pick 1. "
                    "Call this first to get access to the right set of Ableton tools. "
                    "Groups:\n"
                    "- session: tempo, time signature, snapshots, recording, project memory\n"
                    "- mixer: track volumes, panning, sends, mute/solo, routing\n"
                    "- clips: fire/stop clips, notes, quantize, chop, slice\n"
                    "- devices: device parameters, batch set, morph, staging\n"
                    "- arrangement: arrangement clips, automation, loop/punch points\n"
                    "- performance: macros, sidechain, resampling, scenes, observers\n"
                    "- diagnostics: logs, audit, health checks, validation\n"
                    "- templates: classify tracks by role, apply genre mix templates, preview processing\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "groups": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": list(TOOL_GROUPS.keys()),
                            },
                            "minItems": 1,
                            "maxItems": 2,
                            "description": "One or two tool groups to load. Pick two only if the request clearly spans both.",
                        }
                    },
                    "required": ["groups"],
                },
            },
        }
    ]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are AMCPX, an AI music production assistant controlling Ableton Live in real time.\n"
    "You have direct access to MCP tools that read session state, control tracks, clips, devices, and the mixer.\n"
    "The user is a music producer. Be concise. Execute commands directly when asked.\n"
    "Always confirm what you did and the result. Never ask for confirmation unless the action is destructive.\n"
    "Always use slim=True (the default) on get_tracks, get_arrangement_clips, get_session_clips, get_notes, get_devices, get_mix_snapshot, and get_automation_data unless you specifically need full device parameter lists, full note arrays, or full automation envelopes. Only pass slim=False when you have a specific reason to need the complete data."
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="AMCPX Chat")

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(_STATIC_DIR / "index.html"))

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ToolCallResult(BaseModel):
    tool: str
    args: dict
    result: str


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallResult] = []

# ---------------------------------------------------------------------------
# /chat endpoint
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


async def _execute_tool(name: str, args: dict) -> str:
    """Call an MCP tool and return its result as a string."""
    try:
        result = await mcp.call_tool(name, args)
        content_list = result if isinstance(result, list) else getattr(result, "content", [result])
        parts = []
        for item in content_list:
            if hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else "(no output)"
    except ConnectionRefusedError:
        return "Error: Could not connect to Ableton Live. Is the Remote Script running on port 9877?"
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    client = _get_openai_client()

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    executed_tool_calls: list[ToolCallResult] = []

    # tool_search disabled — full tool list injected directly
    tool_definitions = _tools_to_openai_format((await _get_all_tools_cached())[:128])

    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tool_definitions if tool_definitions else None,
            tool_choice="auto" if tool_definitions else None,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump(exclude_none=True))

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            for tc in msg.tool_calls:
                fn = tc.function
                try:
                    args = json.loads(fn.arguments) if fn.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                result_str = await _execute_tool(fn.name, args)
                executed_tool_calls.append(
                    ToolCallResult(tool=fn.name, args=args, result=result_str)
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })
        else:
            reply = msg.content or ""
            return ChatResponse(reply=reply, tool_calls=executed_tool_calls)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    # 0.0.0.0 is intentional — allows access from other devices on the same
    # LAN (e.g. iPad/phone in the studio). Change to 127.0.0.1 for localhost-only.
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)