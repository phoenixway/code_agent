from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static
from rich.text import Text

from modules.agent.technical_interruptions import TechnicalInterruption


def build_technical_interruption_view_model(interruption: TechnicalInterruption | dict | None) -> dict:
    payload = interruption if isinstance(interruption, dict) else None
    if interruption is not None and not isinstance(interruption, dict):
        payload = {
            "kind": interruption.kind,
            "provider": interruption.provider,
            "status_code": interruption.status_code,
            "message": interruption.message,
            "recoverable": interruption.recoverable,
            "retryable": interruption.retryable,
            "resumable": interruption.resumable,
            "active_intent_id": interruption.active_intent_id,
            "resumable_intent_id": interruption.resumable_intent_id,
        }
    payload = dict(payload or {})

    provider = str(payload.get("provider") or "Model").strip()
    status_code = payload.get("status_code")
    message = str(payload.get("message") or "Technical interruption").strip()
    resumable = bool(payload.get("resumable"))
    retryable = bool(payload.get("retryable", True))

    title = "Технічна помилка моделі"
    provider_line = provider.capitalize()
    if status_code is not None:
        provider_line = f"{provider_line}: {status_code}."
    elif provider_line:
        provider_line = f"{provider_line}."

    if resumable:
        summary = "Роботу не завершено. Можна відновити з останнього безпечного стану."
        action_label = "Відновити роботу"
        action_kind = "resume"
        action_enabled = True
    else:
        summary = "Роботу не завершено. Можна повторити запит після відновлення сервісу."
        action_label = "Retry"
        action_kind = "retry"
        action_enabled = retryable

    return {
        "title": title,
        "provider_line": provider_line,
        "message": message,
        "summary": summary,
        "action_label": action_label,
        "action_kind": action_kind,
        "action_enabled": action_enabled,
    }


class TechnicalInterruptionWidget(Static):
    DEFAULT_CSS = """
    TechnicalInterruptionWidget {
        border: round $warning;
        padding: 1;
        width: 1fr;
    }

    TechnicalInterruptionWidget .technical-interruption-title {
        text-style: bold;
    }

    TechnicalInterruptionWidget .technical-interruption-actions {
        margin-top: 1;
    }
    """

    class ResumeRequested(Message):
        def __init__(self, interruption: TechnicalInterruption | dict | None, action_kind: str) -> None:
            super().__init__()
            self.interruption = interruption
            self.action_kind = action_kind

    def __init__(self, interruption: TechnicalInterruption | dict | None):
        super().__init__(classes="chat-message technical-interruption-message", expand=False)
        self.interruption = interruption
        self.view_model = build_technical_interruption_view_model(interruption)
        self.can_focus = False

    def compose(self) -> ComposeResult:
        title = Text(self.view_model["title"], style="bold yellow")
        provider_line = Text(self.view_model["provider_line"], style="bold")
        message = Text(self.view_model["message"])
        summary = Text(self.view_model["summary"], style="dim")
        action_label = str(self.view_model["action_label"])
        disabled = not bool(self.view_model["action_enabled"])

        yield Vertical(
            Static(title, classes="technical-interruption-title"),
            Static(provider_line, classes="technical-interruption-provider"),
            Static(message, classes="technical-interruption-message-text"),
            Static(summary, classes="technical-interruption-summary"),
            Horizontal(
                Button(
                    action_label,
                    id="technical-interruption-action",
                    variant="primary",
                    disabled=disabled,
                ),
                classes="technical-interruption-actions",
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "technical-interruption-action":
            return
        self.post_message(
            self.ResumeRequested(
                self.interruption,
                str(self.view_model.get("action_kind") or "resume"),
            )
        )
