// Max for Live MIDI device script for DJ-Auto.
// inlet 0: UI/control messages, e.g. prompt <text>, bars 4, role chords, generate
// inlet 1: HTTP response dictionary from [maxurl]
// outlet 0: HTTP commands/messages for [maxurl]
// outlet 1: status/debug messages for UI

autowatch = 1;

inlets = 2;
outlets = 2;

var backend_base_url = "http://127.0.0.1:8000";
var default_bars = 4;
var default_role = "chords";
var default_density = "medium";
var default_register = "mid";

var current_prompt = "";
var latest_request_id = null;
var client_request_counter = 0;
var debug_enabled = 0;
var last_applied_notes = [];
var latest_request_endpoint = "";
var current_mode = "generate";

function loadbang() {
    outlet(1, "context", "tempo", "--");
    outlet(1, "context", "meter", "--");
    outlet(1, "param", "mode", current_mode);
    outlet(1, "info", "ready");
}

function anything() {
    // Handle inbound HTTP responses from maxurl (inlet 1)
    if (inlet === 1) {
        handle_http_inbound(messagename, arrayfromargs(arguments));
        return;
    }

    var args = arrayfromargs(messagename, arguments);
    if (args.length === 0) return;

    var cmd = args[0];

    if (cmd === "prompt") {
        args.shift();
        // Strip the "text" token that textedit outputs as the message type
        if (args.length > 0 && args[0] === "text") args.shift();
        var newPrompt = args.join(" ").trim();
        if (newPrompt.length === 0) return; // ignore empty
        current_prompt = newPrompt;
        outlet(1, "set_prompt", current_prompt);
        if (debug_enabled) outlet(1, "debug", "prompt_set", current_prompt);
        return;
    }

    if (cmd === "bars") {
        if (args.length > 1) {
            var b = parseInt(args[1], 10);
            if (isFinite(b) && b > 0) {
                default_bars = b;
                outlet(1, "param", "bars", default_bars);
            }
        }
        return;
    }

    if (cmd === "role") {
        if (args.length > 1) {
            default_role = String(args[1]);
            outlet(1, "param", "role", default_role);
        }
        return;
    }

    if (cmd === "density") {
        if (args.length > 1) {
            default_density = String(args[1]);
            outlet(1, "param", "density", default_density);
        }
        return;
    }

    if (cmd === "register") {
        if (args.length > 1) {
            default_register = String(args[1]);
            outlet(1, "param", "register", default_register);
        }
        return;
    }

    if (cmd === "backend_url") {
        if (args.length > 1) {
            backend_base_url = normalize_backend_base_url(String(args[1]));
            outlet(1, "info", "backend_url_set", backend_base_url);
        }
        return;
    }

    if (cmd === "mode") {
        if (args.length > 1) {
            set_mode(String(args[1]));
        }
        return;
    }

    if (cmd === "generate") {
        set_mode("generate");
        trigger_request("generate");
        return;
    }

    if (cmd === "edit") {
        set_mode("edit");
        trigger_request("edit");
        return;
    }

    if (cmd === "submit") {
        trigger_request(current_mode);
        return;
    }
}

function msg_int(v) {
    default_bars = Math.max(1, parseInt(v, 10) || 4);
    outlet(1, "param", "bars", default_bars);
}

function debug(v) {
    debug_enabled = v ? 1 : 0;
    outlet(1, "debug_enabled", debug_enabled);
}

function set_mode(mode) {
    var nextMode = String(mode || "").toLowerCase();
    if (nextMode !== "edit") nextMode = "generate";
    current_mode = nextMode;
    outlet(1, "param", "mode", current_mode);
}

