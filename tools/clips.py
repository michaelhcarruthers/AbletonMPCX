"""Fire the clip slot at (track_index, slot_index).

    WARNING: Firing a clip that is already playing will STOP it (Live's default toggle
    behaviour). Always call get_clip_playing_state(track_index, slot_index) first and
    check is_playing / is_triggered before firing if you want to avoid accidentally
    stopping a running clip.

    Args:
        track_index: Track index.
        slot_index: Clip slot index.
        record_length: Optional recording length in beats (for empty slots).
        launch_quantization: Optional launch quantization override (0-13).

    Returns:
        Empty dict on success.
    """