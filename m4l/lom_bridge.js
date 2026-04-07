// lom_bridge.js — Max js object for Live Object Model (LOM) queries
// Bridges node.script (Node for Max) to Live's LOM via Max's LiveAPI
//
// Receives messages from node.script outlet 0:
//   live_get    <id> <path> <prop>          — get a LOM property value
//   live_getcount <id> <path> <prop>        — get count of a LOM list property
//   live_call   <id> <path> <method> [...]  — call a LOM method
//
// Sends results back to node.script inlet 0:
//   live_result <id> [<value> ...]          — success response
//   live_error  <id> <message>              — error response

outlets = 1;
inlets = 1;

// Delay (ms) given to the LiveAPI callback chain for get_notes_extended to complete
// before the collected results are emitted.  Live fires the callback asynchronously
// and may invoke it multiple times (once per chunk), so a brief deferral is required.
var GET_NOTES_CALLBACK_DELAY_MS = 200;

function live_get() {
    var args = arrayfromargs(arguments);
    var id = args[0];
    var path = args[1];
    var prop = args[2];
    try {
        new LiveAPI(function(results) {
            outlet(0, "live_result", id, results[0]);
        }, path).get(prop);
    } catch (e) {
        outlet(0, "live_error", id, String(e));
    }
}

function live_getcount() {
    var args = arrayfromargs(arguments);
    var id = args[0];
    var path = args[1];
    var prop = args[2];
    try {
        new LiveAPI(function(results) {
            outlet(0, "live_result", id, results[0]);
        }, path).getcount(prop);
    } catch (e) {
        outlet(0, "live_error", id, String(e));
    }
}

function live_call() {
    var args = arrayfromargs(arguments);
    var id = args[0];
    var path = args[1];
    var method = args[2];
    var callArgs = args.slice(3);
    try {
        var responded = false;
        var api = new LiveAPI(function(results) {
            if (!responded) {
                responded = true;
                var resp = [0, "live_result", id].concat(results || []);
                outlet.apply(null, resp);
            }
        }, path);
        api.call.apply(api, [method].concat(callArgs));
        // Fallback for void methods that do not trigger the LiveAPI callback.
        // Schedule(0) defers until after the current execution so that an async
        // callback can still fire first and set responded = true.
        var t = new Task(function() {
            if (!responded) {
                responded = true;
                outlet(0, "live_result", id);
            }
        });
        t.schedule(0);
    } catch (e) {
        outlet(0, "live_error", id, String(e));
    }
}

// Dedicated handler for get_notes_extended.
// live_call() cannot reliably capture the note data returned by get_notes_extended
// because that method fires its LiveAPI callback asynchronously — potentially multiple
// times, once per note chunk.  Using Task.schedule(200) gives all callback invocations
// time to complete before the collected results are emitted.
//
// Message format: live_get_notes_extended <id> <path> <from_time> <time_span> <from_pitch> <pitch_span>
function live_get_notes_extended() {
    var args = arrayfromargs(arguments);
    var id = args[0];
    var path = args[1];
    var fromTime = args[2];
    var timeSpan = args[3];
    var fromPitch = args[4];
    var pitchSpan = args[5];

    var noteData = [];

    try {
        var api = new LiveAPI(function() {
            var results = arrayfromargs(arguments);
            for (var i = 0; i < results.length; i++) {
                noteData.push(results[i]);
            }
        }, path);

        api.call("get_notes_extended", fromTime, timeSpan, fromPitch, pitchSpan);

        var t = new Task(function() {
            var resp = [0, "live_result", id].concat(noteData);
            outlet.apply(null, resp);
        });
        t.schedule(GET_NOTES_CALLBACK_DELAY_MS);
    } catch (e) {
        outlet(0, "live_error", id, String(e));
    }
}
