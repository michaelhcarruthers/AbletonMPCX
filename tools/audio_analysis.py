"""Audio analysis tools — file-based audio measurement and descriptors."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _analyse_audio_file(file_path: str, duration_limit: float = 300.0) -> dict:
    """Run audio analysis and return the result dict. Used by both analyse_audio and designate_reference_audio."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        raise ImportError(
            "librosa and numpy are required for audio analysis. "
            "Install with: pip install librosa soundfile"
        )

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    y, sr = librosa.load(path, sr=None, mono=True, duration=duration_limit)
    duration = len(y) / sr

    stereo_width = None
    try:
        import soundfile as sf
        y_stereo, _ = sf.read(path, always_2d=True)
        if y_stereo.shape[1] >= 2:
            max_samples = int(duration_limit * sr)
            y_stereo = y_stereo[:max_samples]
            L = y_stereo[:, 0].astype(np.float32)
            R = y_stereo[:, 1].astype(np.float32)
            mid = (L + R) / 2.0
            side = (L - R) / 2.0
            mid_rms = float(np.sqrt(np.mean(mid ** 2)) + 1e-9)
            side_rms = float(np.sqrt(np.mean(side ** 2)) + 1e-9)
            stereo_width = round(side_rms / mid_rms, 4)
    except Exception as e:
        logger.debug("Could not compute stereo width for '%s': %s", file_path, e)
    freqs = librosa.fft_frequencies(sr=sr)

    def band_energy(f_low, f_high):
        mask = (freqs >= f_low) & (freqs < f_high)
        return float(np.mean(S[mask, :] ** 2)) if mask.any() else 0.0

    total_energy = float(np.mean(S ** 2)) + 1e-9
    bands = {
        "low":       band_energy(20, 100) / total_energy,
        "low_mid":   band_energy(100, 500) / total_energy,
        "mid":       band_energy(500, 2000) / total_energy,
        "high_mid":  band_energy(2000, 8000) / total_energy,
        "high":      band_energy(8000, sr / 2) / total_energy,
    }
    bands = {k: round(v, 5) for k, v in bands.items()}

    rms = float(np.sqrt(np.mean(y ** 2)))
    loudness_dbfs = round(20 * np.log10(rms + 1e-9), 2)
    peak = float(np.max(np.abs(y)))
    peak_dbfs = round(20 * np.log10(peak + 1e-9), 2)
    crest_factor_db = round(peak_dbfs - loudness_dbfs, 2)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    sc_mean = round(float(np.mean(centroid)), 1)
    sc_std = round(float(np.std(centroid)), 1)

    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
    sr_mean = round(float(np.mean(rolloff)), 1)

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='time')
    transient_density = round(len(onset_frames) / duration, 3) if duration > 0 else 0.0

    hop = int(sr * 0.5)
    rms_frames = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    rms_db_frames = 20 * np.log10(rms_frames + 1e-9)
    dynamic_range = round(float(np.std(rms_db_frames)), 3)

    return {
        "file_path": path,
        "duration_seconds": round(duration, 2),
        "sample_rate": int(sr),
        "tonal_balance": bands,
        "loudness_dbfs": loudness_dbfs,
        "peak_dbfs": peak_dbfs,
        "crest_factor_db": crest_factor_db,
        "spectral_centroid_mean": sc_mean,
        "spectral_centroid_std": sc_std,
        "spectral_rolloff_mean": sr_mean,
        "transient_density_per_sec": transient_density,
        "dynamic_range": dynamic_range,
        "stereo_width": stereo_width,
    }


def analyse_audio(
    file_path: str,
    duration_limit: float = 300.0,
) -> dict:
    """Analyse an audio file and return tonal, loudness, transient, and spectral metrics."""
    return _analyse_audio_file(file_path, duration_limit=duration_limit)
