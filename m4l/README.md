## Max for Live integration (example)

This folder contains example JavaScript for a Max for Live MIDI device that talks
to the DJ‑Auto backend over HTTP.

### Conceptual wiring

Inside Ableton Live:

1. Create a **Max for Live MIDI device**.
2. Add a `js` object and point it to `device.js` (or paste the contents of `device.js` into a JS object).
3. Add UI elements:
   - `textedit` or similar for the user prompt.
   - `textbutton` / `bang` for `Generate`.
   - Optional toggles/menus for `role`, `density`, `bars`, etc.
4. Connect the UI elements to the inlet(s) of the `js` object according to the comments in `device.js`.
5. The JS code will:
   - Read tempo / time signature from Live via the Live API.
   - Build a JSON payload.
   - Use `maxurl` to POST to `http://127.0.0.1:8000/generate_midi`.
   - Parse the result and write notes into the current MIDI clip.

This repo does not contain a fully wired `.amxd` device; instead it gives you
the JS logic and HTTP contract so you can patch the device visually in Max for Live.

