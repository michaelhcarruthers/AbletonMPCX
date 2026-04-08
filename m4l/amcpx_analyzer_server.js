/**
 * amcpx_analyzer_server.js
 * Node for Max — AMCPX Analyzer TCP server
 *
 * Receives named meter messages from Max:
 *   meter_peak <db>
 *   meter_rms <db>
 *
 * Opens a TCP server on port 9880 using Node's built-in net module.
 * Protocol: 4-byte big-endian length prefix + UTF-8 JSON body
 */

const maxApi = require("max-api");
const net = require("net");

const PORT = 9880;
const VERSION = "1.1.0";
const MAX_MESSAGE_SIZE_BYTES = 10 * 1024 * 1024;

const LUFS_SHORT_WINDOW = 30;
const LUFS_INTEGRATED_WINDOW = 400;
const CLIP_THRESHOLD_DB = 0;

maxApi.post(`AMCPX Analyzer starting on port ${PORT}...`);

// ---------------------------------------------------------------------------
// Measurement state
// ---------------------------------------------------------------------------

const measurements = {
    peak_db: -Infinity,
    rms_db: -Infinity,
    lufs_short: -Infinity,
    lufs_integrated: -Infinity,
    crest_factor_db: -Infinity,
    clip_count: 0,
    last_updated: null,
    measuring: true, // default on, since the Max patch metro starts automatically
};

const rmsBuffer = [];
let lastPeakWasClipping = false;

function resetMeasurements() {
    measurements.peak_db = -Infinity;
    measurements.rms_db = -Infinity;
    measurements.lufs_short = -Infinity;
    measurements.lufs_integrated = -Infinity;
    measurements.crest_factor_db = -Infinity;
    measurements.clip_count = 0;
    measurements.last_updated = null;
    rmsBuffer.length = 0;
    lastPeakWasClipping = false;
    // Note: measuring flag is intentionally preserved across reset so that
    // clearing data does not interrupt an active measurement session.
}

function safeNum(val) {
    return Number.isFinite(val) ? val : null;
}

function stampUpdated() {
    measurements.last_updated = new Date().toISOString();
}

function updateCrestFactor() {
    if (Number.isFinite(measurements.peak_db) && Number.isFinite(measurements.rms_db)) {
        measurements.crest_factor_db = measurements.peak_db - measurements.rms_db;
    } else {
        measurements.crest_factor_db = -Infinity;
    }
}

function updateLufs(rmsDb) {
    if (!Number.isFinite(rmsDb)) return;

    rmsBuffer.push(rmsDb);
    if (rmsBuffer.length > LUFS_INTEGRATED_WINDOW) rmsBuffer.shift();

    const shortSlice = rmsBuffer.slice(-LUFS_SHORT_WINDOW);

    if (shortSlice.length > 0) {
        const shortPower =
            shortSlice.reduce((sum, db) => sum + Math.pow(10, db / 10), 0) / shortSlice.length;
        measurements.lufs_short = shortPower > 0 ? 10 * Math.log10(shortPower) : -Infinity;
    } else {
        measurements.lufs_short = -Infinity;
    }

    if (rmsBuffer.length > 0) {
        const intPower =
            rmsBuffer.reduce((sum, db) => sum + Math.pow(10, db / 10), 0) / rmsBuffer.length;
        measurements.lufs_integrated = intPower > 0 ? 10 * Math.log10(intPower) : -Infinity;
    } else {
        measurements.lufs_integrated = -Infinity;
    }
}

function updateClipCount(peakDb) {
    const isClipping = Number.isFinite(peakDb) && peakDb >= CLIP_THRESHOLD_DB;
    if (isClipping && !lastPeakWasClipping) {
        measurements.clip_count += 1;
    }
    lastPeakWasClipping = isClipping;
}

function getMeasurementsForJson() {
    return {
        peak_db: safeNum(measurements.peak_db),
        rms_db: safeNum(measurements.rms_db),
        lufs_short: safeNum(measurements.lufs_short),
        lufs_integrated: safeNum(measurements.lufs_integrated),
        crest_factor_db: safeNum(measurements.crest_factor_db),
        clip_count: measurements.clip_count,
        last_updated: measurements.last_updated,
        measuring: measurements.measuring,
    };
}

// ---------------------------------------------------------------------------
// Max message handlers
// ---------------------------------------------------------------------------

