from __future__ import annotations

import math
import random
from typing import List, Tuple

from .models import EditRequest, Note
from . import midi_utils


def _total_beats(req: EditRequest) -> float:
    numerator, _ = req.time_signature
    return float(req.bars * numerator)


def _clamp_pitch(pitch: int, low: int, high: int) -> int:
    return max(low, min(high, pitch))


def _transpose_notes(
    notes: List[Note], semitones: int, pitch_range: Tuple[int, int]
) -> List[Note]:
    low, high = pitch_range
    out: List[Note] = []
    for n in notes:
        new_pitch = _clamp_pitch(n.pitch + semitones, low, high)
        out.append(
            Note(
                pitch=new_pitch,
                start=n.start,
                duration=n.duration,
                velocity=n.velocity,
                channel=n.channel,
            )
        )
    return out


def _quantize_notes(notes: List[Note], subdivision: str) -> List[Note]:
    out: List[Note] = []
    for n in notes:
        start = midi_utils._quantize_value(float(n.start), subdivision)  # type: ignore[attr-defined]
        duration = midi_utils._quantize_value(
            float(n.duration), subdivision
        )  # type: ignore[attr-defined]
        # avoid zero-length notes
        min_len = 4.0 / 32
        if duration <= 0:
            duration = min_len
        out.append(
            Note(
                pitch=n.pitch,
                start=start,
                duration=duration,
                velocity=n.velocity,
                channel=n.channel,
            )
        )
    return out


def _humanize_notes(req: EditRequest) -> List[Note]:
    # Deterministic pseudo-randomness based on request content.
    seed_val = (
        int(req.tempo * 10)
        + req.bars * 31
        + len(req.notes) * 17
        + sum(n.pitch for n in req.notes)
    )
    rng = random.Random(seed_val)
    total_beats = _total_beats(req)

    out: List[Note] = []
    max_shift = 4.0 / 64  # subtle timing changes
    for n in req.notes:
        shift = rng.uniform(-max_shift, max_shift)
        new_start = max(0.0, min(n.start + shift, total_beats))
        vel_jitter = rng.randint(-5, 5)
        new_vel = max(1, min(127, n.velocity + vel_jitter))
        out.append(
            Note(
                pitch=n.pitch,
                start=new_start,
                duration=n.duration,
                velocity=new_vel,
                channel=n.channel,
            )
        )
    return out


def _simplify_notes(notes: List[Note]) -> List[Note]:
    # Keep roughly every other note, preferring on-beat notes.
    if not notes:
        return notes
    sorted_notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    out: List[Note] = []
    for idx, n in enumerate(sorted_notes):
        # keep all notes very close to integer beats, and otherwise every other note
        if abs(n.start - round(n.start)) < 1e-3 or idx % 2 == 0:
            out.append(n)
    return out


def _densify_notes(req: EditRequest) -> List[Note]:
    # Add simple neighbor notes between existing ones.
    if not req.notes:
        return req.notes
    low, high = req.constraints.pitch_range
    total_beats = _total_beats(req)
    out: List[Note] = []
    step = 4.0 / 16  # 1/16th notes
    for n in req.notes:
        out.append(n)
        middle_start = n.start + n.duration * 0.5
        if middle_start + step <= total_beats:
            new_pitch = _clamp_pitch(n.pitch + 2, low, high)
            out.append(
                Note(
                    pitch=new_pitch,
                    start=middle_start,
                    duration=step,
                    velocity=max(1, min(127, n.velocity - 10)),
                    channel=n.channel,
                )
            )
    return out


def try_apply_deterministic_edit(req: EditRequest):
    """
    Attempt to handle simple text instructions without calling the LLM.
    Returns (notes, warnings, handled: bool).
    """
    instruction = (req.instruction or "").lower().strip()
    if not instruction:
        return req.notes, [], False

    warnings: List[str] = []
    notes = list(req.notes)

    # Transpose up/down by explicit number
    if instruction.startswith("transpose up"):
        parts = instruction.split()
        semitones = 0
        for p in parts:
            if p.isdigit():
                semitones = int(p)
                break
        if semitones != 0:
            notes = _transpose_notes(notes, semitones, req.constraints.pitch_range)
            warnings.append(f"deterministic_transpose_up_{semitones}")
            return notes, warnings, True

    if instruction.startswith("transpose down"):
        parts = instruction.split()
        semitones = 0
        for p in parts:
            if p.isdigit():
                semitones = int(p)
                break
        if semitones != 0:
            notes = _transpose_notes(notes, -semitones, req.constraints.pitch_range)
            warnings.append(f"deterministic_transpose_down_{semitones}")
            return notes, warnings, True

    # Musical intervals
    if "up a fifth" in instruction:
        notes = _transpose_notes(notes, 7, req.constraints.pitch_range)
        warnings.append("deterministic_transpose_up_fifth")
        return notes, warnings, True

    if "up an octave" in instruction:
        notes = _transpose_notes(notes, 12, req.constraints.pitch_range)
        warnings.append("deterministic_transpose_up_octave")
        return notes, warnings, True

    # Quantization
    if "quantize to 1/8" in instruction or "quantise to 1/8" in instruction:
        quantized = _quantize_notes(notes, "1/8")
        total_beats = _total_beats(req)
        constrained, extra_warnings = midi_utils._apply_constraints_to_notes(  # type: ignore[attr-defined]
            quantized, req.constraints, total_beats
        )
        warnings.append("deterministic_quantize_1_8")
        warnings.extend(extra_warnings)
        return constrained, warnings, True

    if "quantize to 1/16" in instruction or "quantise to 1/16" in instruction:
        quantized = _quantize_notes(notes, "1/16")
        total_beats = _total_beats(req)
        constrained, extra_warnings = midi_utils._apply_constraints_to_notes(  # type: ignore[attr-defined]
            quantized, req.constraints, total_beats
        )
        warnings.append("deterministic_quantize_1_16")
        warnings.extend(extra_warnings)
        return constrained, warnings, True

    # Humanize
    if "humanize" in instruction:
        humanized = _humanize_notes(req)
        total_beats = _total_beats(req)
        constrained, extra_warnings = midi_utils._apply_constraints_to_notes(  # type: ignore[attr-defined]
            humanized, req.constraints, total_beats
        )
        warnings.append("deterministic_humanize")
        warnings.extend(extra_warnings)
        return constrained, warnings, True

    # Simplify
    if "simplify" in instruction:
        simplified = _simplify_notes(notes)
        total_beats = _total_beats(req)
        constrained, extra_warnings = midi_utils._apply_constraints_to_notes(  # type: ignore[attr-defined]
            simplified, req.constraints, total_beats
        )
        warnings.append("deterministic_simplify")
        warnings.extend(extra_warnings)
        return constrained, warnings, True

    # Densify
    if "densify" in instruction:
        densified = _densify_notes(req)
        total_beats = _total_beats(req)
        constrained, extra_warnings = midi_utils._apply_constraints_to_notes(  # type: ignore[attr-defined]
            densified, req.constraints, total_beats
        )
        warnings.append("deterministic_densify")
        warnings.extend(extra_warnings)
        return constrained, warnings, True

    return req.notes, [], False

