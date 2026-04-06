# AbletonMPCX Dynamics Telemetry

**Device type:** Max for Live Audio Effect  
**File:** `AbletonMPCX_DynamicsTelemetry.amxd`

## Overview

A Max for Live Audio Effect that measures and reports real-time dynamics
information from a track.  The device passes audio through unmodified; all
processing is analysis-only.  Parameters are exposed via the Live API so the
MCP tools `get_dynamics_telemetry` and `get_dynamics_overview` can read them.

## What it measures

| Metric | Description |
|--------|-------------|
| RMS level | dBFS, 100 ms sliding window |
| Peak level | dBFS, instantaneous sample-accurate peak |
| Crest factor | Peak – RMS (high value = punchy transients, low = compressed) |
| Dynamic range | Difference between loudest and quietest RMS value over the last 4 bars |
| Clipping | True if any sample exceeded 0 dBFS in the last 100 ms |

## Parameters exposed via the Live API

| Parameter name | Type | Range | Default | Access | Notes |
|----------------|------|-------|---------|--------|-------|
| `rms_level` | float | -120–0 | — | Read-only | RMS level in dBFS |
| `peak_level` | float | -120–0 | — | Read-only | Instantaneous peak in dBFS |
| `crest_factor` | float | 0–40 | — | Read-only | Peak – RMS in dB |
| `dynamic_range` | float | 0–60 | — | Read-only | Range over last 4 bars in dB |
| `is_clipping` | float (bool 0/1) | 0–1 | 0 | Read-only | 1 if clipping detected |
| `window_ms` | float | 10–1000 | 100 | R/W | Analysis window size in ms |

## Max patcher notes

- Use `[rms~]` or equivalent for RMS measurement feeding a `[dbtoa]` → `[atodb]`
  chain, then write to `peak_level` and `rms_level` live parameters.
- `crest_factor` is computed as `peak_level - rms_level` in the Max patcher.
- `dynamic_range` uses a 4-bar circular buffer of RMS snapshots; the range is
  `max - min` over the buffer.
- `is_clipping` is set by a `[> 1.0]` comparator on the raw signal; auto-resets
  after 100 ms via `[delay]`.
- All Live parameters use `parameter_enable 1` so they appear in the Live API.
- `window_ms` is read by the patcher to resize the RMS analysis window at runtime.

## MCP tools that use this device

- `get_dynamics_telemetry(track_index, device_index)` — per-device read with interpretation
- `get_dynamics_overview()` — session-wide scan; finds all tracks with this device loaded
