# AbletonMPCX

**AbletonMPCX** is an MCP (Model Context Protocol) server that gives an AI assistant full control of Ableton Live via its Live Object Model (LOM). It consists of two parts:

- **`server.py`** — the MCP server, runs outside Live, exposes 265 tools to the AI.
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
| **Track Routing** | `get_track_routing`, `get_available_routings`, `set_track_input_routing`, `set_track_output_routing` |
| **Resampling** | `setup_resampling_route`, `teardown_resampling_route` |
| **Clip Slots** | `get_clip_slots`, `fire_clip_slot`, `stop_clip_slot`, `create_clip`, `delete_clip`, `duplicate_clip_slot` |
| **Clips** | `get_clip_info`, `set_clip_name`, `set_clip_color`, `set_clip_loop`, `set_clip_markers`, `set_clip_mute`, `set_clip_pitch`, `set_clip_gain`, `set_clip_warp_mode`, `set_clip_launch_mode`, `set_clip_launch_quantization`, `get_clip_follow_actions`, `set_clip_follow_actions`, `fire_clip`, `stop_clip`, `crop_clip`, `duplicate_clip_loop`, `quantize_clip` |
| **Clip Automation Envelopes** | `get_clip_envelopes`, `get_clip_envelope`, `clear_clip_envelope`, `insert_clip_envelope_point`, `set_clip_envelope_points` |
| **MIDI Notes** | `get_notes`, `add_notes`, `replace_all_notes`, `remove_notes`, `apply_note_modifications`, `select_all_notes`, `deselect_all_notes` |
| **Scenes** | `get_scenes`, `get_scene_info`, `create_scene`, `delete_scene`, `duplicate_scene`, `set_scene_name`, `set_scene_tempo`, `set_scene_color`, `fire_scene` |
| **Devices** | `get_devices`, `get_device_info`, `get_device_parameters`, `set_device_parameter`, `set_device_enabled`, `delete_device`, `duplicate_device`, `move_device` |
| **Mixer Device** | `get_mixer_device`, `set_crossfade_assign` |
| **Rack / Drum Rack** | `get_rack_chains`, `get_rack_drum_pads`, `randomize_rack_macros`, `store_rack_variation` |
| **Groove Pool** | `get_grooves`, `extract_groove_from_clip` |
| **Browser** | `get_browser_tree`, `get_browser_items_at_path`, `load_browser_item` |
| **Feel / Humanization** | `analyze_clip_feel`, `humanize_notes`, `humanize_dilla`, `auto_humanize_if_robotic`, `fix_groove_from_reference`, `batch_auto_humanize` |
| **Reference Profiles** | `designate_reference_clip`, `compare_clip_feel`, `designate_reference_mix_state`, `compare_mix_state`, `list_reference_profiles`, `delete_reference_profile` |
| **Tier 2 Audio Analysis** | `designate_reference_audio`, `analyse_audio`, `compare_audio`, `compare_audio_sections` |
| **Audio Analysis** | `get_loudness`, `get_onsets`, `get_spectral_descriptors`, `get_beat_tracking`, `get_envelope` |

---

## Resampling

`setup_resampling_route` and `teardown_resampling_route` configure a destination track for in-session resampling (capturing the processed output of another track).

### How it works

`setup_resampling_route(dest_track_index, source_track_name)` runs a single atomic call on Live's main thread that:
1. Selects the destination track in `song.view` so Live registers subsequent routing changes.
2. Searches `available_input_routing_types` on the destination track for the source track by display name and sets `input_routing_type`.
3. Searches `available_input_routing_channels` for "Post FX" and sets `input_routing_channel` (falls back to the first channel if not found).
4. Sets `current_monitoring_state = 1` (Monitor: In).
5. Sets `arm = True` last — arming after routing avoids the Live limitation where arming too early leaves routing uncommitted.

All applied and confirmed values are returned so the caller can verify the route stuck.

`teardown_resampling_route(dest_track_index)` reverses the setup:
1. Sets `arm = False`.
2. Sets `current_monitoring_state = 0` (Monitor: Auto).

| Tool | Description |
|------|-------------|
| `setup_resampling_route(dest_track_index, source_track_name)` | Route the destination track's input from the named source track (Post FX), set Monitor to In, and arm. Returns confirmed state. |
| `teardown_resampling_route(dest_track_index)` | Disarm the destination track and reset its monitoring state to Auto. |

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

