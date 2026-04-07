/**
 * amcpx_observer_server.js
 * Node for Max — AMCPX Observer TCP server
 * Runs inside node.script in AMCPX_Observer.maxpat
 *
 * Uses max-api to receive state-change notifications from live.observer objects
 * and to call back into Live's LOM via Max message passing (lom_bridge.js).
 * Opens a TCP server on port 9879 using Node's built-in net module.
 *
 * Protocol: 4-byte big-endian length prefix + UTF-8 JSON body
 */

const maxApi = require("max-api");
const net = require("net");

const PORT = 9879;
const VERSION = "1.0.0";
const API_TIMEOUT_MS = 5000;
const MAX_MESSAGE_SIZE_BYTES = 10 * 1024 * 1024;

maxApi.post(`AMCPX Observer starting on port ${PORT}...`);

// ---------------------------------------------------------------------------
// In-memory state — updated by live.observer callbacks
// ---------------------------------------------------------------------------

const state = {
    selected_track_index: null,
    selected_track_name: null,
    selected_device_name: null,
    selected_parameter_name: null,
    selected_parameter_value: null,
    current_song_time: null,
    last_updated: null,
};

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

// ---------------------------------------------------------------------------
// State update helpers
// ---------------------------------------------------------------------------

async function updateSelectedTrack() {
    try {
        const name = await liveGet("live_set view selected_track", "name");
        const trackCount = await liveGetCount("live_set", "tracks");
        let index = null;
        for (let i = 0; i < trackCount; i++) {
            const tname = await liveGet(`live_set tracks ${i}`, "name");
            if (tname === name) {
                index = i;
                break;
            }
        }
        state.selected_track_index = index;
        state.selected_track_name = String(name);
        state.last_updated = new Date().toISOString();
    } catch (e) {
        maxApi.post(`AMCPX Observer: selected_track update error: ${e.message}`);
    }
}

async function updateSelectedDevice() {
    try {
        const name = await liveGet("live_set view selected_track view selected_device", "name");
        state.selected_device_name = String(name);
        state.last_updated = new Date().toISOString();
    } catch (e) {
        // No device selected is a normal condition
        state.selected_device_name = null;
        state.last_updated = new Date().toISOString();
    }
}

async function updateSelectedParameter() {
    try {
        const name = await liveGet(
            "live_set view selected_track view selected_device selected_parameter", "name"
        );
        const value = await liveGet(
            "live_set view selected_track view selected_device selected_parameter", "value"
        );
        state.selected_parameter_name = String(name);
        state.selected_parameter_value = parseFloat(value);
        state.last_updated = new Date().toISOString();
    } catch (e) {
        // No parameter selected is a normal condition
        state.selected_parameter_name = null;
        state.selected_parameter_value = null;
        state.last_updated = new Date().toISOString();
    }
}

// ---------------------------------------------------------------------------
// Max-side handlers — called when live.observer fires a change notification
// ---------------------------------------------------------------------------

maxApi.addHandler("selected_track", async (...args) => {
    await updateSelectedTrack();
    // When track changes, device and parameter context also becomes stale
    await updateSelectedDevice();
    await updateSelectedParameter();
});

maxApi.addHandler("selected_device", async (...args) => {
    await updateSelectedDevice();
    await updateSelectedParameter();
});

maxApi.addHandler("selected_parameter", async (...args) => {
    await updateSelectedParameter();
});

maxApi.addHandler("current_song_time", (...args) => {
    const time = parseFloat(args[0]);
    if (!isNaN(time)) {
        state.current_song_time = time;
        state.last_updated = new Date().toISOString();
    }
});

// ---------------------------------------------------------------------------
// Command handlers — called from TCP clients
// ---------------------------------------------------------------------------

function getPlayheadBars(beats) {
    // Assumes 4/4 time for bar calculation.
    // For non-4/4 projects, use current_song_time (beats) directly.
    if (beats === null || beats === undefined) return null;
    const bar = Math.floor(beats / 4) + 1;
    const beatInBar = (beats % 4) + 1;
    return { bar, beat_in_bar: Math.round(beatInBar * 100) / 100 };
}

function handleCommand(command, params) {
    switch (command) {
        case "ping":
            return { status: "pong", version: VERSION };

        case "get_state":
            return { ...state };

        case "get_selected_track":
            return {
                selected_track_index: state.selected_track_index,
                selected_track_name: state.selected_track_name,
                last_updated: state.last_updated,
            };

        case "get_selected_device":
            return {
                selected_device_name: state.selected_device_name,
                last_updated: state.last_updated,
            };

        case "get_selected_parameter":
            return {
                selected_parameter_name: state.selected_parameter_name,
                selected_parameter_value: state.selected_parameter_value,
                last_updated: state.last_updated,
            };

        case "get_playhead": {
            const bars = getPlayheadBars(state.current_song_time);
            return {
                current_song_time: state.current_song_time,
                bar: bars ? bars.bar : null,
                beat_in_bar: bars ? bars.beat_in_bar : null,
                last_updated: state.last_updated,
            };
        }

        default:
            throw new Error(`Unknown command: ${command}`);
    }
}

// ---------------------------------------------------------------------------
// TCP Server — stream buffering approach (same pattern as amcpx_node_server.js)
// ---------------------------------------------------------------------------

let server = null;

function handleConnection(socket) {
    socket.setNoDelay(true);
    maxApi.post(`AMCPX Observer: client connected from ${socket.remoteAddress}`);

    let buf = Buffer.alloc(0);
    let processing = false;

    async function processBuffer() {
        if (processing) return;
        processing = true;

        try {
            while (true) {
                if (buf.length < 4) break;

                const msgLen = buf.readUInt32BE(0);

                if (msgLen === 0 || msgLen > MAX_MESSAGE_SIZE_BYTES) {
                    maxApi.post(`AMCPX Observer: invalid message length ${msgLen}, closing`);
                    socket.destroy();
                    break;
                }

                if (buf.length < 4 + msgLen) break;

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
                    const result = handleCommand(command, params);
                    response = JSON.stringify({ status: "ok", result });
                } catch (e) {
                    maxApi.post(`AMCPX Observer error [${command}]: ${e.message}`);
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
        processBuffer().catch(err => maxApi.post(`AMCPX Observer: processBuffer error: ${err.message}`));
    });

    socket.on("error", (err) => {
        if (err.code !== "ECONNRESET") {
            maxApi.post(`AMCPX Observer: socket error: ${err.message}`);
        }
    });

    socket.on("close", () => {
        maxApi.post("AMCPX Observer: client disconnected");
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
        maxApi.post("AMCPX Observer: server already running");
        return;
    }

    server = net.createServer(handleConnection);

    server.on("error", (err) => {
        maxApi.post(`AMCPX Observer server error: ${err.message}`);
        if (err.code === "EADDRINUSE") {
            maxApi.post(`AMCPX Observer: port ${PORT} already in use — is another instance running?`);
        }
        server = null;
    });

    server.listen(PORT, "127.0.0.1", () => {
        maxApi.post(`AMCPX Observer: listening on port ${PORT} ✓`);
        maxApi.outlet("listening", PORT);
    });
}

// Auto-start when loaded
startServer();
