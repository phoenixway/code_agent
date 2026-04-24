from __future__ import annotations

import json
import os

import httpx

from .base import BaseChatProvider, ProviderAPIError


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
            "insufficient_quota",
            "rate limit",
            "too many requests",
            "resource exhausted",
        ]
    )


class OpenAICompatibleProvider(BaseChatProvider):
    def __init__(self, model_name, base_url, api_key_env):
        super().__init__(model_name)
        self.base_url = base_url.rstrip("/")
        self.api_key = os.getenv(api_key_env)
        self.provider_name = self._infer_provider_name(self.base_url, model_name)
        if not self.api_key:
            raise ValueError(
                f"Missing API key for {model_name}. Please set the {api_key_env} environment variable."
            )

    @staticmethod
    def _infer_provider_name(base_url: str, model_name: str) -> str:
        text = f"{base_url} {model_name}".lower()
        if "openai" in text or "gpt" in text:
            return "openai"
        if "deepseek" in text:
            return "deepseek"
        return "openai_compatible"

    async def get_streaming_response(self, prompt, history):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": self._prepare_messages(prompt, history),
            "temperature": 0.2,
            "stream": True,
        }

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_bytes = await response.aread()
                        raw_text = error_bytes.decode("utf-8", errors="replace")
                        retry_after = _parse_retry_after_seconds(response)
                        details = {"url": url, "model_name": self.model_name}
                        if response.status_code == 429:
                            if _looks_like_quota_error(raw_text):
                                raise ProviderAPIError.quota_exceeded(
                                    f"{self.provider_name} quota exceeded ({response.status_code}).",
                                    status_code=response.status_code,
                                    retry_after_seconds=retry_after,
                                    provider_name=self.provider_name,
                                    raw_error=raw_text,
                                    details=details,
                                )
                            raise ProviderAPIError.rate_limit(
                                f"{self.provider_name} rate limit error ({response.status_code}).",
                                status_code=response.status_code,
                                retry_after_seconds=retry_after,
                                provider_name=self.provider_name,
                                raw_error=raw_text,
                                details=details,
                            )
                        if response.status_code in {401, 403}:
                            raise ProviderAPIError.auth(
                                f"{self.provider_name} authentication/permission error ({response.status_code}).",
                                status_code=response.status_code,
                                provider_name=self.provider_name,
                                raw_error=raw_text,
                                details=details,
                            )
                        raise ProviderAPIError(
                            f"{self.provider_name} API Error {response.status_code}",
                            kind="provider_error",
                            status_code=response.status_code,
                            provider_name=self.provider_name,
                            raw_error=raw_text,
                            user_message=f"{self.provider_name} provider error.",
                            details=details,
                        )

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        line_text = line[6:]
                        if line_text == "[DONE]":
                            break
                        try:
                            data = json.loads(line_text)
                            choices = data.get("choices", [])
                            if choices:
                                content = choices[0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.RequestError as e:
            raise ProviderAPIError.unavailable(
                f"{self.provider_name} network error: {type(e).__name__}: {e}",
                provider_name=self.provider_name,
                raw_error=repr(e),
                details={"url": url, "model_name": self.model_name},
            ) from e
        except ProviderAPIError:
            raise
        except Exception as e:
            raise ProviderAPIError(
                f"{self.provider_name} error: {type(e).__name__}: {e}",
                kind="provider_error",
                provider_name=self.provider_name,
                raw_error=repr(e),
                details={"url": url, "model_name": self.model_name},
            ) from e