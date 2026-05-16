from __future__ import annotations

import os

from .openai import OpenAICompatibleProvider


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider using the OpenAI-compatible chat completions API."""

    provider_name = "openrouter"

    def __init__(self, model_name: str, settings=None):
        settings = settings or {}
        clean_name = str(model_name or "").strip()

        lower_name = clean_name.lower()
        if lower_name in {"openrouter/free", "openrouter/auto"}:
            clean_name = lower_name
        elif lower_name.startswith("openrouter/"):
            clean_name = clean_name.split("/", 1)[1].strip()

        extra_headers = {}

        referer = (
            settings.get("openrouter_http_referer")
            or os.getenv("OPENROUTER_HTTP_REFERER")
        )
        if referer:
            extra_headers["HTTP-Referer"] = str(referer).strip()

        title = (
            settings.get("openrouter_app_title")
            or settings.get("openrouter_title")
            or os.getenv("OPENROUTER_APP_TITLE")
            or os.getenv("OPENROUTER_TITLE")
        )
        if title:
            extra_headers["X-OpenRouter-Title"] = str(title).strip()

        super().__init__(
            clean_name,
            OPENROUTER_BASE_URL,
            "OPENROUTER_API_KEY",
            provider_name=self.provider_name,
            extra_headers=extra_headers,
        )