function get_song_context() {
    try {
        var song = new LiveAPI("live_set");
        var tempoRaw = song.get("tempo");
        var numRaw = song.get("signature_numerator");
        var denRaw = song.get("signature_denominator");

        var tempo = (tempoRaw && tempoRaw.length) ? parseFloat(tempoRaw[0]) : 120;
        var time_sig_num = (numRaw && numRaw.length) ? parseInt(numRaw[0], 10) : 4;
        var time_sig_den = (denRaw && denRaw.length) ? parseInt(denRaw[0], 10) : 4;

        if (!isFinite(tempo)) tempo = 120;
        if (!isFinite(time_sig_num)) time_sig_num = 4;
        if (!isFinite(time_sig_den)) time_sig_den = 4;

        outlet(1, "context", "tempo", tempo);
        outlet(1, "context", "meter", time_sig_num + "/" + time_sig_den);

        return {
            tempo: tempo,
            time_signature: [time_sig_num, time_sig_den]
        };
    } catch (e) {
        outlet(1, "error", "live_context_failed", e.toString());
        return { tempo: 120, time_signature: [4, 4] };
    }
}

function normalize_backend_base_url(raw) {
    var value = String(raw || "").replace(/\s+$/g, "");
    if (value.indexOf("/generate_midi") >= 0) {
        return value.replace(/\/generate_midi\/?$/, "");
    }
    if (value.indexOf("/edit_midi") >= 0) {
        return value.replace(/\/edit_midi\/?$/, "");
    }
    return value.replace(/\/+$/, "");
}

function build_endpoint_url(path) {
    return normalize_backend_base_url(backend_base_url) + path;
}

function schedule_request(endpointUrl, payloadJson) {
    latest_request_endpoint = endpointUrl;

    client_request_counter += 1;
    var reqDictName = "dj_auto_req_" + client_request_counter;
    var d = new Dict(reqDictName);
    d.clear();

    d.set("url", endpointUrl);
    d.set("http_method", "post");
    d.set("headers[0]", "Content-Type: application/json");

    var postData = new Dict();
    postData.parse(payloadJson);
    d.set("post_data", postData);

    if (debug_enabled) {
        outlet(1, "debug", "request_url", endpointUrl);
        outlet(1, "debug", "request_json", payloadJson);
    }

    outlet(0, "dictionary", reqDictName);
}

function clone_note(note) {
    return {
        pitch: note.pitch,
        start: note.start,
        duration: note.duration,
        velocity: note.velocity,
        channel: typeof note.channel === "number" ? note.channel : 0
    };
}

function get_current_clip() {
    try {
        return new LiveAPI("live_set view detail_clip");
    } catch (e) {
        return null;
    }
}

function parse_live_notes(raw) {
    if (!raw || !raw.length) return [];

    var notes = [];
    if (raw[0] === "notes" && raw.length >= 2) {
        var count = parseInt(raw[1], 10) || 0;
        var index = 2;
        for (var i = 0; i < count; i++) {
            if (raw[index] === "note") index += 1;
            if (index + 4 >= raw.length) break;

            notes.push({
                pitch: parseInt(raw[index], 10) || 0,
                start: parseFloat(raw[index + 1]) || 0,
                duration: parseFloat(raw[index + 2]) || 0,
                velocity: parseInt(raw[index + 3], 10) || 100,
                channel: 0
            });
            index += 5;
        }
    }

    return notes;
}

function get_current_clip_notes() {
    var clip = get_current_clip();
    if (!clip) return last_applied_notes.slice(0);

    var parsed = [];
    try {
        clip.call("select_all_notes");
        var rawNotes;
        try {
            rawNotes = clip.call("get_selected_notes_extended");
        } catch (inner) {
            rawNotes = clip.call("get_selected_notes");
        }
        parsed = parse_live_notes(rawNotes);
    } catch (e) {
        if (debug_enabled) outlet(1, "info", "clip_note_read_failed", e.toString());
    }

    try { clip.call("deselect_all_notes"); } catch (ignored) {}

    if (parsed.length > 0) return parsed;
    return last_applied_notes.slice(0);
}

