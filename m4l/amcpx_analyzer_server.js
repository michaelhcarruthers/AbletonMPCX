/**
 * amcpx_analyzer_server.js
 * Node for Max — AMCPX Analyzer TCP server
 * Runs inside node.script in AMCPX_Analyzer.maxpat
 *
 * Receives peak/RMS metering data from live.meter~ via Max handlers,
 * maintains rolling LUFS approximations, and exposes measurements over TCP.
 *
 * Protocol: 4-byte big-endian length prefix + UTF-8 JSON body
 */

const maxApi = require("max-api");
const net = require("net");

const PORT = 9880;
const VERSION = "1.0.0";
const MAX_MESSAGE_SIZE_BYTES = 10 * 1024 * 1024;

// live.meter~ outputs at ~10 Hz (interval 100 ms)
const LUFS_SHORT_WINDOW = 30;       // 3-second short-term window  (30 × 100 ms)
const LUFS_INTEGRATED_WINDOW = 400; // ~40-second integrated window (400 × 100 ms)

maxApi.post(`AMCPX Analyzer starting on port ${PORT}...`);

// ---------------------------------------------------------------------------
// Measurement state
// ---------------------------------------------------------------------------

const measurements = {
    peak_db: -Infinity,
    rms_db: -Infinity,
    lufs_short: -Infinity,
    lufs_integrated: -Infinity,
    crest_factor_db: 0,
    clip_count: 0,
    last_updated: null,
    measuring: false,
};

const rmsBuffer = [];        // rolling RMS values — LUFS short-term window
const intBuffer = [];        // rolling RMS values — LUFS integrated window

function resetMeasurements() {
    measurements.peak_db = -Infinity;
    measurements.rms_db = -Infinity;
    measurements.lufs_short = -Infinity;
    measurements.lufs_integrated = -Infinity;
    measurements.crest_factor_db = 0;
    measurements.clip_count = 0;
    measurements.last_updated = null;
    measurements.measuring = false;
    rmsBuffer.length = 0;
    intBuffer.length = 0;
}

function updateLufs(rmsDb) {
    rmsBuffer.push(rmsDb);
    if (rmsBuffer.length > LUFS_SHORT_WINDOW) rmsBuffer.shift();

    intBuffer.push(rmsDb);
    if (intBuffer.length > LUFS_INTEGRATED_WINDOW) intBuffer.shift();

    // Convert each dB value to linear power, average across the window, then
    // convert back to dB — this gives an RMS-based LUFS approximation.
    const shortPower = rmsBuffer.reduce((s, db) => s + Math.pow(10, db / 10), 0) / rmsBuffer.length;
    measurements.lufs_short = 10 * Math.log10(shortPower);

    const intPower = intBuffer.reduce((s, db) => s + Math.pow(10, db / 10), 0) / intBuffer.length;
    measurements.lufs_integrated = 10 * Math.log10(intPower);
}

// ---------------------------------------------------------------------------
// Max handlers — receive metering data from live.meter~ (via prepend objects)
// ---------------------------------------------------------------------------

maxApi.addHandler("meter_peak", (peakDb) => {
    const val = parseFloat(peakDb);
    if (!isFinite(val)) return;

    measurements.peak_db = isFinite(measurements.peak_db) ? Math.max(measurements.peak_db, val) : val;
    measurements.last_updated = new Date().toISOString();

    if (val >= 0) {
        measurements.clip_count++;
    }

    if (isFinite(measurements.rms_db)) {
        measurements.crest_factor_db = measurements.peak_db - measurements.rms_db;
    }
});

maxApi.addHandler("meter_rms", (rmsDb) => {
    const val = parseFloat(rmsDb);
    if (!isFinite(val)) return;

    measurements.rms_db = val;
    measurements.last_updated = new Date().toISOString();

    if (isFinite(measurements.peak_db)) {
        measurements.crest_factor_db = measurements.peak_db - measurements.rms_db;
    }

    updateLufs(val);
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function safeNum(val) {
    return isFinite(val) ? val : null;
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
            return { reset: true };

        case "start_measuring":
            measurements.measuring = true;
            return { measuring: true };

        case "stop_measuring":
            measurements.measuring = false;
            return getMeasurementsForJson();

        default:
            throw new Error(`Unknown command: ${command}`);
    }
}

// ---------------------------------------------------------------------------
// TCP Server — stream buffering approach (same as amcpx_node_server.js)
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
                    const errResp = JSON.stringify({ status: "error", error: `Invalid JSON: ${e.message}` });
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
        processBuffer().catch(err => maxApi.post(`AMCPX Analyzer: processBuffer error: ${err.message}`));
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
