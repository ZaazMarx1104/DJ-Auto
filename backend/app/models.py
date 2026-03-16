from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Tuple


@dataclass
class Constraints:
    """Hard limits and quantization settings applied after generation/editing."""

    max_notes_per_bar: int = 12
    pitch_range: Tuple[int, int] = (36, 96)
    quantize: Literal["1/8", "1/16", "1/32"] = "1/16"
    max_polyphony: int = 4


@dataclass
class Note:
    """Single MIDI note event on a beat grid."""

    pitch: int
    start: float
    duration: float
    velocity: int
    channel: int = 0


Role = Literal["bass", "chords", "lead", "drums"]
Density = Literal["sparse", "medium", "dense"]
Register = Literal["low", "mid", "high"]


@dataclass
class GenerateRequest:
    """Request body for generating a new MIDI pattern from text."""

    prompt: str
    tempo: float
    time_signature: Tuple[int, int]
    bars: int
    role: Role = "chords"
    density: Density = "medium"
    register: Register = "mid"
    constraints: Constraints = field(default_factory=Constraints)
    seed: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerateRequest":
        constraints_data = data.get("constraints") or {}
        constraints = Constraints(**constraints_data)
        ts = data.get("time_signature", [4, 4])
        return cls(
            prompt=data["prompt"],
            tempo=float(data["tempo"]),
            time_signature=(int(ts[0]), int(ts[1])),
            bars=int(data["bars"]),
            role=data.get("role", "chords"),
            density=data.get("density", "medium"),
            register=data.get("register", "mid"),
            constraints=constraints,
            seed=data.get("seed"),
        )


@dataclass
class EditRequest:
    """Request body for editing an existing pattern using text instructions."""

    instruction: str
    tempo: float
    time_signature: Tuple[int, int]
    bars: int
    role: Role = "chords"
    constraints: Constraints = field(default_factory=Constraints)
    notes: List[Note] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EditRequest":
        constraints_data = data.get("constraints") or {}
        constraints = Constraints(**constraints_data)
        ts = data.get("time_signature", [4, 4])
        raw_notes = data.get("notes") or []
        notes: List[Note] = []
        for item in raw_notes:
            try:
                notes.append(
                    Note(
                        pitch=int(item["pitch"]),
                        start=float(item["start"]),
                        duration=float(item["duration"]),
                        velocity=int(item["velocity"]),
                        channel=int(item.get("channel", 0)),
                    )
                )
            except Exception:
                continue

        return cls(
            instruction=data["instruction"],
            tempo=float(data["tempo"]),
            time_signature=(int(ts[0]), int(ts[1])),
            bars=int(data["bars"]),
            role=data.get("role", "chords"),
            constraints=constraints,
            notes=notes,
        )


@dataclass
class Meta:
    """Metadata attached to responses for UX and debugging."""

    request_id: str = ""
    warnings: List[str] = field(default_factory=list)
    model: Optional[str] = None
    latency_ms: Optional[int] = None


@dataclass
class MidiResponse:
    """Response body containing concrete MIDI notes and optional metadata."""

    notes: List[Note]
    meta: Meta = field(default_factory=Meta)


def midi_response_to_dict(response: MidiResponse) -> Dict[str, Any]:
    """Serialize MidiResponse to a JSON-serializable dict."""
    return {
        "notes": [asdict(n) for n in response.notes],
        "meta": asdict(response.meta),
    }

