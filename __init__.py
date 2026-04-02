"""
AbletonMPCX Remote Script
Runs inside Ableton Live as a Control Surface.
Listens on localhost:9877 for JSON commands from server.py.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json
import socket
import threading

try:
    import Queue as queue
except ImportError:
    import queue

import Live  # noqa: F401 — provided by Ableton's Python environment

from _Framework.ControlSurface import ControlSurface


def create_instance(c_instance):
    return AbletonMPCX(c_instance)


class AbletonMPCX(ControlSurface):
    """MCP Remote Script — bridges server.py to the Ableton Live Object Model."""

    HOST = "localhost"
    PORT = 9877
    THREAD_TIMEOUT = 10.0  # seconds to wait for scheduled mutations

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, c_instance):
        super(AbletonMPCX, self).__init__(c_instance)
        self._server_socket = None
        self._server_thread = None
        self._running = False
        self._start_server()

    def disconnect(self):
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        super(AbletonMPCX, self).disconnect()

    # ------------------------------------------------------------------
    # Socket server
    # ------------------------------------------------------------------

    def _start_server(self):
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.HOST, self.PORT))
            self._server_socket.listen(5)
            self._running = True
            self._server_thread = threading.Thread(target=self._accept_loop, name="AbletonMPCX-Server")
            self._server_thread.daemon = True
            self._server_thread.start()
        except Exception as e:
            self.log_message("AbletonMPCX: Failed to start server: {}".format(e))

    def _accept_loop(self):
        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                try:
                    conn, _ = self._server_socket.accept()
                except socket.timeout:
                    continue
                t = threading.Thread(target=self._handle_connection, args=(conn,))
                t.daemon = True
                t.start()
            except Exception as e:
                if self._running:
                    self.log_message("AbletonMPCX: Accept error: {}".format(e))
                break

    def _handle_connection(self, conn):
        try:
            data = b""
            conn.settimeout(5.0)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                try:
                    request = json.loads(data.decode("utf-8"))
                    break
                except ValueError:
                    continue
            if not data:
                return
            response = self._dispatch(request)
            conn.sendall(json.dumps(response).encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall(json.dumps({"status": "error", "error": str(e)}).encode("utf-8"))
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, request):
        try:
            command = request.get("command", "")
            params = request.get("params", {})
            handler = getattr(self, "_cmd_{}".format(command), None)
            if handler is None:
                return {"status": "error", "error": "Unknown command: {}".format(command)}
            # Read-only commands run directly; mutating ones run on main thread via schedule_message
            result = handler(params)
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _run_on_main_thread(self, fn):
        """Schedule fn on Live's main thread and block until it returns."""
        result_queue = queue.Queue()

        def wrapper():
            try:
                result_queue.put(("ok", fn()))
            except Exception as exc:
                result_queue.put(("error", str(exc)))

        self.schedule_message(0, wrapper)
        kind, value = result_queue.get(timeout=self.THREAD_TIMEOUT)
        if kind == "error":
            raise RuntimeError(value)
        return value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def song(self):
        return self._ControlSurface__c_instance.song()

    def _get_track(self, track_index):
        tracks = list(self.song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError("track_index {} out of range (0-{})".format(track_index, len(tracks) - 1))
        return tracks[track_index]

    def _get_return_track(self, index):
        tracks = list(self.song.return_tracks)
        if index < 0 or index >= len(tracks):
            raise IndexError("return track index {} out of range (0-{})".format(index, len(tracks) - 1))
        return tracks[index]

    def _get_scene(self, scene_index):
        scenes = list(self.song.scenes)
        if scene_index < 0 or scene_index >= len(scenes):
            raise IndexError("scene_index {} out of range (0-{})".format(scene_index, len(scenes) - 1))
        return scenes[scene_index]

    def _get_clip_slot(self, track_index, slot_index):
        track = self._get_track(track_index)
        slots = list(track.clip_slots)
        if slot_index < 0 or slot_index >= len(slots):
            raise IndexError("slot_index {} out of range".format(slot_index))
        return slots[slot_index]

    def _get_clip(self, track_index, slot_index):
        slot = self._get_clip_slot(track_index, slot_index)
        if not slot.has_clip:
            raise RuntimeError("No clip at track={}, slot={}".format(track_index, slot_index))
        return slot.clip

    def _get_device(self, track_index, device_index):
        track = self._get_track(track_index)
        devices = list(track.devices)
        if device_index < 0 or device_index >= len(devices):
            raise IndexError("device_index {} out of range".format(device_index))
        return devices[device_index]

    @staticmethod
    def _color(obj):
        try:
            return obj.color
        except AttributeError:
            return 0

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    def _cmd_get_app_version(self, params):
        app = self._ControlSurface__c_instance.application()
        return {"version": app.get_version_string()}

    # ------------------------------------------------------------------
    # Song
    # ------------------------------------------------------------------

    def _cmd_get_song_info(self, params):
        s = self.song
        info = {
            "tempo": s.tempo,
            "time_signature_numerator": s.signature_numerator,
            "time_signature_denominator": s.signature_denominator,
            "is_playing": s.is_playing,
            "loop": s.loop,
            "loop_start": s.loop_start,
            "loop_length": s.loop_length,
            "record_mode": s.record_mode,
            "session_record": s.session_record,
            "overdub": s.overdub,
            "metronome": s.metronome,
            "swing_amount": s.swing_amount,
            "current_song_time": s.current_song_time,
            "back_to_arranger": s.back_to_arranger,
        }
        try:
            info["groove_amount"] = s.groove_amount
        except AttributeError:
            pass
        try:
            info["scale_mode"] = s.scale_mode
            info["scale_name"] = s.scale_name
            info["root_note"] = s.root_note
        except AttributeError:
            pass
        try:
            info["clip_trigger_quantization"] = int(s.clip_trigger_quantization)
            info["midi_recording_quantization"] = int(s.midi_recording_quantization)
        except AttributeError:
            pass
        return info

    def _cmd_set_tempo(self, params):
        def fn():
            self.song.tempo = float(params["tempo"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_time_signature(self, params):
        def fn():
            if "numerator" in params:
                self.song.signature_numerator = int(params["numerator"])
            if "denominator" in params:
                self.song.signature_denominator = int(params["denominator"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_record_mode(self, params):
        def fn():
            self.song.record_mode = bool(params["record_mode"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_session_record(self, params):
        def fn():
            self.song.session_record = bool(params["session_record"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_overdub(self, params):
        def fn():
            self.song.overdub = bool(params["overdub"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_metronome(self, params):
        def fn():
            self.song.metronome = bool(params["metronome"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_loop(self, params):
        def fn():
            if "enabled" in params:
                self.song.loop = bool(params["enabled"])
            if "loop_start" in params:
                self.song.loop_start = float(params["loop_start"])
            if "loop_length" in params:
                self.song.loop_length = float(params["loop_length"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_swing_amount(self, params):
        def fn():
            self.song.swing_amount = float(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_groove_amount(self, params):
        def fn():
            self.song.groove_amount = float(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_back_to_arranger(self, params):
        def fn():
            self.song.back_to_arranger = bool(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_trigger_quantization(self, params):
        def fn():
            self.song.clip_trigger_quantization = int(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_midi_recording_quantization(self, params):
        def fn():
            self.song.midi_recording_quantization = int(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scale_mode(self, params):
        def fn():
            self.song.scale_mode = bool(params["scale_mode"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scale_name(self, params):
        def fn():
            self.song.scale_name = str(params["scale_name"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_root_note(self, params):
        def fn():
            self.song.root_note = int(params["root_note"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_start_playing(self, params):
        def fn():
            self.song.start_playing()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_playing(self, params):
        def fn():
            self.song.stop_playing()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_continue_playing(self, params):
        def fn():
            self.song.continue_playing()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_tap_tempo(self, params):
        def fn():
            self.song.tap_tempo()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_undo(self, params):
        def fn():
            self.song.undo()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_redo(self, params):
        def fn():
            self.song.redo()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_capture_midi(self, params):
        destination = int(params.get("destination", 0))
        def fn():
            self.song.capture_midi(destination)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_capture_and_insert_scene(self, params):
        def fn():
            self.song.capture_and_insert_scene()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_jump_by(self, params):
        beats = float(params["beats"])
        def fn():
            self.song.jump_by(beats)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_jump_to_next_cue(self, params):
        def fn():
            self.song.jump_to_next_cue()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_jump_to_prev_cue(self, params):
        def fn():
            self.song.jump_to_prev_cue()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_all_clips(self, params):
        quantized = bool(params.get("quantized", 1))
        def fn():
            self.song.stop_all_clips(quantized)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_cue_points(self, params):
        cues = []
        for cp in self.song.cue_points:
            cues.append({"name": cp.name, "time": cp.time})
        return cues

    def _cmd_jump_to_cue_point(self, params):
        index = int(params["index"])
        cue_points = list(self.song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("cue point index {} out of range".format(index))
        cp = cue_points[index]
        def fn():
            cp.jump()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_or_delete_cue(self, params):
        def fn():
            self.song.set_or_delete_cue()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_re_enable_automation(self, params):
        def fn():
            self.song.re_enable_automation()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_play_selection(self, params):
        def fn():
            self.song.play_selection()
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # Song.View
    # ------------------------------------------------------------------

    def _cmd_get_selected_track(self, params):
        view = self.song.view
        sel = view.selected_track
        all_tracks = list(self.song.tracks)
        try:
            idx = all_tracks.index(sel)
        except ValueError:
            idx = -1
        return {"index": idx, "name": sel.name}

    def _cmd_set_selected_track(self, params):
        track = self._get_track(int(params["track_index"]))
        def fn():
            self.song.view.selected_track = track
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_selected_scene(self, params):
        view = self.song.view
        sel = view.selected_scene
        all_scenes = list(self.song.scenes)
        try:
            idx = all_scenes.index(sel)
        except ValueError:
            idx = -1
        return {"index": idx, "name": sel.name}

    def _cmd_set_selected_scene(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        def fn():
            self.song.view.selected_scene = scene
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_follow_song(self, params):
        return {"follow_song": self.song.view.follow_song}

    def _cmd_set_follow_song(self, params):
        val = bool(params["follow_song"])
        def fn():
            self.song.view.follow_song = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_draw_mode(self, params):
        try:
            return {"draw_mode": self.song.view.draw_mode}
        except AttributeError:
            return {"draw_mode": False}

    def _cmd_set_draw_mode(self, params):
        val = bool(params["draw_mode"])
        def fn():
            self.song.view.draw_mode = val
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # Master Track
    # ------------------------------------------------------------------

    def _cmd_get_master_track(self, params):
        master = self.song.master_track
        mixer = master.mixer_device
        return {
            "volume": mixer.volume.value,
            "pan": mixer.panning.value,
            "crossfader": mixer.crossfader.value,
        }

    def _cmd_set_master_volume(self, params):
        val = float(params["value"])
        def fn():
            self.song.master_track.mixer_device.volume.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_master_pan(self, params):
        val = float(params["value"])
        def fn():
            self.song.master_track.mixer_device.panning.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_crossfader(self, params):
        val = float(params["value"])
        def fn():
            self.song.master_track.mixer_device.crossfader.value = val
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # Track
    # ------------------------------------------------------------------

    def _cmd_get_tracks(self, params):
        result = []
        for i, track in enumerate(self.song.tracks):
            mixer = track.mixer_device
            result.append({
                "index": i,
                "name": track.name,
                "color": self._color(track),
                "mute": track.mute,
                "solo": track.solo,
                "arm": track.arm if hasattr(track, "arm") else False,
                "volume": mixer.volume.value,
                "pan": mixer.panning.value,
                "is_midi_track": track.has_midi_input,
                "is_audio_track": track.has_audio_input,
                "is_group_track": track.is_foldable if hasattr(track, "is_foldable") else False,
                "device_count": len(list(track.devices)),
                "clip_slot_count": len(list(track.clip_slots)),
            })
        return result

    def _cmd_get_track_info(self, params):
        track_index = int(params["track_index"])
        track = self._get_track(track_index)
        mixer = track.mixer_device
        sends = [{"index": i, "value": s.value} for i, s in enumerate(mixer.sends)]
        clip_slots_summary = []
        for j, slot in enumerate(track.clip_slots):
            entry = {"slot_index": j, "has_clip": slot.has_clip}
            if slot.has_clip:
                clip = slot.clip
                entry["clip_name"] = clip.name
                entry["is_playing"] = clip.is_playing
                entry["is_recording"] = clip.is_recording
            clip_slots_summary.append(entry)
        devices_summary = [{"index": k, "name": d.name, "class_name": d.class_name} for k, d in enumerate(track.devices)]
        info = {
            "index": track_index,
            "name": track.name,
            "color": self._color(track),
            "mute": track.mute,
            "solo": track.solo,
            "arm": track.arm if hasattr(track, "arm") else False,
            "volume": mixer.volume.value,
            "pan": mixer.panning.value,
            "sends": sends,
            "crossfade_assign": int(mixer.crossfade_assign),
            "is_midi_track": track.has_midi_input,
            "is_audio_track": track.has_audio_input,
            "is_foldable": track.is_foldable if hasattr(track, "is_foldable") else False,
            "fold_state": int(track.fold_state) if hasattr(track, "fold_state") else 0,
            "clip_slots": clip_slots_summary,
            "devices": devices_summary,
        }
        try:
            info["input_routing_type"] = str(track.input_routing_type)
            info["output_routing_type"] = str(track.output_routing_type)
        except AttributeError:
            pass
        return info

    def _cmd_get_return_tracks(self, params):
        result = []
        for i, track in enumerate(self.song.return_tracks):
            mixer = track.mixer_device
            result.append({
                "index": i,
                "name": track.name,
                "volume": mixer.volume.value,
                "pan": mixer.panning.value,
                "color": self._color(track),
            })
        return result

    def _cmd_create_midi_track(self, params):
        index = int(params.get("index", -1))
        def fn():
            self.song.create_midi_track(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_create_audio_track(self, params):
        index = int(params.get("index", -1))
        def fn():
            self.song.create_audio_track(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_create_return_track(self, params):
        def fn():
            self.song.create_return_track()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_track(self, params):
        track_index = int(params["track_index"])
        def fn():
            self.song.delete_track(track_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_return_track(self, params):
        index = int(params["index"])
        def fn():
            self.song.delete_return_track(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_track(self, params):
        track_index = int(params["track_index"])
        def fn():
            self.song.duplicate_track(track_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_name(self, params):
        track = self._get_track(int(params["track_index"]))
        name = str(params["name"])
        def fn():
            track.name = name
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_color(self, params):
        track = self._get_track(int(params["track_index"]))
        color = int(params["color"])
        def fn():
            track.color = color
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_mute(self, params):
        track = self._get_track(int(params["track_index"]))
        mute = bool(params["mute"])
        def fn():
            track.mute = mute
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_solo(self, params):
        track = self._get_track(int(params["track_index"]))
        solo = bool(params["solo"])
        def fn():
            track.solo = solo
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_arm(self, params):
        track = self._get_track(int(params["track_index"]))
        arm = bool(params["arm"])
        def fn():
            track.arm = arm
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_volume(self, params):
        track = self._get_track(int(params["track_index"]))
        val = float(params["value"])
        def fn():
            track.mixer_device.volume.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_pan(self, params):
        track = self._get_track(int(params["track_index"]))
        val = float(params["value"])
        def fn():
            track.mixer_device.panning.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_send(self, params):
        track = self._get_track(int(params["track_index"]))
        send_index = int(params["send_index"])
        val = float(params["value"])
        sends = list(track.mixer_device.sends)
        if send_index < 0 or send_index >= len(sends):
            raise IndexError("send_index {} out of range".format(send_index))
        send = sends[send_index]
        def fn():
            send.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_crossfade_assign(self, params):
        track = self._get_track(int(params["track_index"]))
        val = int(params["value"])
        def fn():
            track.mixer_device.crossfade_assign = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_track_clips(self, params):
        track = self._get_track(int(params["track_index"]))
        def fn():
            track.stop_all_clips()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_fold_state(self, params):
        track = self._get_track(int(params["track_index"]))
        fold_state = int(params["fold_state"])
        def fn():
            track.fold_state = fold_state
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # ClipSlot
    # ------------------------------------------------------------------

    def _cmd_get_clip_slots(self, params):
        track = self._get_track(int(params["track_index"]))
        result = []
        for j, slot in enumerate(track.clip_slots):
            entry = {
                "slot_index": j,
                "has_clip": slot.has_clip,
                "is_playing": slot.is_playing,
                "is_recording": slot.is_recording,
                "is_triggered": slot.is_triggered,
            }
            result.append(entry)
        return result

    def _cmd_fire_clip_slot(self, params):
        slot = self._get_clip_slot(int(params["track_index"]), int(params["slot_index"]))
        record_length = params.get("record_length")
        launch_quantization = params.get("launch_quantization")
        def fn():
            if record_length is not None:
                slot.set_fire_button_state(True)
            else:
                slot.fire()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_clip_slot(self, params):
        slot = self._get_clip_slot(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            slot.stop()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_create_clip(self, params):
        slot = self._get_clip_slot(int(params["track_index"]), int(params["slot_index"]))
        length = float(params.get("length", 4.0))
        def fn():
            slot.create_clip(length)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_clip(self, params):
        slot = self._get_clip_slot(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            slot.delete_clip()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_clip_slot(self, params):
        track_index = int(params["track_index"])
        slot_index = int(params["slot_index"])
        track = self._get_track(track_index)
        def fn():
            track.duplicate_clip_slot(slot_index)
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # Clip
    # ------------------------------------------------------------------

    def _cmd_get_clip_info(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        info = {
            "name": clip.name,
            "length": clip.length,
            "is_playing": clip.is_playing,
            "is_recording": clip.is_recording,
            "is_midi_clip": clip.is_midi_clip,
            "looping": clip.looping,
            "loop_start": clip.loop_start,
            "loop_end": clip.loop_end,
            "start_marker": clip.start_marker,
            "end_marker": clip.end_marker,
            "color": self._color(clip),
            "muted": clip.muted,
            "launch_mode": int(clip.launch_mode),
            "launch_quantization": int(clip.launch_quantization),
            "signature_numerator": clip.signature_numerator,
            "signature_denominator": clip.signature_denominator,
        }
        if not clip.is_midi_clip:
            try:
                info["gain"] = clip.gain
                info["warping"] = clip.warping
                info["warp_mode"] = int(clip.warp_mode)
                info["pitch_coarse"] = clip.pitch_coarse
                info["pitch_fine"] = clip.pitch_fine
            except AttributeError:
                pass
        try:
            info["velocity_amount"] = clip.velocity_amount
        except AttributeError:
            pass
        return info

    def _cmd_set_clip_name(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        name = str(params["name"])
        def fn():
            clip.name = name
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_color(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        color = int(params["color"])
        def fn():
            clip.color = color
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_loop(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            if "looping" in params:
                clip.looping = bool(params["looping"])
            if "loop_start" in params:
                clip.loop_start = float(params["loop_start"])
            if "loop_end" in params:
                clip.loop_end = float(params["loop_end"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_markers(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            if "start_marker" in params:
                clip.start_marker = float(params["start_marker"])
            if "end_marker" in params:
                clip.end_marker = float(params["end_marker"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_mute(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        mute = bool(params["mute"])
        def fn():
            clip.muted = mute
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_pitch(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            if "pitch_coarse" in params:
                clip.pitch_coarse = int(params["pitch_coarse"])
            if "pitch_fine" in params:
                clip.pitch_fine = float(params["pitch_fine"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_gain(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        gain = float(params["gain"])
        def fn():
            clip.gain = gain
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_warp_mode(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        warp_mode = int(params["warp_mode"])
        def fn():
            clip.warp_mode = warp_mode
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_launch_mode(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        launch_mode = int(params["launch_mode"])
        def fn():
            clip.launch_mode = launch_mode
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_launch_quantization(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        lq = int(params["launch_quantization"])
        def fn():
            clip.launch_quantization = lq
        self._run_on_main_thread(fn)
        return {}

    def _cmd_fire_clip(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            clip.fire()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_clip(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            clip.stop()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_crop_clip(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            clip.crop()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_clip_loop(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            clip.duplicate_loop()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_quantize_clip(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        grid = int(params["quantization_grid"])
        amount = float(params.get("amount", 1.0))
        def fn():
            clip.quantize(grid, amount)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        if not clip.is_midi_clip:
            raise RuntimeError("Clip is not a MIDI clip")
        raw = clip.get_all_notes_extended()
        notes = []
        for n in raw.get("notes", []):
            notes.append({
                "note_id": n.get("note_id"),
                "pitch": n.get("pitch"),
                "start_time": n.get("start_time"),
                "duration": n.get("duration"),
                "velocity": n.get("velocity", 100),
                "mute": n.get("mute", False),
                "probability": n.get("probability", 1.0),
                "velocity_deviation": n.get("velocity_deviation", 0),
                "release_velocity": n.get("release_velocity", 64),
            })
        return {"notes": notes}

    def _cmd_add_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        notes = params["notes"]
        if not clip.is_midi_clip:
            raise RuntimeError("Clip is not a MIDI clip")
        def fn():
            clip.add_new_notes({"notes": notes})
        self._run_on_main_thread(fn)
        return {}

    def _cmd_remove_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        from_pitch = int(params.get("from_pitch", 0))
        pitch_span = int(params.get("pitch_span", 128))
        from_time = float(params.get("from_time", 0.0))
        time_span = params.get("time_span")
        if not clip.is_midi_clip:
            raise RuntimeError("Clip is not a MIDI clip")
        def fn():
            if time_span is not None:
                clip.remove_notes_extended(from_pitch, pitch_span, from_time, float(time_span))
            else:
                clip.remove_notes_extended(from_pitch, pitch_span, from_time, clip.length)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_apply_note_modifications(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        notes = params["notes"]
        if not clip.is_midi_clip:
            raise RuntimeError("Clip is not a MIDI clip")
        def fn():
            clip.apply_note_modifications({"notes": notes})
        self._run_on_main_thread(fn)
        return {}

    def _cmd_select_all_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        if not clip.is_midi_clip:
            raise RuntimeError("Clip is not a MIDI clip")
        def fn():
            clip.select_all_notes()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_deselect_all_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        if not clip.is_midi_clip:
            raise RuntimeError("Clip is not a MIDI clip")
        def fn():
            clip.deselect_all_notes()
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # Scene
    # ------------------------------------------------------------------

    def _cmd_get_scenes(self, params):
        result = []
        for i, scene in enumerate(self.song.scenes):
            entry = {
                "index": i,
                "name": scene.name,
                "color": self._color(scene),
                "is_empty": scene.is_empty,
                "is_triggered": scene.is_triggered,
            }
            try:
                entry["tempo"] = scene.tempo
                entry["time_signature_numerator"] = scene.time_signature_numerator
                entry["time_signature_denominator"] = scene.time_signature_denominator
            except AttributeError:
                pass
            result.append(entry)
        return result

    def _cmd_get_scene_info(self, params):
        scene_index = int(params["scene_index"])
        scene = self._get_scene(scene_index)
        info = {
            "index": scene_index,
            "name": scene.name,
            "color": self._color(scene),
            "is_empty": scene.is_empty,
            "is_triggered": scene.is_triggered,
        }
        try:
            info["tempo"] = scene.tempo
            info["time_signature_numerator"] = scene.time_signature_numerator
            info["time_signature_denominator"] = scene.time_signature_denominator
        except AttributeError:
            pass
        return info

    def _cmd_create_scene(self, params):
        index = int(params.get("index", -1))
        def fn():
            self.song.create_scene(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_scene(self, params):
        index = int(params["index"])
        def fn():
            self.song.delete_scene(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_scene(self, params):
        index = int(params["index"])
        def fn():
            self.song.duplicate_scene(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_name(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        name = str(params["name"])
        def fn():
            scene.name = name
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_tempo(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        tempo = float(params["tempo"])
        def fn():
            scene.tempo = tempo
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_color(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        color = int(params["color"])
        def fn():
            scene.color = color
        self._run_on_main_thread(fn)
        return {}

    def _cmd_fire_scene(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        def fn():
            scene.fire()
        self._run_on_main_thread(fn)
        return {}

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

    def _cmd_get_device_info(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        return {
            "name": device.name,
            "class_name": device.class_name,
            "class_display_name": device.class_display_name,
            "type": int(device.type),
            "is_active": device.is_active,
            "can_have_chains": device.can_have_chains,
            "can_have_drum_pads": device.can_have_drum_pads,
            "parameter_count": len(list(device.parameters)),
        }

    def _cmd_get_device_parameters(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        result = []
        for i, p in enumerate(device.parameters):
            entry = {
                "index": i,
                "name": p.name,
                "value": p.value,
                "min": p.min,
                "max": p.max,
                "default_value": p.default_value,
                "is_quantized": p.is_quantized,
                "value_string": p.str_for_value(p.value),
                "automation_state": int(p.automation_state),
            }
            if p.is_quantized:
                try:
                    entry["value_items"] = list(p.value_items)
                except AttributeError:
                    pass
            result.append(entry)
        return result

    def _cmd_set_device_parameter(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        param_index = int(params["parameter_index"])
        val = float(params["value"])
        parameters = list(device.parameters)
        if param_index < 0 or param_index >= len(parameters):
            raise IndexError("parameter_index {} out of range".format(param_index))
        param = parameters[param_index]
        clamped = max(param.min, min(param.max, val))
        def fn():
            param.value = clamped
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_device_enabled(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        enabled = bool(params["enabled"])
        def fn():
            device.parameters[0].value = 1.0 if enabled else 0.0
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_device(self, params):
        track_index = int(params["track_index"])
        device_index = int(params["device_index"])
        track = self._get_track(track_index)
        def fn():
            track.delete_device(device_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_device(self, params):
        track_index = int(params["track_index"])
        device_index = int(params["device_index"])
        track = self._get_track(track_index)
        def fn():
            track.duplicate_device(device_index)
        self._run_on_main_thread(fn)
        return {}

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

    # ------------------------------------------------------------------
    # RackDevice
    # ------------------------------------------------------------------

    def _cmd_get_rack_chains(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        if not device.can_have_chains:
            raise RuntimeError("Device does not support chains")
        result = []
        for i, chain in enumerate(device.chains):
            result.append({
                "index": i,
                "name": chain.name,
                "color": self._color(chain),
                "mute": chain.mute,
                "solo": chain.solo if hasattr(chain, "solo") else False,
            })
        return result

    def _cmd_get_rack_drum_pads(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        if not device.can_have_drum_pads:
            raise RuntimeError("Device does not have drum pads")
        result = []
        for pad in device.drum_pads:
            result.append({
                "note": pad.note,
                "name": pad.name,
                "mute": pad.mute,
                "solo": pad.solo if hasattr(pad, "solo") else False,
            })
        return result

    def _cmd_randomize_rack_macros(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        def fn():
            device.randomize()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_store_rack_variation(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]))
        def fn():
            device.store_variation()
        self._run_on_main_thread(fn)
        return {}

    # ------------------------------------------------------------------
    # GroovePool
    # ------------------------------------------------------------------

    def _cmd_get_grooves(self, params):
        result = []
        try:
            for groove in self.song.groove_pool.grooves:
                result.append({
                    "name": groove.name,
                    "quantization_amount": groove.quantization_amount,
                    "timing_amount": groove.timing_amount,
                    "random_amount": groove.random_amount,
                    "velocity_amount": groove.velocity_amount,
                })
        except AttributeError:
            pass
        return result

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def _cmd_get_browser_tree(self, params):
        category_type = str(params.get("category_type", "all"))
        app = self._ControlSurface__c_instance.application()
        browser = app.browser

        def serialize_item(item, depth=0):
            entry = {"name": item.name}
            try:
                entry["uri"] = item.uri
            except AttributeError:
                pass
            if depth < 2:
                try:
                    entry["children"] = [serialize_item(c, depth + 1) for c in item.children]
                except AttributeError:
                    pass
            return entry

        categories = {
            "instruments": browser.instruments,
            "sounds": browser.sounds,
            "drums": browser.drums,
            "audio_effects": browser.audio_effects,
            "midi_effects": browser.midi_effects,
        }

        if category_type == "all":
            return {k: [serialize_item(c) for c in v.children] for k, v in categories.items()}
        elif category_type in categories:
            root = categories[category_type]
            return {category_type: [serialize_item(c) for c in root.children]}
        else:
            raise ValueError("Unknown category_type: {}".format(category_type))

    def _cmd_get_browser_items_at_path(self, params):
        path = str(params["path"])
        app = self._ControlSurface__c_instance.application()
        browser = app.browser
        parts = [p for p in path.split("/") if p]

        root_map = {
            "instruments": browser.instruments,
            "sounds": browser.sounds,
            "drums": browser.drums,
            "audio_effects": browser.audio_effects,
            "midi_effects": browser.midi_effects,
        }

        if not parts or parts[0] not in root_map:
            raise ValueError("Path must start with: {}".format(", ".join(root_map.keys())))

        current = root_map[parts[0]]
        for part in parts[1:]:
            found = None
            for child in current.children:
                if child.name.lower() == part.lower():
                    found = child
                    break
            if found is None:
                raise ValueError("Path segment '{}' not found".format(part))
            current = found

        items = []
        for child in current.children:
            entry = {"name": child.name, "is_folder": child.is_folder}
            try:
                entry["uri"] = child.uri
            except AttributeError:
                pass
            items.append(entry)
        return {"items": items}

    def _cmd_load_browser_item(self, params):
        uri = str(params["uri"])
        track_index = int(params.get("track_index", 0))
        track = self._get_track(track_index)
        app = self._ControlSurface__c_instance.application()
        browser = app.browser

        def _find_item_by_uri(root, uri):
            if hasattr(root, "uri") and root.uri == uri:
                return root
            try:
                for child in root.children:
                    found = _find_item_by_uri(child, uri)
                    if found:
                        return found
            except AttributeError:
                pass
            return None

        categories = [
            browser.instruments, browser.sounds, browser.drums,
            browser.audio_effects, browser.midi_effects,
        ]
        item = None
        for cat in categories:
            item = _find_item_by_uri(cat, uri)
            if item:
                break

        if item is None:
            raise ValueError("Browser item with URI '{}' not found".format(uri))

        def fn():
            self.song.view.selected_track = track
            browser.load_item(item)

        self._run_on_main_thread(fn)
        return {}
