from __future__ import absolute_import
import Live
from _Framework.ControlSurface import ControlSurface
from _Framework.InputControlElement import MIDI_CC_TYPE
from _Framework.EncoderElement import EncoderElement
from _Framework.DeviceComponent import DeviceComponent

CHANNEL = 0
ENCODER_CC_START = 70   # CC 70-77


class LPD8(ControlSurface):

    def __init__(self, c_instance):
        super(LPD8, self).__init__(c_instance)
        with self.component_guard():
            self._setup_encoders()
            self._setup_device()

    def _setup_encoders(self):
        self._encoders = []
        for i in range(8):
            enc = EncoderElement(
                MIDI_CC_TYPE,
                CHANNEL,
                ENCODER_CC_START + i,
                Live.MidiMap.MapMode.absolute,
            )
            enc.name = 'Encoder_{0}'.format(i + 1)
            self._encoders.append(enc)

    def _setup_device(self):
        self._device = DeviceComponent()
        self._device.name = 'Device_Component'
        self._device.set_parameter_controls(tuple(self._encoders))
        self.set_device_component(self._device)
