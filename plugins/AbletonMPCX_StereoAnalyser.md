# AbletonMPCX Stereo Analyser

**Device type:** Max for Live Audio Effect  
**File:** `AbletonMPCX_StereoAnalyser.amxd`

## Overview

A Max for Live Audio Effect that measures stereo width and channel correlation
in real time.  The device passes audio through unmodified; all processing is
analysis-only.  Parameters are exposed via the Live API so the MCP tools
`get_stereo_field` and `get_stereo_overview` can read them.

## What it measures

| Metric | Description |
|--------|-------------|
| Correlation | Pearson cross-correlation of L and R channels (-1.0 to +1.0) |
| Stereo width | Normalised width estimate (0.0 = mono, 1.0 = full stereo) |
| Mid level | Level of the M (L+R) channel in dBFS |
| Side level | Level of the S (L–R) channel in dBFS |
| Phase issues | True when correlation drops below -0.3 (potential cancellation) |

## Parameters exposed via the Live API

| Parameter name | Type | Range | Default | Access | Notes |
|----------------|------|-------|---------|--------|-------|
| `correlation` | float | -1.0–1.0 | — | Read-only | L/R cross-correlation (+1 = mono) |
| `stereo_width` | float | 0.0–1.0 | — | Read-only | Normalised stereo width |
| `mid_level` | float | -120–0 | — | Read-only | Mid channel dBFS |
| `side_level` | float | -120–0 | — | Read-only | Side channel dBFS |
| `phase_issues` | float (bool 0/1) | 0–1 | 0 | Read-only | 1 when correlation < -0.3 |

## Max patcher notes

### Mid/Side matrix
```
M = (L + R) / 2
S = (L - R) / 2
```

### Correlation
Correlation is computed as the normalised cross-product of L and R over a short
window (e.g. 50 ms):
```
corr = sum(L * R) / sqrt(sum(L^2) * sum(R^2))
```
`[corr~]` or a custom `[pfft~]` patch can implement this.

### Stereo width
```
width = RMS(S) / (RMS(M) + RMS(S) + epsilon)
```

### Phase issues flag
A `[< -0.3]` comparator on the `correlation` parameter drives `phase_issues`.
Auto-resets when correlation rises back above -0.3.

### Live parameters
All parameters use `parameter_enable 1`.  `correlation` uses a float Live
parameter with range -1.0 to 1.0; `phase_issues` uses a float mapped to 0/1.

## Stereo correlation reference

| Correlation | Meaning |
|-------------|---------|
| +1.0 | Perfectly mono (identical L and R) |
| +0.5 to +1.0 | Good mono compatibility |
| 0.0 to +0.5 | Normal stereo |
| -0.3 to 0.0 | Wide but still compatible |
| < -0.3 | Phase cancellation risk — **phase_issues = 1** |
| -1.0 | Perfectly out of phase (complete cancellation in mono) |

## MCP tools that use this device

- `get_stereo_field(track_index, device_index)` — per-device read with interpretation
  and recommendations
- `get_stereo_overview()` — session-wide scan; finds all tracks with this device
  loaded and reports phase-problem tracks