function infer_clip_bars(notes, fallbackBars, timeSignature) {
    var maxEnd = 0.0;
    for (var i = 0; i < notes.length; i++) {
        var n = notes[i];
        if (typeof n.start !== "number" || typeof n.duration !== "number") continue;
        var end = n.start + n.duration;
        if (end > maxEnd) maxEnd = end;
    }

    if (maxEnd <= 0) return fallbackBars;

    var beatsPerBar = timeSignature[0] * (4.0 / timeSignature[1]);
    if (!isFinite(beatsPerBar) || beatsPerBar <= 0) return fallbackBars;

    return Math.max(1, Math.ceil(maxEnd / beatsPerBar));
}

function trigger_request(mode) {
    // Always require a prompt — cleared after each request so reuse is impossible
    if (!current_prompt || current_prompt.length === 0) {
        outlet(1, "error", "prompt_missing", "No prompt set — type something and press Enter first");
        return;
    }

    var songContext = get_song_context();
    var tempo = songContext.tempo;
    var time_sig_num = songContext.time_signature[0];
    var time_sig_den = songContext.time_signature[1];
    var currentNotes = get_current_clip_notes();
    var hasExistingClipNotes = currentNotes.length > 0;
    var isEditRequest = String(mode || current_mode).toLowerCase() === "edit";
    var endpointPath = isEditRequest ? "/edit_midi" : "/generate_midi";
    var endpointUrl = build_endpoint_url(endpointPath);

    if (isEditRequest && !hasExistingClipNotes) {
        outlet(1, "error", "edit_notes_missing", "Edit request requires notes in the current clip");
        return;
    }

    var client_request_id = "req_" + (client_request_counter + 1) + "_" + new Date().getTime();
    latest_request_id = client_request_id;

    var constraints = {
        max_notes_per_bar: 12,
        pitch_range: [48, 84],
        quantize: "1/16",
        max_polyphony: 4
    };

    var bars = isEditRequest
        ? infer_clip_bars(currentNotes, default_bars, [time_sig_num, time_sig_den])
        : default_bars;

    var body;
    if (isEditRequest) {
        body = {
            instruction: current_prompt,
            tempo: tempo,
            time_signature: [time_sig_num, time_sig_den],
            bars: bars,
            role: default_role,
            client_request_id: client_request_id,
            constraints: constraints,
            notes: currentNotes
        };
    } else {
        body = {
            prompt: current_prompt,
            tempo: tempo,
            time_signature: [time_sig_num, time_sig_den],
            bars: bars,
            role: default_role,
            density: default_density,
            register: default_register,
            client_request_id: client_request_id,
            constraints: constraints
        };
    }

    if (debug_enabled) {
        outlet(1, "info",
            (isEditRequest ? "sent_edit" : "sent_generate"),
            client_request_id, endpointUrl,
            "notes", currentNotes.length, "bars", bars
        );
    } else {
        outlet(1, "info", isEditRequest ? "sent_edit" : "sent_generate");
    }

    schedule_request(endpointUrl, JSON.stringify(body));

    // Clear prompt immediately so it can never be reused on the next click
    current_prompt = "";
}

