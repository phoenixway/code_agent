from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .base import BaseChatProvider, ProviderAPIError
from .gemini import (
    build_gemini_generate_content_payload,
    extract_gemini_texts_from_response,
)

try:
    import google.auth
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except ImportError as exc:  # pragma: no cover - exercised indirectly by init error path
    GOOGLE_AUTH_IMPORT_ERROR = exc
    google = None
    GoogleAuthRequest = None
    service_account = None
else:
    GOOGLE_AUTH_IMPORT_ERROR = None


VERTEX_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _safe_error_text(response: httpx.Response) -> str:
    try:
        return response.text
    except Exception:
        return ""


def _extract_google_error_message(raw_text: str) -> str:
    if not raw_text:
        return ""

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text.strip()

    error = data.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        status = str(error.get("status") or "").strip()
        code = error.get("code")

        parts: list[str] = []
        if code:
            parts.append(f"code={code}")
        if status:
            parts.append(f"status={status}")
        if message:
            parts.append(message)

        return " | ".join(parts).strip()

    return raw_text.strip()


def extract_vertexai_texts_from_response(data: dict[str, Any]) -> list[str]:
    """
    Extract text from Vertex AI Gemini generateContent response.

    Expected non-streaming Vertex AI shape:

    {
      "candidates": [
        {
          "content": {
            "role": "model",
            "parts": [
              {"text": "Hello!"}
            ]
          },
          "finishReason": "STOP"
        }
      ]
    }

    Keep this separate from the Gemini Developer API extractor because provider
    response shapes may drift independently.
    """
    texts: list[str] = []

    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return texts

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content")
        if not isinstance(content, dict):
            continue

        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        for part in parts:
            if not isinstance(part, dict):
                continue

            text = part.get("text")
            if isinstance(text, str) and text:
                texts.append(text)

    return texts


def _extract_finish_reasons(data: dict[str, Any]) -> list[str]:
    finish_reasons: list[str] = []

    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return finish_reasons

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        finish_reason = candidate.get("finishReason")
        if isinstance(finish_reason, str) and finish_reason:
            finish_reasons.append(finish_reason)

    return finish_reasons


def classify_vertexai_error_response(
    response: httpx.Response,
    raw_text: str,
    *,
    provider_name: str,
    model_name: str,
    url: str,
    project_id: str,
    location: str,
) -> ProviderAPIError:
    google_message = _extract_google_error_message(raw_text)

    details = {
        "url": url,
        "model_name": model_name,
        "project_id": project_id,
        "location": location,
        "google_error": google_message,
    }

    if response.status_code in {401, 403}:
        suffix = f" Google says: {google_message}" if google_message else ""
        return ProviderAPIError(
            f"{provider_name} authentication/permission error ({response.status_code}).{suffix}",
            kind="vertexai_auth_error",
            status_code=response.status_code,
            provider_name=provider_name,
            raw_error=raw_text,
            user_message=(
                "Vertex AI authentication failed. Check Application Default Credentials, "
                "IAM permissions, billing, and that the Vertex AI API is enabled for this project."
                f"{suffix}"
            ),
            details={**details, "error_code": "VERTEXAI_AUTH_ERROR"},
        )

    if response.status_code == 404:
        suffix = f" Google says: {google_message}" if google_message else ""
        return ProviderAPIError(
            f"{provider_name} model or location not found ({response.status_code}).{suffix}",
            kind="vertexai_model_or_location_not_found",
            status_code=response.status_code,
            provider_name=provider_name,
            raw_error=raw_text,
            user_message=(
                "Vertex AI model or location was not found. Check model name, project_id, and location."
                f"{suffix}"
            ),
            details={**details, "error_code": "VERTEXAI_MODEL_OR_LOCATION_NOT_FOUND"},
        )

    if response.status_code == 429:
        suffix = f" Google says: {google_message}" if google_message else ""
        return ProviderAPIError(
            f"{provider_name} quota or rate limit reached ({response.status_code}).{suffix}",
            kind="vertexai_quota_or_rate_limit",
            status_code=response.status_code,
            provider_name=provider_name,
            raw_error=raw_text,
            user_message=(
                "Vertex AI quota or rate limit reached for this turn."
                f"{suffix}"
            ),
            details={**details, "error_code": "VERTEXAI_QUOTA_OR_RATE_LIMIT"},
        )

    suffix = f" Google says: {google_message}" if google_message else ""
    return ProviderAPIError(
        f"{provider_name} API Error {response.status_code}.{suffix}",
        kind="provider_error",
        status_code=response.status_code,
        provider_name=provider_name,
        raw_error=raw_text,
        user_message=f"Vertex AI provider error.{suffix}",
        details=details,
    )


