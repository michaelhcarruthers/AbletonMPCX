# Akai LPD8 Remote Script for Ableton Live 12
#
# Replicates the "Instant Mappings" behavior removed in Live 12:
#   - Encoders (CC 70–77) → parameters 1–8 of the currently selected device
#   - Pads (Notes 36–43)  → received by Live but not mapped (no drum rack binding)
#   - Automatically follows whichever device the user selects in Live
#
# Installation:
#   Copy the LPD8 folder to:
#     Mac: ~/Library/Preferences/Ableton/Live x.x.x/User Remote Scripts/LPD8/
#     Win: \Users\[username]\AppData\Roaming\Ableton\Live x.x.x\Preferences\User Remote Scripts\LPD8\
#   Then in Live: Preferences → Link/Tempo/MIDI → Control Surface → select LPD8
#                 Input: LPD8,  Output: LPD8

from __future__ import absolute_import

import Live
from _Framework.ControlSurface import ControlSurface
from _Framework.InputControlElement import MIDI_CC_TYPE
from _Framework.EncoderElement import EncoderElement
from _Framework.DeviceComponent import DeviceComponent

CHANNEL = 0           # MIDI channel 1 (zero-indexed)
ENCODER_CC_START = 70  # CC 70–77  →  encoders 1–8


def create_instance(c_instance):
    """Entry point called by Live when the script is loaded."""
    return LPD8(c_instance)


class LPD8(ControlSurface):
    """Remote Script that maps the Akai LPD8 to the currently selected device."""

    def __init__(self, c_instance):
        super(LPD8, self).__init__(c_instance)
        with self.component_guard():
            self._setup_encoders()
            self._setup_device()

    def _setup_encoders(self):
        """Create one EncoderElement per physical encoder (CC 70–77)."""
        self._encoders = []
        for i in range(8):
            enc = EncoderElement(
                MIDI_CC_TYPE,
                CHANNEL,
                ENCODER_CC_START + i,
                Live.MidiMap.MapMode.absolute,
            )
            enc.name = "Encoder_{}".format(i + 1)
            self._encoders.append(enc)

    def _setup_device(self):
        """Wire encoders to a DeviceComponent and register it with Live."""
        self._device = DeviceComponent()
        self._device.name = "Device_Component"
        self._device.set_parameter_controls(tuple(self._encoders))
        self.set_device_component(self._device)