function apply_notes_to_clip(notes, clip_length_beats) {
    var minDuration = 4.0 / 32.0;
    var sanitized = [];
    for (var i = 0; i < notes.length; i++) {
        var n = notes[i];
        if (typeof n.pitch !== "number" || typeof n.start !== "number" || typeof n.duration !== "number") continue;
        if (n.start < 0 || n.start >= clip_length_beats) continue;

        var duration = n.duration;
        if (duration <= 0) duration = minDuration;
        if (n.start + duration > clip_length_beats) {
            duration = clip_length_beats - n.start;
            if (duration <= 0) continue;
        }

        var velocity = typeof n.velocity === "number" ? n.velocity : 100;
        if (velocity < 1) velocity = 1;
        if (velocity > 127) velocity = 127;

        sanitized.push({
            pitch: n.pitch,
            start: n.start,
            duration: duration,
            velocity: velocity
        });
    }

    if (sanitized.length === 0) {
        outlet(1, "error", "no_valid_notes", "No valid notes to write");
        return;
    }

    try {
        var slot = new LiveAPI("live_set view highlighted_clip_slot");
        var hasClip = slot.get("has_clip");
        if (!hasClip || hasClip[0] === 0) {
            slot.call("create_clip", clip_length_beats);
        }

        var clip = new LiveAPI("live_set view detail_clip");
        clip.set("loop_start", 0.0);
        clip.set("loop_end", clip_length_beats);

        // Clear existing notes
        clip.call("remove_notes_extended", 0, 0, clip_length_beats, 128);

		// Build notes dict and write via add_new_notes
        var notesData = { "notes": [] };
        for (var j = 0; j < sanitized.length; j++) {
            var sn = sanitized[j];
            notesData.notes.push({
                pitch:            sn.pitch,
                start_time:       sn.start,
                duration:         sn.duration,
                velocity:         sn.velocity,
                mute:             0,
                probability:      1.0,
                release_velocity: 64
            });
        }
        var nd = new Dict("dj_auto_notes");
        nd.clear();
        nd.setparse("wrapper", JSON.stringify(notesData));
        var notesDict = nd.get("wrapper");
        clip.call("add_new_notes", notesDict);

        // Cache for edit requests
        last_applied_notes = [];
        for (var k = 0; k < sanitized.length; k++) {
            last_applied_notes.push({
                pitch: sanitized[k].pitch,
                start: sanitized[k].start,
                duration: sanitized[k].duration,
                velocity: sanitized[k].velocity,
                channel: 0
            });
        }

        outlet(1, "info", "notes_written", sanitized.length);

    } catch (e) {
        outlet(1, "error", "clip_write_failed", e.toString());
    }
}

function handle_http_inbound(msg, args) {
    if (msg === "dictionary" && args.length > 0) {
        handle_response_dict(args[0]);
        return;
    }
    if (debug_enabled) {
        outlet(1, "debug", "http_in", msg, args.join(" "));
    }
}

function handle_response_dict(dictName) {
    try {
        var d = new Dict(dictName);
        var statusVal = d.get("status");
        var status = statusVal ? parseInt(String(statusVal), 10) : 0;

        if (debug_enabled) {
            outlet(1, "debug", "response_dict", dictName, "status", status);
        }

        var bodyValue = d.get("body");
        if (!bodyValue) {
            outlet(1, "error", "missing_response_body", dictName);
            return;
        }

        var bodyText = (bodyValue && bodyValue.stringify) ? bodyValue.stringify() : String(bodyValue);
        var payload = JSON.parse(bodyText);
        handle_backend_response(payload);

    } catch (e) {
        outlet(1, "error", "response_dict_parse_failed", e.toString());
    }
}

function handle_backend_response(payload) {
    if (!payload || typeof payload !== "object") return;

    if (payload.error) {
        var err = payload.error;
        outlet(1, "error", err.code || "UNKNOWN_ERROR", err.message || "");
        return;
    }

    var meta = payload.meta || {};
    var resp_id = meta.request_id || null;

    if (latest_request_id && resp_id && resp_id !== latest_request_id) {
        if (debug_enabled) outlet(1, "info", "stale_response_ignored", resp_id);
        return;
    }

    var notes = payload.notes || [];
    if (!notes || notes.length === 0) {
        outlet(1, "error", "empty_notes_response", latest_request_endpoint || "unknown_endpoint");
        return;
    }

    var maxEnd = 0.0;
    for (var i = 0; i < notes.length; i++) {
        var n = notes[i];
        if (typeof n.start !== "number" || typeof n.duration !== "number") continue;
        var end = n.start + n.duration;
        if (end > maxEnd) maxEnd = end;
    }
    if (maxEnd <= 0) maxEnd = default_bars * 4;

    apply_notes_to_clip(notes, maxEnd);
}