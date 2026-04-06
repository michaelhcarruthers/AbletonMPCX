# AbletonMPCX Roadmap

## What is AbletonMPCX?

AbletonMPCX is a Model Context Protocol (MCP) server that exposes Ableton Live's session, transport, mixer, device, clip, and arrangement APIs as callable tools. An AI agent (Claude, Copilot, etc.) connects to the MCP server via stdio and can then control every aspect of a running Live session — from setting tempo and firing clips to humanising MIDI, building arrangement scaffolds, and sweeping effect parameters using natural-language magnitude descriptions.

---

## Current Module Structure

```
server.py                  # 24-line entry point — imports all modules, starts observer thread
helpers/
  __init__.py              # FastMCP instance (mcp), TCP socket helpers (_send), operation log, project memory
  cache.py                 # In-process state-diff cache
  session_state.py         # Per-session AI handoff: save/load/summary helpers
  summarizer.py            # Compact response summarisers
  vocabulary.py            # Natural language → parameter delta / time mappings
tools/
  session.py               # Song, transport, snapshots, views, scaffolds, capabilities (112 tools)
  tracks.py                # Track creation, routing, mix controls (27 tools)
  clips.py                 # Clip editing, notes, envelopes, device management (48 tools)
  devices.py               # Browser, scenes, rack, return tracks (25 tools)
  audit.py                 # Audio analysis, humanise, reference profiles, health report (28 tools)
  spectrum.py              # Spectrum analyser telemetry, automation writing (8 tools)
  performance.py           # DJ/live performance macros (10 tools)
  diagnostics.py           # Mix balance, preset audit, library scanning (6 tools)
  arrangement_bridge.py    # M4L bridge tools — arrangement clips via port 9878 (6 tools)
m4l/
  AMCPX_Bridge.maxpat      # Max for Live patch — TCP server on port 9878
  amcpx_node_server.js     # Node for Max TCP server — LiveAPI access to arrangement_clips
  README.md                # Setup instructions
session_state.json         # Persisted AI handoff state (written each significant session)
```

**Total registered MCP tools: 269**

---

## Completed PRs

| PR | Description |
|----|-------------|
| #17–#35 | Phases 1–7 — core tool suite built incrementally |
| #36 | Performance FX macros (filter sweep, reverb throw, stutter, delay echo) |
| #41 | Combined session management, performance macros, sound recording, arrangement automation |
| #44 | Project audit tools (health report, missing media, reference profiles) |
| #45 | DJ blend/transition macros |
| #47 | Refactor — split 9 103-line server.py into focused domain modules |
| #48 | Repo infrastructure (ROADMAP, session state, get_capabilities, vocabulary) |
| #49 | Core tools A–D: auto_orient, cleanup, relative parameter adjustment, arrangement clips |
| #50 | Mix intelligence E–G: levels overview, clipping watch, batch audit, screenshot |
| #51 | Performance optimisation H–N: state diff, summarisers, diagnostics, bundling, alias registry |
| #52 | Plugins P1–P3: spectrum peak hold, dynamics telemetry, stereo field analyser |
| #53 | Fix 8 bundled code review issues: broken imports, clip duplication bug, schema drift, dead imports, stale docs |
| #54 | M4L bridge: `AMCPX_Bridge.amxd` + `tools/arrangement_bridge.py` — full Arrangement View access via port 9878 |

---

## Full Build Queue

### Repo infrastructure (completed in #48)

| ID | Item | Status |
|----|------|--------|
| R1 | `ROADMAP.md` — single recovery document | ✅ Done |
| R2 | `helpers/session_state.py` + `session_state.json` — AI handoff file | ✅ Done |
| R3 | `get_capabilities()` — grouped capability surface on connect | ✅ Done |
| R4 | `helpers/vocabulary.py` — natural language → parameter delta | ✅ Done |

### Core tools

