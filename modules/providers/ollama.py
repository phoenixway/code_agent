from __future__ import annotations

import json
import os

import httpx

from .base import BaseChatProvider, ProviderAPIError


class OllamaProvider(BaseChatProvider):
    provider_name = "ollama"

    def __init__(self, model_name, settings=None):
        super().__init__(model_name)

        settings = settings or {}

        raw_base_url = (
            settings.get("ollama_base_url")
            or os.getenv("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434"
        )

        raw_base_url = str(raw_base_url).strip().rstrip("/")

        if raw_base_url.endswith("/api/chat"):
            self.base_url = raw_base_url[:-9].rstrip("/")
        else:
            self.base_url = raw_base_url

        self.url = f"{self.base_url}/api/chat"

    async def get_streaming_response(self, prompt, history):
        payload = {
            "model": self.model_name,
            "messages": self._prepare_messages(prompt, history),
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
                async with client.stream("POST", self.url, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raw_text = error_text.decode("utf-8", errors="replace")
                        if response.status_code == 429:
                            raise ProviderAPIError.rate_limit(
                                f"Ollama rate limit error ({response.status_code}) at {self.url}",
                                status_code=response.status_code,
                                provider_name=self.provider_name,
                                raw_error=raw_text,
                                details={"url": self.url, "model_name": self.model_name},
                            )
                        raise ProviderAPIError(
                            f"Ollama Error {response.status_code} at {self.url}",
                            kind="provider_error",
                            status_code=response.status_code,
                            provider_name=self.provider_name,
                            raw_error=raw_text,
                            user_message="Ollama provider error.",
                            details={"url": self.url, "model_name": self.model_name},
                        )

                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if "message" in data:
                            content = data["message"].get("content", "")
                            if content:
                                yield content

                        if data.get("done"):
                            break

        except httpx.RequestError as e:
            raise ProviderAPIError.unavailable(
                f"Ollama request error to {self.url}: {type(e).__name__}: {repr(e)}",
                provider_name=self.provider_name,
                raw_error=repr(e),
                details={"url": self.url, "model_name": self.model_name},
            ) from e
        except ProviderAPIError:
            raise
        except Exception as e:
            raise ProviderAPIError(
                f"Ollama unexpected error at {self.url}: {type(e).__name__}: {repr(e)}",
                kind="provider_error",
                provider_name=self.provider_name,
                raw_error=repr(e),
                details={"url": self.url, "model_name": self.model_name},
            ) from e