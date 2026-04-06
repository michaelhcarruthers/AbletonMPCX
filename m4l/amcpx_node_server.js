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
// LiveAPI helpers — call Max messages that use the live.path / LiveAPI system
// We use maxApi.call to invoke Max functions and get results back
// ---------------------------------------------------------------------------

/**
 * Call a Live API path and get a property value.
 * Uses Max's "live.object" style messaging via node.script outlet.
 */
async function liveGet(path, prop) {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error(`Timeout getting ${prop} from ${path}`)), API_TIMEOUT_MS);
        maxApi.call("live_get", path, prop)
            .then(result => { clearTimeout(timeout); resolve(result); })
            .catch(err => { clearTimeout(timeout); reject(err); });
    });
}

async function liveGetCount(path, prop) {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error(`Timeout getcount ${prop} from ${path}`)), API_TIMEOUT_MS);
        maxApi.call("live_getcount", path, prop)
            .then(result => { clearTimeout(timeout); resolve(result); })
            .catch(err => { clearTimeout(timeout); reject(err); });
    });
}

async function liveCall(path, method, ...args) {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error(`Timeout calling ${method} on ${path}`)), API_TIMEOUT_MS);
        maxApi.call("live_call", path, method, ...args)
            .then(result => { clearTimeout(timeout); resolve(result); })
            .catch(err => { clearTimeout(timeout); reject(err); });
    });
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

    const rawNotes = await liveCall(clipPath, "get_notes", 0, 0, clipLength, 128);

    const notes = [];
    if (rawNotes && rawNotes.length > 0) {
        for (let i = 0; i < rawNotes.length; i += 5) {
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
    await liveCall(clipPath, "remove_notes", 0, 0, clipLength, 128);

    if (notes.length > 0) {
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
        await liveCall(clipPath, "set_notes", ...noteArgs);
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
// TCP Server
// ---------------------------------------------------------------------------

let server = null;

function recvExactly(socket, n) {
    return new Promise((resolve, reject) => {
        let buf = Buffer.alloc(0);
        const onData = (chunk) => {
            buf = Buffer.concat([buf, chunk]);
            if (buf.length >= n) {
                socket.removeListener("data", onData);
                socket.removeListener("error", onError);
                resolve(buf.slice(0, n));
            }
        };
        const onError = (err) => {
            socket.removeListener("data", onData);
            reject(err);
        };
        socket.on("data", onData);
        socket.once("error", onError);
    });
}

async function handleConnection(socket) {
    socket.setNoDelay(true);
    maxApi.post(`AMCPX Bridge: client connected from ${socket.remoteAddress}`);

    try {
        while (true) {
            // Read 4-byte length prefix
            const header = await recvExactly(socket, 4);
            const msgLen = header.readUInt32BE(0);

            if (msgLen === 0 || msgLen > MAX_MESSAGE_SIZE_BYTES) {
                maxApi.post(`AMCPX Bridge: invalid message length ${msgLen}, closing`);
                break;
            }

            // Read body
            const body = await recvExactly(socket, msgLen);
            const jsonStr = body.toString("utf8");

            let request;
            try {
                request = JSON.parse(jsonStr);
            } catch (e) {
                const errResp = JSON.stringify({ status: "error", error: `Invalid JSON: ${e.message}` });
                const errBuf = Buffer.from(errResp, "utf8");
                const lenBuf = Buffer.alloc(4);
                lenBuf.writeUInt32BE(errBuf.length, 0);
                socket.write(Buffer.concat([lenBuf, errBuf]));
                continue;
            }

            const command = request.command || "";
            const params = request.params || {};

            let response;
            try {
                const result = await handleCommand(command, params);
                response = { status: "ok", result };
            } catch (e) {
                maxApi.post(`AMCPX Bridge error [${command}]: ${e.message}`);
                response = { status: "error", error: e.message };
            }

            const respStr = JSON.stringify(response);
            const respBuf = Buffer.from(respStr, "utf8");
            const lenBuf = Buffer.alloc(4);
            lenBuf.writeUInt32BE(respBuf.length, 0);
            socket.write(Buffer.concat([lenBuf, respBuf]));
        }
    } catch (e) {
        if (e.code !== "ECONNRESET" && e.message !== "read ECONNRESET") {
            maxApi.post(`AMCPX Bridge: connection error: ${e.message}`);
        }
    }

    socket.destroy();
    maxApi.post("AMCPX Bridge: client disconnected");
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
