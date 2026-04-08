def fire_clip_slot(clip_slot):
    """
    Fires the given clip slot.

    WARNING: Ensure to stop a playing clip before firing the slot.
    Call get_clip_playing_state first to check if a clip is currently playing.
    """
    clip_slot.fire()


def get_clip_playing_state(clip):
    """
    Returns whether the clip is currently playing.
    """
    return clip.is_playing

# The rest of the content of tools/clips.py remains identical to commit af14eb4a694af7f7a9394acf05b8829d81b8a19b