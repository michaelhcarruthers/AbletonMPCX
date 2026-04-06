# AMCPX Bridge — Max for Live Device

The `AMCPX_Bridge.amxd` device gives the AMCPX MCP server full access to
Ableton's Arrangement View — something the Python Remote Script API cannot do.

## Setup

1. Open your Live set
2. Drag `AMCPX_Bridge.amxd` onto **any track** (MIDI or Audio)
3. Make sure the device is **active** (green power button, not bypassed)
4. Leave it there for the session — it runs silently in the background

## What it enables

| Tool | Description |
|------|-------------|
| `m4l_ping()` | Check the bridge is running |
| `m4l_get_arrangement_clips()` | List ALL arrangement clips with positions |
| `m4l_get_arrangement_clip_info()` | Full info for one clip |
| `m4l_get_arrangement_clip_notes()` | Read MIDI notes from any arrangement clip |
| `m4l_set_arrangement_clip_notes()` | Write MIDI notes to any arrangement clip |
| `m4l_get_arrangement_overview()` | High-level arrangement structure summary |

## How it works

The device opens a TCP server on **port 9878** (separate from the Remote Script
on port 9877). The MCP server connects to it using the same length-prefixed JSON
protocol used by the Remote Script.

Inside the device, a JavaScript file (`amcpx_bridge.js`) uses Max for Live's
`LiveAPI` to traverse `song.tracks[n].arrangement_clips` — the only reliable
way to access arrangement clips in Ableton Live.

## Requirements

- Ableton Live 11 or 12 with Max for Live (Suite edition, or Max for Live add-on)
- AMCPX MCP server running

> **Note:** The TCP server in the patch uses `mxj net.tcp.server`, a Java-based
> Max object included with Max for Live. It is available in all standard Max for
> Live installations.
