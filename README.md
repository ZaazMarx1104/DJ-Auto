## DJ-Auto – LLM‑powered Text‑to‑MIDI for Ableton Live

DJ‑Auto is an experimental setup for controlling Ableton Live MIDI clips using natural language.

The MVP consists of:
- **Python backend** (FastAPI) running locally, exposing simple JSON HTTP endpoints for generating and editing MIDI patterns with an LLM.
- **Max for Live MIDI device** that sends user text prompts and clip context to the backend, then writes the returned notes into the selected MIDI clip.

This repo currently contains the **backend** implementation and example code for the **Max for Live** side.

### Features (MVP)

- **Generate MIDI from text**: e.g. “4‑bar jazzy chords in C minor at 110 BPM”.
- **Text‑based edits**: e.g. “make the second half more syncopated” (later phases).
- **Exact notes at exact times**: backend always returns a concrete note list (pitch, start, duration, velocity, channel), quantized to a configurable grid.
- **Cost‑aware**: compact JSON schemas, optional use of smaller/cheaper LLM models, and strict limits on clip length and note counts.

---

### Backend quickstart

1. **Create and activate a virtualenv** (optional but recommended):

```bash
cd DJ-Auto
python -m venv .venv
.\.venv\Scripts\activate  # on Windows PowerShell
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**:

Create a `.env` file in the repo root (or set environment variables directly):

```bash
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4.1-mini
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
```

4. **Run the backend server**:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

5. **Test the health endpoint**:

Open `http://127.0.0.1:8000/health` in a browser or run:

```bash
curl http://127.0.0.1:8000/health
```

You should see:

```json
{"status":"ok"}
```

---

### API overview (MVP)

- `GET /health` – Simple health check.
- `POST /generate_midi` – Generate a new MIDI pattern from a text prompt.
- `POST /edit_midi` – Edit an existing pattern based on text instructions.

Requests and responses use a compact JSON schema documented in `backend/app/models.py`.

---

### Max for Live integration (high‑level)

- Create a **Max for Live MIDI device**.
- Add a `js` object that loads the script from `m4l/device.js` (or copy the code into a JS object).
- Wire UI elements (text box, buttons) to the JS script to:
  - Collect tempo, time signature, bar length, and optionally role/density.
  - Send an HTTP `POST` to `http://127.0.0.1:8000/generate_midi` with the JSON payload.
  - Receive the note list and write it into the current MIDI clip.

Refer to `m4l/README.md` and `m4l/device.js` for concrete wiring suggestions.

---

### Status

This is an MVP focused on:
- A clean JSON contract between Ableton and the backend.
- Exact, quantized note generation.
- Robustness (validation and repair loops) and cost‑aware LLM usage.

Future work may include more advanced editing, multi‑track context, and integration with scale/chord detection devices.

