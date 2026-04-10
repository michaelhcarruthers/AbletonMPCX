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
        "write_arrangement_volume_automation",
        "mix_section",
        "analyze_section_levels",
        "duplicate_arrangement_clip",
        "duplicate_arrangement_clip_batch",
        "set_clip_envelope_points",
        "insert_clip_envelope_point",
        "clear_clip_envelope",
        "get_automation_data",
        "set_arrangement_automation",
    ],
    "session": [
        "get_session", "set_session", "load_", "save_", "snapshot",
        "recall_snapshot", "diff_snapshot", "list_snapshot",
        "delete_snapshot", "capture_snapshot", "restore_snapshot",
        "start_recording", "stop_recording", "arm_", "disarm_",
        "suggest_", "get_project", "set_project", "get_memory",
        "get_session_health", "set_tempo", "set_time_signature",
        "get_tempo", "get_time_signature",
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
        "mix_section", "analyze_section_levels",
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
        "write_arrangement_volume_automation",
        "mix_section", "analyze_section_levels",
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

TOOL_GROUP_MODULES: dict[str, list[str]] = {
    "base": [
        "tools.arrangement_bridge",   # write_dynamic_automation, write_arrangement_volume_automation
    ],
    "session": [
        "tools.session",
        "tools.session_snapshots",
        "tools.session_suggestions",
        "tools.session_recording",
    ],
    "mixer": [
        "tools.tracks",
    ],
    "clips": [
        "tools.clips",                # already in base, safe to repeat (importlib won't re-execute)
    ],
    "devices": [
        "tools.devices",
        "tools.staging",
        "tools.morph",
        "tools.reference",
    ],
    "arrangement": [
        "tools.arrangement_bridge",   # already in base, safe to repeat
    ],
    "performance": [
        "tools.performance",
    ],
    "diagnostics": [
        "tools.diagnostics",
        "tools.audit",
        "tools.realtime_analyzer",
        "tools.spectrum",
        "tools.theory",
        "tools.analysis",
        "tools.dispatchers.analysis_tool",
    ],
    "templates": [
        "tools.mix_templates",
        "tools.theory",
    ],
    "observer": [
        "tools.observer_bridge",
    ],
    "dispatcher": [
        # Implementation modules must be loaded first so dispatchers can import them.
        "tools.session",
        "tools.session_snapshots",
        "tools.session_suggestions",
        "tools.session_recording",
        "tools.tracks",
        "tools.clips",
        "tools.devices",
        "tools.staging",
        "tools.morph",
        "tools.reference",
        "tools.audit",
        "tools.performance",
        "tools.diagnostics",
        "tools.arrangement_bridge",
        "tools.observer_bridge",
        "tools.realtime_analyzer",
        "tools.mix_templates",
        "tools.theory",
        "tools.spectrum",
        "tools.analysis",
        # Dispatcher modules — registered after all implementation modules.
        "tools.dispatchers.arrangement_tool",
        "tools.dispatchers.device_tool",
        "tools.dispatchers.analysis_tool",
        "tools.dispatchers.render_tool",
        "tools.dispatchers.project_tool",
    ],
}
