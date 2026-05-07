"""Guard and streak policy helpers for response pipeline."""

from __future__ import annotations

from .semantic_accessors import has_substantial_think


class ResponseGuardPolicy:
    def __init__(self, state):
        self.state = state

    def memory_checkpoint_streak(self) -> int:
        return int(getattr(self.state, "consecutive_memory_checkpoint_only_count", 0) or 0)

    def nonproductive_thinking_streak(self) -> int:
        return int(getattr(self.state, "consecutive_nonproductive_thinking_count", 0) or 0)

    def set_nonproductive_thinking_state(self, value: bool, reason: str = "") -> int:
        current = int(getattr(self.state, "consecutive_nonproductive_thinking_count", 0) or 0)
        if value:
            current += 1
        else:
            current = 0
            reason = ""
        try:
            setattr(self.state, "consecutive_nonproductive_thinking_count", current)
            setattr(self.state, "last_nonproductive_thinking_reason", str(reason or ""))
        except Exception:
            pass
        return current

    def reflection_repair_pending(self) -> bool:
        return bool(getattr(self.state, "think_reflection_repair_pending", False))

    def reflection_repair_kind(self) -> str:
        return str(getattr(self.state, "think_reflection_repair_kind", "") or "").strip()

    def set_reflection_repair_pending(self, value: bool, kind: str = "") -> None:
        try:
            setattr(self.state, "think_reflection_repair_pending", bool(value))
            setattr(self.state, "think_reflection_repair_kind", str(kind or "").strip() if value else "")
        except Exception:
            pass

    def note_missing_think_reflection_warning(self, intent_id: str = "") -> int:
        normalized_intent_id = str(intent_id or "").strip()
        current_intent_id = str(getattr(self.state, "missing_think_reflection_warning_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "missing_think_reflection_warning_count", 0) or 0)

        if not normalized_intent_id or normalized_intent_id != current_intent_id:
            current_count = 0

        current_count += 1
        try:
            setattr(self.state, "missing_think_reflection_warning_count", current_count)
            setattr(self.state, "missing_think_reflection_warning_intent_id", normalized_intent_id)
        except Exception:
            pass
        return current_count

    def clear_missing_think_reflection_warning(self) -> None:
        try:
            setattr(self.state, "missing_think_reflection_warning_count", 0)
            setattr(self.state, "missing_think_reflection_warning_intent_id", "")
        except Exception:
            pass

    def clear_terminal_plaintext_completion(self) -> None:
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", False)
            setattr(self.state, "terminal_plaintext_completion_text", "")
        except Exception:
            pass

    def is_nonproductive_thinking_turn(
        self,
        semantics,
        raw_response: str,
        parsed_output,
        parsed_action_count: int,
        *,
        plaintext_answer_path: bool,
        intent_transition_handled: bool = False,
        memory_checkpoint_and_action: bool = False,
        memory_checkpoint_and_text: bool = False,
        reflection_only_repair: bool = False,
    ) -> bool:
        if intent_transition_handled:
            return False
        if not has_substantial_think(raw_response):
            return False
        if semantics.has_any_action_proposal(parsed_output, parsed_action_count):
            return False
        if plaintext_answer_path:
            return False
        if memory_checkpoint_and_action or memory_checkpoint_and_text:
            return False
        if reflection_only_repair:
            return False
        return True
