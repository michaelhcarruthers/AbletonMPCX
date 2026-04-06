# This module is deprecated and no longer provides any active tools.
#
# The MCPSpectrumTelemetry AU plugin-based spectrum analyser has been removed.
# Audio analysis is now handled by the file-based analysis stack in tools/analysis.py:
#   - get_loudness()            — LUFS, true peak via pyloudnorm
#   - get_onsets()              — transient/onset detection via aubio
#   - get_spectral_descriptors() — brightness, key, timbral fingerprint via essentia
#   - get_beat_tracking()       — BPM, beats, downbeats via madmom
#   - get_envelope()            — smoothed dynamics, crest factor via scipy
