from __future__ import annotations

import json
import os
from typing import Any

import httpx

from modules.system_prompts import load_active_system_prompt
from .base import BaseChatProvider, ProviderAPIError

AI_STUDIO_PREPAY_DEPLETED_MARKERS = (
    "prepayment credits are depleted",
    "prepay credits are depleted",
)


def _parse_retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if not header:
        return None
    try:
        return float(header.strip())
    except Exception:
        return None


def _looks_like_quota_error(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        marker in lowered
        for marker in [
            "quota exceeded",
            "quota",
            "resource exhausted",
            "rate limit",
            "too many requests",
        ]
    )


def _looks_like_ai_studio_prepay_exhausted(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in AI_STUDIO_PREPAY_DEPLETED_MARKERS)


def build_gemini_generate_content_payload(
    prompt: str,
    history: list,
    *,
    system_prompt: str | None = None,
    system_key: str = "system_instruction",
) -> dict[str, Any]:
    if system_prompt is None:
        system_prompt = load_active_system_prompt()
    payload = {
        "contents": prepare_gemini_contents(prompt, history),
    }
    if str(system_prompt or "").strip():
        payload[system_key] = {"parts": [{"text": str(system_prompt).strip()}]}
    return payload


def prepare_gemini_contents(prompt, history):
    contents = []

    history_items = list(history or [])
    if history_items and history_items[0].get("role") == "system":
        history_items = history_items[1:]

    for m in history_items:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            continue

        gemini_role = "user" if role == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": content}]})

    if prompt and str(prompt).strip():
        contents.append({"role": "user", "parts": [{"text": str(prompt).strip()}]})

    return contents


def extract_gemini_texts_from_response(data: Any) -> list[str]:
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return []

    texts: list[str] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        candidates = item.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                text = part.get("text")
                if text:
                    texts.append(text)

    return texts


def classify_gemini_error_response(
    response: httpx.Response,
    raw_text: str,
    *,
    provider_name: str,
    model_name: str,
    url: str,
) -> ProviderAPIError:
    retry_after = _parse_retry_after_seconds(response)
    details = {"url": url, "model_name": model_name}
    if response.status_code == 429:
        if _looks_like_ai_studio_prepay_exhausted(raw_text):
            return ProviderAPIError(
                f"{provider_name} AI Studio prepay credits are depleted ({response.status_code}).",
                kind="billing_exhausted_ai_studio_prepay",
                status_code=response.status_code,
                retry_after_seconds=retry_after,
                provider_name=provider_name,
                raw_error=raw_text,
                user_message=(
                    "Gemini AI Studio prepay credits are depleted. "
                    "Google Cloud trial credits do not cover this API path. "
                    "Add AI Studio credits or switch to vertexai/modelname."
                ),
                details={**details, "error_code": "BILLING_EXHAUSTED_AI_STUDIO_PREPAY"},
            )
        if _looks_like_quota_error(raw_text):
            return ProviderAPIError.quota_exceeded(
                f"{provider_name} quota exceeded ({response.status_code}).",
                status_code=response.status_code,
                retry_after_seconds=retry_after,
                provider_name=provider_name,
                raw_error=raw_text,
                details=details,
            )
        return ProviderAPIError.rate_limit(
            f"{provider_name} rate limit error ({response.status_code}).",
            status_code=response.status_code,
            retry_after_seconds=retry_after,
            provider_name=provider_name,
            raw_error=raw_text,
            details=details,
        )
    if response.status_code in {401, 403}:
        return ProviderAPIError.auth(
            f"{provider_name} authentication/permission error ({response.status_code}).",
            status_code=response.status_code,
            provider_name=provider_name,
            raw_error=raw_text,
            details=details,
        )
    return ProviderAPIError(
        f"{provider_name} API Error {response.status_code}",
        kind="provider_error",
        status_code=response.status_code,
        provider_name=provider_name,
        raw_error=raw_text,
        user_message=f"{provider_name} provider error.",
        details=details,
    )


class GeminiProvider(BaseChatProvider):
    provider_name = "gemini"

    def __init__(self, model_name, settings=None):
        settings = settings or {}
        clean_name = str(model_name).strip()

        if clean_name.lower().startswith("gemini/"):
            clean_name = clean_name.split("/", 1)[1].strip()

        super().__init__(clean_name)

        self.api_key = settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Missing API key for Gemini. Please set GEMINI_API_KEY.")

        self.url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model_name}:streamGenerateContent?key={self.api_key}"
        )

    def _prepare_contents(self, prompt, history):
        return prepare_gemini_contents(prompt, history)

    def _extract_texts_from_response(self, data: Any) -> list[str]:
        return extract_gemini_texts_from_response(data)

    async def get_streaming_response(self, prompt, history):
        system_prompt = None
        if history and history[0].get("role") == "system":
            system_prompt = history[0].get("content")
        payload = build_gemini_generate_content_payload(
            prompt,
            history,
            system_prompt=system_prompt,
        )

        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
                response = await client.post(self.url, json=payload)

                if response.status_code != 200:
                    raw_text = response.text
                    raise classify_gemini_error_response(
                        response,
                        raw_text,
                        provider_name=self.provider_name,
                        model_name=self.model_name,
                        url=self.url,
                    )

                raw_text = response.text.strip()
                if not raw_text:
                    raise ProviderAPIError(
                        "Gemini returned an empty response body.",
                        kind="empty_response",
                        provider_name=self.provider_name,
                    )

                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError as e:
                    raise ProviderAPIError(
                        f"Gemini response was not valid JSON: {e}",
                        kind="invalid_provider_payload",
                        provider_name=self.provider_name,
                        raw_error=raw_text[:1000],
                    ) from e

                texts = self._extract_texts_from_response(data)
                if not texts:
                    raise ProviderAPIError(
                        "Gemini returned valid JSON but no text parts were found.",
                        kind="invalid_provider_payload",
                        provider_name=self.provider_name,
                        raw_error=raw_text[:1000],
                    )

                for text in texts:
                    yield text

        except httpx.RequestError as e:
            raise ProviderAPIError.unavailable(
                f"Gemini request error: {type(e).__name__}: {e}",
                provider_name=self.provider_name,
                raw_error=repr(e),
                details={"url": self.url, "model_name": self.model_name},
            ) from e
        except ProviderAPIError:
            raise
        except Exception as e:
            raise ProviderAPIError(
                f"Gemini unexpected error: {type(e).__name__}: {e}",
                kind="provider_error",
                provider_name=self.provider_name,
                raw_error=repr(e),
                details={"url": self.url, "model_name": self.model_name},
            ) from e
