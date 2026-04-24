"""Structured technical interruption helpers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from modules.providers.base import ProviderAPIError


@dataclass(slots=True)
class TechnicalInterruption:
    message: str
    kind: str = "technical_interruption"
    provider: str | None = None
    status_code: int | None = None
    recoverable: bool = True
    retryable: bool = True
    resumable: bool = False
    active_intent_id: str | None = None
    resumable_intent_id: str | None = None
    retry_after_seconds: float | None = None
    details: dict | None = None
    created_at: float = field(default_factory=time.time)


_STATUS_CODE_RE = re.compile(r"\b(?:api\s+error|http|status)\s*(?:code\s*)?(429|500|502|503|504|408)\b", re.IGNORECASE)
_PROVIDER_RE = re.compile(r"\b(gemini|openai|ollama|deepseek)\b", re.IGNORECASE)
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgemini returned valid json but no text parts\b", re.IGNORECASE), "invalid_provider_payload"),
    (re.compile(r"\bno text parts\b", re.IGNORECASE), "invalid_provider_payload"),
    (re.compile(r"\bempty provider response\b", re.IGNORECASE), "empty_response"),
    (re.compile(r"\breturned an empty response body\b", re.IGNORECASE), "empty_response"),
    (re.compile(r"\bservice unavailable\b", re.IGNORECASE), "provider_unavailable"),
    (re.compile(r"\brate limit\b", re.IGNORECASE), "rate_limit"),
    (re.compile(r"\bquota exceeded\b", re.IGNORECASE), "quota_exceeded"),
    (re.compile(r"\btimeout\b", re.IGNORECASE), "timeout"),
    (re.compile(r"\bconnection reset\b", re.IGNORECASE), "connection_error"),
    (re.compile(r"\bconnection error\b", re.IGNORECASE), "connection_error"),
]


def _normalize_provider(text: str) -> str | None:
    match = _PROVIDER_RE.search(text or "")
    return match.group(1).lower() if match else None


def _status_code(text: str) -> int | None:
    match = _STATUS_CODE_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _kind_from_text(text: str) -> str | None:
    for pattern, kind in _PATTERNS:
        if pattern.search(text or ""):
            return kind
    if _STATUS_CODE_RE.search(text or ""):
        return "provider_error"
    if re.search(r"^\s*error:\s*(gemini|openai|ollama|deepseek|provider|model)\b", text or "", re.IGNORECASE):
        return "provider_error"
    return None


def interruption_from_provider_error(error: ProviderAPIError, *, provider_name: str | None = None) -> TechnicalInterruption:
    provider = str(provider_name or error.provider_name or "").strip() or None
    kind = str(error.kind or "provider_error").strip() or "provider_error"
    retryable = kind not in {"auth_error", "provider_init_error"}
    recoverable = kind not in {"auth_error"}
    if error.status_code in {408, 429, 500, 502, 503, 504}:
        retryable = True
        recoverable = True
    message = str(error.user_message or error.message or "Provider error").strip()
    if error.status_code in {500, 502, 503, 504} and kind == "provider_error":
        message = f"{(provider or 'Provider').capitalize()} API temporarily unavailable"
    elif error.status_code == 429 and kind in {"provider_error", "rate_limit", "quota_exceeded"}:
        message = f"{(provider or 'Provider').capitalize()} rate limit reached"
    elif error.status_code == 408 and kind in {"provider_error", "provider_unavailable"}:
        message = f"{(provider or 'Provider').capitalize()} request timed out"
    return TechnicalInterruption(
        kind=kind,
        provider=provider,
        status_code=error.status_code,
        message=message,
        recoverable=recoverable,
        retryable=retryable,
        retry_after_seconds=error.retry_after_seconds,
        details=error.to_dict(),
    )


def detect_technical_interruption(value) -> TechnicalInterruption | None:
    if isinstance(value, TechnicalInterruption):
        return value
    if isinstance(value, ProviderAPIError):
        return interruption_from_provider_error(value)

    text = str(value or "").strip()
    if not text:
        return None

    kind = _kind_from_text(text)
    if not kind:
        return None

    status_code = _status_code(text)
    provider = _normalize_provider(text)
    retryable = True
    recoverable = True
    if kind == "auth_error":
        retryable = False
        recoverable = False

    return TechnicalInterruption(
        kind=kind,
        provider=provider,
        status_code=status_code,
        message=text,
        recoverable=recoverable,
        retryable=retryable,
        details={"detected_from_text": True},
    )
