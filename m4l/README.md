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

Inside the device, `node.script` runs `amcpx_node_server.js` — a Node for Max
script that opens the TCP server and uses `maxApi.call` to query Live's LOM via
`LiveAPI`. This gives full access to `song.tracks[n].arrangement_clips` — the
only reliable way to read arrangement clips in Ableton Live.

## TCP Protocol

All messages use a **4-byte big-endian length prefix + UTF-8 JSON body**. The
server uses a persistent per-connection buffer (stream buffering) to correctly
handle cases where the header and body arrive in the same TCP chunk.

## Troubleshooting

- Run `lsof -i :9878` in Terminal — you should see a `node` process listening
- If the Max console says `can't find file amcpx_node_server.js`, make sure
  `amcpx_node_server.js` is in the same folder as `AMCPX_Bridge.amxd`
- If `node.script` does not auto-start, right-click it → Inspector → enable **Autostart**
- Remove and re-add the device in Live after any file changes

## Requirements

- Ableton Live 11 or 12 with Max for Live (Suite edition, or Max for Live add-on)
- AMCPX MCP server running

---

# AMCPX Observer — Max for Live Device

The `AMCPX_Observer.amxd` device watches the currently selected track, device,
parameter, and playhead position — pushing state continuously to Node so Claude
always has current context without polling.

## Setup

1. Open your Live set
2. Drag `AMCPX_Observer.amxd` onto **any track** (MIDI or Audio)
3. Make sure the device is **active** (green power button, not bypassed)
4. Leave it there for the session — it updates state automatically

## What it enables

| Tool | Description |
|------|-------------|
| `m4l_observer_ping()` | Check the observer device is running |
| `m4l_get_observer_state()` | Full state snapshot (track, device, parameter, playhead) |
| `m4l_get_selected_track()` | Currently selected track index and name |
| `m4l_get_selected_device()` | Currently selected device name |
| `m4l_get_selected_parameter()` | Currently selected parameter name and value |
| `m4l_get_playhead()` | Current song time in beats and bar number |

## How it works

The device opens a TCP server on **port 9879** (separate from the Bridge on 9878
and the Remote Script on 9877). Inside the device, four `live.observer` objects
watch `live_set.view.selected_track`, `selected_device`, `selected_parameter`,
and `live_set.current_song_time`. When any value changes, the observer fires a
message to `node.script` which runs `amcpx_observer_server.js`. The Node script
updates an in-memory state object; TCP clients call `get_state` (or individual
sub-commands) to read the latest values without any round-trip to Live's LOM.

The `current_song_time` observer is throttled to 100ms via a `speedlim` object
to avoid flooding Node with audio-rate updates.

## TCP Protocol

Same as the Bridge device: **4-byte big-endian length prefix + UTF-8 JSON body**.
Stream buffering (persistent per-connection buffer, single `data` listener) handles
TCP chunks correctly.

## Troubleshooting

- Run `lsof -i :9879` in Terminal — you should see a `node` process listening
- If the Max console says `can't find file amcpx_observer_server.js`, make sure
  `amcpx_observer_server.js` is in the same folder as `AMCPX_Observer.amxd`
- If `node.script` does not auto-start, right-click it → Inspector → enable **Autostart**
- Remove and re-add the device in Live after any file changes
