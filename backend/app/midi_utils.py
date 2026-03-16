from __future__ import annotations

import math
from typing import Iterable, List, Tuple

from .models import Constraints, EditRequest, GenerateRequest, MidiResponse, Note


def _quantize_value(value: float, subdivision: str) -> float:
    """Quantize a beat value to the nearest subdivision (1/8, 1/16, 1/32)."""
    denom = {"1/8": 8, "1/16": 16, "1/32": 32}[subdivision]
    step = 4.0 / denom  # in beats (4 beats per bar for quarter note in 4/4)
    return round(value / step) * step


def _apply_constraints_to_notes(
    notes: Iterable[Note],
    constraints: Constraints,
    total_beats: float,
) -> Tuple[List[Note], List[str]]:
    """Quantize, clamp, and enforce basic constraints on a note list."""
    warnings: List[str] = []
    processed: List[Note] = []
    max_notes = constraints.max_notes_per_bar * max(1, int(total_beats))
    low, high = constraints.pitch_range

    for note in notes:
        if len(processed) >= max_notes:
            warnings.append("note_count_reduced_to_fit_constraints")
            break

        pitch = min(max(note.pitch, low), high)
        start = _quantize_value(float(note.start), constraints.quantize)
        duration = max(
            _quantize_value(float(note.duration), constraints.quantize), 4.0 / 32
        )

        if start >= total_beats:
            continue
        if start + duration > total_beats:
            duration = max(total_beats - start, 4.0 / 32)
            warnings.append("notes_truncated_to_clip_length")

        velocity = min(max(note.velocity, 1), 127)
        channel = min(max(note.channel, 0), 15)

        processed.append(
            Note(
                pitch=pitch,
                start=start,
                duration=duration,
                velocity=velocity,
                channel=channel,
            )
        )

    # Rough max polyphony enforcement by limiting overlapping notes at same time.
    if constraints.max_polyphony > 0 and processed:
        processed.sort(key=lambda n: (n.start, -n.duration))
        filtered: List[Note] = []
        current_time = None
        stack: List[Note] = []
        for n in processed:
            if current_time is None or abs(n.start - current_time) < 1e-6:
                current_time = n.start
                stack.append(n)
            else:
                stack.sort(key=lambda x: x.velocity, reverse=True)
                filtered.extend(stack[: constraints.max_polyphony])
                stack = [n]
                current_time = n.start
        if stack:
            stack.sort(key=lambda x: x.velocity, reverse=True)
            filtered.extend(stack[: constraints.max_polyphony])
        processed = filtered

    return processed, warnings


def post_process_generated(
    req: GenerateRequest, raw_payload: dict
) -> Tuple[List[Note], List[str]]:
    """
    Convert the raw LLM payload into validated Note objects and apply constraints.
    """
    numerator, _ = req.time_signature
    total_beats = float(req.bars * numerator)
    raw_notes = raw_payload.get("notes", [])

    notes: List[Note] = []
    for item in raw_notes:
        try:
            notes.append(Note(**item))
        except Exception:
            # Skip malformed entries; higher-level validation keeps UX robust.
            continue

    notes, warnings = _apply_constraints_to_notes(notes, req.constraints, total_beats)
    return notes, warnings


def post_process_edited(
    req: EditRequest, raw_payload: dict
) -> Tuple[List[Note], List[str]]:
    """
    Same as post_process_generated but for edit responses.
    """
    numerator, _ = req.time_signature
    total_beats = float(req.bars * numerator)
    raw_notes = raw_payload.get("notes", [])

    notes: List[Note] = []
    for item in raw_notes:
        try:
            notes.append(Note(**item))
        except Exception:
            continue

    notes, warnings = _apply_constraints_to_notes(notes, req.constraints, total_beats)
    return notes, warnings


def dummy_pattern(req: GenerateRequest) -> List[Note]:
    """
    Simple deterministic pattern used before wiring in the LLM.

    This lets you test the end-to-end flow (M4L -> backend -> MIDI clip)
    without any external dependencies.
    """
    numerator, _ = req.time_signature
    total_beats = float(req.bars * numerator)
    step = 1.0  # quarter notes

    base_pitch = {
        "bass": 36,
        "chords": 48,
        "lead": 60,
        "drums": 36,
    }.get(req.role, 48)

    notes: List[Note] = []
    t = 0.0
    while t < total_beats:
        notes.append(
            Note(
                pitch=base_pitch,
                start=t,
                duration=step,
                velocity=96,
                channel=0,
            )
        )
        t += step
    constrained, _ = _apply_constraints_to_notes(
        notes, req.constraints, total_beats
    )
    return constrained

