from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from .config import get_settings
from .models import EditRequest, GenerateRequest, Meta, MidiResponse, midi_response_to_dict
from . import llm_client, midi_utils
from . import deterministic_edits


settings = get_settings()


def _build_meta(
    request_id: str,
    warnings: Optional[List[str]] = None,
    model: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> Dict[str, Any]:
    meta = Meta(
        request_id=request_id,
        warnings=warnings or [],
        model=model,
        latency_ms=latency_ms,
    )
    return {
        "request_id": meta.request_id,
        "warnings": meta.warnings,
        "model": meta.model,
        "latency_ms": meta.latency_ms,
    }


def _error_response(
    request_id: str,
    code: str,
    message: str,
    status_code: int,
    retry_after_seconds: Optional[int] = None,
    model: Optional[str] = None,
    warnings: Optional[List[str]] = None,
    latency_ms: Optional[int] = None,
) -> JSONResponse:
    body: Dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "retry_after_seconds": retry_after_seconds,
        },
        "meta": _build_meta(
            request_id=request_id,
            warnings=warnings,
            model=model,
            latency_ms=latency_ms,
        ),
    }
    return JSONResponse(body, status_code=status_code)


async def health(request: Request) -> JSONResponse:
    key_present = bool(settings.groq_api_key)
    return JSONResponse(
        {"status": "ok", "llm_provider": "groq", "llm_key_present": key_present}
    )


async def generate_midi(request: Request) -> JSONResponse:
    """
    Generate a new MIDI pattern from a text prompt.

    For early MVP testing, you can switch between a dummy deterministic
    pattern and the LLM-backed generator by toggling the `use_dummy`
    flag below.
    """
    request_id = str(uuid4())
    t0 = time.time()

    try:
        data = await request.json()
    except Exception:
        return _error_response(
            request_id=request_id,
            code="INVALID_JSON",
            message="Invalid JSON body",
            status_code=400,
            model=None,
            latency_ms=int((time.time() - t0) * 1000),
        )

    client_request_id = data.get("client_request_id")
    if isinstance(client_request_id, str) and client_request_id:
        request_id = client_request_id

    try:
        req = GenerateRequest.from_dict(data)
    except KeyError as exc:
        return _error_response(
            request_id=request_id,
            code="VALIDATION_ERROR",
            message=f"Missing required field: {exc}",
            status_code=400,
            model=None,
            latency_ms=int((time.time() - t0) * 1000),
        )

    use_dummy = False  # Set to True while testing without an LLM/API key.
    warnings: List[str] = []

    if use_dummy:
        notes = midi_utils.dummy_pattern(req)
    else:
        try:
            raw_payload = await llm_client.generate_notes(req)
        except llm_client.GroqError as exc:
            logger.exception("generate_midi LLM call failed")
            return _error_response(
                request_id=request_id,
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
                retry_after_seconds=exc.retry_after_seconds,
                model=settings.llm_model,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as exc:
            logger.exception("generate_midi unexpected LLM failure")
            return _error_response(
                request_id=request_id,
                code="INTERNAL_ERROR",
                message=str(exc),
                status_code=502,
                model=settings.llm_model,
                latency_ms=int((time.time() - t0) * 1000),
            )
        notes, warnings = midi_utils.post_process_generated(req, raw_payload)

    latency_ms = int((time.time() - t0) * 1000)
    meta = Meta(
        request_id=request_id,
        warnings=warnings,
        model=settings.llm_model if not use_dummy else None,
        latency_ms=latency_ms,
    )
    response = MidiResponse(notes=notes, meta=meta)
    return JSONResponse(midi_response_to_dict(response))


async def edit_midi(request: Request) -> JSONResponse:
    """
    Edit an existing MIDI pattern using text instructions.
    """
    request_id = str(uuid4())
    t0 = time.time()

    try:
        data = await request.json()
    except Exception:
        return _error_response(
            request_id=request_id,
            code="INVALID_JSON",
            message="Invalid JSON body",
            status_code=400,
            model=None,
            latency_ms=int((time.time() - t0) * 1000),
        )

    client_request_id = data.get("client_request_id")
    if isinstance(client_request_id, str) and client_request_id:
        request_id = client_request_id

    try:
        req = EditRequest.from_dict(data)
    except KeyError as exc:
        return _error_response(
            request_id=request_id,
            code="VALIDATION_ERROR",
            message=f"Missing required field: {exc}",
            status_code=400,
            model=None,
            latency_ms=int((time.time() - t0) * 1000),
        )

    t0 = time.time()
    warnings: List[str] = []

    det_notes, det_warnings, handled = deterministic_edits.try_apply_deterministic_edit(
        req
    )
    if handled:
        notes = det_notes
        warnings.extend(det_warnings)
        model = None
    else:
        try:
            raw_payload = await llm_client.edit_notes(req)
        except llm_client.GroqError as exc:
            return _error_response(
                request_id=request_id,
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
                retry_after_seconds=exc.retry_after_seconds,
                model=settings.llm_model,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as exc:
            return _error_response(
                request_id=request_id,
                code="INTERNAL_ERROR",
                message=str(exc),
                status_code=502,
                model=settings.llm_model,
                latency_ms=int((time.time() - t0) * 1000),
            )
        notes, post_warnings = midi_utils.post_process_edited(req, raw_payload)
        warnings.extend(post_warnings)
        model = settings.llm_model

    latency_ms = int((time.time() - t0) * 1000)
    meta = Meta(
        request_id=request_id,
        warnings=warnings,
        model=model,
        latency_ms=latency_ms,
    )
    response = MidiResponse(notes=notes, meta=meta)
    return JSONResponse(midi_response_to_dict(response))


routes = [
    Route("/health", health),
    Route("/generate_midi", generate_midi, methods=["POST"]),
    Route("/edit_midi", edit_midi, methods=["POST"]),
]

app = Starlette(debug=False, routes=routes)