## Tier 2 Audio Analysis

Tier 2 audio analysis requires librosa:

```
pip install librosa soundfile
```

Point the server at an audio file on disk (an exported bounce or a reference track). The server analyses it and stores a named audio analysis profile. The observer and `suggest_next_actions` can then compare the current session against it.

| Tool | Description |
|------|-------------|
| `designate_reference_audio(file_path, label='default_audio')` | Analyse an audio file (WAV, AIFF, FLAC, MP3) and store it as a named reference audio profile. Captures tonal balance, integrated loudness, peak level, crest factor, spectral centroid, spectral rolloff, transient density, dynamic range, and stereo width. |
| `analyse_audio(file_path)` | Analyse an audio file and return the same metrics without storing a reference profile. |
| `compare_audio(file_path, reference_label='default_audio')` | Analyse an audio file and compare it against a stored reference profile. Returns per-metric deltas and human-readable flags. |
| `compare_audio_sections(file_path, reference_label='default_audio', num_sections=4)` | Split a target audio file into N equal sections and compare each against the reference. Useful for detecting arrangement energy progression. |

> **Note:** All audio analysis tools use lazy imports. If `librosa` is not installed, the tools raise a clear `ImportError` with an install hint instead of crashing the server on startup.

---

## Workflow Loop Tools

High-level tools that combine feel analysis and humanization into single calls. These are pure server-side wrappers — no `__init__.py` changes are required.

| Tool | Description |
|------|-------------|
| `auto_humanize_if_robotic(track_index, slot_index, ...)` | Analyse the clip's feel score and apply humanization automatically if it meets the robotic threshold. Returns `applied`, `feel_score_before`, `feel_score_after`, and the humanization style used. |
| `fix_groove_from_reference(track_index, slot_index, reference_label, ...)` | Compare a clip's feel against a stored reference profile and apply targeted humanize_dilla() corrections to close timing/velocity gaps. Requires a profile created with `designate_reference_clip()`. |
| `batch_auto_humanize(track_indices, slot_index, ...)` | Run `auto_humanize_if_robotic()` across multiple tracks at the same slot index (scene row). Returns per-track results plus `applied_count` and `skipped_count`. |

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

## Audio Analysis

AbletonMPCX includes a file-based audio analysis stack built on industry-standard Python libraries. Pass an exported audio file (WAV, AIFF, or FLAC) to any of the tools below — no plugin required.

### Dependencies

```
pip install pyloudnorm aubio essentia madmom scipy soundfile
```

### Tools

| Tool | Purpose | Library |
|---|---|---|
| `get_loudness(file_path)` | Integrated LUFS, true peak, and loudness range (ITU-R BS.1770-4) | pyloudnorm |
| `get_onsets(file_path)` | Transient/onset times and inter-onset intervals | aubio |
| `get_spectral_descriptors(file_path)` | Brightness (spectral centroid), key, spectral rolloff, flatness, timbral MFCC fingerprint | essentia |
| `get_beat_tracking(file_path)` | BPM, beat positions, downbeat positions | madmom |
| `get_envelope(file_path)` | Smoothed amplitude envelope, crest factor, dynamic range | scipy |

### Usage Example

```python
# Loudness and dynamic range of a bounce
get_loudness("/path/to/track.wav")

# Onset/transient map — useful for groove analysis
get_onsets("/path/to/drums.wav")

# Spectral brightness and key
get_spectral_descriptors("/path/to/pad.wav")

# BPM and beat grid
get_beat_tracking("/path/to/loop.wav")

# Smoothed dynamics and crest factor
get_envelope("/path/to/bass.wav")

# Compare spectral balance across multiple files
analyze_mix_balance(
    file_paths=["/path/to/kick.wav", "/path/to/bass.wav", "/path/to/pad.wav"],
    reference_file_path="/path/to/master_bounce.wav",
)
```

---

## Audio Analysis Stack

AMCPX includes a five-library file-based analysis stack for deep offline and near-real-time audio analysis.

### Libraries

| Library | Best for | Mode |
|---|---|---|
| **scipy** | Smoothing, filters, envelopes, peak logic, utility DSP | Core always-on |
| **aubio** | Onset detection, pitch, tempo, transient finding, drum hit detection | Core always-on |
| **essentia** | Spectral features, tonal descriptors, brightness/density hints | Analysis core |
| **pyloudnorm** | LUFS loudness, true peak, gain staging, before/after checks, reference normalization | Loudness/reference |
| **madmom** | Beat tracking, downbeat detection, groove-aware rhythm analysis | Rhythm specialist |

