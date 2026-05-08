from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from modules.system_prompts import load_active_system_prompt


class ProviderAPIError(Exception):
    """Structured exception for provider/API/runtime failures."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "provider_error",
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        provider_name: str | None = None,
        user_message: str | None = None,
        raw_error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message or "").strip() or "Provider error"
        self.kind = str(kind or "provider_error").strip()
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.provider_name = str(provider_name or "").strip() or None
        self.user_message = str(user_message or "").strip() or None
        self.raw_error = str(raw_error or "").strip() or None
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "kind": self.kind,
            "status_code": self.status_code,
            "retry_after_seconds": self.retry_after_seconds,
            "provider_name": self.provider_name,
            "user_message": self.user_message,
            "raw_error": self.raw_error,
            "details": self.details,
        }

    @property
    def is_rate_limit(self) -> bool:
        return self.kind in {"rate_limit", "quota_exceeded"}

    @classmethod
    def rate_limit(
        cls,
        message: str,
        *,
        status_code: int | None = 429,
        retry_after_seconds: float | None = None,
        provider_name: str | None = None,
        raw_error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ProviderAPIError":
        return cls(
            message,
            kind="rate_limit",
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
            provider_name=provider_name,
            raw_error=raw_error,
            user_message="Provider rate limit reached for this turn.",
            details=details,
        )

    @classmethod
    def quota_exceeded(
        cls,
        message: str,
        *,
        status_code: int | None = 429,
        retry_after_seconds: float | None = None,
        provider_name: str | None = None,
        raw_error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ProviderAPIError":
        return cls(
            message,
            kind="quota_exceeded",
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
            provider_name=provider_name,
            raw_error=raw_error,
            user_message="Provider quota exceeded for this turn.",
            details=details,
        )

    @classmethod
    def unavailable(
        cls,
        message: str,
        *,
        status_code: int | None = None,
        provider_name: str | None = None,
        raw_error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ProviderAPIError":
        return cls(
            message,
            kind="provider_unavailable",
            status_code=status_code,
            provider_name=provider_name,
            raw_error=raw_error,
            user_message="Provider is temporarily unavailable.",
            details=details,
        )

    @classmethod
    def auth(
        cls,
        message: str,
        *,
        status_code: int | None = 401,
        provider_name: str | None = None,
        raw_error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ProviderAPIError":
        return cls(
            message,
            kind="auth_error",
            status_code=status_code,
            provider_name=provider_name,
            raw_error=raw_error,
            user_message="Provider authentication failed.",
            details=details,
        )


class BaseChatProvider(ABC):
    """Abstract base class for all chat providers."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def _prepare_messages(self, prompt: str, history: list) -> list:
        messages: list[dict[str, str]] = []
        system_already_present = bool(history and history[0].get("role") == "system")
        if not system_already_present:
            messages.append({"role": "system", "content": load_active_system_prompt()})

        for msg in history:
            content = msg.get("content", "").strip()
            if content:
                messages.append({"role": msg["role"], "content": content})

        if prompt and prompt.strip():
            messages.append({"role": "user", "content": prompt.strip()})

        return messages

    @abstractmethod
    async def get_streaming_response(self, prompt: str, history: list):
        raise NotImplementedError