class VertexAIProvider(BaseChatProvider):
    provider_name = "vertexai"

    def __init__(self, model_name, settings=None):
        settings = settings or {}

        clean_name = str(model_name).strip()
        if clean_name.lower().startswith("vertexai/"):
            clean_name = clean_name.split("/", 1)[1].strip()

        if not clean_name:
            raise ValueError(
                "Vertex AI model name is missing. Use model format like vertexai/gemini-2.5-flash."
            )

        super().__init__(clean_name)

        vertex_settings = settings.get("vertexai") or {}

        self.project_id = str(
            vertex_settings.get("project_id")
            or os.getenv("VERTEXAI_PROJECT_ID")
            or ""
        ).strip()

        self.location = str(
            vertex_settings.get("location")
            or os.getenv("VERTEXAI_LOCATION")
            or "us-central1"
        ).strip() or "us-central1"

        self.publisher = str(
            vertex_settings.get("publisher")
            or os.getenv("VERTEXAI_PUBLISHER")
            or "google"
        ).strip() or "google"

        self.use_adc = _as_bool(vertex_settings.get("use_adc", True), default=True)

        # Explicit service-account credential only.
        #
        # Do NOT manually parse GOOGLE_APPLICATION_CREDENTIALS here.
        # google.auth.default() knows how to handle user ADC and service accounts.
        self.credentials_json = str(
            vertex_settings.get("credentials_json")
            or os.getenv("VERTEXAI_CREDENTIALS_JSON")
            or ""
        ).strip()

        if not self.project_id:
            raise ValueError(
                "Vertex AI project_id is missing. Set vertexai.project_id or VERTEXAI_PROJECT_ID."
            )

        self.model_resource = (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/{self.publisher}/models/{self.model_name}"
        )
        self.url = self._build_generate_content_url()
        self._credentials = None

    def _build_generate_content_url(self) -> str:
        if self.location.lower() == "global":
            host = "https://aiplatform.googleapis.com"
        else:
            host = f"https://{self.location}-aiplatform.googleapis.com"

        return f"{host}/v1/{self.model_resource}:generateContent"

    def _raise_google_auth_import_error(self) -> None:
        hint = (
            "Vertex AI support requires google-auth and requests. "
            "Install them in Angelica's venv:\n"
            "/home/romankozak/studio/public/it/angelica-ai/venv/bin/python3 "
            "-m pip install google-auth requests"
        )

        if GOOGLE_AUTH_IMPORT_ERROR is None:
            raise ValueError(hint)

        raise ValueError(
            f"{hint}\nOriginal import error: {GOOGLE_AUTH_IMPORT_ERROR!r}"
        ) from GOOGLE_AUTH_IMPORT_ERROR

    def _load_credentials(self):
        if google is None or GoogleAuthRequest is None:
            self._raise_google_auth_import_error()

        if self.credentials_json:
            if service_account is None:
                raise ValueError(
                    "Vertex AI support requires google-auth service account support. "
                    f"Original import error: {GOOGLE_AUTH_IMPORT_ERROR!r}"
                )

            path_candidate = Path(self.credentials_json)
            if path_candidate.exists():
                return service_account.Credentials.from_service_account_file(
                    str(path_candidate),
                    scopes=[VERTEX_CLOUD_SCOPE],
                )

            try:
                info = json.loads(self.credentials_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "VERTEXAI_CREDENTIALS_JSON must be a valid service account JSON string "
                    "or a path to a service account JSON file."
                ) from exc

            return service_account.Credentials.from_service_account_info(
                info,
                scopes=[VERTEX_CLOUD_SCOPE],
            )

        if self.use_adc:
            try:
                credentials, _project = google.auth.default(scopes=[VERTEX_CLOUD_SCOPE])
            except Exception as exc:
                raise ValueError(
                    "Vertex AI credentials are missing or invalid. Configure Google "
                    "Application Default Credentials with:\n"
                    "gcloud auth application-default login\n"
                    "Also check VERTEXAI_PROJECT_ID and VERTEXAI_LOCATION."
                ) from exc

            return credentials

        raise ValueError(
            "Vertex AI credentials are missing. Configure Google Application Default "
            "Credentials or explicit VERTEXAI_CREDENTIALS_JSON."
        )

    def _get_access_token(self) -> str:
        if self._credentials is None:
            self._credentials = self._load_credentials()

        credentials = self._credentials

        if GoogleAuthRequest is None:
            self._raise_google_auth_import_error()

        if not getattr(credentials, "valid", False) or getattr(credentials, "token", None) is None:
            try:
                credentials.refresh(GoogleAuthRequest())
            except Exception as exc:
                raise ValueError(
                    "Vertex AI credentials could not be refreshed. Check ADC/service account "
                    "credentials, IAM permissions, billing, and that Vertex AI API is enabled."
                ) from exc

        token = str(getattr(credentials, "token", "") or "").strip()
        if not token:
            raise ValueError(
                "Vertex AI credentials did not produce an access token. Configure Google "
                "Application Default Credentials or service account credentials."
            )

        return token

    async def get_streaming_response(self, prompt, history):
        payload = build_gemini_generate_content_payload(
            prompt,
            history,
            system_key="systemInstruction",
        )

        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

        try:
            # TODO: add streamGenerateContent when/if UI benefits from true incremental Vertex streaming.
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
                response = await client.post(self.url, headers=headers, json=payload)

            if response.status_code != 200:
                raise classify_vertexai_error_response(
                    response,
                    _safe_error_text(response),
                    provider_name=self.provider_name,
                    model_name=self.model_name,
                    url=self.url,
                    project_id=self.project_id,
                    location=self.location,
                )

            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise ProviderAPIError(
                    f"{self.provider_name} returned invalid JSON.",
                    kind="provider_error",
                    status_code=response.status_code,
                    provider_name=self.provider_name,
                    raw_error=response.text,
                    user_message="Vertex AI returned invalid JSON.",
                    details={
                        "url": self.url,
                        "model_name": self.model_name,
                        "project_id": self.project_id,
                        "location": self.location,
                    },
                ) from exc

            texts = extract_vertexai_texts_from_response(data)
            if not texts:
                texts = extract_gemini_texts_from_response(data)

            if not texts:
                finish_reasons = _extract_finish_reasons(data)
                prompt_feedback = data.get("promptFeedback")
                raw_json = json.dumps(data, ensure_ascii=False)
                raw_preview = raw_json[:1200]

                raise ProviderAPIError(
                    f"{self.provider_name} returned no text.",
                    kind="provider_error",
                    status_code=response.status_code,
                    provider_name=self.provider_name,
                    raw_error=raw_json,
                    user_message=(
                        "Vertex AI returned no text. "
                        f"finish_reasons={finish_reasons or 'none'}; "
                        f"prompt_feedback={prompt_feedback or 'none'}; "
                        f"raw_preview={raw_preview}"
                    ),
                    details={
                        "url": self.url,
                        "model_name": self.model_name,
                        "project_id": self.project_id,
                        "location": self.location,
                        "finish_reasons": finish_reasons,
                        "prompt_feedback": prompt_feedback,
                    },
                )

            # Keep the provider contract compatible with streaming callers:
            # yield one complete chunk for now.
            yield "".join(texts)

        except ProviderAPIError:
            raise
        except ValueError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderAPIError(
                f"{self.provider_name} HTTP error: {exc}",
                kind="provider_error",
                status_code=None,
                provider_name=self.provider_name,
                raw_error=str(exc),
                user_message="Vertex AI HTTP request failed.",
                details={
                    "url": self.url,
                    "model_name": self.model_name,
                    "project_id": self.project_id,
                    "location": self.location,
                },
            ) from exc