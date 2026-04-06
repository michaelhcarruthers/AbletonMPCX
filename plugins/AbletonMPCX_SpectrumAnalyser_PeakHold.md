# AbletonMPCX Spectrum Analyser — Peak Hold Mod

**Device type:** Max for Live Audio Effect (or MIDI Effect if used on MIDI tracks)  
**Base device:** Existing AbletonMPCX spectrum analyser  
**File:** `AbletonMPCX_SpectrumAnalyser_PeakHold.amxd`

## Overview

This is a modification of the existing AbletonMPCX spectrum analyser plugin that
adds a **peak hold** feature.  Instead of only reporting the instantaneous
frequency/magnitude, the device tracks the highest peak reached over a
configurable time window and exposes it via the Live API so Claude (via MCP tools
`get_spectrum_peak` and `reset_spectrum_peak`) can query it.

## Parameters exposed via the Live API

All parameter names are exact — the MCP tools match them case-insensitively.

| Parameter name | Type | Range | Default | Access | Notes |
|----------------|------|-------|---------|--------|-------|
| `peak_hold_enabled` | bool (0/1) | 0–1 | 1 | R/W | Enables or disables peak hold tracking |
| `peak_hold_time` | float | 0.1–60.0 | 3.0 | R/W | Hold window in seconds |
| `peak_frequency` | float | 20–20000 | — | Read-only | Hz of the current held peak |
| `peak_magnitude` | float | -120–0 | — | Read-only | dB of the current held peak |
| `peak_reset` | float (bang) | 0–1 | — | Write-only | Set to 1.0 to reset the held peak |

## Max patcher notes

- `peak_frequency` and `peak_magnitude` should be driven by a `[peak~]` or
  equivalent analysis object inside the patcher.
- `peak_reset` triggers an internal `[bang]` via a `[>= 1]` threshold gate; the
  parameter value should be auto-reset to 0 after the bang fires.
- `peak_hold_time` feeds a `[timer]` or `[delay]` that clears the held values
  after the window elapses (when `peak_hold_enabled` is 1).
- Live parameters map to `[live.dial]` or `[live.numbox]` objects with
  `parameter_enable 1`.

## MCP tools that use this device

- `get_spectrum_peak(track_index, device_index)` — reads the four read-only values
- `reset_spectrum_peak(track_index, device_index)` — triggers `peak_reset`
