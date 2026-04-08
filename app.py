def _group_selector_tool() -> list[dict]:
    from tool_groups import TOOL_GROUPS
    return [{
        "type": "function",
        "function": {
            "name": "select_tool_group",
            "description": (
                "Select the tool group that best matches the user's request. "
                "Call this first to get access to the right set of Ableton tools.\n"
                "Groups:\n"
                "- session: tempo, time signature, snapshots, recording, project memory\n"
                "- mixer: track volumes, panning, sends, mute/solo, routing\n"
                "- clips: fire/stop clips, notes, quantize, chop, slice\n"
                "- devices: device parameters, batch set, morph, staging\n"
                "- arrangement: arrangement clips, automation, loop/punch points\n"
                "- performance: macros, sidechain, resampling, scenes, observers\n"
                "- analysis: LUFS, peak, RMS, spectrum, real-time analyzer\n"
                "- diagnostics: logs, audit, health checks, validation\n"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": "string",
                        "enum": list(TOOL_GROUPS.keys()),
                        "description": "The tool group to load."
                    }
                },
                "required": ["group"],
            },
        },
    }]