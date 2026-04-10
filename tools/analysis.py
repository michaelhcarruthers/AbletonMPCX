"""Audio analysis tools — loudness, onsets, spectral descriptors, beat tracking, and envelope."""
from __future__ import annotations

import os

from helpers import mcp


# ---------------------------------------------------------------------------
# get_loudness — pyloudnorm (ITU-R BS.1770-4)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_loudness(file_path: str) -> dict:
    """Measure perceptual loudness of an audio file using ITU-R BS.1770-4."""
    try:
        import soundfile as sf
        import pyloudnorm as pyln
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "pyloudnorm and soundfile are required for loudness analysis. "
            "Install with: pip install pyloudnorm soundfile"
        ) from exc

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    data, rate = sf.read(path)

    meter = pyln.Meter(rate)
    integrated = meter.integrated_loudness(data)

    # Short-term loudness over the last 3 seconds
    samples_3s = int(rate * 3)
    short_data = data[-samples_3s:] if len(data) > samples_3s else data
    short_term = meter.integrated_loudness(short_data)

    # True peak via 4x oversampling as required by ITU-R BS.1770-4
    from scipy.signal import resample as _resample
    oversampled = _resample(data, len(data) * 4, axis=0)
    true_peak = float(20 * np.log10(np.max(np.abs(oversampled)) + 1e-9))

    return {
        "integrated_lufs": round(float(integrated), 2),
        "short_term_lufs": round(float(short_term), 2),
        "true_peak_dbfs": round(true_peak, 2),
        "file_path": file_path,
    }


# ---------------------------------------------------------------------------
# get_onsets — aubio
# ---------------------------------------------------------------------------

@mcp.tool()
def get_onsets(file_path: str, method: str = "complex", threshold: float = 0.3) -> dict:
    """Detect note/transient onsets in an audio file using aubio."""
    try:
        import aubio
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "aubio is required for onset detection. "
            "Install with: pip install aubio"
        ) from exc

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    win_s = 512
    hop_s = 256
    src = aubio.source(path, hop_size=hop_s)
    samplerate = src.samplerate
    onset_detector = aubio.onset(method, win_s, hop_s, samplerate)
    onset_detector.set_threshold(threshold)

    onsets = []
    while True:
        samples, read = src()
        if onset_detector(samples):
            onsets.append(float(onset_detector.get_last_s()))
        if read < hop_s:
            break

    intervals = np.diff(onsets) if len(onsets) > 1 else []
    avg_interval = float(np.mean(intervals)) if len(intervals) > 0 else 0.0
    estimated_bpm = round(60.0 / avg_interval, 1) if avg_interval > 0 else 0.0

    return {
        "onsets_seconds": [round(o, 4) for o in onsets],
        "onset_count": len(onsets),
        "average_interval_seconds": round(avg_interval, 4),
        "estimated_bpm": estimated_bpm,
        "method": method,
        "file_path": file_path,
    }


# ---------------------------------------------------------------------------
# get_spectral_descriptors — essentia
# ---------------------------------------------------------------------------

@mcp.tool()
def get_spectral_descriptors(file_path: str) -> dict:
    """Extract perceptual spectral descriptors from an audio file using Essentia."""
    try:
        import essentia.standard as es
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "essentia is required for spectral descriptor analysis. "
            "Install with: pip install essentia"
        ) from exc

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    loader = es.MonoLoader(filename=path)
    audio = loader()

    w = es.Windowing(type='hann')
    spec = es.Spectrum()
    centroid = es.SpectralCentroidTime()
    rolloff = es.RollOff()
    flatness = es.FlatnessDB()
    mfcc = es.MFCC()

    centroids, rolloffs, flatnesses, mfccs = [], [], [], []

    frame_size = 2048
    hop_size = 1024
    for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size):
        windowed = w(frame)
        spectrum = spec(windowed)
        centroids.append(centroid(frame))
        rolloffs.append(rolloff(spectrum))
        flatnesses.append(flatness(spectrum))
        _, mfcc_coeffs = mfcc(spectrum)
        mfccs.append(mfcc_coeffs)

    key_detector = es.KeyExtractor()
    key, scale, strength = key_detector(audio)

    mfcc_mean = np.mean(mfccs, axis=0).tolist() if mfccs else []

    return {
        "spectral_centroid": round(float(np.mean(centroids)), 2),
        "spectral_spread": round(float(np.std(centroids)), 2),
        "spectral_flatness": round(float(np.mean(flatnesses)), 4),
        "spectral_rolloff": round(float(np.mean(rolloffs)), 2),
        "mfcc_mean": [round(float(v), 4) for v in mfcc_mean],
        "key": "{} {}".format(key, scale),
        "key_strength": round(float(strength), 4),
        "file_path": file_path,
    }


