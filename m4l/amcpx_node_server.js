/**
 * amcpx_node_server.js
 * Node for Max — AMCPX Bridge TCP server
 * Runs inside node.script in AMCPX_Bridge.maxpat
 *
 * Uses max-api to call back into Live's LOM via Max message passing.
 * Opens a TCP server on port 9878 using Node's built-in net module.
 *
 * Protocol: 4-byte big-endian length prefix + UTF-8 JSON body
 */

const maxApi = require("max-api");
const net = require("net");

const PORT = 9878;
const VERSION = "2.0.0";
const API_TIMEOUT_MS = 5000;
const MAX_MESSAGE_SIZE_BYTES = 10 * 1024 * 1024;

maxApi.post(`AMCPX Bridge starting on port ${PORT}...`);

// ---------------------------------------------------------------------------
// LiveAPI helpers — outlet/handler RPC bridge to lom_bridge.js (Max js object)
//
// Node sends:  live_get / live_getcount / live_call  out of outlet 0
// Max routes the message to lom_bridge.js which uses LiveAPI to query the LOM
// and sends back:  live_result <id> [<value>...]  or  live_error <id> <msg>
// ---------------------------------------------------------------------------

let _reqId = 0;
const _pending = new Map();

maxApi.addHandler("live_result", (...args) => {
    const id = args[0];
    const values = args.slice(1);
    const entry = _pending.get(id);
    if (entry) {
        _pending.delete(id);
        clearTimeout(entry.timeout);
        entry.resolve(values.length === 1 ? values[0] : values);
    }
});

maxApi.addHandler("live_error", (...args) => {
    const id = args[0];
    const msg = args.slice(1).join(" ");
    const entry = _pending.get(id);
    if (entry) {
        _pending.delete(id);
        clearTimeout(entry.timeout);
        entry.reject(new Error(msg));
    }
});

function liveRPC(type, ...args) {
    return new Promise((resolve, reject) => {
        _reqId = (_reqId >= Number.MAX_SAFE_INTEGER) ? 1 : _reqId + 1;
        const id = _reqId;
        const timeout = setTimeout(() => {
            _pending.delete(id);
            reject(new Error(`Timeout: ${type} ${args.join(" ")}`));
        }, API_TIMEOUT_MS);
        _pending.set(id, { resolve, reject, timeout });
        maxApi.outlet(type, id, ...args);
    });
}

async function liveGet(path, prop) {
    return liveRPC("live_get", path, prop);
}

async function liveGetCount(path, prop) {
    return liveRPC("live_getcount", path, prop);
}

