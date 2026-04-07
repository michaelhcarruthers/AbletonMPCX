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
