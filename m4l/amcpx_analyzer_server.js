/**
 * amcpx_analyzer_server.js
 * Node for Max — AMCPX Analyzer TCP server
 *
 * Receives named meter messages from Max:
 *   meter_peak <db>
 *   meter_rms <db>
 *   band_sub / band_bass / band_low_mid / band_mid / band_presence / band_air <db>
 *   spectral_centroid <hz>
 *   spectral_tilt <value>
 *   dominant_peak_hz <hz>
 *
 * Opens a TCP server on port 9880 using Node's built-in net module.
 * Protocol: 4-byte big-endian length prefix + UTF-8 JSON body
 */

const maxApi = require("max-api");
const net = require("net");

const PORT = 9880;
const VERSION = "2.0.0";
const MAX_MESSAGE_SIZE_BYTES = 10 * 1024 * 1024;

const LUFS_SHORT_WINDOW = 30;
const LUFS_INTEGRATED_WINDOW = 400;
const CLIP_THRESHOLD_DB = 0;

maxApi.post(`AMCPX Analyzer v2 starting on port ${PORT}...`);

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
    bands: {
        sub: -Infinity,
        bass: -Infinity,
        low_mid: -Infinity,
        mid: -Infinity,
        presence: -Infinity,
        air: -Infinity,
    },
    spectral_centroid_hz: -Infinity,
    spectral_tilt: -Infinity,
    dominant_peak_hz: -Infinity,
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
    measurements.bands.sub = -Infinity;
    measurements.bands.bass = -Infinity;
    measurements.bands.low_mid = -Infinity;
    measurements.bands.mid = -Infinity;
    measurements.bands.presence = -Infinity;
    measurements.bands.air = -Infinity;
    measurements.spectral_centroid_hz = -Infinity;
    measurements.spectral_tilt = -Infinity;
    measurements.dominant_peak_hz = -Infinity;
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
        bands: getBandsForJson(),
        spectral_centroid_hz: safeNum(measurements.spectral_centroid_hz),
        spectral_tilt: safeNum(measurements.spectral_tilt),
        dominant_peak_hz: safeNum(measurements.dominant_peak_hz),
        last_updated: measurements.last_updated,
        measuring: measurements.measuring,
    };
}

function getBandsForJson() {
    return {
        sub: safeNum(measurements.bands.sub),
        bass: safeNum(measurements.bands.bass),
        low_mid: safeNum(measurements.bands.low_mid),
        mid: safeNum(measurements.bands.mid),
        presence: safeNum(measurements.bands.presence),
        air: safeNum(measurements.bands.air),
    };
}

function classifyBand(db) {
    if (!Number.isFinite(db)) return "unknown";
    if (db >= -18) return "high";
    if (db >= -30) return "slightly_high";
    if (db >= -42) return "balanced";
    if (db >= -54) return "slightly_low";
    return "low";
}

function computeFlags() {
    const b = measurements.bands;
    const flags = [];
    if (Number.isFinite(b.low_mid) && b.low_mid > -24) flags.push("low_mid_buildup");
    if (Number.isFinite(b.air) && b.air < -48) flags.push("needs_air");
    if (Number.isFinite(b.air) && b.air < -54) flags.push("air_low");
    if (Number.isFinite(b.presence) && b.presence > -22) flags.push("presence_forward");
    if (Number.isFinite(b.bass) && b.bass > -20) flags.push("bass_heavy");
    if (Number.isFinite(measurements.spectral_tilt) && measurements.spectral_tilt < -8) flags.push("dark_tilt");
    if (Number.isFinite(measurements.spectral_tilt) && measurements.spectral_tilt > 8) flags.push("bright_tilt");
    return flags;
}

function getTonalBalanceForJson() {
    return {
        bands: {
            sub: classifyBand(measurements.bands.sub),
            bass: classifyBand(measurements.bands.bass),
            low_mid: classifyBand(measurements.bands.low_mid),
            mid: classifyBand(measurements.bands.mid),
            presence: classifyBand(measurements.bands.presence),
            air: classifyBand(measurements.bands.air),
        },
        spectral_centroid_hz: safeNum(measurements.spectral_centroid_hz),
        spectral_tilt: safeNum(measurements.spectral_tilt),
        dominant_peak_hz: safeNum(measurements.dominant_peak_hz),
        flags: computeFlags(),
        last_updated: measurements.last_updated,
        measuring: measurements.measuring,
    };
}

