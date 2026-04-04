# AbletonMPCX

**AbletonMPCX** is an MCP (Model Context Protocol) server that gives an AI assistant full control of Ableton Live via its Live Object Model (LOM). It consists of two parts:

- **`server.py`** — the MCP server, runs outside Live, exposes ~100 tools to the AI.
- **`__init__.py`** — the Ableton Remote Script, runs *inside* Live, receives commands over a local TCP socket and executes them on Live's main thread.

---

## Requirements

- Python 3.10+
- [`mcp[cli]`](https://pypi.org/project/mcp/) ≥ 1.0.0
- Ableton Live 11 or later (Live 12 recommended)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/michaelhcarruthers/AbletonMPCX.git
cd AbletonMPCX
```

### 2. Install Python dependencies

```bash
pip install mcp[cli]
```

### 3. Install the Remote Script inside Ableton Live

Copy (or symlink) the `AbletonMPCX` folder into Ableton's MIDI Remote Scripts directory so that `__init__.py` lives at:

| Platform | Path |
|----------|------|
| **macOS** | `~/Library/Preferences/Ableton/Live <version>/User Remote Scripts/AbletonMPCX/__init__.py` |
| **Windows** | `%APPDATA%\Ableton\Live <version>\Preferences\User Remote Scripts\AbletonMPCX\__init__.py` |

Quick copy on macOS:
```bash
LIVE_VERSION="Live 12.1"   # adjust to your version
mkdir -p ~/Library/Preferences/Ableton/"$LIVE_VERSION"/User\ Remote\ Scripts/AbletonMPCX
cp __init__.py ~/Library/Preferences/Ableton/"$LIVE_VERSION"/User\ Remote\ Scripts/AbletonMPCX/
```

### 4. Enable the Control Surface in Live

1. Open Ableton Live.
2. Go to **Preferences → Link, Tempo & MIDI** (or **Link/MIDI** in older versions).
3. Under **Control Surfaces**, select **AbletonMPCX** in one of the slots.
4. Set **Input** and **Output** to **None** (AbletonMPCX uses TCP, not MIDI ports).
5. Click **OK**. Live will load the script and start listening on `localhost:9877`.

### 5. Run the MCP server

```bash
python server.py
```

Or configure it in your MCP client (e.g. Claude Desktop) by adding an entry to `mcp_servers.json`:

```json
{
  "mcpServers": {
    "ableton": {
      "command": "python",
      "args": ["/path/to/AbletonMPCX/server.py"]
    }
  }
}
```

---

## Available Tools

Tools are grouped by area of the Live Object Model:

| Category | Tools |
|----------|-------|
| **Application** | `get_app_version` |
| **Song / Transport** | `get_song_info`, `start_playing`, `stop_playing`, `continue_playing`, `tap_tempo`, `undo`, `redo`, `set_tempo`, `set_time_signature`, `set_metronome`, `set_loop`, `set_record_mode`, `set_session_record`, `set_overdub`, `set_swing_amount`, `set_groove_amount`, `set_back_to_arranger`, `set_clip_trigger_quantization`, `set_midi_recording_quantization`, `set_scale_mode`, `set_scale_name`, `set_root_note`, `capture_midi`, `capture_and_insert_scene`, `jump_by`, `jump_to_next_cue`, `jump_to_prev_cue`, `stop_all_clips`, `get_cue_points`, `jump_to_cue_point`, `set_or_delete_cue`, `re_enable_automation`, `play_selection` |
| **Song.View** | `get_selected_track`, `set_selected_track`, `get_selected_scene`, `set_selected_scene`, `get_follow_song`, `set_follow_song`, `get_draw_mode`, `set_draw_mode` |
| **Master Track** | `get_master_track`, `set_master_volume`, `set_master_pan`, `set_crossfader` |
| **Tracks** | `get_tracks`, `get_track_info`, `create_audio_track`, `create_midi_track`, `create_return_track`, `delete_track`, `delete_return_track`, `duplicate_track`, `set_track_name`, `set_track_color`, `set_track_mute`, `set_track_solo`, `set_track_arm`, `set_track_volume`, `set_track_pan`, `set_track_send`, `set_crossfade_assign`, `stop_track_clips`, `set_track_fold_state`, `get_return_tracks`, `get_track_routing`, `set_track_input_routing_type`, `set_track_input_routing_channel`, `set_track_output_routing_type`, `set_track_output_routing_channel` |
| **Clip Slots** | `get_clip_slots`, `fire_clip_slot`, `stop_clip_slot`, `create_clip`, `delete_clip`, `duplicate_clip_slot` |
| **Clips** | `get_clip_info`, `set_clip_name`, `set_clip_color`, `set_clip_loop`, `set_clip_markers`, `set_clip_mute`, `set_clip_pitch`, `set_clip_gain`, `set_clip_warp_mode`, `set_clip_launch_mode`, `set_clip_launch_quantization`, `get_clip_follow_actions`, `set_clip_follow_actions`, `fire_clip`, `stop_clip`, `crop_clip`, `duplicate_clip_loop`, `quantize_clip` |
| **MIDI Notes** | `get_notes`, `add_notes`, `replace_all_notes`, `remove_notes`, `apply_note_modifications`, `select_all_notes`, `deselect_all_notes` |
| **Scenes** | `get_scenes`, `get_scene_info`, `create_scene`, `delete_scene`, `duplicate_scene`, `set_scene_name`, `set_scene_tempo`, `set_scene_color`, `fire_scene` |
| **Devices** | `get_devices`, `get_device_info`, `get_device_parameters`, `set_device_parameter`, `set_device_enabled`, `delete_device`, `duplicate_device` |
| **Mixer Device** | `get_mixer_device`, `set_crossfade_assign` |
| **Rack / Drum Rack** | `get_rack_chains`, `get_rack_drum_pads`, `randomize_rack_macros`, `store_rack_variation` |
| **Groove Pool** | `get_grooves` |
| **Browser** | `get_browser_tree`, `get_browser_items_at_path`, `load_browser_item` |
| **Feel / Humanization** | `analyze_clip_feel`, `humanize_notes`, `humanize_dilla` |
| **Reference Profiles** | `designate_reference_clip`, `compare_clip_feel`, `designate_reference_mix_state`, `compare_mix_state`, `list_reference_profiles`, `delete_reference_profile` |

---

## Reference Profiles

Reference profiles let you capture the feel or mix state of a clip/session and compare it against future states. All profiles are stored in-process and persisted to project memory (requires `set_project_id()` to be called first).

### Clip feel profiles

| Tool | Description |
|------|-------------|
| `designate_reference_clip(track_index, slot_index, label='default')` | Analyse a MIDI clip's timing and velocity feel and save it as a named reference. Captures timing variance, lateness bias, velocity spread, and per-pitch stats. |
| `compare_clip_feel(track_index, slot_index, reference_label='default')` | Compare a MIDI clip against a stored clip feel reference. Returns deltas and human-readable flags (tighter/looser timing, earlier/later bias, uniform/varied velocities). |

### Mix state profiles

| Tool | Description |
|------|-------------|
| `designate_reference_mix_state(label='default', scene_index=None)` | Capture the current mix state (volumes, panning, sends, mute/solo, device counts) as a named reference. |
| `compare_mix_state(reference_label='default', scene_index=None)` | Compare the current mix state against a stored reference. Reports per-track volume, pan, send, and mute changes plus master volume delta. |

### Profile management

| Tool | Description |
|------|-------------|
| `list_reference_profiles()` | List all stored reference profiles with their type, timestamp, and key stats. |
| `delete_reference_profile(label)` | Delete a reference profile by label (in-process and from project memory). |

---

## Protocol

The MCP server (`server.py`) communicates with the Remote Script (`__init__.py`) over a plain TCP socket on `localhost:9877`.

**Request** (JSON):
```json
{"command": "set_tempo", "params": {"tempo": 128.0}}
```

**Success response**:
```json
{"status": "ok", "result": {}}
```

**Error response**:
```json
{"status": "error", "error": "track_index 99 out of range"}
```

---

## Notes

- The Remote Script runs on Ableton's internal Python interpreter (CPython 3.6+ in Live 11/12).
- All state-mutating operations are dispatched to Live's main thread via `schedule_message` to avoid threading issues.
- A new TCP connection is opened for each MCP tool call; no persistent connection is required.
- The server listens only on `localhost` — it is not exposed to the network.

