# AbletonMPCX Plugins

This directory contains documentation for the Max for Live (`.amxd`) devices
that extend the AbletonMPCX MCP server's spectrum analysis and dynamics
telemetry capabilities.

The actual Max patcher implementation is done separately.  Each `.md` file
below describes the parameters a device must expose via the Live API so that
the corresponding MCP tools can read them.

| File | Device | Purpose |
|------|--------|---------|
| `AbletonMPCX_SpectrumAnalyser_PeakHold.md` | Peak hold mod for existing spectrum plugin | P1 |
| `AbletonMPCX_DynamicsTelemetry.md` | Dynamics telemetry Audio Effect | P2 |
| `AbletonMPCX_StereoAnalyser.md` | Stereo field analyser Audio Effect | P3 |

## MCP tools

| Tool | Device | Notes |
|------|--------|-------|
| `get_spectrum_peak` | Spectrum (peak hold mod) | Reads peak_frequency / peak_magnitude |
| `reset_spectrum_peak` | Spectrum (peak hold mod) | Triggers peak_reset bang |
| `get_dynamics_telemetry` | AbletonMPCX_DynamicsTelemetry | Per-device read |
| `get_dynamics_overview` | AbletonMPCX_DynamicsTelemetry | Session-wide scan |
| `get_stereo_field` | AbletonMPCX_StereoAnalyser | Per-device read |
| `get_stereo_overview` | AbletonMPCX_StereoAnalyser | Session-wide scan |
