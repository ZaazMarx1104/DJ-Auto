from __future__ import annotations

from .models import EditRequest, GenerateRequest


SYSTEM_PROMPT = """
You are a MIDI pattern generator and editor.

You MUST output valid JSON ONLY, matching this exact schema:

{
  "notes": [
    { "pitch": int, "start": float, "duration": float, "velocity": int, "channel": int }
  ]
}

Rules:
- "start" and "duration" are in beats, relative to clip start (0.0).
- All notes must fit within the clip: [0, total_beats).
- Use only MIDI pitches 0–127 and velocities 1–127.
- Respect role, pitch_range, and max_notes_per_bar that I provide.
- Do not include explanations, comments, or any text outside the JSON.
"""


def build_generate_user_prompt(req: GenerateRequest) -> str:
    numerator, denominator = req.time_signature
    total_beats = req.bars * numerator
    low, high = req.constraints.pitch_range

    return f"""
User request: {req.prompt}

Context:
- Tempo: {req.tempo} BPM
- Time signature: {numerator}/{denominator}
- Bars: {req.bars} (total beats: {total_beats})
- Role: {req.role}
- Density: {req.density}
- Register: {req.register}
- Pitch range: {low} to {high}
- Max notes per bar: {req.constraints.max_notes_per_bar}
- Quantize: {req.constraints.quantize}

Task:
Design a musically coherent pattern that fits this role and context.
Return a single JSON object with a \"notes\" array only.
Every note must obey the pitch range and clip bounds.
"""


def build_edit_user_prompt(req: EditRequest) -> str:
    numerator, denominator = req.time_signature
    total_beats = req.bars * numerator
    low, high = req.constraints.pitch_range

    # Keep the embedded notes reasonably compact; they will already be JSON‑serializable.
    notes_repr = [
        {
            "pitch": n.pitch,
            "start": n.start,
            "duration": n.duration,
            "velocity": n.velocity,
            "channel": n.channel,
        }
        for n in req.notes
    ]

    return f"""
Edit instruction: {req.instruction}

Current clip context:
- Tempo: {req.tempo} BPM
- Time signature: {numerator}/{denominator}
- Bars: {req.bars} (total beats: {total_beats})
- Role: {req.role}
- Pitch range: {low} to {high}
- Max notes per bar: {req.constraints.max_notes_per_bar}
- Quantize: {req.constraints.quantize}

Current notes (JSON array):
{notes_repr}

Task:
Apply the edit instruction to the current notes and return a NEW set of notes as JSON.
Return the FULL updated note list (not a diff).
Your output must be a single JSON object with a \"notes\" array and nothing else.
"""

