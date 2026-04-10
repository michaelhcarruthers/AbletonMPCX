"""Analysis dispatcher — routes analysis, feel, reference, and theory workflows."""
from __future__ import annotations

from helpers import mcp

from tools.audit import (
    analyze_clip_feel,
    humanize_dilla,
    humanize_notes,
    auto_humanize_if_robotic,
    batch_auto_humanize,
    fix_groove_from_reference,
    designate_reference_clip,
    compare_clip_feel,
    designate_reference_mix_state,
    compare_mix_state,
    designate_reference_audio,
    compare_audio,
    compare_audio_sections,
    list_reference_profiles,
    delete_reference_profile,
    analyse_audio,
    get_pending_suggestions,
)
from tools.session import analyse_mix_state
from tools.theory import check_key, check_key_batch
from tools.diagnostics import analyze_mix_balance
from tools.analysis import (
    get_loudness,
    get_onsets,
    get_spectral_descriptors,
    get_beat_tracking,
    get_envelope,
)
from tools.spectrum import get_spectrum_bands, get_spectrum_overview
from tools.realtime_analyzer import (
    m4l_analyzer_ping,
    m4l_get_levels,
    m4l_get_lufs,
    m4l_get_peak_level,
    m4l_get_crest_factor,
    m4l_reset_analyzer,
    m4l_measure_for_seconds,
)

# ---------------------------------------------------------------------------
# Action implementations (thin wrappers)
# ---------------------------------------------------------------------------

def _action_feel(**kwargs):
    return analyze_clip_feel(**kwargs)


def _action_humanize(**kwargs):
    style = kwargs.pop("style", "dilla")
    if style == "dilla":
        return humanize_dilla(**kwargs)
    return humanize_notes(**kwargs)


def _action_humanize_auto(**kwargs):
    return auto_humanize_if_robotic(**kwargs)


def _action_humanize_batch(**kwargs):
    return batch_auto_humanize(**kwargs)


def _action_humanize_from_ref(**kwargs):
    return fix_groove_from_reference(**kwargs)


def _action_reference_clip_save(**kwargs):
    return designate_reference_clip(**kwargs)


def _action_reference_clip_compare(**kwargs):
    return compare_clip_feel(**kwargs)


def _action_reference_mix_save(**kwargs):
    return designate_reference_mix_state(**kwargs)


def _action_reference_mix_compare(**kwargs):
    return compare_mix_state(**kwargs)


def _action_reference_audio_save(**kwargs):
    return designate_reference_audio(**kwargs)


def _action_reference_audio_compare(**kwargs):
    return compare_audio(**kwargs)


def _action_reference_audio_sections(**kwargs):
    return compare_audio_sections(**kwargs)


def _action_reference_list(**kwargs):
    return list_reference_profiles()


def _action_reference_delete(**kwargs):
    return delete_reference_profile(**kwargs)


def _action_audio_analyse(**kwargs):
    return analyse_audio(**kwargs)


def _action_mix_state(**kwargs):
    return analyse_mix_state()


def _action_suggestions(**kwargs):
    return get_pending_suggestions(**kwargs)


def _action_key_check(**kwargs):
    return check_key(**kwargs)


def _action_key_check_batch(**kwargs):
    return check_key_batch(**kwargs)


def _action_loudness(**kwargs):
    return get_loudness(**kwargs)


def _action_onsets(**kwargs):
    return get_onsets(**kwargs)


def _action_spectral(**kwargs):
    return get_spectral_descriptors(**kwargs)


def _action_beat_track(**kwargs):
    return get_beat_tracking(**kwargs)


def _action_envelope(**kwargs):
    return get_envelope(**kwargs)


def _action_spectrum_bands(**kwargs):
    return get_spectrum_bands(**kwargs)


def _action_spectrum_overview(**kwargs):
    return get_spectrum_overview()


def _action_m4l_ping(**kwargs):
    return m4l_analyzer_ping()


def _action_m4l_levels(**kwargs):
    return m4l_get_levels()


def _action_m4l_lufs(**kwargs):
    return m4l_get_lufs()


def _action_m4l_peak(**kwargs):
    return m4l_get_peak_level()


def _action_m4l_crest(**kwargs):
    return m4l_get_crest_factor()


def _action_m4l_reset(**kwargs):
    return m4l_reset_analyzer()


def _action_m4l_measure(**kwargs):
    return m4l_measure_for_seconds(**kwargs)


def _action_mix_balance(**kwargs):
    return analyze_mix_balance(**kwargs)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTIONS = {
    "feel": _action_feel,
    "humanize": _action_humanize,
    "humanize_auto": _action_humanize_auto,
    "humanize_batch": _action_humanize_batch,
    "humanize_from_ref": _action_humanize_from_ref,
    "reference_clip_save": _action_reference_clip_save,
    "reference_clip_compare": _action_reference_clip_compare,
    "reference_mix_save": _action_reference_mix_save,
    "reference_mix_compare": _action_reference_mix_compare,
    "reference_audio_save": _action_reference_audio_save,
    "reference_audio_compare": _action_reference_audio_compare,
    "reference_audio_sections": _action_reference_audio_sections,
    "reference_list": _action_reference_list,
    "reference_delete": _action_reference_delete,
    "audio_analyse": _action_audio_analyse,
    "mix_state": _action_mix_state,
    "suggestions": _action_suggestions,
    "key_check": _action_key_check,
    "key_check_batch": _action_key_check_batch,
    "loudness": _action_loudness,
    "onsets": _action_onsets,
    "spectral": _action_spectral,
    "beat_track": _action_beat_track,
    "envelope": _action_envelope,
    "spectrum_bands": _action_spectrum_bands,
    "spectrum_overview": _action_spectrum_overview,
    "m4l_ping": _action_m4l_ping,
    "m4l_levels": _action_m4l_levels,
    "m4l_lufs": _action_m4l_lufs,
    "m4l_peak": _action_m4l_peak,
    "m4l_crest": _action_m4l_crest,
    "m4l_reset": _action_m4l_reset,
    "m4l_measure": _action_m4l_measure,
    "mix_balance": _action_mix_balance,
}


@mcp.tool()
def analysis_tool(action: str, **kwargs) -> dict:
    """Analysis, feel, reference, and theory workflows. Actions: feel, humanize, humanize_auto, humanize_batch, humanize_from_ref, reference_clip_save, reference_clip_compare, reference_mix_save, reference_mix_compare, reference_audio_save, reference_audio_compare, reference_audio_sections, reference_list, reference_delete, audio_analyse, mix_state, suggestions, key_check, key_check_batch, loudness, onsets, spectral, beat_track, envelope, spectrum_bands, spectrum_overview, m4l_ping, m4l_levels, m4l_lufs, m4l_peak, m4l_crest, m4l_reset, m4l_measure, mix_balance."""
    if action not in _ACTIONS:
        return {
            "status": "error",
            "error": f"Unknown action '{action}'",
            "valid_actions": sorted(_ACTIONS.keys()),
        }
    try:
        return _ACTIONS[action](**kwargs)
    except TypeError as exc:
        return {"status": "error", "error": str(exc)}
