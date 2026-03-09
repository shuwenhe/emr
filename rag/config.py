from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: Optional[float]) -> Optional[float]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass
class Settings:
    kb_path: str
    provider: str
    llm_model: str
    embed_model: str
    openai_base_url: Optional[str]
    openai_api_key: Optional[str]
    ollama_base_url: Optional[str]
    top_k: int
    score_threshold: Optional[float]
    cache_provider: str
    redis_host: str
    redis_port: int
    redis_db: int
    cache_ttl: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            kb_path=os.getenv("KB_PATH", "./rag/kb/current"),
            provider=os.getenv("PROVIDER", "ollama"),
            llm_model=os.getenv("LLM_MODEL", "qwen-7b"),
            embed_model=os.getenv("EMBED_MODEL", "bge-m3:latest"),
            openai_base_url=os.getenv("OPENAI_BASE_URL"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            top_k=_get_int("TOP_K", 5),
            score_threshold=_get_float("SCORE_THRESHOLD", None),
            cache_provider=os.getenv("CACHE_PROVIDER", "memory"),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=_get_int("REDIS_PORT", 6379),
            redis_db=_get_int("REDIS_DB", 0),
            cache_ttl=_get_int("CACHE_TTL", 3600),
        )


def clamp_provider(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider not in {"ollama", "openai-compatible"}:
        return "ollama"
    return provider
