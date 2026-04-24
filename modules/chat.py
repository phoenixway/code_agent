from __future__ import annotations

import logging

from modules.providers.base import ProviderAPIError
from modules.providers.gemini import GeminiProvider
from modules.providers.ollama import OllamaProvider
from modules.providers.openai import OpenAICompatibleProvider

log = logging.getLogger(__name__)

PROVIDERS = {
    "gemini": (GeminiProvider, []),
    "deepseek": (OpenAICompatibleProvider, ["https://api.deepseek.com", "DEEPSEEK_API_KEY"]),
    "gpt": (OpenAICompatibleProvider, ["https://api.openai.com/v1", "OPENAI_API_KEY"]),
    "ollama": (OllamaProvider, []),
    "qwen": (OllamaProvider, []),
    "llama": (OllamaProvider, []),
}


def _strip_provider_prefix(model_name: str, provider_keyword: str) -> str:
    if not model_name:
        return model_name

    text = str(model_name).strip()
    prefix = f"{provider_keyword}/"
    if text.lower().startswith(prefix):
        return text[len(prefix):].strip()

    return text


def get_chat_provider(model_name, settings=None):
    if not model_name or not str(model_name).strip():
        raise ProviderAPIError("No model name provided for provider initialization.")

    original_model_name = str(model_name).strip()
    m_lower = original_model_name.lower()
    settings = settings or {}

    for keyword, (provider_class, args) in PROVIDERS.items():
        if keyword in m_lower:
            try:
                if provider_class == OllamaProvider:
                    clean_name = _strip_provider_prefix(original_model_name, "ollama")
                    return provider_class(clean_name, settings=settings)

                if provider_class == GeminiProvider:
                    clean_name = _strip_provider_prefix(original_model_name, "gemini")
                    return provider_class(clean_name, settings=settings)

                return provider_class(original_model_name, *args)

            except ValueError as e:
                log.warning("Provider initialization failed for model '%s': %s", original_model_name, e)
                raise ProviderAPIError(
                    f"Provider initialization failed for '{original_model_name}': {e}",
                    kind="provider_init_error",
                    provider_name=keyword,
                    user_message=f"Provider initialization failed for {original_model_name}.",
                    raw_error=repr(e),
                ) from e
            except ProviderAPIError:
                raise
            except Exception as e:
                log.exception("Unexpected provider initialization failure for model '%s'", original_model_name)
                raise ProviderAPIError(
                    f"Unexpected provider initialization failure for '{original_model_name}': {type(e).__name__}: {e}",
                    kind="provider_init_error",
                    provider_name=keyword,
                    user_message=f"Unexpected provider initialization failure for {original_model_name}.",
                    raw_error=repr(e),
                ) from e

    try:
        return GeminiProvider("gemini-2.5-flash", settings=settings)
    except Exception as e:
        log.exception("Default provider initialization failed")
        raise ProviderAPIError(
            f"Default provider initialization failed: {type(e).__name__}: {e}",
            kind="provider_init_error",
            provider_name="gemini",
            user_message="Default provider initialization failed.",
            raw_error=repr(e),
        ) from e