maxApi.addHandler("meter_peak", (...args) => {
    const val = Number(args[0]);

    if (!Number.isFinite(val)) {
        maxApi.post(`AMCPX Analyzer: invalid meter_peak payload: ${JSON.stringify(args)}`);
        return;
    }

    if (!measurements.measuring) return;

    measurements.peak_db = val;
    updateClipCount(val);
    updateCrestFactor();
    stampUpdated();
});

maxApi.addHandler("meter_rms", (...args) => {
    const val = Number(args[0]);

    if (!Number.isFinite(val)) {
        maxApi.post(`AMCPX Analyzer: invalid meter_rms payload: ${JSON.stringify(args)}`);
        return;
    }

    if (!measurements.measuring) return;

    measurements.rms_db = val;
    updateLufs(val);
    updateCrestFactor();
    stampUpdated();
});

maxApi.addHandler("debug_state", () => {
    maxApi.post(`AMCPX Analyzer state: ${JSON.stringify(getMeasurementsForJson())}`);
});

maxApi.addHandler("debug_handlers", () => {
    maxApi.post("AMCPX Analyzer: handlers loaded for meter_peak, meter_rms, debug_state, debug_handlers");
});

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

async function handleCommand(command) {
    switch (command) {
        case "ping":
            return { status: "pong", version: VERSION };

        case "get_levels":
            return getMeasurementsForJson();

        case "get_lufs":
            return {
                lufs_short: safeNum(measurements.lufs_short),
                lufs_integrated: safeNum(measurements.lufs_integrated),
            };

        case "get_peak":
            return {
                peak_db: safeNum(measurements.peak_db),
                clip_count: measurements.clip_count,
            };

        case "get_crest_factor":
            return {
                crest_factor_db: safeNum(measurements.crest_factor_db),
                peak_db: safeNum(measurements.peak_db),
                rms_db: safeNum(measurements.rms_db),
            };

        case "reset":
            resetMeasurements();
            return { reset: true, measuring: measurements.measuring };

        case "start_measuring":
            measurements.measuring = true;
            maxApi.outlet("set_measuring", 1);
            stampUpdated();
            return { measuring: true };

        case "stop_measuring":
            measurements.measuring = false;
            maxApi.outlet("set_measuring", 0);
            stampUpdated();
            return getMeasurementsForJson();

        default:
            throw new Error(`Unknown command: ${command}`);
    }
}

// ---------------------------------------------------------------------------
// TCP Server
// ---------------------------------------------------------------------------

let server = null;

function handleConnection(socket) {
    socket.setNoDelay(true);
    maxApi.post(`AMCPX Analyzer: client connected from ${socket.remoteAddress}`);

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
                    maxApi.post(`AMCPX Analyzer: invalid message length ${msgLen}, closing`);
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
                    const errResp = JSON.stringify({
                        status: "error",
                        error: `Invalid JSON: ${e.message}`,
                    });
                    sendResponse(socket, errResp);
                    continue;
                }

                const command = request.command || "";

                let response;
                try {
                    const result = await handleCommand(command);
                    response = JSON.stringify({ status: "ok", result });
                } catch (e) {
                    maxApi.post(`AMCPX Analyzer error [${command}]: ${e.message}`);
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
        processBuffer().catch((err) => {
            maxApi.post(`AMCPX Analyzer: processBuffer error: ${err.message}`);
        });
    });

    socket.on("error", (err) => {
        if (err.code !== "ECONNRESET") {
            maxApi.post(`AMCPX Analyzer: socket error: ${err.message}`);
        }
    });

    socket.on("close", () => {
        maxApi.post("AMCPX Analyzer: client disconnected");
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
        maxApi.post("AMCPX Analyzer: server already running");
        return;
    }

    server = net.createServer(handleConnection);

    server.on("error", (err) => {
        maxApi.post(`AMCPX Analyzer server error: ${err.message}`);
        if (err.code === "EADDRINUSE") {
            maxApi.post(`AMCPX Analyzer: port ${PORT} already in use — is another instance running?`);
        }
        server = null;
    });

    server.listen(PORT, "127.0.0.1", () => {
        maxApi.post(`AMCPX Analyzer: listening on port ${PORT} ✓`);
        maxApi.outlet("listening", PORT);
    });
}

// Auto-start when loaded
startServer();
