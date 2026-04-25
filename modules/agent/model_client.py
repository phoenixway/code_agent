"""Клієнт для роботи з AI моделями."""

import json
import re

from modules.chat import get_chat_provider
from modules.history import HistoryManager
from modules.providers.base import ProviderAPIError
from .technical_interruptions import TechnicalInterruption as ModelTechnicalInterruption
from .technical_interruptions import interruption_from_provider_error


class ModelTechnicalInterruptionError(Exception):
    def __init__(self, interruption: ModelTechnicalInterruption):
        self.interruption = interruption
        super().__init__(interruption.message)

class ModelClient:
    """Відповідає за комунікацію з LLM та управління контекстом запиту."""
    ACTION_BLOCK_RE = re.compile(r"<action(?:\s+[^>]*)?>(.*?)</action>", re.IGNORECASE | re.DOTALL)
    FILE_CONTENT_OPEN_RE = re.compile(r"<file_content(?:\s+[^>]*)?>", re.IGNORECASE)
    FILE_CONTENT_FULL_RE = re.compile(r"<file_content(?:\s+[^>]*)?>.*?</file_content>", re.IGNORECASE | re.DOTALL)
    FILE_BLOCK_ACTION_TYPES = {"write_file_block", "append_file_block"}
    
    def __init__(self, config, logger=None, comm_logger=None):
        self.config = config
        self.log = logger
        self.comm_log = comm_logger # Відновлено логер комунікації
        self.chat = get_chat_provider(config.default_model, settings=getattr(config, "settings", None))
        self._tokenizer_warning_logged = False
        self._smart_stop_trailing_text_limit = 200
        
    async def get_streaming_response(
        self,
        query: str,
        history_manager: HistoryManager,
        ui=None,
        state=None,
        system_message: str | None = None,
        injected_messages: list[dict[str, str]] | None = None,
    ):
        """Отримує відповідь від моделі частинами з підтримкою Smart Stop."""
        full_text = ""
        if state is not None:
            try:
                setattr(state, "last_model_response_stop_reason", "")
            except Exception:
                pass
        history_data = history_manager.get_history_for_api()
        if system_message and isinstance(system_message, str):
            history_data = [{"role": "system", "content": system_message}] + history_data
        if injected_messages:
            normalized_messages = []
            for message in injected_messages:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role", "") or "").strip()
                content = message.get("content", "")
                if role and isinstance(content, str) and content.strip():
                    normalized_messages.append({"role": role, "content": content})
            if normalized_messages:
                history_data = history_data + normalized_messages

        if self.log:
            self.log.debug(
                "Model.request query_chars=%s history_messages=%s system_message_chars=%s injected_messages=%s",
                len(query or ""),
                len(history_data),
                len(system_message or "") if isinstance(system_message, str) else 0,
                len(injected_messages or []),
            )
            if isinstance(system_message, str) and system_message.strip():
                self.log.debug("Model.request.system_message\n%s", system_message)
            if injected_messages:
                try:
                    self.log.debug(
                        "Model.request.injected_messages\n%s",
                        json.dumps(injected_messages, ensure_ascii=False, indent=2),
                    )
                except Exception as e:
                    self.log.warning("Model.request injected message serialization failed: %s", e)
            try:
                self.log.debug(
                    "Model.request.history_payload\n%s",
                    json.dumps(history_data, ensure_ascii=False, indent=2),
                )
            except Exception as e:
                self.log.warning("Model.request history payload serialization failed: %s", e)
        
        # 1. Логування вихідного запиту
        if self.comm_log:
            self.comm_log.info(self._format_comm_block("OUTGOING", query))
        
        try:
            async for chunk in self.chat.get_streaming_response(query, history_data):
                full_text += chunk
                
                # --- SMART STOP LOGIC ---
                # Зупиняємо достроково лише коли вже є повні action-блоки
                # і модель продовжує "балакати" поза ними.
                # Це не ріже multi-action батчі (кілька <action>...</action> підряд).
                if self._should_smart_stop(full_text):
                    if state is not None:
                        try:
                            setattr(state, "last_model_response_stop_reason", "smart_stop_trailing_non_action")
                        except Exception:
                            pass
                    if self.comm_log:
                        self.comm_log.info("--- SMART STOP TRIGGERED (trailing non-action text detected) ---")
                    # Примусово обриваємо генерацію
                    break
                # ------------------------

        except ProviderAPIError as e:
            interruption = self._provider_error_to_interruption(e)
            if self.log:
                self.log.error("AI provider interruption: %s", interruption.message)
            raise ModelTechnicalInterruptionError(interruption) from e
        except Exception as e:
            interruption = ModelTechnicalInterruption(
                provider=str(getattr(self.chat, "provider_name", "") or getattr(self.chat, "model_name", "") or "model"),
                message=f"Model runtime error: {type(e).__name__}: {e}",
                kind="model_runtime_error",
                recoverable=True,
                retryable=True,
                details={"raw_error": repr(e)},
            )
            if self.log:
                self.log.error("AI runtime interruption: %s", interruption.message)
            raise ModelTechnicalInterruptionError(interruption) from e
        
        # 2. Логування вхідної відповіді (вже обрізаної)
        if self.comm_log:
            self.comm_log.info(self._format_comm_block("INCOMING", full_text))
        if self.log:
            self.log.debug(
                "Model.response raw_chars=%s smart_stop_limit=%s",
                len(full_text or ""),
                self._smart_stop_trailing_text_limit,
            )
            self.log.debug("Model.response.raw\n%s", full_text)
            
        # 3. Оновлення статистики токенів
        if state and ui:
            await self._update_token_stats(query, full_text, history_manager, ui, state)
            
        return full_text

    def _provider_error_to_interruption(self, error: ProviderAPIError) -> ModelTechnicalInterruption:
        return interruption_from_provider_error(
            error,
            provider_name=str(
                getattr(self.chat, "provider_name", "")
                or getattr(self.chat, "model_name", "")
                or "provider"
            ).strip(),
        )

    def _format_comm_block(self, direction: str, payload: str) -> str:
        """
        Build a compact communication-log block without extra empty lines
        above/below payload.
        """
        body = "" if payload is None else str(payload).strip("\n")
        if not body:
            return f"--- {direction} ---"
        return f"--- {direction} ---\n{body}"

    def _should_smart_stop(self, full_text: str) -> bool:
        if not full_text or "</action>" not in full_text:
            return False
        lower = full_text.lower()
        open_count = lower.count("<action")
        close_count = lower.count("</action>")
        # Якщо ще незакриті action-блоки, чекати далі.
        if close_count < open_count:
            return False
        last_close = lower.rfind("</action>")
        if last_close == -1:
            return False
        trailing = full_text[last_close + len("</action>"):]
        trailing_stripped = trailing.lstrip()
        if not trailing_stripped:
            return False
        if self._trailing_valid_file_content_package(full_text, trailing_stripped):
            return False
        # Якщо далі одразу стартує наступний action-блок — це валідний батч.
        if trailing_stripped.lower().startswith("<action"):
            return False
        # Дозволяємо короткі пробіли/службовий шум; блокуємо довгий "хвіст" поза action.
        return len(trailing_stripped) >= self._smart_stop_trailing_text_limit

    def _last_completed_action_type(self, full_text: str) -> str:
        matches = list(self.ACTION_BLOCK_RE.finditer(str(full_text or "")))
        if not matches:
            return ""
        body = (matches[-1].group(1) or "").strip()
        try:
            payload = json.loads(body)
        except Exception:
            start = body.find("{")
            end = body.rfind("}")
            if start < 0 or end < 0 or start >= end:
                return ""
            try:
                payload = json.loads(body[start : end + 1])
            except Exception:
                return ""
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("type") or payload.get("action") or "").strip().lower()

    def _trailing_valid_file_content_package(self, full_text: str, trailing_stripped: str) -> bool:
        if not isinstance(trailing_stripped, str) or not trailing_stripped.lower().startswith("<file_content"):
            return False
        if self._last_completed_action_type(full_text) not in self.FILE_BLOCK_ACTION_TYPES:
            return False
        if not self.FILE_CONTENT_OPEN_RE.match(trailing_stripped):
            return False
        full_match = self.FILE_CONTENT_FULL_RE.match(trailing_stripped)
        if full_match is None:
            # The model is still streaming the raw file body; do not smart-stop yet.
            return True
        trailing_after_block = trailing_stripped[full_match.end():].lstrip()
        if not trailing_after_block:
            return True
        if trailing_after_block.lower().startswith("<action"):
            return True
        return False
    
    async def _update_token_stats(self, query, response, history_manager, ui, state):
        """Підраховує токени та оновлює UI."""
        try:
            p_tokens = self._estimate_tokens(query)
            c_tokens = self._estimate_tokens(response)
            
            state.add_tokens(p_tokens, c_tokens)
            
            if hasattr(ui, 'update_token_status'):
                await ui.update_token_status(
                    history_tokens=history_manager.current_token_count,
                    max_tokens=history_manager.max_tokens,
                    session_tokens=state.session_tokens
                )
        except Exception as e:
            if self.log: self.log.warning(f"Token update failed: {e}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate tokens safely even if provider has no tokenizer support."""
        tokenizer = None
        get_tokenizer = getattr(self.chat, "get_tokenizer", None)
        if callable(get_tokenizer):
            try:
                tokenizer = get_tokenizer()
            except Exception as e:
                if self.log and not self._tokenizer_warning_logged:
                    self.log.warning(f"Tokenizer unavailable, using fallback estimation: {e}")
                    self._tokenizer_warning_logged = True
        elif self.log and not self._tokenizer_warning_logged:
            self.log.info(
                "Provider has no get_tokenizer(); using character-based token estimation."
            )
            self._tokenizer_warning_logged = True

        if tokenizer and hasattr(tokenizer, "encode"):
            try:
                return len(tokenizer.encode(text))
            except Exception:
                # If tokenizer fails for some text, fallback to approximation.
                pass
        if not text:
            return 0
        return max(1, len(text) // 4)

    async def switch_model(self, model_name: str, ui=None):
        """Перемикає провайдера моделі."""
        if hasattr(self.chat, 'model_name') and self.chat.model_name == model_name:
            if ui: await ui.print_system(f"Модель {model_name} вже активна.")
            return True

        if ui: await ui.print_system(f"Перемикаюсь на {model_name}...")
        
        new_provider = get_chat_provider(model_name, settings=getattr(self.config, "settings", None))
        if new_provider:
            self.chat = new_provider
            if ui:
                await ui.update_header(f"{self.chat.model_name}")
                await ui.print_system(f"Модель змінено на {model_name}")
            return True
        return False
