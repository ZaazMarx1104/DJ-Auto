// Minimal example JS for a Max for Live MIDI device that talks to the DJ-Auto backend.
//
// This script assumes:
// - inlet 0: messages from UI, e.g. ["prompt", "4-bar jazzy chords in C minor"]
// - inlet 1: bangs to trigger generation, e.g. "generate"
//
// You still need to:
// - Add a [maxurl] object in the patch and connect it to this JS via send/receive or inlets.
// - Wire the returned note list into clip creation / modification (e.g. via Live API).
//
// The goal is to demonstrate the JSON contract and basic HTTP call pattern.

inlets = 2;
outlets = 2; // outlet 0: HTTP request body; outlet 1: debug/status

var backend_host = "127.0.0.1";
var backend_port = 8000;
var default_bars = 4;
var default_role = "chords";
var default_density = "medium";
var default_register = "mid";

var current_prompt = "";

// Response buffering and request tracking
var response_buffer = "";
var latest_request_id = null;
var client_request_counter = 0;
var debug_enabled = 0;


function anything() {
    // Handle messages like: prompt some text...
    var args = arrayfromargs(messagename, arguments);
    if (args.length === 0) {
        return;
    }
    var cmd = args[0];
    if (cmd === "prompt") {
        args.shift();
        current_prompt = args.join(" ");
        outlet(1, "set_prompt", current_prompt);
    } else if (cmd === "generate") {
        trigger_generate();
    }
}


function msg_int(v) {
    // Could be used to set bars or other numeric parameters from UI.
}

function debug(v) {
    debug_enabled = v ? 1 : 0;
    outlet(1, "debug_enabled", debug_enabled);
}


function trigger_generate() {
    if (!current_prompt || current_prompt.length === 0) {
        outlet(1, "error", "No prompt set");
        return;
    }

    // For MVP, we do not fetch tempo/time signature from Live here.
    // You can extend this script with Live API calls to make it context-aware.
    var tempo = 120;
    var time_sig_num = 4;
    var time_sig_den = 4;

    client_request_counter += 1;
    var client_request_id = "req_" + client_request_counter + "_" + new Date().getTime();
    latest_request_id = client_request_id;

    var body = {
        prompt: current_prompt,
        tempo: tempo,
        time_signature: [time_sig_num, time_sig_den],
        bars: default_bars,
        role: default_role,
        density: default_density,
        register: default_register,
        client_request_id: client_request_id,
        constraints: {
            max_notes_per_bar: 12,
            pitch_range: [48, 84],
            quantize: "1/16",
            max_polyphony: 4
        }
    };

    var json = JSON.stringify(body);
    // Send the JSON string out of outlet 0; connect this to [maxurl] in your patch.
    outlet(0, "post_body", json);
    if (debug_enabled) {
        outlet(1, "info", "sent_generate " + client_request_id);
    } else {
        outlet(1, "info", "sent_generate");
    }
}

// --- Live API helpers ---

function get_or_create_target_clip(clip_length_beats) {
    // Target: highlighted clip slot in the Session view
    var slot = new LiveAPI("live_set view highlighted_clip_slot");

    // If no clip exists, create one with the desired length
    var hasClip = slot.get("has_clip");
    if (!hasClip || hasClip[0] === 0) {
        slot.call("create_clip", clip_length_beats);
    }

    // After creation, the slot now contains a clip; get the detail_clip
    var clip = new LiveAPI("live_set view detail_clip");
    return clip;
}

function apply_notes_to_clip(notes, clip_length_beats) {
    var clip = get_or_create_target_clip(clip_length_beats);
    if (!clip) {
        outlet(1, "error", "No clip available");
        return;
    }

    // Set clip loop length to match our generated content
    clip.set("loop_start", 0.0);
    clip.set("loop_end", clip_length_beats);

    // Replace all notes in the clip
    // Live API pattern:
    //   call replace_notes
    //   call notes <count>
    //   call note <pitch> <start> <duration> <velocity> <mute>
    //   call done
    clip.call("select_all_notes");
    clip.call("replace_notes");

    // Sanitize and filter notes
    var sanitized = [];
    var minDuration = 4.0 / 32.0;
    for (var i = 0; i < notes.length; i++) {
        var n = notes[i];
        var pitch = n.pitch;
        var start = n.start;
        var duration = n.duration;
        var velocity = n.velocity;

        if (typeof start !== "number" || typeof duration !== "number") {
            continue;
        }
        if (start < 0 || start >= clip_length_beats) {
            continue;
        }
        if (duration <= 0) {
            duration = minDuration;
        }
        if (start + duration > clip_length_beats) {
            duration = clip_length_beats - start;
            if (duration <= 0) {
                continue;
            }
        }

        if (typeof pitch !== "number") {
            continue;
        }
        if (typeof velocity !== "number") {
            velocity = 100;
        }
        if (velocity < 1) {
            velocity = 1;
        } else if (velocity > 127) {
            velocity = 127;
        }

        sanitized.push({
            pitch: pitch,
            start: start,
            duration: duration,
            velocity: velocity
        });
    }

    clip.call("notes", sanitized.length);

    for (var j = 0; j < sanitized.length; j++) {
        var sn = sanitized[j];
        var mute = 0;
        clip.call("note", sn.pitch, sn.start, sn.duration, sn.velocity, mute);
    }

    clip.call("done");
    clip.call("deselect_all_notes");

    outlet(1, "info", "notes_written " + sanitized.length);
}

// --- maxurl response handling ---

function body() {
    var args = arrayfromargs(arguments);
    var chunk = args.join(" ");
    if (!chunk || chunk.length === 0) {
        return;
    }

    response_buffer += chunk;

    var parsed;
    try {
        parsed = JSON.parse(response_buffer);
    } catch (e) {
        // Incomplete JSON; wait for more chunks
        return;
    }

    // Successfully parsed; clear buffer and handle
    response_buffer = "";
    handle_backend_response(parsed);
}

function handle_backend_response(payload) {
    if (!payload || typeof payload !== "object") {
        return;
    }

    if (payload.error) {
        var err = payload.error;
        if (debug_enabled) {
            outlet(1, "error", err.code || "UNKNOWN_ERROR", err.message || "");
        }
        return;
    }

    var meta = payload.meta || {};
    var resp_id = meta.request_id || null;
    if (latest_request_id && resp_id && resp_id !== latest_request_id) {
        if (debug_enabled) {
            outlet(1, "info", "stale_response_ignored " + resp_id);
        }
        return;
    }

    var notes = payload.notes || [];
    if (!notes || notes.length === 0) {
        if (debug_enabled) {
            outlet(1, "info", "no_notes_in_response");
        }
        return;
    }

    var maxEnd = 0.0;
    for (var i = 0; i < notes.length; i++) {
        var n = notes[i];
        var start = n.start;
        var dur = n.duration;
        if (typeof start !== "number" || typeof dur !== "number") {
            continue;
        }
        var end = start + dur;
        if (end > maxEnd) {
            maxEnd = end;
        }
    }
    if (maxEnd <= 0) {
        maxEnd = default_bars * 4;
    }

    apply_notes_to_clip(notes, maxEnd);
}