async function liveCall(path, method, ...args) {
    return liveRPC("live_call", path, method, ...args);
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

async function handleCommand(command, params) {
    switch (command) {
        case "ping":
            return { status: "pong", version: VERSION };

        case "get_arrangement_clips":
            return await getArrangementClips(params);

        case "get_arrangement_clip_info":
            return await getArrangementClipInfo(params);

        case "get_arrangement_clip_notes":
            return await getArrangementClipNotes(params);

        case "set_arrangement_clip_notes":
            return await setArrangementClipNotes(params);

        case "get_arrangement_overview":
            return await getArrangementOverview(params);

        case "get_detail_clip":
            return await getDetailClip(params);

        case "find_clip_by_name":
            return await findClipByName(params);

        case "find_clips_at_bar":
            return await findClipsAtBar(params);

        default:
            throw new Error(`Unknown command: ${command}`);
    }
}

// ---------------------------------------------------------------------------
// get_arrangement_clips
// ---------------------------------------------------------------------------

async function getArrangementClips(params) {
    const trackFilter = (params.track_index !== undefined && params.track_index !== null)
        ? parseInt(params.track_index) : -1;

    const trackCount = await liveGetCount("live_set", "tracks");
    const results = [];

    for (let t = 0; t < trackCount; t++) {
        if (trackFilter >= 0 && t !== trackFilter) continue;

        const trackPath = `live_set tracks ${t}`;
        const trackName = await liveGet(trackPath, "name");
        const clipCount = await liveGetCount(trackPath, "arrangement_clips");

        for (let c = 0; c < clipCount; c++) {
            try {
                const clipPath = `live_set tracks ${t} arrangement_clips ${c}`;
                const [name, startTime, endTime, length, isMidi, color, muted, looping] = await Promise.all([
                    liveGet(clipPath, "name"),
                    liveGet(clipPath, "start_time"),
                    liveGet(clipPath, "end_time"),
                    liveGet(clipPath, "length"),
                    liveGet(clipPath, "is_midi_clip"),
                    liveGet(clipPath, "color"),
                    liveGet(clipPath, "muted"),
                    liveGet(clipPath, "looping"),
                ]);

                results.push({
                    track_index: t,
                    track_name: String(trackName),
                    clip_index: c,
                    clip_name: String(name),
                    start_time: parseFloat(startTime) || 0,
                    end_time: parseFloat(endTime) || 0,
                    length: parseFloat(length) || 0,
                    is_midi_clip: isMidi === 1,
                    is_audio_clip: isMidi !== 1,
                    color: parseInt(color) || 0,
                    muted: muted === 1,
                    looping: looping === 1,
                    start_bar: Math.floor((parseFloat(startTime) || 0) / 4) + 1,
                    length_bars: (parseFloat(length) || 0) / 4.0,
                });
            } catch (e) {
                maxApi.post(`AMCPX Bridge: skipping clip ${c} on track ${t}: ${e.message}`);
            }
        }
    }

    return results;
}

// ---------------------------------------------------------------------------
// get_arrangement_clip_info
// ---------------------------------------------------------------------------

async function getArrangementClipInfo(params) {
    const trackIndex = parseInt(params.track_index);
    const clipIndex = parseInt(params.clip_index);

    const trackPath = `live_set tracks ${trackIndex}`;
    const clipCount = await liveGetCount(trackPath, "arrangement_clips");

    if (clipIndex < 0 || clipIndex >= clipCount) {
        throw new Error(`clip_index ${clipIndex} out of range (${clipCount} arrangement clips on track ${trackIndex})`);
    }

    const clipPath = `live_set tracks ${trackIndex} arrangement_clips ${clipIndex}`;
    const trackName = await liveGet(trackPath, "name");

    const [name, startTime, endTime, length, isMidi, color, muted, looping, loopStart, loopEnd] = await Promise.all([
        liveGet(clipPath, "name"),
        liveGet(clipPath, "start_time"),
        liveGet(clipPath, "end_time"),
        liveGet(clipPath, "length"),
        liveGet(clipPath, "is_midi_clip"),
        liveGet(clipPath, "color"),
        liveGet(clipPath, "muted"),
        liveGet(clipPath, "looping"),
        liveGet(clipPath, "loop_start"),
        liveGet(clipPath, "loop_end"),
    ]);

    const st = parseFloat(startTime) || 0;
    const len = parseFloat(length) || 0;

    return {
        track_index: trackIndex,
        track_name: String(trackName),
        clip_index: clipIndex,
        clip_name: String(name),
        start_time: st,
        end_time: parseFloat(endTime) || 0,
        length: len,
        is_midi_clip: isMidi === 1,
        color: parseInt(color) || 0,
        muted: muted === 1,
        looping: looping === 1,
        loop_start: parseFloat(loopStart) || 0,
        loop_end: parseFloat(loopEnd) || 0,
        start_bar: Math.floor(st / 4) + 1,
        length_bars: len / 4.0,
    };
}

// ---------------------------------------------------------------------------
// get_arrangement_clip_notes
// ---------------------------------------------------------------------------

async function getArrangementClipNotes(params) {
    const trackIndex = parseInt(params.track_index);
    const clipIndex = parseInt(params.clip_index);

    const trackPath = `live_set tracks ${trackIndex}`;
    const clipCount = await liveGetCount(trackPath, "arrangement_clips");

    if (clipIndex < 0 || clipIndex >= clipCount) {
        throw new Error(`clip_index ${clipIndex} out of range (${clipCount} arrangement clips on track ${trackIndex})`);
    }

    const clipPath = `live_set tracks ${trackIndex} arrangement_clips ${clipIndex}`;
    const isMidi = await liveGet(clipPath, "is_midi_clip");

    if (isMidi !== 1) {
        throw new Error(`Arrangement clip ${clipIndex} on track ${trackIndex} is not a MIDI clip`);
    }

    const clipName = await liveGet(clipPath, "name");
    const clipLength = parseFloat(await liveGet(clipPath, "length")) || 0;
    const startTime = parseFloat(await liveGet(clipPath, "start_time")) || 0;

    const rawNotes = await liveRPC("live_get_notes_extended", clipPath, 0, clipLength, 0, 128);

    const notes = [];
    if (rawNotes && rawNotes.length > 0) {
        const stride = 8;
        for (let i = 0; i + stride <= rawNotes.length; i += stride) {
            notes.push({
                pitch: parseInt(rawNotes[i]),
                start_time: parseFloat(rawNotes[i + 1]),
                duration: parseFloat(rawNotes[i + 2]),
                velocity: parseInt(rawNotes[i + 3]),
                mute: rawNotes[i + 4] === 1,
            });
        }
    }

    return {
        track_index: trackIndex,
        clip_index: clipIndex,
        clip_name: String(clipName),
        clip_start_time: startTime,
        clip_length: clipLength,
        notes,
        note_count: notes.length,
    };
}

// ---------------------------------------------------------------------------
// set_arrangement_clip_notes
// ---------------------------------------------------------------------------

async function setArrangementClipNotes(params) {
    const trackIndex = parseInt(params.track_index);
    const clipIndex = parseInt(params.clip_index);
    const notes = params.notes || [];

    const trackPath = `live_set tracks ${trackIndex}`;
    const clipCount = await liveGetCount(trackPath, "arrangement_clips");

    if (clipIndex < 0 || clipIndex >= clipCount) {
        throw new Error(`clip_index ${clipIndex} out of range (${clipCount} arrangement clips on track ${trackIndex})`);
    }

    const clipPath = `live_set tracks ${trackIndex} arrangement_clips ${clipIndex}`;
    const isMidi = await liveGet(clipPath, "is_midi_clip");
    if (isMidi !== 1) throw new Error("Clip is not a MIDI clip");

    const clipLength = parseFloat(await liveGet(clipPath, "length")) || 0;

    const noteArgs = [];
    for (const n of notes) {
        noteArgs.push(
            parseInt(n.pitch),
            parseFloat(n.start_time),
            parseFloat(n.duration),
            parseInt(n.velocity !== undefined ? n.velocity : 100),
            n.mute ? 1 : 0
        );
    }

    try {
        // Fast path: replace_all_notes is atomic (Live 11.1+).
        // For an empty note list we skip it and use the undo-step path below.
        if (notes.length > 0) {
            await liveCall(clipPath, "replace_all_notes", ...noteArgs);
        } else {
            // Wrap the clear-only case in an undo step so Live does not see
            // a transient zero-note state that could trigger auto-deletion.
            await liveCall("live_set", "begin_undo_step", "AMCPX set notes");
            try {
                await liveCall(clipPath, "remove_notes", 0, 0, clipLength, 128);
                await liveCall("live_set", "end_undo_step");
            } catch (eClear) {
                await liveCall("live_set", "end_undo_step").catch(() => {});
                throw eClear;
            }
        }
    } catch (e) {
        // replace_all_notes not available (Live ≤ 11.0) — fall back to the
        // wrapped remove + set pattern, guarded by a single undo step so
        // Live never processes the intermediate zero-note state.
        // Re-throw immediately for the clear-only path (no fallback needed).
        if (notes.length === 0) throw e;
        try {
            await liveCall("live_set", "begin_undo_step", "AMCPX set notes");
            await liveCall(clipPath, "remove_notes", 0, 0, clipLength, 128);
            await liveCall(clipPath, "set_notes", ...noteArgs);
            await liveCall("live_set", "end_undo_step");
        } catch (e2) {
            await liveCall("live_set", "end_undo_step").catch(() => {});
            throw e2;
        }
    }

    return { track_index: trackIndex, clip_index: clipIndex, note_count: notes.length };
}

// ---------------------------------------------------------------------------
// get_arrangement_overview
// ---------------------------------------------------------------------------

async function getArrangementOverview(params) {
    const clips = await getArrangementClips({});
    const tempo = parseFloat(await liveGet("live_set", "tempo")) || 120;

    if (clips.length === 0) {
        return { total_clips: 0, total_bars: 0, tracks_with_clips: 0, clips_per_track: [], tempo };
    }

    const trackMap = {};
    let maxBar = 0;

    for (const clip of clips) {
        const t = clip.track_index;
        if (!trackMap[t]) {
            trackMap[t] = { track_index: t, track_name: clip.track_name, clip_count: 0, first_bar: clip.start_bar, last_bar: clip.start_bar };
        }
        trackMap[t].clip_count++;
        const clipEndBar = Math.ceil(clip.start_bar + clip.length_bars);
        if (clipEndBar > trackMap[t].last_bar) trackMap[t].last_bar = clipEndBar;
        if (clipEndBar > maxBar) maxBar = clipEndBar;
    }

    const clipsPerTrack = Object.values(trackMap).sort((a, b) => a.track_index - b.track_index);

    return {
        total_clips: clips.length,
        total_bars: maxBar,
        tracks_with_clips: clipsPerTrack.length,
        clips_per_track: clipsPerTrack,
        tempo,
    };
}

// ---------------------------------------------------------------------------
// get_detail_clip
// ---------------------------------------------------------------------------

async function getDetailClip(params) {
    const clipPath = "live_set view detail_clip";
    const isMidi = await liveGet(clipPath, "is_midi_clip");
    const name = await liveGet(clipPath, "name");
    const length = parseFloat(await liveGet(clipPath, "length")) || 0;
    const startTime = parseFloat(await liveGet(clipPath, "start_time")) || 0;
    const endTime = parseFloat(await liveGet(clipPath, "end_time")) || 0;
    const looping = await liveGet(clipPath, "looping");
    const loopStart = parseFloat(await liveGet(clipPath, "loop_start")) || 0;
    const loopEnd = parseFloat(await liveGet(clipPath, "loop_end")) || 0;

    let notes = [];
    if (isMidi === 1) {
        const rawNotes = await liveRPC("live_get_notes_extended", clipPath, 0, length, 0, 128);
        if (rawNotes && rawNotes.length > 0) {
            const stride = 8;
            for (let i = 0; i + stride <= rawNotes.length; i += stride) {
                notes.push({
                    pitch: parseInt(rawNotes[i]),
                    start_time: parseFloat(rawNotes[i + 1]),
                    duration: parseFloat(rawNotes[i + 2]),
                    velocity: parseInt(rawNotes[i + 3]),
                    mute: rawNotes[i + 4] === 1,
                });
            }
        }
    }

    return {
        clip_name: String(name),
        start_time: startTime,
        end_time: endTime,
        length,
        is_midi_clip: isMidi === 1,
        looping: looping === 1,
        loop_start: loopStart,
        loop_end: loopEnd,
        notes,
        note_count: notes.length,
        start_bar: Math.floor(startTime / 4) + 1,
        length_bars: length / 4.0,
    };
}

// ---------------------------------------------------------------------------
// find_clip_by_name
// ---------------------------------------------------------------------------

async function findClipByName(params) {
    const nameQuery = String(params.name || "").toLowerCase();
    const trackFilter = (params.track_index !== undefined && params.track_index !== null)
        ? parseInt(params.track_index) : -1;

    const allClips = await getArrangementClips(trackFilter >= 0 ? { track_index: trackFilter } : {});
    const matches = allClips.filter(c => c.clip_name.toLowerCase().includes(nameQuery));

    return { clips: matches, total_found: matches.length };
}

// ---------------------------------------------------------------------------
// find_clips_at_bar
// ---------------------------------------------------------------------------

async function findClipsAtBar(params) {
    const bar = parseInt(params.bar) || 1;
    const trackFilter = (params.track_index !== undefined && params.track_index !== null)
        ? parseInt(params.track_index) : -1;

    const beats = (bar - 1) * 4;
    const allClips = await getArrangementClips(trackFilter >= 0 ? { track_index: trackFilter } : {});
    const matches = allClips.filter(c => c.start_time <= beats && beats < c.end_time);

    return { clips: matches, bar, beat_position: beats, total_found: matches.length };
}

// ---------------------------------------------------------------------------
// TCP Server — stream buffering approach (replaces broken recvExactly)
// ---------------------------------------------------------------------------

let server = null;

function handleConnection(socket) {
    socket.setNoDelay(true);
    maxApi.post(`AMCPX Bridge: client connected from ${socket.remoteAddress}`);

    let buf = Buffer.alloc(0);
    let processing = false;

    async function processBuffer() {
        if (processing) return;
        processing = true;

        try {
            while (true) {
                // Need at least 4 bytes for the length prefix
                if (buf.length < 4) break;

                const msgLen = buf.readUInt32BE(0);

                if (msgLen === 0 || msgLen > MAX_MESSAGE_SIZE_BYTES) {
                    maxApi.post(`AMCPX Bridge: invalid message length ${msgLen}, closing`);
                    socket.destroy();
                    break;
                }

                // Need 4 header bytes + msgLen body bytes
                if (buf.length < 4 + msgLen) break;

                // Extract the message
                const body = buf.slice(4, 4 + msgLen);
                buf = buf.slice(4 + msgLen);

                const jsonStr = body.toString("utf8");
                let request;
                try {
                    request = JSON.parse(jsonStr);
                } catch (e) {
                    const errResp = JSON.stringify({ status: "error", error: `Invalid JSON: ${e.message}` });
                    sendResponse(socket, errResp);
                    continue;
                }

                const command = request.command || "";
                const params = request.params || {};

                let response;
                try {
                    const result = await handleCommand(command, params);
                    response = JSON.stringify({ status: "ok", result });
                } catch (e) {
                    maxApi.post(`AMCPX Bridge error [${command}]: ${e.message}`);
                    response = JSON.stringify({ status: "error", error: e.message });
                }

                sendResponse(socket, response);
            }
        } finally {
            processing = false;
        }
    }

    socket.on("data", (chunk) => {
        buf = Buffer.concat([buf, chunk]);
        processBuffer().catch(err => maxApi.post(`AMCPX Bridge: processBuffer error: ${err.message}`));
    });

    socket.on("error", (err) => {
        if (err.code !== "ECONNRESET") {
            maxApi.post(`AMCPX Bridge: socket error: ${err.message}`);
        }
    });

    socket.on("close", () => {
        maxApi.post("AMCPX Bridge: client disconnected");
    });
}

function sendResponse(socket, jsonStr) {
    const respBuf = Buffer.from(jsonStr, "utf8");
    const lenBuf = Buffer.alloc(4);
    lenBuf.writeUInt32BE(respBuf.length, 0);
    socket.write(Buffer.concat([lenBuf, respBuf]));
}

function startServer() {
    if (server) {
        maxApi.post("AMCPX Bridge: server already running");
        return;
    }

    server = net.createServer(handleConnection);

    server.on("error", (err) => {
        maxApi.post(`AMCPX Bridge server error: ${err.message}`);
        if (err.code === "EADDRINUSE") {
            maxApi.post(`AMCPX Bridge: port ${PORT} already in use — is another instance running?`);
        }
        server = null;
    });

    server.listen(PORT, "127.0.0.1", () => {
        maxApi.post(`AMCPX Bridge: listening on port ${PORT} ✓`);
        maxApi.outlet("listening", PORT);
    });
}

// Auto-start when loaded
startServer();