| ID | Item | Status |
|----|------|--------|
| A | Auto-orient on connect | ✅ Done |
| B | Empty tracks, unused returns, stage + execute cleanup | ✅ Done |
| C | Relative parameter changes (uses R4 vocabulary) | ✅ Done |
| D | Arrangement clips + missing file detection | ✅ Done |

### Mix intelligence

| ID | Item | Status |
|----|------|--------|
| E | `get_mix_levels_overview()` + `watch_for_clipping()` | ⬜ Pending |
| F | Batch audit — `open_set(path)` + `batch_audit_projects(paths)` | ✅ Done |
| G | Screenshot tool — autonomous, no human in loop | ⬜ Pending |

### Performance optimisation

| ID | Item | Status |
|----|------|--------|
| H | State diff cache | ✅ Done |
| I | Compact summarisers | ✅ Done |
| J | Diagnostic tools per question | ✅ Done |
| K | Threshold engine for spectrum data | ✅ Done |
| L | Tool call bundling | ✅ Done (`get_full_session_state`) |
| M | Per-project cached audit JSON files | ✅ Done |
| N | Device/parameter alias registry | ✅ Done |

### Plugins

| ID | Item | Status |
|----|------|--------|
| P1 | Peak hold mod to existing spectrum plugin | ✅ Done |
| P2 | Dynamics telemetry plugin | ✅ Done |
| P3 | Stereo field analyser | ✅ Done |

### M4L Bridge

| ID | Item | Status |
|----|------|--------|
| M1 | `m4l/AMCPX_Bridge.maxpat` — Max patch with TCP server on port 9878 | ✅ Done |
| M2 | `m4l/amcpx_node_server.js` — Node for Max TCP server with stream buffering | ✅ Done |
| M3 | `tools/arrangement_bridge.py` — 6 MCP tools connecting to port 9878 | ✅ Done |

---

## Key Design Decisions

- **Transport**: JSON over TCP on `localhost:9877`. Each message is length-prefixed (4-byte big-endian header + UTF-8 JSON body). Ableton-side plugin listens; MCP server is the client.
- **M4L Bridge**: The `AMCPX_Bridge.amxd` Max for Live device exposes a second TCP server on `localhost:9878` using the same length-prefixed JSON protocol. It runs via `node.script` (Node for Max) executing `amcpx_node_server.js`. The server uses **stream buffering** (persistent per-connection buffer) to correctly handle TCP framing — a single `data` listener accumulates chunks and processes complete messages. It provides full Arrangement View access via `LiveAPI` — something the Python Remote Script API cannot do. Tools in `tools/arrangement_bridge.py` connect to port 9878 independently.
- **MCP pattern**: FastMCP (`mcp.server.fastmcp`). Every public action is a `@mcp.tool()` function. The server runs over stdio (Claude connects via `mcp` CLI or MCP config JSON).
- **Vocabulary system**: Natural-language magnitude words ("a little", "a lot", "drenched") map to normalised deltas (0.0–1.0) via `helpers/vocabulary.py`. Time words ("fast", "gradually") map to seconds.
- **Module layout**: One concern per file. `helpers/__init__.py` owns the shared FastMCP instance and TCP primitives; `tools/*.py` own the business logic. No circular imports.
- **Snapshots**: Full session snapshots stored in `~/.ableton_mpcx/projects/<project_id>.json`. In-process snapshot cache in `helpers/__init__.py`.

---

## How to Resume Work After a Context Reset

1. Read this file (`ROADMAP.md`) to orient.
2. Read `session_state.json` (or call `get_capabilities()` once connected) to know exact current state.
3. Check open PRs on GitHub for any in-progress work.
4. Pick the next pending item from the build queue above and open a new PR.

### Quick start commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the MCP server (connects to Ableton on localhost:9877)
python server.py
```

The Ableton-side Remote Script plugin must be running inside Live before the MCP server can communicate. See `README.md` for full setup instructions.