function getAnalyzerSummary() {
    const tonal = getTonalBalanceForJson();
    const flags = tonal.flags;

    let overall_tilt = "balanced";
    if (Number.isFinite(measurements.spectral_tilt)) {
        if (measurements.spectral_tilt < -8) overall_tilt = "dark";
        else if (measurements.spectral_tilt > 8) overall_tilt = "bright";
    }

    let suggestion_focus = "No strong tonal warning right now.";
    if (flags.includes("low_mid_buildup") && flags.includes("needs_air")) {
        suggestion_focus = "Check low-mid buildup and top-end openness. Likely mud plus lack of air.";
    } else if (flags.includes("low_mid_buildup")) {
        suggestion_focus = "Check bass body, piano warmth, and other low-mid sources.";
    } else if (flags.includes("needs_air")) {
        suggestion_focus = "Top end looks rolled off. Check cymbals, highs, and air band balance.";
    } else if (flags.includes("bass_heavy")) {
        suggestion_focus = "Low end looks heavy. Check bass weight and kick balance.";
    } else if (flags.includes("presence_forward")) {
        suggestion_focus = "Presence region may be pushing forward. Check upper mids for edge.";
    }

    return {
        overall_tilt,
        bands: tonal.bands,
        flags,
        spectral_centroid_hz: tonal.spectral_centroid_hz,
        spectral_tilt: tonal.spectral_tilt,
        dominant_peak_hz: tonal.dominant_peak_hz,
        suggestion_focus,
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

function addBandHandler(messageName, bandKey) {
    maxApi.addHandler(messageName, (...args) => {
        const val = Number(args[0]);

        if (!Number.isFinite(val)) {
            maxApi.post(`AMCPX Analyzer: invalid ${messageName} payload: ${JSON.stringify(args)}`);
            return;
        }

        if (!measurements.measuring) return;

        measurements.bands[bandKey] = val;
        stampUpdated();
    });
}

addBandHandler("band_sub", "sub");
addBandHandler("band_bass", "bass");
addBandHandler("band_low_mid", "low_mid");
addBandHandler("band_mid", "mid");
addBandHandler("band_presence", "presence");
addBandHandler("band_air", "air");

maxApi.addHandler("spectral_centroid", (...args) => {
    const val = Number(args[0]);

    if (!Number.isFinite(val)) {
        maxApi.post(`AMCPX Analyzer: invalid spectral_centroid payload: ${JSON.stringify(args)}`);
        return;
    }

    if (!measurements.measuring) return;

    measurements.spectral_centroid_hz = val;
    stampUpdated();
});

maxApi.addHandler("spectral_tilt", (...args) => {
    const val = Number(args[0]);

    if (!Number.isFinite(val)) {
        maxApi.post(`AMCPX Analyzer: invalid spectral_tilt payload: ${JSON.stringify(args)}`);
        return;
    }

    if (!measurements.measuring) return;

    measurements.spectral_tilt = val;
    stampUpdated();
});

maxApi.addHandler("dominant_peak_hz", (...args) => {
    const val = Number(args[0]);

    if (!Number.isFinite(val)) {
        maxApi.post(`AMCPX Analyzer: invalid dominant_peak_hz payload: ${JSON.stringify(args)}`);
        return;
    }

    if (!measurements.measuring) return;

    measurements.dominant_peak_hz = val;
    stampUpdated();
});

maxApi.addHandler("debug_state", () => {
    maxApi.post(`AMCPX Analyzer state: ${JSON.stringify(getMeasurementsForJson())}`);
});

maxApi.addHandler("debug_handlers", () => {
    maxApi.post("AMCPX Analyzer: handlers loaded for meter_peak, meter_rms, band_sub, band_bass, band_low_mid, band_mid, band_presence, band_air, spectral_centroid, spectral_tilt, dominant_peak_hz, debug_state, debug_handlers");
});

function getContextBands() {
    const b = measurements.bands;
    // Map existing 6 bands into 5 context groups (sub+bass→low, low_mid, mid, presence→high_mid, air→high)
    const entries = [
        { key: "low",      dbs: [b.sub, b.bass] },
        { key: "low_mid",  dbs: [b.low_mid] },
        { key: "mid",      dbs: [b.mid] },
        { key: "high_mid", dbs: [b.presence] },
        { key: "high",     dbs: [b.air] },
    ];

    const powers = {};
    for (const { key, dbs } of entries) {
        const valid = dbs.filter(v => Number.isFinite(v));
        if (valid.length === 0) return null;
        // Convert dB to linear power (10^(dB/10)) before averaging and normalizing
        const linSum = valid.reduce((s, db) => s + Math.pow(10, db / 10), 0);
        powers[key] = linSum / valid.length;
    }

    const total = Object.values(powers).reduce((s, v) => s + v, 0);
    if (total === 0) return null;

    const result = {};
    for (const [k, v] of Object.entries(powers)) {
        result[k] = Math.round((v / total) * 10000) / 10000;
    }
    return result;
}

function classifySpectralTilt() {
    const t = measurements.spectral_tilt;
    if (!Number.isFinite(t)) return null;
    // Thresholds in dB/octave: > +8 = bright (high-frequency heavy),
    // < -8 = dark (low-frequency heavy), otherwise balanced.
    if (t < -8) return "dark";
    if (t > 8) return "bright";
    return "balanced";
}

function getContextSuggestionFocus() {
    const flags = computeFlags();
    if (flags.includes("low_mid_buildup") && flags.includes("needs_air")) {
        return "Check low-mid buildup and top-end openness.";
    }
    if (flags.includes("low_mid_buildup")) return "Check low-mid buildup.";
    if (flags.includes("needs_air")) return "Top end looks rolled off.";
    if (flags.includes("bass_heavy")) return "Low end looks heavy.";
    if (flags.includes("presence_forward")) return "Presence region may be pushing forward.";
    return null;
}



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

        case "get_tonal_balance":
            return getTonalBalanceForJson();

        case "get_analyzer_summary":
            return getAnalyzerSummary();

        case "get_context": {
            const dataValid = measurements.last_updated !== null && Number.isFinite(measurements.lufs_integrated);
            return {
                lufs: safeNum(measurements.lufs_integrated),
                peak_dbfs: safeNum(measurements.peak_db),
                spectral_tilt: classifySpectralTilt(),
                bands: getContextBands(),
                suggestion_focus: dataValid ? getContextSuggestionFocus() : null,
                data_valid: dataValid,
                last_updated: measurements.last_updated,
            };
        }

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
