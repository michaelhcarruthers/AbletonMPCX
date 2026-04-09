"""
Tool group definitions for AMCPX chat UI.
Maps group names to tool name prefixes so the chat UI can route requests
to the right subset of tools without exceeding OpenAI's 128-tool limit.
"""

TOOL_GROUPS: dict[str, list[str]] = {
    "base": [
        "get_song_info_minimal",
        "get_tracks",
        "list_arrangement_clips",
        "get_arrangement_overview",
        "write_dynamic_automation",
        "duplicate_arrangement_clip",
        "duplicate_arrangement_clip_batch",
    ],
    "session": [
        "get_session", "set_session", "load_", "save_", "snapshot",
        "recall_snapshot", "diff_snapshot", "list_snapshot",
        "delete_snapshot", "capture_snapshot", "restore_snapshot",
        "start_recording", "stop_recording", "arm_", "disarm_",
        "suggest_", "get_project", "set_project", "get_memory",
        "get_session_health", "set_tempo", "set_time_signature",
        "get_tempo", "get_time_signature",
        "get_song_info_minimal",
    ],
    "mixer": [
        "set_track_volume", "get_track_volume", "set_track_pan",
        "get_track_pan", "set_track_mute", "get_track_mute",
        "set_track_solo", "get_track_solo", "set_track_send",
        "get_track_send", "set_track_send_batch", "set_track_color",
        "get_track_color", "get_track_name", "set_track_name",
        "get_tracks", "get_track_info", "create_track", "delete_track",
        "duplicate_track", "clone_track", "group_tracks", "ungroup_tracks",
        "move_track", "fold_track", "set_crossfader", "get_crossfader",
        "set_master_volume", "get_master_volume", "set_cue_volume",
        "get_return_tracks",
    ],
    "clips": [
        "fire_clip", "stop_clip", "get_clip", "set_clip", "create_clip",
        "delete_clip", "duplicate_clip", "move_clip", "get_notes",
        "set_notes", "add_notes", "remove_notes", "get_notes_extended",
        "quantize_clip", "transpose_clip", "set_clip_color",
        "set_clip_color_batch", "set_clip_name", "get_clip_name",
        "get_playing_clip", "list_clips", "chop_", "slice_",
    ],
    "devices": [
        "get_device", "set_device", "get_devices", "add_device",
        "delete_device", "set_device_parameter", "get_device_parameter",
        "set_device_parameters_batch", "perform_device_parameter_moves",
        "set_device_parameter_cs", "enable_device", "disable_device",
        "morph_", "stage_", "unstage_", "commit_stage",
        "save_reference", "load_reference", "list_references",
        "get_reference", "delete_reference",
    ],
    "arrangement": [
        "get_arrangement", "set_arrangement", "create_arrangement_clip",
        "delete_arrangement_clip", "move_arrangement_clip",
        "get_arrangement_automation", "set_arrangement_automation",
        "clear_arrangement_automation", "dump_session_to_arrangement",
        "get_arrangement_length", "set_loop_", "get_loop_",
        "set_punch_", "get_punch_",
        "write_dynamic_automation",
    ],
    "performance": [
        "perform_macro", "perform_macro_live", "setup_sidechain",
        "teardown_sidechain", "setup_resampling", "teardown_resampling",
        "get_observer", "set_observer", "subscribe_", "unsubscribe_",
        "fire_scene", "stop_all_clips", "jump_to_", "set_follow_action",
    ],
    "diagnostics": [
        "get_log", "get_operation_log", "get_audit", "run_diagnostic",
        "check_", "validate_", "inspect_", "get_health",
        "export_audit", "clear_log",
        "get_latency_report",
    ],
    "templates": [
        "classify_tracks", "apply_mix_template", "preview_mix_template",
        "list_mix_templates", "set_track_role", "get_track_roles",
        "validate_track_roles", "clear_track_role",
    ],
}
