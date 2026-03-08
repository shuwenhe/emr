from __future__ import annotations

import os
from typing import Optional


SUPPORTED_PROVIDERS = {"ollama", "openai-compatible"}


def clamp_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    if value not in SUPPORTED_PROVIDERS:
        return "ollama"
    return value


def build_embeddings(
    provider: str,
    embed_model: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
):
    provider = clamp_provider(provider)
    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        resolved_base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaEmbeddings(model=embed_model, base_url=resolved_base_url)

    if provider == "openai-compatible":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=embed_model, base_url=base_url, api_key=api_key)

    raise ValueError(f"Unsupported provider: {provider}")