# ---------------------------------------------------------------------------
# get_beat_tracking — madmom
# ---------------------------------------------------------------------------

@mcp.tool()
def get_beat_tracking(file_path: str) -> dict:
    """Detect beats and downbeats in an audio file using madmom."""
    try:
        import madmom
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "madmom is required for beat tracking. "
            "Install with: pip install madmom"
        ) from exc

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    proc = madmom.features.beats.RNNBeatProcessor()
    act = proc(path)
    beat_proc = madmom.features.beats.BeatTrackingProcessor(fps=100)
    beats = beat_proc(act)

    downbeats = []
    ts_guess = "unknown"
    try:
        dbeat_proc = madmom.features.downbeats.RNNDownBeatProcessor()
        dbeat_act = dbeat_proc(path)
        db_proc = madmom.features.downbeats.DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)
        downbeat_data = db_proc(dbeat_act)
        downbeats = [float(b[0]) for b in downbeat_data if int(b[1]) == 1]
        if len(beats) > 0 and len(downbeats) > 0:
            avg_beats_per_bar = len(beats) / len(downbeats)
            ts_guess = (
                "4/4" if abs(avg_beats_per_bar - 4) < 1
                else "3/4" if abs(avg_beats_per_bar - 3) < 1
                else "unknown"
            )
    except Exception:
        pass

    intervals = np.diff(beats)
    bpm = round(float(60.0 / np.mean(intervals)), 2) if len(intervals) > 0 else 0.0

    return {
        "beats_seconds": [round(float(b), 4) for b in beats],
        "downbeats_seconds": [round(float(b), 4) for b in downbeats],
        "bpm": bpm,
        "beat_count": len(beats),
        "time_signature_guess": ts_guess,
        "file_path": file_path,
    }


# ---------------------------------------------------------------------------
# get_envelope — scipy.signal
# ---------------------------------------------------------------------------

@mcp.tool()
def get_envelope(file_path: str, smoothing_ms: float = 10.0, num_points: int = 200) -> dict:
    """Extract a smoothed amplitude envelope from an audio file using scipy."""
    try:
        import soundfile as sf
        import numpy as np
        from scipy.signal import butter, filtfilt
    except ImportError as exc:
        raise ImportError(
            "soundfile, numpy, and scipy are required for envelope extraction. "
            "Install with: pip install soundfile numpy scipy"
        ) from exc

    path = os.path.expanduser(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError("Audio file not found: {}".format(path))

    data, sr = sf.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    y = data.astype(float)

    rectified = np.abs(y)
    smoothing_samples = max(int(sr * smoothing_ms / 1000), 3)

    # Low-pass Butterworth filter for a smooth envelope.
    # smoothing_samples = sr * smoothing_ms / 1000, so the cutoff in Hz is sr/smoothing_samples.
    # Normalized to Nyquist (0–1 where 1 = sr/2): Wn = 2 * (sr/smoothing_samples) / sr = 2/smoothing_samples.
    wn = min(0.99, 2.0 / smoothing_samples)
    b, a = butter(4, wn, btype='low')
    envelope = filtfilt(b, a, rectified)
    envelope = np.clip(envelope, 0, None)

    peak_val = float(np.max(envelope))
    envelope_norm = envelope / peak_val if peak_val > 0 else envelope

    # Downsample to num_points
    indices = np.linspace(0, len(envelope_norm) - 1, num_points, dtype=int)
    envelope_out = envelope_norm[indices].tolist()
    times_out = (indices / sr).tolist()

    rms = float(np.sqrt(np.mean(y ** 2)))
    peak = float(np.max(np.abs(y)))
    crest_db = float(20 * np.log10(peak / (rms + 1e-9)))

    return {
        "envelope": [round(float(v), 4) for v in envelope_out],
        "times_seconds": [round(float(t), 4) for t in times_out],
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "crest_factor_db": round(crest_db, 2),
        "duration_seconds": round(len(y) / sr, 3),
        "file_path": file_path,
    }
