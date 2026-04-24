"""Guard and streak policy helpers for response pipeline."""

from __future__ import annotations


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

    def set_reflection_repair_pending(self, value: bool) -> None:
        try:
            setattr(self.state, "think_reflection_repair_pending", bool(value))
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
        if not semantics.has_substantial_think(raw_response):
            return False
        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
            return False
        if plaintext_answer_path:
            return False
        if memory_checkpoint_and_action or memory_checkpoint_and_text:
            return False
        if reflection_only_repair:
            return False
        return True