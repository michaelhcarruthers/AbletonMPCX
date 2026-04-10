"""Arrangement dispatcher — routes arrangement and song-structure workflows."""
from __future__ import annotations

from helpers import mcp

from tools.session import (
    auto_orient,
    build_scene_scaffold,
    list_scaffold_templates,
    place_clip_in_arrangement,
    duplicate_clip_to_scenes,
    arrange_from_scene_scaffold,
    insert_tempo_section,
    create_song_from_brief,
    auto_name_all_tracks,
    auto_name_clip,
    auto_name_scene,
)

# ---------------------------------------------------------------------------
# Action implementations (thin wrappers)
# ---------------------------------------------------------------------------

def _action_overview(**kwargs):
    return auto_orient()


def _action_scaffold(**kwargs):
    return build_scene_scaffold(**kwargs)


def _action_scaffold_from_template(**kwargs):
    return build_scene_scaffold(**kwargs)


def _action_list_templates(**kwargs):
    return list_scaffold_templates()


def _action_place(**kwargs):
    return place_clip_in_arrangement(**kwargs)


def _action_duplicate(**kwargs):
    return duplicate_clip_to_scenes(**kwargs)


def _action_build_from_scenes(**kwargs):
    return arrange_from_scene_scaffold(**kwargs)


def _action_tempo_section(**kwargs):
    return insert_tempo_section(**kwargs)


def _action_create_song(**kwargs):
    return create_song_from_brief(**kwargs)


def _action_auto_name_tracks(**kwargs):
    return auto_name_all_tracks(**kwargs)


def _action_auto_name_clip(**kwargs):
    return auto_name_clip(**kwargs)


def _action_auto_name_scene(**kwargs):
    return auto_name_scene(**kwargs)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTIONS = {
    "overview": _action_overview,
    "scaffold": _action_scaffold,
    "scaffold_from_template": _action_scaffold_from_template,
    "list_templates": _action_list_templates,
    "place": _action_place,
    "duplicate": _action_duplicate,
    "build_from_scenes": _action_build_from_scenes,
    "tempo_section": _action_tempo_section,
    "create_song": _action_create_song,
    "auto_name_tracks": _action_auto_name_tracks,
    "auto_name_clip": _action_auto_name_clip,
    "auto_name_scene": _action_auto_name_scene,
}


@mcp.tool()
def arrangement_tool(action: str, **kwargs) -> dict:
    """Arrangement and song-structure workflows. Actions: overview, scaffold, scaffold_from_template, list_templates, place, duplicate, build_from_scenes, tempo_section, create_song, auto_name_tracks, auto_name_clip, auto_name_scene."""
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
