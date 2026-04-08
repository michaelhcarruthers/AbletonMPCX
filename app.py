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

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
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
import tools.analysis            # noqa: F401
import tools.realtime_analyzer   # noqa: F401
import tools.arrangement_bridge  # noqa: F401
import tools.observer_bridge     # noqa: F401
import tools.audit               # noqa: F401

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
# Build OpenAI tool definitions from the FastMCP instance
# ---------------------------------------------------------------------------

async def _get_tool_definitions() -> list[dict]:
    """Convert FastMCP tool list to OpenAI function-calling format."""
    tools_list = await mcp.list_tools()
    definitions = []
    for tool in tools_list:
        # Strip the wrapping title key that FastMCP adds; OpenAI wants a plain
        # object schema with just properties / required / etc.
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


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are AMCPX, an AI music production assistant controlling Ableton Live in real time.\n"
    "You have direct access to MCP tools that read session state, control tracks, clips, devices, and the mixer.\n"
    "The user is a music producer. Be concise. Execute commands directly when asked.\n"
    "Always confirm what you did and the result. Never ask for confirmation unless the action is destructive."
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
    """Call an MCP tool and return its result as a string.

    Catches connection errors so the model can explain them to the user
    without crashing the server.
    """
    try:
        content_list, _output = await mcp.call_tool(name, args)
        # content_list is a list of TextContent / other MCP content objects
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
        # Catch-all for unexpected tool errors so OpenAI can relay them to the
        # user.  SystemExit / KeyboardInterrupt are BaseException subclasses and
        # are not caught here.
        return f"Error: {exc}"


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    client = _get_openai_client()
    tool_definitions = await _get_tool_definitions()

    # Build the messages array
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    executed_tool_calls: list[ToolCallResult] = []

    # Agentic loop — keep going until the model stops calling tools
    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tool_definitions if tool_definitions else None,
            tool_choice="auto" if tool_definitions else None,
        )

        choice = response.choices[0]
        msg = choice.message

        # Append the assistant turn to the running messages list
        messages.append(msg.model_dump(exclude_none=True))

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            # Execute each tool call and feed results back
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
            # Model is done — extract final text reply
            reply = msg.content or ""
            return ChatResponse(reply=reply, tool_calls=executed_tool_calls)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    # 0.0.0.0 is intentional — allows access from other devices on the same
    # LAN (e.g. iPad/phone in the studio).  Change to 127.0.0.1 if you want
    # localhost-only access.
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
