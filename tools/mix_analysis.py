"""Mix analysis tools — spectral balance analysis across audio files."""
from __future__ import annotations


def analyze_mix_balance(
    file_paths: list[str],
    reference_file_path: str | None = None,
    crowded_threshold_hz: float = 1000.0,
    missing_threshold_hz: float = -1000.0,
) -> dict:
    """Analyse spectral balance across a set of audio files using file-based analysis."""
    from tools.analysis import get_spectral_descriptors

    if not file_paths:
        return {"error": "file_paths must not be empty."}

    # Analyse all files
    results = []
    errors = []
    for fp in file_paths:
        try:
            desc = get_spectral_descriptors(fp)
            results.append(desc)
        except Exception as exc:
            errors.append({"file_path": fp, "error": str(exc)})

    if not results:
        return {"error": "Could not analyse any files.", "details": errors}

    # Analyse reference file (if provided and not already in results)
    ref_centroid: float
    ref_desc: dict | None = None
    if reference_file_path:
        try:
            ref_desc = get_spectral_descriptors(reference_file_path)
            ref_centroid = ref_desc["spectral_centroid"]
        except Exception as exc:
            return {"error": "Could not analyse reference file: {}".format(exc)}
    else:
        ref_centroid = sum(r["spectral_centroid"] for r in results) / len(results)

    # Classify each file
    bright: list[str] = []
    dark: list[str] = []
    balanced: list[str] = []
    recommendations: list[str] = []

    for desc in results:
        fp = desc["file_path"]
        delta = desc["spectral_centroid"] - ref_centroid
        desc["centroid_delta_hz"] = round(delta, 1)

        if delta >= crowded_threshold_hz:
            bright.append(fp)
            recommendations.append(
                "{} is spectrally bright ({:+.0f} Hz above reference centroid) — "
                "consider high-shelf cut or low-passing competing elements.".format(
                    fp, delta
                )
            )
        elif delta <= missing_threshold_hz:
            dark.append(fp)
            recommendations.append(
                "{} is spectrally dark ({:+.0f} Hz below reference centroid) — "
                "consider high-shelf boost or presence boost.".format(fp, delta)
            )
        else:
            balanced.append(fp)

    if bright and dark:
        summary = "{} file(s) bright, {} file(s) dark relative to reference.".format(
            len(bright), len(dark)
        )
    elif bright:
        summary = "{} file(s) spectrally bright relative to reference.".format(len(bright))
    elif dark:
        summary = "{} file(s) spectrally dark relative to reference.".format(len(dark))
    else:
        summary = "All files are spectrally balanced relative to reference."

    output: dict = {
        "results":              results,
        "reference_centroid_hz": round(ref_centroid, 2),
        "bright":               bright,
        "dark":                 dark,
        "balanced":             balanced,
        "recommendations":      recommendations,
        "summary":              summary,
        "file_count":           len(results),
    }
    if ref_desc:
        output["reference_file"] = reference_file_path
        output["reference_descriptors"] = ref_desc
    if errors:
        output["errors"] = errors
    return output