### Real-time vs Offline split

**Real-time / near-real-time:** aubio, scipy, selected essentia features

**Offline / batch / decision support:** pyloudnorm, madmom, heavier essentia features

### Recommended usage by task

| Task | Libraries |
|---|---|
| Telemetry / mix decisions | essentia + scipy + pyloudnorm |
| Chopping / transients | aubio + scipy |
| Rhythm / groove analysis | madmom + aubio |
| Reference compare | pyloudnorm + essentia |

### Tools

| Tool | Library | Purpose |
|---|---|---|
| `get_loudness(file_path)` | pyloudnorm | LUFS, true peak, loudness baseline |
| `get_onsets(file_path)` | aubio | Transient/onset detection |
| `get_spectral_descriptors(file_path)` | essentia | Brightness, key, timbral fingerprint |
| `get_beat_tracking(file_path)` | madmom | BPM, beats, downbeats |
| `get_envelope(file_path)` | scipy | Smoothed dynamics, crest factor |

### Architecture

The spectrum plugin and analysis stack are complementary:

| Layer | Role |
|---|---|
| **MCPSpectrumTelemetry plugin** | Sensors — continuous low-latency per-track band energy from inside Live |
| **Analysis stack (aubio, essentia, etc.)** | Brain — deeper decisions, chopping, loudness, reference comparison |

Plugin = sensors. Python stack = brain.

The plugin provides continuous low-latency data from inside Live at audio rate. Use the plugin for live telemetry and the analysis stack for decisions.

---

## Performance Macros

Performance macros let you trigger multi-parameter musical gestures with a single command.

### Design principles

- **Existing devices first** — `perform_macro` never adds devices. It only targets devices already on the track.
- **Fail gracefully** — if a device is missing, it reports what was skipped and why.
- **Setup macros are separate** — `setup_fx_chain` is the only tool that adds devices, and only for one-time chain creation.

### Available macros

| Macro | Effect | Devices targeted |
|---|---|---|
| `build` | Filter opens + drive rises + reverb comes in + width expands | Auto Filter, Saturator, Reverb, Utility |
| `break` | Filter closes + delay feedback spikes + width narrows | Auto Filter, Simple Delay, Utility |
| `throw` | Reverb wet swell + filter opens momentarily | Reverb, Auto Filter |
| `drop` | Hard low-pass + echo out | Auto Filter, Simple Delay |
| `heat` | Drive + resonance + compression tightens | Saturator, Auto Filter, Compressor |
| `space` | Reverb + delay open + width expands | Reverb, Simple Delay, Utility |
| `tension` | Filter closes + resonance rises + drive up | Auto Filter, Saturator |
| `release` | Reverb burst + filter opens + drive fades | Reverb, Auto Filter, Saturator, Utility |
| `filter_drive` | Filter sweep + drive rise together | Auto Filter, Saturator |

### Usage

```python
# Check what's available on a track first
check_macro_readiness(track_index=1, macro_name="build")

# Trigger a macro
perform_macro(track_index=1, macro_name="build", start_bar=31, start_beat=1, length_beats=4.0)

# With intensity scaling (0.0–1.0)
perform_macro(track_index=0, macro_name="throw", start_bar=50, start_beat=3, length_beats=1.0, intensity=0.7)

# Set a static intensity (no automation, just set values)
set_macro_intensity(track_index=1, macro_name="build", intensity=0.8)

# One-time setup: add the device chain a macro needs
setup_fx_chain(track_index=3, chain_type="build_chain")
```

### Workflow

1. Call `check_macro_readiness(track, macro)` — see what's ready and what's missing
2. If devices are missing, call `setup_fx_chain(track, chain_type)` once
3. Call `perform_macro(track, macro, bar, beat, length)` to trigger
4. Undo with a single Cmd+Z — all changes are grouped into one undo step

---

## Notes

- The Remote Script runs on Ableton's internal Python interpreter (CPython 3.6+ in Live 11/12).
- All state-mutating operations are dispatched to Live's main thread via `schedule_message` to avoid threading issues.
- A new TCP connection is opened for each MCP tool call; no persistent connection is required.
- The server listens only on `localhost` — it is not exposed to the network.

