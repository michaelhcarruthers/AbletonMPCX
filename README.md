## Audio Analysis

AbletonMPCX includes a five-library file-based analysis stack for deep offline and near-real-time audio analysis. Pass an exported audio file (WAV, AIFF, or FLAC) to any of the tools below — no plugin required.

### Dependencies

```
pip install pyloudnorm aubio essentia madmom scipy soundfile
```

### Libraries

| Library | Best for | Mode |
|---|---|---|
| **scipy** | Smoothing, filters, envelopes, peak logic, utility DSP | Core always-on |
| **aubio** | Onset detection, pitch, tempo, transient finding, drum hit detection | Core always-on |
| **essentia** | Spectral features, tonal descriptors, brightness/density hints | Analysis core |
| **pyloudnorm** | LUFS loudness, true peak, gain staging, reference normalization | Loudness/reference |
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

### Architecture

The MCPSpectrumTelemetry plugin and this analysis stack are complementary, not competing.

| Layer | Role |
|---|---|
| **MCPSpectrumTelemetry plugin** | Sensors — continuous low-latency per-track band energy from inside Live |
| **Analysis stack (aubio, essentia, etc.)** | Brain — deeper decisions, chopping, loudness, reference comparison |

**Plugin = sensors. Python stack = brain.**

The plugin provides continuous low-latency data from inside Live at audio rate — something the Python libraries cannot do without exporting audio first. Use the plugin for live telemetry and the analysis stack for decisions.
