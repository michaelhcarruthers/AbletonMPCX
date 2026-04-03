# Existing content (truncated for brevity)

# ------------------------------------------------------------------
# Device
# ------------------------------------------------------------------

    def _cmd_get_devices(self, params):
        track = self._get_track(int(params["track_index"]))
        result = []
        for i, device in enumerate(track.devices):
            result.append({
                "index": i,
                "name": device.name,
                "class_name": device.class_name,
                "type": int(device.type),
                "is_active": device.is_active,
            })
        return result

# ------------------------------------------------------------------
# MixerDevice
# ------------------------------------------------------------------

    def _cmd_get_mixer_device(self, params):
        track = self._get_track(int(params["track_index"]))
        mixer = track.mixer_device
        sends = [{"index": i, "name": s.name, "value": s.value} for i, s in enumerate(mixer.sends)]
        return {
            "volume": mixer.volume.value,
            "pan": mixer.panning.value,
            "crossfade_assign": int(mixer.crossfade_assign),
            "sends": sends,
        }

# Existing content continues...
