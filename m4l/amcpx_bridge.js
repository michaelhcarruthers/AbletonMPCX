// amcpx_bridge.js
// Max for Live JS — full arrangement view access via LiveAPI
// Runs inside a js object in AMCPX_Bridge.amxd
// Protocol: 4-byte big-endian length prefix + UTF-8 JSON body (same as Remote Script)

autowatch = 1;
inlets = 1;
outlets = 1;

// ---------------------------------------------------------------------------
// Command dispatch
// ---------------------------------------------------------------------------

// Required Max JS stubs — called by the inlet when integers/floats arrive.
// The bridge uses only string (JSON) messages, so these are intentionally no-ops.
function msg_int(v) {}
function msg_float(v) {}

function anything() {
    // Called by the TCP server with raw data — handled via bang/list
}

function dispatch(json_str) {
    var request, response;
    try {
        request = JSON.parse(json_str);
    } catch(e) {
        return JSON.stringify({status: "error", error: "Invalid JSON: " + e.message});
    }

    var command = request.command || "";
    var params = request.params || {};

    try {
        var result = handle_command(command, params);
        response = {status: "ok", result: result};
    } catch(e) {
        response = {status: "error", error: e.message};
    }

    return JSON.stringify(response);
}

function handle_command(command, params) {
    switch(command) {
        case "get_arrangement_clips":
            return get_arrangement_clips(params);
        case "get_arrangement_clip_notes":
            return get_arrangement_clip_notes(params);
        case "get_arrangement_clip_info":
            return get_arrangement_clip_info(params);
        case "set_arrangement_clip_notes":
            return set_arrangement_clip_notes(params);
        case "get_arrangement_overview":
            return get_arrangement_overview(params);
        case "ping":
            return {status: "pong", version: "1.0.0"};
        default:
            throw new Error("Unknown command: " + command);
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function get_song() {
    return new LiveAPI("live_set");
}

function get_track(track_index) {
    return new LiveAPI("live_set tracks " + track_index);
}

function get_arrangement_clip_api(track_index, clip_index) {
    return new LiveAPI("live_set tracks " + track_index + " arrangement_clips " + clip_index);
}

// ---------------------------------------------------------------------------
// get_arrangement_clips
// Returns all arrangement clips across all tracks (or filtered by track_index)
// ---------------------------------------------------------------------------

function get_arrangement_clips(params) {
    var song = get_song();
    var track_count = song.getcount("tracks");
    var track_filter = (params.track_index !== undefined && params.track_index !== null)
                       ? parseInt(params.track_index) : -1;

    var results = [];

    for (var t = 0; t < track_count; t++) {
        if (track_filter >= 0 && t !== track_filter) continue;

        var track = get_track(t);
        var track_name = track.get("name");
        var clip_count = track.getcount("arrangement_clips");

        for (var c = 0; c < clip_count; c++) {
            try {
                var clip = get_arrangement_clip_api(t, c);
                var start_time = parseFloat(clip.get("start_time") || 0);
                var end_time = parseFloat(clip.get("end_time") || 0);
                var length = parseFloat(clip.get("length") || 0);
                var name = clip.get("name") || "";
                var is_midi = parseInt(clip.get("is_midi_clip") || 0) === 1;
                var color = parseInt(clip.get("color") || 0);
                var muted = parseInt(clip.get("muted") || 0) === 1;
                var looping = parseInt(clip.get("looping") || 0) === 1;

                results.push({
                    track_index: t,
                    track_name: String(track_name),
                    clip_index: c,
                    clip_name: String(name),
                    start_time: start_time,
                    end_time: end_time,
                    length: length,
                    is_midi_clip: is_midi,
                    is_audio_clip: !is_midi,
                    color: color,
                    muted: muted,
                    looping: looping,
                    start_bar: Math.floor(start_time / 4) + 1,
                    length_bars: length / 4.0
                });
            } catch(e) {
                // skip clips that error
            }
        }
    }

    return results;
}

// ---------------------------------------------------------------------------
// get_arrangement_clip_info
// Returns info for a single arrangement clip
// ---------------------------------------------------------------------------

function get_arrangement_clip_info(params) {
    var track_index = parseInt(params.track_index);
    var clip_index = parseInt(params.clip_index);

    var track = get_track(track_index);
    var clip_count = track.getcount("arrangement_clips");
    if (clip_index < 0 || clip_index >= clip_count) {
        throw new Error("clip_index " + clip_index + " out of range for track " + track_index + " (" + clip_count + " arrangement clips)");
    }

    var clip = get_arrangement_clip_api(track_index, clip_index);
    var track_name = track.get("name");

    return {
        track_index: track_index,
        track_name: String(track_name),
        clip_index: clip_index,
        clip_name: String(clip.get("name") || ""),
        start_time: parseFloat(clip.get("start_time") || 0),
        end_time: parseFloat(clip.get("end_time") || 0),
        length: parseFloat(clip.get("length") || 0),
        is_midi_clip: parseInt(clip.get("is_midi_clip") || 0) === 1,
        color: parseInt(clip.get("color") || 0),
        muted: parseInt(clip.get("muted") || 0) === 1,
        looping: parseInt(clip.get("looping") || 0) === 1,
        loop_start: parseFloat(clip.get("loop_start") || 0),
        loop_end: parseFloat(clip.get("loop_end") || 0),
        start_bar: Math.floor(parseFloat(clip.get("start_time") || 0) / 4) + 1,
        length_bars: parseFloat(clip.get("length") || 0) / 4.0
    };
}

// ---------------------------------------------------------------------------
// get_arrangement_clip_notes
// Returns all MIDI notes from a specific arrangement clip
// ---------------------------------------------------------------------------

function get_arrangement_clip_notes(params) {
    var track_index = parseInt(params.track_index);
    var clip_index = parseInt(params.clip_index);

    var track = get_track(track_index);
    var clip_count = track.getcount("arrangement_clips");
    if (clip_index < 0 || clip_index >= clip_count) {
        throw new Error("clip_index " + clip_index + " out of range (" + clip_count + " arrangement clips on track " + track_index + ")");
    }

    var clip = get_arrangement_clip_api(track_index, clip_index);
    var is_midi = parseInt(clip.get("is_midi_clip") || 0) === 1;
    if (!is_midi) {
        throw new Error("Arrangement clip " + clip_index + " on track " + track_index + " is not a MIDI clip");
    }

    var clip_name = String(clip.get("name") || "");
    var clip_length = parseFloat(clip.get("length") || 0);
    var start_time = parseFloat(clip.get("start_time") || 0);

    // get_notes returns: pitch, time, duration, velocity, mute (repeated)
    var raw_notes = clip.call("get_notes", 0, 0, clip_length, 128);

    var notes = [];
    if (raw_notes && raw_notes.length > 0) {
        // raw_notes is a flat array: [pitch, time, dur, vel, mute, pitch, time, ...]
        for (var i = 0; i < raw_notes.length; i += 5) {
            notes.push({
                pitch: parseInt(raw_notes[i]),
                start_time: parseFloat(raw_notes[i+1]),
                duration: parseFloat(raw_notes[i+2]),
                velocity: parseInt(raw_notes[i+3]),
                mute: raw_notes[i+4] === 1
            });
        }
    }

    return {
        track_index: track_index,
        clip_index: clip_index,
        clip_name: clip_name,
        clip_start_time: start_time,
        clip_length: clip_length,
        notes: notes,
        note_count: notes.length
    };
}

// ---------------------------------------------------------------------------
// set_arrangement_clip_notes
// Replace all MIDI notes in a specific arrangement clip
// ---------------------------------------------------------------------------

function set_arrangement_clip_notes(params) {
    var track_index = parseInt(params.track_index);
    var clip_index = parseInt(params.clip_index);
    var notes = params.notes || [];

    var track = get_track(track_index);
    var clip_count = track.getcount("arrangement_clips");
    if (clip_index < 0 || clip_index >= clip_count) {
        throw new Error("clip_index " + clip_index + " out of range (" + clip_count + " arrangement clips on track " + track_index + ")");
    }

    var clip = get_arrangement_clip_api(track_index, clip_index);
    var is_midi = parseInt(clip.get("is_midi_clip") || 0) === 1;
    if (!is_midi) {
        throw new Error("Clip is not a MIDI clip");
    }

    var clip_length = parseFloat(clip.get("length") || 0);

    // Remove all existing notes first
    clip.call("remove_notes", 0, 0, clip_length, 128);

    // Build flat array for set_notes: [pitch, time, dur, vel, mute, ...]
    if (notes.length > 0) {
        var note_args = [];
        for (var i = 0; i < notes.length; i++) {
            var n = notes[i];
            note_args.push(
                parseInt(n.pitch),
                parseFloat(n.start_time),
                parseFloat(n.duration),
                parseInt(n.velocity !== undefined ? n.velocity : 100),
                n.mute ? 1 : 0
            );
        }
        clip.call.apply(clip, ["set_notes"].concat(note_args));
    }

    return {
        track_index: track_index,
        clip_index: clip_index,
        note_count: notes.length
    };
}

// ---------------------------------------------------------------------------
// get_arrangement_overview
// High-level summary of all arrangement clips
// ---------------------------------------------------------------------------

function get_arrangement_overview(params) {
    var clips = get_arrangement_clips({});
    var song = get_song();
    var tempo = parseFloat(song.get("tempo") || 120);

    if (clips.length === 0) {
        return {
            total_clips: 0,
            total_bars: 0,
            tracks_with_clips: 0,
            clips_per_track: [],
            tempo: tempo
        };
    }

    var track_map = {};
    var max_bar = 0;

    for (var i = 0; i < clips.length; i++) {
        var clip = clips[i];
        var t = clip.track_index;
        if (!track_map[t]) {
            track_map[t] = {
                track_index: t,
                track_name: clip.track_name,
                clip_count: 0,
                first_bar: clip.start_bar,
                last_bar: clip.start_bar
            };
        }
        track_map[t].clip_count++;
        var clip_end_bar = Math.ceil(clip.start_bar + clip.length_bars);
        if (clip_end_bar > track_map[t].last_bar) track_map[t].last_bar = clip_end_bar;
        if (clip_end_bar > max_bar) max_bar = clip_end_bar;
    }

    var clips_per_track = [];
    for (var key in track_map) {
        clips_per_track.push(track_map[key]);
    }
    clips_per_track.sort(function(a, b) { return a.track_index - b.track_index; });

    return {
        total_clips: clips.length,
        total_bars: max_bar,
        tracks_with_clips: clips_per_track.length,
        clips_per_track: clips_per_track,
        tempo: tempo
    };
}
