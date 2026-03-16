from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from .config import get_settings
from .models import EditRequest, GenerateRequest
from .prompts import SYSTEM_PROMPT, build_edit_user_prompt, build_generate_user_prompt


_settings = get_settings()
_client: httpx.AsyncClient | None = None


class GroqError(RuntimeError):
    """Structured error for Groq-related failures."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        if not _settings.groq_api_key:
            raise GroqError(
                code="MISSING_API_KEY",
                message=(
                    "GROQ_API_KEY is not set. Set it in your environment or .env file "
                    "before starting the backend."
                ),
                status_code=400,
                retry_after_seconds=None,
            )
        _client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {_settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    return _client


async def _call_llm(system: str, user: str) -> Dict[str, Any]:
    """
    Call the Groq LLM and return parsed JSON for the notes payload.

    This assumes the model is instructed to return a JSON object with a top-level
    \"notes\" array.
    """
    client = _get_client()
    try:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": _settings.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.8,
                "response_format": {"type": "json_object"},
            },
        )
    except httpx.HTTPError as exc:
        raise GroqError(
            code="NETWORK_ERROR",
            message=f"Network error while calling Groq: {exc}",
            status_code=502,
            retry_after_seconds=None,
        ) from exc

    status = resp.status_code
    if status != 200:
        retry_after_header = resp.headers.get("Retry-After")
        retry_after: Optional[int] = None
        if retry_after_header is not None:
            try:
                retry_after = int(retry_after_header)
            except ValueError:
                retry_after = None

        try:
            error_payload = resp.json()
        except Exception:
            error_payload = resp.text

        if status == 401:
            raise GroqError(
                code="INVALID_API_KEY",
                message=f"Groq API returned 401 Unauthorized: {error_payload}",
                status_code=401,
                retry_after_seconds=None,
            )
        if status == 429:
            raise GroqError(
                code="OUT_OF_FREE_QUOTA",
                message=f"Groq API returned 429 quota/ratelimit error: {error_payload}",
                status_code=429,
                retry_after_seconds=retry_after,
            )

        raise GroqError(
            code="GROQ_API_ERROR",
            message=f"Groq API error {status}: {error_payload}",
            status_code=status,
            retry_after_seconds=retry_after,
        )

    payload = resp.json()
    choices = payload.get("choices") or []
    if not choices:
        raise GroqError(
            code="BAD_LLM_RESPONSE",
            message="LLM response contained no choices.",
            status_code=502,
            retry_after_seconds=None,
        )
    content = choices[0]["message"]["content"]
    if not content:
        raise GroqError(
            code="BAD_LLM_RESPONSE",
            message="LLM returned empty content.",
            status_code=502,
            retry_after_seconds=None,
        )
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise GroqError(
            code="BAD_LLM_RESPONSE",
            message=f"Failed to parse LLM JSON: {exc}",
            status_code=502,
            retry_after_seconds=None,
        ) from exc
    if "notes" not in data or not isinstance(data["notes"], list):
        raise GroqError(
            code="BAD_LLM_RESPONSE",
            message="LLM response missing 'notes' array.",
            status_code=502,
            retry_after_seconds=None,
        )
    return data


async def generate_notes(req: GenerateRequest) -> Dict[str, Any]:
    """Generate a new pattern from a high-level text prompt."""
    user = build_generate_user_prompt(req)
    return await _call_llm(SYSTEM_PROMPT, user)


async def edit_notes(req: EditRequest) -> Dict[str, Any]:
    """Edit an existing pattern based on text instructions."""
    user = build_edit_user_prompt(req)
    return await _call_llm(SYSTEM_PROMPT, user)
