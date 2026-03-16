from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    """Runtime configuration loaded from environment variables."""

    groq_api_key: Optional[str]
    llm_model: str
    backend_host: str
    backend_port: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        llm_model=os.getenv("LLM_MODEL", "llama-3.1-8b-instant"),
        backend_host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
    )

