"""
AbletonMPCX Remote Script
Runs inside Ableton Live as a Control Surface.
Listens on localhost:9877 for JSON commands from server.py.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json
import math
import os
import socket
import struct
import threading
import traceback

try:
    import Queue as queue
except ImportError:
    import queue

try:
    TimeoutError
except NameError:
    # Python 2 (Ableton Live < 11)
    TimeoutError = RuntimeError

import Live  # noqa: F401 – provided by Ableton's Python environment

from _Framework.ControlSurface import ControlSurface

def create_instance(c_instance):
    return AbletonMPCX(c_instance)


class AbletonMPCX(ControlSurface):
    """MCP Remote Script – bridges server.py to the Ableton Live Object Model."""

    HOST = "localhost"
    PORT = 9877
    THREAD_TIMEOUT = 10.0  # seconds to wait for scheduled mutations
    PROTOCOL_VERSION = "1.0.0"

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def __init__(self, c_instance):
        super(AbletonMPCX, self).__init__(c_instance)
        self._server_socket = None
        self._server_thread = None
        self._running = False
        self._initialized = True  # safe to call self.song() from here onward
        self._start_server()

    def disconnect(self):
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        super(AbletonMPCX, self).disconnect()

    # -------------------------------------------------------------------------
    # Socket server
    # -------------------------------------------------------------------------

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
            conn.settimeout(5.0)
            # Read 4-byte length prefix
            header = self._recv_exactly(conn, 4)
            if not header:
                return
            msg_len = struct.unpack(">I", header)[0]
            if msg_len > 10 * 1024 * 1024:  # 10 MB sanity cap
                raise RuntimeError("Incoming message too large: {} bytes".format(msg_len))
            data = self._recv_exactly(conn, msg_len)
            if data is None:
                return
            request = json.loads(data.decode("utf-8"))
            response = self._dispatch(request)
            payload = json.dumps(response).encode("utf-8")
            conn.sendall(struct.pack(">I", len(payload)) + payload)
        except Exception as e:
            try:
                err_payload = json.dumps({"status": "error", "error": str(e)}).encode("utf-8")
                conn.sendall(struct.pack(">I", len(err_payload)) + err_payload)
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _recv_exactly(self, conn, n):
        """Read exactly n bytes from conn, returning None if the connection closes early."""
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(min(65536, n - len(buf)))
            if not chunk:
                return None
            buf += chunk
        return buf

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------

    def _dispatch(self, request):
        try:
            command = request.get("command", "")
            params = request.get("params", {})
            handler = getattr(self, "_cmd_{}".format(command), None)
            if handler is None:
                return {"status": "error", "error": "Unknown command: {}".format(command)}
            result = handler(params)
            return {"status": "ok", "result": result}
        except Exception as e:
            self.log_message("AbletonMPCX dispatch error: {}\n{}".format(e, traceback.format_exc()))
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
        try:
            kind, value = result_queue.get(timeout=self.THREAD_TIMEOUT)
        except queue.Empty:
            raise TimeoutError(
                "Live main thread did not respond within {}s. "
                "Live may be busy or the Remote Script may have crashed.".format(self.THREAD_TIMEOUT)
            )
        if kind == "error":
            raise RuntimeError(value)
        return value

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @property
    def _song(self):
        if not getattr(self, '_initialized', False):
            raise RuntimeError("AbletonMPCX not yet initialized")
        return self.song()

    def _get_track(self, track_index):
        if track_index == -1:
            return self._song.master_track
        tracks = list(self._song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError("track_index {} out of range (0-{})".format(track_index, len(tracks) - 1))
        return tracks[track_index]

    def _get_return_track(self, index):
        tracks = list(self._song.return_tracks)
        if index < 0 or index >= len(tracks):
            raise IndexError("return track index {} out of range (0-{})".format(index, len(tracks) - 1))
        return tracks[index]

    def _resolve_track(self, track_index: int, is_return: bool = False):
        """Resolve a track by index from either regular or return tracks."""
        if is_return:
            return self._get_return_track(track_index)
        return self._get_track(track_index)

    def _get_scene(self, scene_index):
        scenes = list(self._song.scenes)
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

    def _get_device(self, track_index, device_index, is_return=False):
        track = self._resolve_track(track_index, is_return)
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

    @staticmethod
    def _safe(obj, attr, default=None):
        try:
            return getattr(obj, attr)
        except AttributeError:
            return default

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------

    def _cmd_get_app_version(self, params):
        app = self.application()
        return {"version": app.get_version_string()}

    def _cmd_open_set(self, params):
        """Open an Ableton Live set file by path."""
        set_path = str(params["set_path"])
        def fn():
            app = self.application()
            if hasattr(app, "open_project"):
                app.open_project(set_path)
            else:
                raise RuntimeError(
                    "open_project() not available in this version of Ableton Live. "
                    "Open the set manually."
                )
        self._run_on_main_thread(fn)
        return {"set_path": set_path}

    # -------------------------------------------------------------------------
    # Song (read)
    # -------------------------------------------------------------------------

    def _cmd_get_song_info(self, params):
        s = self._song
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
        for attr in ("groove_amount", "scale_mode", "scale_name", "root_note"):
            try:
                info[attr] = getattr(s, attr)
            except AttributeError:
                pass
        try:
            info["clip_trigger_quantization"] = int(s.clip_trigger_quantization)
            info["midi_recording_quantization"] = int(s.midi_recording_quantization)
        except AttributeError:
            pass
        for attr in ("exclusive_arm", "exclusive_solo", "select_on_launch"):
            try:
                info[attr] = getattr(s, attr)
            except AttributeError:
                pass
        return info

    # -------------------------------------------------------------------------
    # Song (write)
    # -------------------------------------------------------------------------

    def _cmd_set_tempo(self, params):
        def fn():
            self._song.tempo = float(params["tempo"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_time_signature(self, params):
        def fn():
            if "numerator" in params:
                self._song.signature_numerator = int(params["numerator"])
            if "denominator" in params:
                self._song.signature_denominator = int(params["denominator"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_record_mode(self, params):
        def fn():
            self._song.record_mode = bool(params["record_mode"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_session_record(self, params):
        def fn():
            self._song.session_record = bool(params["session_record"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_overdub(self, params):
        def fn():
            self._song.overdub = bool(params["overdub"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_metronome(self, params):
        def fn():
            self._song.metronome = bool(params["metronome"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_loop(self, params):
        def fn():
            if "enabled" in params:
                self._song.loop = bool(params["enabled"])
            if "loop_start" in params:
                self._song.loop_start = float(params["loop_start"])
            if "loop_length" in params:
                self._song.loop_length = float(params["loop_length"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_swing_amount(self, params):
        def fn():
            self._song.swing_amount = float(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_groove_amount(self, params):
        def fn():
            self._song.groove_amount = float(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_back_to_arranger(self, params):
        def fn():
            self._song.back_to_arranger = bool(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_trigger_quantization(self, params):
        def fn():
            self._song.clip_trigger_quantization = int(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_midi_recording_quantization(self, params):
        def fn():
            self._song.midi_recording_quantization = int(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scale_mode(self, params):
        def fn():
            self._song.scale_mode = bool(params["scale_mode"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scale_name(self, params):
        def fn():
            self._song.scale_name = str(params["scale_name"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_root_note(self, params):
        def fn():
            self._song.root_note = int(params["root_note"])
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Transport
    # -------------------------------------------------------------------------

    def _cmd_start_playing(self, params):
        def fn():
            self._song.start_playing()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_playing(self, params):
        def fn():
            self._song.stop_playing()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_continue_playing(self, params):
        def fn():
            self._song.continue_playing()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_tap_tempo(self, params):
        def fn():
            self._song.tap_tempo()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_undo(self, params):
        def fn():
            self._song.undo()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_redo(self, params):
        def fn():
            self._song.redo()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_capture_midi(self, params):
        destination = int(params.get("destination", 0))
        def fn():
            self._song.capture_midi(destination)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_capture_and_insert_scene(self, params):
        def fn():
            self._song.capture_and_insert_scene()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_jump_by(self, params):
        beats = float(params["beats"])
        def fn():
            self._song.jump_by(beats)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_jump_to_next_cue(self, params):
        def fn():
            self._song.jump_to_next_cue()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_jump_to_prev_cue(self, params):
        def fn():
            self._song.jump_to_prev_cue()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_stop_all_clips(self, params):
        quantized = bool(params.get("quantized", 1))
        def fn():
            self._song.stop_all_clips(quantized)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_re_enable_automation(self, params):
        def fn():
            self._song.re_enable_automation()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_play_selection(self, params):
        def fn():
            self._song.play_selection()
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Cue Points
    # -------------------------------------------------------------------------

    def _cmd_get_cue_points(self, params):
        cues = []
        for cp in self._song.cue_points:
            cues.append({"name": cp.name, "time": cp.time})
        return cues

    def _cmd_jump_to_cue_point(self, params):
        index = int(params["index"])
        cue_points = list(self._song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("cue point index {} out of range".format(index))
        cp = cue_points[index]
        def fn():
            cp.jump()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_or_delete_cue(self, params):
        def fn():
            self._song.set_or_delete_cue()
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Song.View
    # -------------------------------------------------------------------------

    def _cmd_get_selected_track(self, params):
        view = self._song.view
        sel = view.selected_track
        all_tracks = list(self._song.tracks)
        try:
            idx = all_tracks.index(sel)
        except ValueError:
            idx = -1
        return {"index": idx, "name": sel.name}

    def _cmd_set_selected_track(self, params):
        track = self._get_track(int(params["track_index"]))
        def fn():
            self._song.view.selected_track = track
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_selected_scene(self, params):
        view = self._song.view
        sel = view.selected_scene
        all_scenes = list(self._song.scenes)
        try:
            idx = all_scenes.index(sel)
        except ValueError:
            idx = -1
        return {"index": idx, "name": sel.name}

    def _cmd_set_selected_scene(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        def fn():
            self._song.view.selected_scene = scene
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_follow_song(self, params):
        return {"follow_song": self._song.view.follow_song}

    def _cmd_set_follow_song(self, params):
        val = bool(params["follow_song"])
        def fn():
            self._song.view.follow_song = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_draw_mode(self, params):
        try:
            return {"draw_mode": self._song.view.draw_mode}
        except AttributeError:
            return {"draw_mode": False}

    def _cmd_set_draw_mode(self, params):
        val = bool(params["draw_mode"])
        def fn():
            self._song.view.draw_mode = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_focus_view(self, params):
        view_name = str(params["view_name"])
        def fn():
            self.application().view.focus_view(view_name)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_show_view(self, params):
        view_name = str(params["view_name"])
        def fn():
            self.application().view.show_view(view_name)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_hide_view(self, params):
        view_name = str(params["view_name"])
        def fn():
            self.application().view.hide_view(view_name)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_is_view_visible(self, params):
        view_name = str(params["view_name"])
        return {"visible": self.application().view.is_view_visible(view_name)}

    def _cmd_available_main_views(self, params):
        return {"views": list(self.application().view.available_main_views())}

    def _cmd_set_exclusive_arm(self, params):
        def fn():
            self._song.exclusive_arm = bool(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_exclusive_solo(self, params):
        def fn():
            self._song.exclusive_solo = bool(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_select_on_launch(self, params):
        def fn():
            self._song.select_on_launch = bool(params["value"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_nudge_up(self, params):
        def fn():
            self._song.nudge_up = True
        self._run_on_main_thread(fn)
        return {}

    def _cmd_nudge_down(self, params):
        def fn():
            self._song.nudge_down = True
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_appointed_device(self, params):
        """Return the currently appointed (focused) device."""
        try:
            device = self._song.appointed_device
            if device is None:
                return {"device": None}
            tracks = list(self._song.tracks)
            for ti, track in enumerate(tracks + [self._song.master_track]):
                for di, d in enumerate(track.devices):
                    if d == device:
                        return {
                            "track_index": ti if ti < len(tracks) else -1,
                            "device_index": di,
                            "name": device.name,
                            "class_name": device.class_name,
                        }
        except AttributeError:
            pass
        return {"device": None}

    # -------------------------------------------------------------------------
    # Master Track
    # -------------------------------------------------------------------------

    def _cmd_get_master_track(self, params):
        master = self._song.master_track
        mixer = master.mixer_device
        return {
            "volume": mixer.volume.value,
            "pan": mixer.panning.value,
            "crossfader": mixer.crossfader.value,
        }

    def _cmd_set_master_volume(self, params):
        val = float(params["value"])
        def fn():
            self._song.master_track.mixer_device.volume.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_master_pan(self, params):
        val = float(params["value"])
        def fn():
            self._song.master_track.mixer_device.panning.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_crossfader(self, params):
        val = float(params["value"])
        def fn():
            self._song.master_track.mixer_device.crossfader.value = val
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Track (read)
    # -------------------------------------------------------------------------

    def _cmd_get_tracks(self, params):
        result = []
        for i, track in enumerate(self._song.tracks):
            mixer = track.mixer_device
            try:
                arm_val = track.arm
            except (AttributeError, RuntimeError):
                arm_val = False
            result.append({
                "index": i,
                "name": track.name,
                "color": self._color(track),
                "mute": track.mute,
                "solo": track.solo,
                "arm": arm_val,
                "volume": mixer.volume.value,
                "pan": mixer.panning.value,
                "is_midi_track": track.has_midi_input,
                "is_audio_track": track.has_audio_input,
                "is_group_track": track.is_foldable if hasattr(track, "is_foldable") else False,
                "device_count": len(list(track.devices)),
                "clip_slot_count": len(list(track.clip_slots)),
            })
        return result

    def _cmd_get_track_names(self, params):
        """Return a lightweight list of all track names and indices."""
        result = []
        for i, track in enumerate(self._song.tracks):
            result.append({"index": i, "name": track.name})
        if params.get("include_returns", False):
            for i, track in enumerate(self._song.return_tracks):
                result.append({"index": i, "name": track.name, "is_return": True})
        if params.get("include_master", False):
            result.append({"index": -1, "name": self._song.master_track.name, "is_master": True})
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
        devices_summary = [{"index": k, "name": d.name, "class_name": d.class_name, "is_active": d.is_active} for k, d in enumerate(track.devices)]
        try:
            arm_val = track.arm
        except (AttributeError, RuntimeError):
            arm_val = False
        info = {
            "index": track_index,
            "name": track.name,
            "color": self._color(track),
            "mute": track.mute,
            "solo": track.solo,
            "arm": arm_val,
            "volume": mixer.volume.value,
            "pan": mixer.panning.value,
            "sends": sends,
            "crossfade_assign": int(mixer.crossfade_assign),
            "is_midi_track": track.has_midi_input,
            "is_audio_track": track.has_audio_input,
            "is_foldable": track.is_foldable if hasattr(track, "is_foldable") else False,
            "fold_state": self._safe_fold_state(track),
            "clip_slots": clip_slots_summary,
            "devices": devices_summary,
        }
        try:
            info["input_routing_type"] = str(track.input_routing_type)
            info["output_routing_type"] = str(track.output_routing_type)
        except AttributeError:
            pass
        return info

    def _cmd_get_track_playing_state(self, params):
        """Return which slot is currently playing/queued for a track."""
        track = self._get_track(int(params["track_index"]))
        return {
            "playing_slot_index": self._safe(track, "playing_slot_index", -1),
            "fired_slot_index": self._safe(track, "fired_slot_index", -1),
        }

    def _cmd_get_return_tracks(self, params):
        result = []
        for i, track in enumerate(self._song.return_tracks):
            mixer = track.mixer_device
            result.append({
                "index": i,
                "name": track.name,
                "volume": mixer.volume.value,
                "pan": mixer.panning.value,
                "color": self._color(track),
            })
        return result

    def _cmd_get_track_routing(self, params):
        track = self._get_track(int(params["track_index"]))
        result = {}
        for attr in ("input_routing_type", "input_routing_channel",
                     "output_routing_type", "output_routing_channel"):
            try:
                val = getattr(track, attr)
                result[attr] = str(val)
                if attr in ("input_routing_type", "output_routing_type"):
                    try:
                        available_attr = "available_" + attr + "s"
                        result["available_" + attr + "s"] = [str(r) for r in getattr(track, available_attr)]
                    except AttributeError:
                        pass
            except AttributeError:
                pass
        return result

    def _cmd_set_track_input_routing_type(self, params):
        track = self._get_track(int(params["track_index"]))
        value = int(params["value"])
        def fn():
            try:
                available = list(track.available_input_routing_types)
                if value < 0 or value >= len(available):
                    raise IndexError("input_routing_type index {} out of range (0-{})".format(value, len(available) - 1))
                track.input_routing_type = available[value]
            except AttributeError as e:
                raise RuntimeError("input_routing_type not settable: {}".format(e))
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_input_routing_channel(self, params):
        track = self._get_track(int(params["track_index"]))
        value = int(params["value"])
        def fn():
            try:
                available = list(track.available_input_routing_channels)
                if value < 0 or value >= len(available):
                    raise IndexError("input_routing_channel index {} out of range (0-{})".format(value, len(available) - 1))
                track.input_routing_channel = available[value]
            except AttributeError as e:
                raise RuntimeError("input_routing_channel not settable: {}".format(e))
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_output_routing_type(self, params):
        track = self._get_track(int(params["track_index"]))
        value = int(params["value"])
        def fn():
            try:
                available = list(track.available_output_routing_types)
                if value < 0 or value >= len(available):
                    raise IndexError("output_routing_type index {} out of range (0-{})".format(value, len(available) - 1))
                track.output_routing_type = available[value]
            except AttributeError as e:
                raise RuntimeError("output_routing_type not settable: {}".format(e))
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_track_output_routing_channel(self, params):
        track = self._get_track(int(params["track_index"]))
        value = int(params["value"])
        def fn():
            try:
                available = list(track.available_output_routing_channels)
                if value < 0 or value >= len(available):
                    raise IndexError("output_routing_channel index {} out of range (0-{})".format(value, len(available) - 1))
                track.output_routing_channel = available[value]
            except AttributeError as e:
                raise RuntimeError("output_routing_channel not settable: {}".format(e))
        self._run_on_main_thread(fn)
        return {}

    def _apply_routing(self, track, type_attr, channel_attr,
                       routing_type_name, routing_channel_name):
        """Apply routing type and/or channel by display name; return an errors dict."""
        out = {}
        if routing_type_name is not None:
            try:
                available = list(getattr(track, "available_" + type_attr + "s"))
                match = next((r for r in available if r.display_name == routing_type_name), None)
                if match is None:
                    out["routing_type_error"] = "No {} with display_name '{}'".format(
                        type_attr, routing_type_name)
                else:
                    setattr(track, type_attr, match)
            except AttributeError as e:
                out["routing_type_error"] = "{} not settable: {}".format(type_attr, e)
        if routing_channel_name is not None:
            try:
                available = list(getattr(track, "available_" + channel_attr + "s"))
                match = next((r for r in available if r.display_name == routing_channel_name), None)
                if match is None:
                    out["routing_channel_error"] = "No {} with display_name '{}'".format(
                        channel_attr, routing_channel_name)
                else:
                    setattr(track, channel_attr, match)
            except AttributeError as e:
                out["routing_channel_error"] = "{} not settable: {}".format(channel_attr, e)
        return out

    def _cmd_get_available_routings(self, params):
        track = self._get_track(int(params["track_index"]))
        result = {}
        for attr, key in (
            ("available_input_routing_types", "input_routing_types"),
            ("available_input_routing_channels", "input_routing_channels"),
            ("available_output_routing_types", "output_routing_types"),
            ("available_output_routing_channels", "output_routing_channels"),
        ):
            try:
                result[key] = [r.display_name for r in getattr(track, attr)]
            except AttributeError:
                result[key] = []
        return result

    def _cmd_set_track_input_routing(self, params):
        track = self._get_track(int(params["track_index"]))
        routing_type_name = params.get("routing_type_name")
        routing_channel_name = params.get("routing_channel_name")
        out = {}
        def fn():
            out.update(self._apply_routing(
                track, "input_routing_type", "input_routing_channel",
                routing_type_name, routing_channel_name))
        self._run_on_main_thread(fn)
        return out

    def _cmd_set_track_output_routing(self, params):
        track = self._get_track(int(params["track_index"]))
        routing_type_name = params.get("routing_type_name")
        routing_channel_name = params.get("routing_channel_name")
        out = {}
        def fn():
            out.update(self._apply_routing(
                track, "output_routing_type", "output_routing_channel",
                routing_type_name, routing_channel_name))
        self._run_on_main_thread(fn)
        return out

    # -------------------------------------------------------------------------
    # Track (write)
    # -------------------------------------------------------------------------

    def _cmd_create_midi_track(self, params):
        index = int(params.get("index", -1))
        def fn():
            self._song.create_midi_track(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_create_audio_track(self, params):
        index = int(params.get("index", -1))
        def fn():
            self._song.create_audio_track(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_create_return_track(self, params):
        def fn():
            self._song.create_return_track()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_track(self, params):
        track_index = int(params["track_index"])
        def fn():
            self._song.delete_track(track_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_return_track(self, params):
        index = int(params["index"])
        def fn():
            self._song.delete_return_track(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_track(self, params):
        track_index = int(params["track_index"])
        def fn():
            self._song.duplicate_track(track_index)
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

    def _safe_fold_state(self, track):
        try:
            return int(track.fold_state)
        except (AttributeError, RuntimeError):
            return 0

    def _cmd_set_track_fold_state(self, params):
        track = self._get_track(int(params["track_index"]))
        fold_state = int(params["fold_state"])
        def fn():
            try:
                track.fold_state = fold_state
            except (AttributeError, RuntimeError):
                raise RuntimeError("track at index {} is not foldable".format(int(params["track_index"])))
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_mixer_snapshot(self, params):
        """
        Apply volume, pan, and/or sends to multiple tracks in a single main-thread call.
        states: list of dicts with track_index and any of: volume, pan, sends (list of floats), mute, arm
        """
        states = params.get("states", [])
        def fn():
            for state in states:
                track_index = int(state["track_index"])
                track = self._get_track(track_index)
                mixer = track.mixer_device
                if "volume" in state:
                    mixer.volume.value = float(state["volume"])
                if "pan" in state:
                    mixer.panning.value = float(state["pan"])
                if "sends" in state:
                    send_list = list(mixer.sends)
                    for i, val in enumerate(state["sends"]):
                        if i < len(send_list):
                            send_list[i].value = float(val)
                if "mute" in state:
                    track.mute = bool(state["mute"])
                if "arm" in state and hasattr(track, "arm"):
                    track.arm = bool(state["arm"])
        self._run_on_main_thread(fn)
        return {"tracks_updated": len(states)}

    def _cmd_set_return_track_volume(self, params):
        track = self._get_return_track(int(params["index"]))
        val = float(params["value"])
        def fn():
            track.mixer_device.volume.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_return_track_pan(self, params):
        track = self._get_return_track(int(params["index"]))
        val = float(params["value"])
        def fn():
            track.mixer_device.panning.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_return_track_name(self, params):
        track = self._get_return_track(int(params["index"]))
        name = str(params["name"])
        def fn():
            track.name = name
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_return_track_mute(self, params):
        track = self._get_return_track(int(params["index"]))
        mute = bool(params["mute"])
        def fn():
            track.mute = mute
        self._run_on_main_thread(fn)
        return {}

    def _cmd_begin_undo_step(self, params):
        """Open an undo step with a given name. All mutations until end_undo_step are grouped."""
        name = str(params.get("name", "MCP Operation"))
        def fn():
            self._song.begin_undo_step(name)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_end_undo_step(self, params):
        """Close the current undo step, grouping all changes since begin_undo_step into one."""
        def fn():
            self._song.end_undo_step()
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # ClipSlot
    # -------------------------------------------------------------------------

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
        def fn():
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

    # -------------------------------------------------------------------------
    # Clip (read)
    # -------------------------------------------------------------------------

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

    def _cmd_get_clip_playing_position(self, params):
        """Return the current playhead position within the clip (in beats)."""
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        return {"playing_position": self._safe(clip, "playing_position", 0.0)}

    def _cmd_get_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            if not clip.is_midi_clip:
                raise RuntimeError("Clip is not a MIDI clip")
            notes = []
            for note in clip.get_notes(0, 0, clip.length, 128):
                notes.append({
                    "pitch": note[0],
                    "start_time": note[1],
                    "duration": note[2],
                    "velocity": note[3],
                    "mute": note[4],
                })
            return {"notes": notes}
        return self._run_on_main_thread(fn)

    # -------------------------------------------------------------------------
    # Clip (write)
    # -------------------------------------------------------------------------

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

    def _cmd_set_clip_warping(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        warping = bool(params["warping"])
        def fn():
            clip.warping = warping
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_velocity_amount(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        value = float(params["value"])
        def fn():
            clip.velocity_amount = value
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
        val = int(params["launch_mode"])
        def fn():
            clip.launch_mode = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_clip_launch_quantization(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        val = int(params["launch_quantization"])
        def fn():
            clip.launch_quantization = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_get_clip_follow_actions(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        result = {}
        for attr in ("follow_action_time", "follow_action_linked",
                     "follow_action_enabled",
                     "follow_action_a", "follow_action_b",
                     "follow_action_chance_a", "follow_action_chance_b"):
            try:
                val = getattr(clip, attr)
                # FollowAction enum values are int-like but not plain Python ints;
                # cast to int so they serialise correctly over JSON.
                if not isinstance(val, (bool, float, str)) and hasattr(val, "__index__"):
                    result[attr] = int(val)
                else:
                    result[attr] = val
            except AttributeError:
                pass  # Property not available in this Live version
        return result

    def _cmd_set_clip_follow_actions(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        settable = {
            "follow_action_time": float,
            "follow_action_linked": bool,
            "follow_action_enabled": bool,
            "follow_action_a": int,
            "follow_action_b": int,
            "follow_action_chance_a": int,
            "follow_action_chance_b": int,
        }
        updates = {k: v for k, v in params.items() if k in settable}
        errors = {}
        def fn():
            for key, val in updates.items():
                try:
                    cast = settable[key]
                    setattr(clip, key, cast(val))
                except AttributeError:
                    errors[key] = "not available in this Live version"
                except Exception as e:
                    errors[key] = str(e)
        self._run_on_main_thread(fn)
        result = {"updated": list(updates.keys())}
        if errors:
            result["errors"] = errors
        return result

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

    def _cmd_add_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        notes = params.get("notes", [])
        note_tuples = tuple(
            (int(n["pitch"]), float(n["start_time"]), float(n["duration"]),
             int(n.get("velocity", 100)), bool(n.get("mute", False)))
            for n in notes
        )
        def fn():
            existing = clip.get_notes(0, 0, clip.length, 128)
            clip.set_notes(existing + note_tuples)
        self._run_on_main_thread(fn)
        return {"note_count": len(note_tuples)}

    def _cmd_replace_all_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        notes = params.get("notes", [])
        note_tuples = tuple(
            (int(n["pitch"]), float(n["start_time"]), float(n["duration"]),
             int(n.get("velocity", 100)), bool(n.get("mute", False)))
            for n in notes
        )
        def fn():
            if not clip.is_midi_clip:
                raise RuntimeError("Clip is not a MIDI clip")
            clip.set_notes(note_tuples)
        self._run_on_main_thread(fn)
        return {"note_count": len(note_tuples)}

    def _cmd_remove_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        from_time = float(params.get("from_time", 0.0))
        from_pitch = int(params.get("from_pitch", 0))
        time_span = float(params.get("time_span", clip.length))
        pitch_span = int(params.get("pitch_span", 128))
        def fn():
            clip.remove_notes(from_time, from_pitch, time_span, pitch_span)
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Clip Automation Envelopes
    # -------------------------------------------------------------------------

    def _cmd_get_clip_envelopes(self, params):
        """Return all automation envelopes on a clip, with device/parameter identity."""
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        if not hasattr(clip, "automation_envelopes"):
            return []
        result = []
        for i, env in enumerate(clip.automation_envelopes):
            try:
                param = env.automation_parameter
                result.append({
                    "index": i,
                    "parameter_name": param.name if param else None,
                    "parameter_original_name": getattr(param, "original_name", None),
                })
            except Exception:
                result.append({"index": i, "error": "could not read envelope"})
        return result

    def _cmd_get_clip_envelope(self, params):
        """Return all automation points for one envelope. envelope_index: index into clip.automation_envelopes."""
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        envelope_index = int(params["envelope_index"])
        try:
            envelopes = clip.automation_envelopes
        except AttributeError:
            raise RuntimeError("clip.automation_envelopes not available in this Live version")
        env = envelopes[envelope_index]
        points = []
        try:
            for event in env.automation_events:
                points.append({
                    "time": float(event.start),
                    "value": float(event.value),
                    "in_tangent": float(getattr(event, "in_tangent_x", 0.0)),
                    "out_tangent": float(getattr(event, "out_tangent_x", 0.0)),
                })
        except AttributeError:
            pass
        param = getattr(env, "automation_parameter", None)
        return {
            "envelope_index": envelope_index,
            "parameter_name": param.name if param else None,
            "points": points,
        }

    def _cmd_clear_clip_envelope(self, params):
        """Clear all automation events from an envelope by index."""
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        envelope_index = int(params["envelope_index"])
        def fn():
            try:
                env = clip.automation_envelopes[envelope_index]
                env.clear_all_envelopes()
            except AttributeError:
                raise RuntimeError("clear_all_envelopes not available in this Live version")
        self._run_on_main_thread(fn)
        return {}

    def _cmd_insert_clip_envelope_point(self, params):
        """Insert a single automation point. time in beats, value is the parameter value."""
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        envelope_index = int(params["envelope_index"])
        time = float(params["time"])
        value = float(params["value"])
        def fn():
            try:
                env = clip.automation_envelopes[envelope_index]
                env.insert_step(time, 0.0, value)
            except AttributeError:
                raise RuntimeError("insert_step not available in this Live version")
        self._run_on_main_thread(fn)
        return {"time": time, "value": value}

    def _cmd_set_clip_envelope_points(self, params):
        """Replace all automation points in a clip envelope atomically (clear then insert all)."""
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        envelope_index = int(params["envelope_index"])
        points = params.get("points", [])
        def fn():
            try:
                env = clip.automation_envelopes[envelope_index]
            except (AttributeError, IndexError) as e:
                raise RuntimeError("Cannot access envelope {}: {}".format(envelope_index, e))
            try:
                env.clear_all_envelopes()
            except AttributeError:
                pass
            for pt in points:
                try:
                    env.insert_step(float(pt["time"]), 0.0, float(pt["value"]))
                except AttributeError:
                    raise RuntimeError("insert_step not available in this Live version")
        self._run_on_main_thread(fn)
        return {"point_count": len(points)}

    # -------------------------------------------------------------------------
    # Arrangement automation
    # -------------------------------------------------------------------------

    def _cmd_get_arrangement_automation_targets(self, params):
        """Return all automatable parameters for a track/device combination."""
        track_index = int(params["track_index"])
        device_index = params.get("device_index")
        track = self._get_track(track_index)
        result = []
        if device_index is not None:
            device = self._get_device(track_index, int(device_index))
            for i, p in enumerate(device.parameters):
                result.append({
                    "parameter_index": i,
                    "name": p.name,
                    "original_name": getattr(p, "original_name", p.name),
                    "value": p.value,
                    "min": p.min,
                    "max": p.max,
                    "is_quantized": p.is_quantized,
                })
            return {"parameters": result, "device_name": device.name}
        # No device_index — return mixer parameters
        mixer = track.mixer_device
        for i, p in enumerate(mixer.parameters):
            result.append({
                "parameter_index": i,
                "name": p.name,
                "original_name": getattr(p, "original_name", p.name),
                "value": p.value,
                "min": p.min,
                "max": p.max,
                "is_quantized": p.is_quantized,
            })
        return {"parameters": result, "device_name": "Mixer"}

    def _cmd_write_arrangement_automation(self, params):
        """Write automation points to an arrangement lane for a device parameter."""
        track_index = int(params["track_index"])
        device_index = params.get("device_index")
        parameter_index = int(params["parameter_index"])
        points = params.get("points", [])
        clear_range = bool(params.get("clear_range", False))

        track = self._get_track(track_index)

        if device_index is not None:
            device = self._get_device(track_index, int(device_index))
            parameters = list(device.parameters)
        else:
            parameters = list(track.mixer_device.parameters)
            device_index = None

        if parameter_index < 0 or parameter_index >= len(parameters):
            raise IndexError("parameter_index {} out of range".format(parameter_index))
        target_param = parameters[parameter_index]
        param_name = target_param.name

        def fn():
            if not hasattr(track, "automation_envelopes"):
                raise RuntimeError(
                    "Arrangement automation requires Live 9+. "
                    "track.automation_envelopes not available."
                )
            # Get or create the envelope for this parameter
            env = None
            if hasattr(track, "automation_envelope") and callable(track.automation_envelope):
                try:
                    env = track.automation_envelope(target_param)
                except Exception:
                    env = None
            if env is None:
                for candidate in track.automation_envelopes:
                    try:
                        if candidate.automation_parameter == target_param:
                            env = candidate
                            break
                    except Exception:
                        continue
            if env is None:
                raise RuntimeError(
                    "Could not get or create arrangement automation envelope "
                    "for parameter '{}'.".format(param_name)
                )
            if clear_range and points:
                times = [float(pt["time"]) for pt in points]
                start_time = min(times)
                end_time = max(times)
                try:
                    env.clear_envelope(start_time, end_time - start_time)
                except AttributeError:
                    pass
            for pt in points:
                try:
                    env.insert_step(float(pt["time"]), 0.0, float(pt["value"]))
                except AttributeError:
                    raise RuntimeError("insert_step not available in this Live version")
            return len(points)

        points_written = self._run_on_main_thread(fn)
        return {
            "points_written": points_written,
            "parameter_name": param_name,
            "track_index": track_index,
            "device_index": device_index,
        }

    # -------------------------------------------------------------------------
    # Device (read)
    # -------------------------------------------------------------------------

    def _cmd_get_devices(self, params):
        track = self._resolve_track(int(params["track_index"]), bool(params.get("is_return_track", False)))
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

    def _cmd_get_device_parameters(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        result = []
        for i, p in enumerate(device.parameters):
            result.append({
                "index": i,
                "name": p.name,
                "value": p.value,
                "min": p.min,
                "max": p.max,
                "is_quantized": p.is_quantized,
                "value_string": str(p),
                "is_enabled": p.is_enabled,
                "original_name": p.original_name,
            })
        return {"name": device.name, "class_name": device.class_name, "parameters": result}

    # -------------------------------------------------------------------------
    # Device (write)
    # -------------------------------------------------------------------------

    def _cmd_set_device_parameter(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        param_index = int(params["parameter_index"])
        parameters = list(device.parameters)
        if param_index < 0 or param_index >= len(parameters):
            raise IndexError("parameter_index {} out of range".format(param_index))
        param = parameters[param_index]
        val = float(params["value"])
        def fn():
            param.value = val
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_device_parameter_human(self, params):
        """
        Set a device parameter using human-readable units.
        Accepts 'hz' for frequency (clamped to param range), 'ms' for time,
        or 'normalized' to pass through a raw 0-1 value.
        'db' is NOT supported — use 'normalized' instead.
        Raises ValueError for unsupported units.
        """
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        param_index = int(params["parameter_index"])
        parameters = list(device.parameters)
        if param_index < 0 or param_index >= len(parameters):
            raise IndexError("parameter_index {} out of range".format(param_index))
        param = parameters[param_index]
        value = float(params["value"])
        unit = str(params.get("unit", "normalized")).lower()

        p_min = param.min
        p_max = param.max

        def clamp(v, lo, hi):
            return max(lo, min(hi, v))

        if unit == "hz":
            # Live stores frequency parameters in Hz directly.
            # Just clamp to the parameter's valid range.
            val = clamp(value, p_min, p_max)
        elif unit == "ms":
            # Linear ms mapping within param range (which is already in ms for attack/release)
            val = clamp(value, p_min, p_max)
        elif unit == "db":
            # Live's volume/gain parameters do not use a standard linear-amplitude curve.
            # Use 'normalized' and consult get_device_parameters to understand the range.
            raise ValueError(
                "Unit 'db' is not supported — Live's gain parameters use an internal curve. "
                "Use unit='normalized' with a value in [0.0, 1.0] instead, or use "
                "set_device_parameter with a raw value from get_device_parameters."
            )
        elif unit == "normalized":
            val = p_min + clamp(value, 0.0, 1.0) * (p_max - p_min)
        else:
            raise ValueError("Unrecognised unit '{}'. Valid units: 'hz', 'ms', 'normalized'".format(unit))

        def fn():
            param.value = val
        self._run_on_main_thread(fn)
        return {"value_set": val, "param_min": p_min, "param_max": p_max}

    def _cmd_set_device_on_off(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        enabled = bool(params["enabled"])
        def fn():
            device.parameters[0].value = float(enabled)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_device(self, params):
        track = self._resolve_track(int(params["track_index"]), bool(params.get("is_return_track", False)))
        device_index = int(params["device_index"])
        def fn():
            track.delete_device(device_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_move_device(self, params):
        """
        Reorder a device within the same track using duplicate + delete.
        Cross-track moves are not supported by the Live Python API.
        """
        track_index = int(params["track_index"])
        device_index = int(params["device_index"])
        is_return = bool(params.get("is_return_track", False))
        target_track_index = int(params.get("target_track_index", track_index))

        if target_track_index != track_index:
            raise RuntimeError(
                "Cross-track device move is not supported by the Live Python API. "
                "Use delete_device() + load_browser_item() to recreate the device on the target track."
            )

        def fn():
            track = self._resolve_track(track_index, is_return)
            if device_index >= len(list(track.devices)):
                raise IndexError("device_index {} out of range".format(device_index))
            track.duplicate_device(device_index)
            # Duplicate lands at device_index+1; delete original at device_index
            track.delete_device(device_index)

        self._run_on_main_thread(fn)
        return {"track_index": track_index, "device_index": device_index}

    # -------------------------------------------------------------------------
    # Scenes
    # -------------------------------------------------------------------------

    def _cmd_get_scenes(self, params):
        result = []
        for i, scene in enumerate(self._song.scenes):
            result.append({
                "index": i,
                "name": scene.name,
                "color": self._color(scene),
                "tempo": scene.tempo if hasattr(scene, "tempo") else None,
                "tempo_enabled": scene.tempo_enabled if hasattr(scene, "tempo_enabled") else False,
                "time_signature_numerator": scene.time_signature_numerator if hasattr(scene, "time_signature_numerator") else None,
                "time_signature_denominator": scene.time_signature_denominator if hasattr(scene, "time_signature_denominator") else None,
                "time_signature_enabled": scene.time_signature_enabled if hasattr(scene, "time_signature_enabled") else False,
            })
        return result

    def _cmd_get_scene_info(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        return {
            "name": scene.name,
            "color": self._color(scene),
            "tempo": scene.tempo if hasattr(scene, "tempo") else None,
            "tempo_enabled": scene.tempo_enabled if hasattr(scene, "tempo_enabled") else False,
            "time_signature_numerator": scene.time_signature_numerator if hasattr(scene, "time_signature_numerator") else None,
            "time_signature_denominator": scene.time_signature_denominator if hasattr(scene, "time_signature_denominator") else None,
            "time_signature_enabled": scene.time_signature_enabled if hasattr(scene, "time_signature_enabled") else False,
        }

    def _cmd_create_scene(self, params):
        index = int(params.get("index", -1))
        def fn():
            self._song.create_scene(index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_delete_scene(self, params):
        scene_index = int(params["scene_index"])
        def fn():
            self._song.delete_scene(scene_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_duplicate_scene(self, params):
        scene_index = int(params["scene_index"])
        def fn():
            self._song.duplicate_scene(scene_index)
        self._run_on_main_thread(fn)
        return {}

    def _cmd_fire_scene(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        def fn():
            scene.fire()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_name(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        name = str(params["name"])
        def fn():
            scene.name = name
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_color(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        color = int(params["color"])
        def fn():
            scene.color = color
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_tempo(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        def fn():
            if "tempo" in params:
                scene.tempo = float(params["tempo"])
            if "tempo_enabled" in params:
                scene.tempo_enabled = bool(params["tempo_enabled"])
        self._run_on_main_thread(fn)
        return {}

    def _cmd_set_scene_time_signature(self, params):
        scene = self._get_scene(int(params["scene_index"]))
        def fn():
            if "numerator" in params:
                scene.time_signature_numerator = int(params["numerator"])
            if "denominator" in params:
                scene.time_signature_denominator = int(params["denominator"])
            if "enabled" in params:
                scene.time_signature_enabled = bool(params["enabled"])
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Clip (additional operations)
    # -------------------------------------------------------------------------

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

    def _cmd_apply_note_modifications(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        modifications = params.get("notes", [])
        def fn():
            existing = clip.get_notes(0, 0, clip.length, 128)
            mod_map = {}
            for m in modifications:
                key = (int(m["pitch"]), float(m["start_time"]))
                mod_map[key] = m
            updated = []
            for note in existing:
                key = (note[0], note[1])
                if key in mod_map:
                    m = mod_map[key]
                    updated.append((
                        int(m.get("pitch", note[0])),
                        float(m.get("start_time", note[1])),
                        float(m.get("duration", note[2])),
                        int(m.get("velocity", note[3])),
                        bool(m.get("mute", note[4])),
                    ))
                else:
                    updated.append(note)
            clip.set_notes(tuple(updated))
        self._run_on_main_thread(fn)
        return {}

    def _cmd_select_all_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            clip.select_all_notes()
        self._run_on_main_thread(fn)
        return {}

    def _cmd_deselect_all_notes(self, params):
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        def fn():
            clip.deselect_all_notes()
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # Device (additional operations)
    # -------------------------------------------------------------------------

    def _cmd_get_device_info(self, params):
        return self._cmd_get_device_parameters(params)

    def _cmd_set_device_enabled(self, params):
        return self._cmd_set_device_on_off(params)

    def _cmd_duplicate_device(self, params):
        track = self._resolve_track(int(params["track_index"]), bool(params.get("is_return_track", False)))
        device_index = int(params["device_index"])
        def fn():
            track.duplicate_device(device_index)
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # MixerDevice
    # -------------------------------------------------------------------------

    def _cmd_get_mixer_device(self, params):
        track = self._get_track(int(params["track_index"]))
        mixer = track.mixer_device
        result = {
            "volume": mixer.volume.value,
            "panning": mixer.panning.value,
        }
        try:
            result["sends"] = [s.value for s in mixer.sends]
        except AttributeError:
            result["sends"] = []
        try:
            result["crossfade_assign"] = int(mixer.crossfade_assign)
        except AttributeError:
            pass
        return result

    # -------------------------------------------------------------------------
    # RackDevice
    # -------------------------------------------------------------------------

    def _cmd_get_rack_chains(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        try:
            chains = device.chains
        except AttributeError:
            raise RuntimeError("Device does not support chains (not a Rack)")
        result = []
        for i, chain in enumerate(chains):
            result.append({
                "index": i,
                "name": chain.name,
                "mute": chain.mute,
                "solo": self._safe(chain, "solo", False),
            })
        return result

    def _cmd_get_rack_drum_pads(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        try:
            drum_pads = device.drum_pads
        except AttributeError:
            raise RuntimeError("Device does not support drum pads (not a Drum Rack)")
        result = []
        for pad in drum_pads:
            try:
                if not list(pad.chains):
                    continue
            except AttributeError:
                continue
            result.append({
                "note": pad.note,
                "name": pad.name,
                "mute": pad.mute,
                "solo": self._safe(pad, "solo", False),
            })
        return result

    def _cmd_randomize_rack_macros(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        def fn():
            try:
                device.randomize_macros()
            except AttributeError:
                raise RuntimeError("Device does not support randomize_macros (not a Rack)")
        self._run_on_main_thread(fn)
        return {}

    def _cmd_store_rack_variation(self, params):
        device = self._get_device(int(params["track_index"]), int(params["device_index"]), bool(params.get("is_return_track", False)))
        def fn():
            try:
                device.store_variation()
            except AttributeError:
                raise RuntimeError("Device does not support store_variation (not a Rack)")
        self._run_on_main_thread(fn)
        return {}

    # -------------------------------------------------------------------------
    # GroovePool
    # -------------------------------------------------------------------------

    def _cmd_get_grooves(self, params):
        try:
            groove_pool = self._song.groove_pool
            grooves = groove_pool.grooves
        except AttributeError:
            return []
        result = []
        for i, groove in enumerate(grooves):
            result.append({
                "index": i,
                "name": groove.name,
                "base": self._safe(groove, "base", None),
                "quantization": self._safe(groove, "quantization", None),
                "timing": self._safe(groove, "timing", None),
                "random": self._safe(groove, "random", None),
                "velocity": self._safe(groove, "velocity", None),
            })
        return result

    def _cmd_extract_groove_from_clip(self, params):
        """
        Extract timing/velocity feel from a MIDI clip into the groove pool.
        Requires Live 10+ (Song.create_midi_clip_groove).
        """
        clip = self._get_clip(int(params["track_index"]), int(params["slot_index"]))
        groove_name = str(params.get("groove_name", "Extracted Groove"))

        def fn():
            if not hasattr(self._song, "create_midi_clip_groove"):
                raise RuntimeError(
                    "extract_groove_from_clip requires Live 10+ with create_midi_clip_groove. "
                    "Use analyze_clip_feel() to read groove characteristics instead."
                )
            try:
                groove = self._song.create_midi_clip_groove(clip)
                if hasattr(groove, "name"):
                    groove.name = groove_name
                return {
                    "method": "native",
                    "groove_name": groove_name,
                    "groove_count": len(list(self._song.groove_pool.grooves)),
                }
            except Exception as e:
                raise RuntimeError("create_midi_clip_groove failed: {}".format(e))

        return self._run_on_main_thread(fn)

    # -------------------------------------------------------------------------
    # Browser
    # -------------------------------------------------------------------------

    def _cmd_get_browser_tree(self, params):
        try:
            browser = self.application().browser
        except AttributeError:
            raise RuntimeError("Browser not supported in this version of Ableton Live")
        category_type = params.get("category_type", "all")
        category_map = {
            "instruments": "instruments",
            "sounds": "sounds",
            "drums": "drums",
            "audio_effects": "audio_effects",
            "midi_effects": "midi_effects",
        }

        def _iter_items(items, depth):
            result = []
            for item in items:
                entry = {
                    "name": item.name,
                    "is_folder": item.is_folder,
                    "uri": self._safe(item, "uri", None),
                }
                if depth > 0 and item.is_folder:
                    try:
                        entry["children"] = _iter_items(item.children, depth - 1)
                    except AttributeError:
                        pass
                result.append(entry)
            return result

        if category_type == "all":
            roots = []
            for attr in ("instruments", "sounds", "drums", "audio_effects", "midi_effects"):
                try:
                    root = getattr(browser, attr)
                    roots.append({
                        "name": attr,
                        "children": _iter_items(root.children, 1),
                    })
                except AttributeError:
                    pass
            return {"tree": roots}
        attr = category_map.get(category_type)
        if attr is None:
            raise ValueError("Unknown category_type: {}".format(category_type))
        try:
            root = getattr(browser, attr)
        except AttributeError:
            raise RuntimeError("Category '{}' not supported by browser".format(category_type))
        return {"tree": _iter_items(root.children, 1)}

    def _cmd_get_browser_items_at_path(self, params):
        try:
            browser = self.application().browser
        except AttributeError:
            raise RuntimeError("Browser not supported in this version of Ableton Live")
        path = str(params["path"])
        segments = [s for s in path.split("/") if s]
        if not segments:
            raise ValueError("path must not be empty")
        attr_map = {
            "instruments": "instruments",
            "sounds": "sounds",
            "drums": "drums",
            "audio_effects": "audio_effects",
            "midi_effects": "midi_effects",
        }
        root_attr = attr_map.get(segments[0])
        if root_attr is None:
            raise ValueError("Unknown root category: {}. Must be one of: {}".format(
                segments[0], ", ".join(attr_map)))
        try:
            node = getattr(browser, root_attr)
        except AttributeError:
            raise RuntimeError("Category '{}' not supported by browser".format(segments[0]))
        for segment in segments[1:]:
            found = None
            try:
                for child in node.children:
                    if child.name == segment:
                        found = child
                        break
            except AttributeError:
                pass
            if found is None:
                raise RuntimeError("Path segment '{}' not found under '{}'".format(
                    segment, getattr(node, "name", "?")))
            node = found
        items = []
        try:
            for item in node.children:
                items.append({
                    "name": item.name,
                    "is_folder": item.is_folder,
                    "uri": self._safe(item, "uri", None),
                })
        except AttributeError:
            pass
        return {"items": items}

    def _cmd_load_browser_item(self, params):
        try:
            browser = self.application().browser
        except AttributeError:
            raise RuntimeError("Browser not supported in this version of Ableton Live")
        uri = str(params["uri"])
        track_index = int(params.get("track_index", 0))
        is_return = bool(params.get("is_return_track", False))
        track = self._resolve_track(track_index, is_return)

        def _find_item(node, target_uri):
            try:
                children = node.children
            except AttributeError:
                return None
            for child in children:
                child_uri = getattr(child, "uri", None)
                if child_uri and str(child_uri) == target_uri:
                    return child
                if child.is_folder:
                    found = _find_item(child, target_uri)
                    if found is not None:
                        return found
            return None

        found_item = None
        for attr in ("instruments", "sounds", "drums", "audio_effects", "midi_effects", "plugins", "clips", "samples"):
            try:
                root = getattr(browser, attr)
                found_item = _find_item(root, uri)
                if found_item is not None:
                    break
            except AttributeError:
                continue

        if found_item is None:
            raise RuntimeError("No browser item found with URI: {}".format(uri))

        def fn():
            self._song.view.selected_track = track
            try:
                browser.load_item(found_item)
            except AttributeError:
                raise RuntimeError("browser.load_item() not supported in this version of Ableton Live")

        self._run_on_main_thread(fn)
        return {}

    def _cmd_add_native_device(self, params):
        """Insert a native Ableton device onto a track by searching the browser by name or URI fragment."""
        track_index = int(params["track_index"])
        device_name = str(params["device_name"]).lower()
        is_return = bool(params.get("is_return_track", False))
        track = self._resolve_track(track_index, is_return)
        try:
            browser = self.application().browser
        except AttributeError:
            raise RuntimeError("Browser not supported in this version of Ableton Live")

        def _find_by_name(node):
            try:
                children = node.children
            except AttributeError:
                return None
            for child in children:
                try:
                    if device_name in child.name.lower():
                        return child
                    uri = str(getattr(child, "uri", "") or "")
                    if device_name in uri.lower():
                        return child
                    if child.is_folder:
                        found = _find_by_name(child)
                        if found is not None:
                            return found
                except AttributeError:
                    continue
            return None

        found_item = None
        for category_attr in ("instruments", "audio_effects", "midi_effects", "plugins"):
            try:
                category = getattr(browser, category_attr)
                found_item = _find_by_name(category)
                if found_item is not None:
                    break
            except AttributeError:
                continue

        if found_item is None:
            raise RuntimeError(
                "Device '{}' not found in browser. Try names like: "
                "'Compressor', 'Glue Compressor', 'EQ Eight', 'Limiter', "
                "'Multiband Dynamics', 'Saturator', 'Auto Filter', 'Reverb', "
                "'Delay', 'Utility', 'Drum Rack', 'Instrument Rack'".format(params["device_name"])
            )

        def fn():
            self._song.view.selected_track = track
            browser.load_item(found_item)

        self._run_on_main_thread(fn)
        return {"device_name": found_item.name}

    # -------------------------------------------------------------------------
    # Protocol versioning
    # -------------------------------------------------------------------------

    def _cmd_get_protocol_version(self, params):
        return {"protocol_version": self.PROTOCOL_VERSION}

    # -------------------------------------------------------------------------
    # Capability / context discovery
    # -------------------------------------------------------------------------

    def _cmd_get_selected_context(self, params):
        """Return the currently selected track, scene, clip slot, and appointed device."""
        view = self._song.view
        context = {}

        # Selected track
        try:
            sel_track = view.selected_track
            all_tracks = list(self._song.tracks)
            try:
                track_idx = all_tracks.index(sel_track)
            except ValueError:
                track_idx = -1
            context["selected_track"] = {"index": track_idx, "name": sel_track.name}
        except AttributeError:
            context["selected_track"] = None

        # Selected scene
        try:
            sel_scene = view.selected_scene
            all_scenes = list(self._song.scenes)
            try:
                scene_idx = all_scenes.index(sel_scene)
            except ValueError:
                scene_idx = -1
            context["selected_scene"] = {"index": scene_idx, "name": sel_scene.name}
        except AttributeError:
            context["selected_scene"] = None

        # Detail clip (clip open in Detail View)
        try:
            detail_clip = view.detail_clip
            if detail_clip is not None:
                context["detail_clip"] = {"name": detail_clip.name, "is_midi_clip": detail_clip.is_midi_clip}
            else:
                context["detail_clip"] = None
        except AttributeError:
            context["detail_clip"] = None

        # Appointed device
        try:
            device = self._song.appointed_device
            if device is not None:
                all_tracks = list(self._song.tracks)
                master = self._song.master_track
                found = None
                for ti, t in enumerate(all_tracks):
                    for di, d in enumerate(t.devices):
                        if d == device:
                            found = {"track_index": ti, "device_index": di, "name": device.name, "class_name": device.class_name}
                            break
                    if found:
                        break
                if not found:
                    for di, d in enumerate(master.devices):
                        if d == device:
                            found = {"track_index": -1, "device_index": di, "name": device.name, "class_name": device.class_name}
                            break
                context["appointed_device"] = found
            else:
                context["appointed_device"] = None
        except AttributeError:
            context["appointed_device"] = None

        return context

    def _cmd_get_session_snapshot(self, params):
        """
        Return a full normalised snapshot of the current session state.
        Includes song info, all tracks (with mixer + device list), return tracks,
        master track, and scene list. Does NOT include clip notes (too large).
        """
        s = self._song
        snapshot = {}

        # Song-level
        snapshot["tempo"] = s.tempo
        snapshot["time_signature"] = "{}/{}".format(s.signature_numerator, s.signature_denominator)
        snapshot["is_playing"] = s.is_playing
        for attr in ("exclusive_arm", "exclusive_solo", "select_on_launch", "groove_amount", "swing_amount",
                     "scale_mode", "scale_name", "root_note"):
            try:
                snapshot[attr] = getattr(s, attr)
            except AttributeError:
                pass

        # Tracks
        tracks = []
        for i, track in enumerate(s.tracks):
            mixer = track.mixer_device
            try:
                arm_val = track.arm
            except (AttributeError, RuntimeError):
                arm_val = False
            t = {
                "index": i,
                "name": track.name,
                "color": self._color(track),
                "mute": track.mute,
                "solo": track.solo,
                "arm": arm_val,
                "volume": mixer.volume.value,
                "pan": mixer.panning.value,
                "sends": [send.value for send in mixer.sends],
                "is_midi_track": track.has_midi_input,
                "is_audio_track": track.has_audio_input,
                "device_count": len(list(track.devices)),
                "devices": [{"index": di, "name": d.name, "class_name": d.class_name, "is_active": d.is_active} for di, d in enumerate(track.devices)],
                "clip_count": sum(1 for slot in track.clip_slots if slot.has_clip),
            }
            tracks.append(t)
        snapshot["tracks"] = tracks

        # Return tracks
        returns = []
        for i, track in enumerate(s.return_tracks):
            mixer = track.mixer_device
            returns.append({
                "index": i,
                "name": track.name,
                "volume": mixer.volume.value,
                "pan": mixer.panning.value,
                "mute": track.mute,
            })
        snapshot["return_tracks"] = returns

        # Master track
        master = s.master_track
        master_mixer = master.mixer_device
        snapshot["master_track"] = {
            "volume": master_mixer.volume.value,
            "pan": master_mixer.panning.value,
            "devices": [{"index": di, "name": d.name, "class_name": d.class_name, "is_active": d.is_active} for di, d in enumerate(master.devices)],
        }

        # Scenes
        snapshot["scenes"] = [{"index": i, "name": scene.name} for i, scene in enumerate(s.scenes)]
        snapshot["scene_count"] = len(snapshot["scenes"])
        snapshot["track_count"] = len(tracks)

        return snapshot

    # -------------------------------------------------------------------------
    # Missing media
    # -------------------------------------------------------------------------

    def _cmd_get_missing_media(self, params):
        """Return all clips with missing/offline audio files."""
        s = self._song
        all_tracks = list(s.tracks) + list(s.return_tracks)
        missing = []
        total_checked = 0
        for track_index, track in enumerate(all_tracks):
            is_return = track_index >= len(list(s.tracks))
            display_index = track_index - len(list(s.tracks)) if is_return else track_index
            for slot_index, slot in enumerate(track.clip_slots):
                if not slot.has_clip:
                    continue
                clip = slot.clip
                if not clip.is_audio_clip:
                    continue
                total_checked += 1
                try:
                    file_path = clip.file_path
                except AttributeError:
                    file_path = ""
                if not file_path or not os.path.exists(file_path):
                    missing.append({
                        "track_index": track_index,
                        "track_name": track.name,
                        "clip_index": slot_index,
                        "clip_name": clip.name,
                        "sample_path": file_path,
                        "status": "missing" if file_path else "no_path",
                        "is_return_track": is_return,
                    })
        return {"missing": missing, "total_checked": total_checked}

    def _cmd_search_missing_media(self, params):
        """Search folders to relink missing audio samples."""
        search_folders = params.get("search_folders", [])
        missing_result = self._cmd_get_missing_media({})
        missing_clips = missing_result.get("missing", [])

        relinked = []
        still_missing = []

        # Build a filename→path index up front to avoid repeated os.walk calls
        filename_index = {}
        for folder in search_folders:
            try:
                for root, _dirs, files in os.walk(folder):
                    for fname in files:
                        if fname not in filename_index:
                            filename_index[fname] = os.path.join(root, fname)
            except (OSError, IOError):
                pass  # skip inaccessible or non-existent folders

        s = self._song
        all_tracks = list(s.tracks) + list(s.return_tracks)

        for entry in missing_clips:
            track_index = entry["track_index"]
            slot_index = entry["clip_index"]
            original_path = entry["sample_path"]
            filename = os.path.basename(original_path) if original_path else ""

            if not filename:
                still_missing.append({
                    "sample_name": "",
                    "original_path": original_path,
                    "track_index": track_index,
                    "clip_index": slot_index,
                })
                continue

            found_path = filename_index.get(filename)

            if found_path:
                track = all_tracks[track_index]
                slot = list(track.clip_slots)[slot_index]
                clip = slot.clip
                new_path = found_path

                def _relink(c=clip, p=new_path):
                    try:
                        c.file_path = p
                    except AttributeError:
                        pass

                self._run_on_main_thread(_relink)
                relinked.append({
                    "sample_name": filename,
                    "old_path": original_path,
                    "new_path": new_path,
                    "track_index": track_index,
                    "clip_index": slot_index,
                })
            else:
                still_missing.append({
                    "sample_name": filename,
                    "original_path": original_path,
                    "track_index": track_index,
                    "clip_index": slot_index,
                })

        return {
            "relinked": relinked,
            "still_missing": still_missing,
            "relinked_count": len(relinked),
            "still_missing_count": len(still_missing),
            "searched_folders": search_folders,
        }
