"""Memory-board response application stage for orchestrator model output."""

from __future__ import annotations

import re

from .decision_models import MemoryBoardDecision
from .responses.stage_logging import OrchestrationStageLogger


class MemoryBoardStageHandler:
    THINK_BLOCK_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    MEMORY_BLOCK_RE = re.compile(
        r"<(fact|finding|decision|preference|progress|path)\b[^>]*>.*?</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    MEMORY_REVIEW_RE = re.compile(r"<memory_review\b[^>]*/>", re.IGNORECASE)
    SUBGOAL_BLOCK_RE = re.compile(r"<subgoal\b[^>]*(?:>.*?</subgoal>|/>)", re.IGNORECASE | re.DOTALL)
    MEMORY_UPDATE_DONE_RE = re.compile(r"<memory_update_done\s*/>", re.IGNORECASE)
    ACTION_BLOCK_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
    ACTION_TAG_RE = re.compile(r"<action\b", re.IGNORECASE)
    GENERIC_TAG_RE = re.compile(r"</?[^>]+>", re.IGNORECASE)

    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.memory_board_engine = getattr(agent, "memory_board_engine", None)
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def _safe_setattr(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass

    def _safe_getattr(self, obj, name: str, default=None):
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    def _strip_memory_update_done(self, text: str) -> str:
        value = str(text or "")
        value = self.MEMORY_REVIEW_RE.sub(" ", value)
        value = self.MEMORY_UPDATE_DONE_RE.sub(" ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    def _set_memory_checkpoint_state(self, value: bool) -> int:
        current = int(getattr(self.state, "consecutive_memory_checkpoint_only_count", 0) or 0)
        current = current + 1 if value else 0
        self._safe_setattr("last_memory_checkpoint_only", bool(value))
        self._safe_setattr("consecutive_memory_checkpoint_only_count", current)
        return current

    def _strip_control_blocks_for_visible_text(self, text: str) -> str:
        """Strip control-only blocks.

        Memory tag content is checkpoint payload, not user-facing final text.
        This method is intentionally based on the memory-engine clean_text,
        not on the raw model response, because tests and real engine behavior
        may pass placeholders/raw text while clean_text is authoritative after
        memory extraction.
        """
        value = str(text or "")
        if not value.strip():
            return ""

        value = self.THINK_BLOCK_RE.sub(" ", value)
        value = self.ACTION_BLOCK_RE.sub(" ", value)
        value = self.MEMORY_BLOCK_RE.sub(" ", value)
        value = self.MEMORY_REVIEW_RE.sub(" ", value)
        value = self.SUBGOAL_BLOCK_RE.sub(" ", value)
        value = self.MEMORY_UPDATE_DONE_RE.sub(" ", value)
        value = self.GENERIC_TAG_RE.sub(" ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _cleaned_response_is_checkpoint_only(self, clean_response: str) -> bool:
        return not bool(self._strip_control_blocks_for_visible_text(clean_response))

    def _cleaned_response_has_visible_text(self, clean_response: str) -> bool:
        return bool(self._strip_control_blocks_for_visible_text(clean_response))

    def _response_has_action(self, response_text: str) -> bool:
        return bool(self.ACTION_TAG_RE.search(str(response_text or "")))


    def _build_checkpoint_followup_query(self, streak: int) -> str:
        prefix = "SYSTEM: Memory updates were recorded. "

        if streak >= 3:
            return (
                prefix
                + "Do not return memory tags only again. "
                "Return exactly one of the following: "
                "(1) one valid <action>, "
                "(2) a brief plain-text continuation explaining what you still need to determine, "
                "or (3) a final plain-text answer if current evidence is enough."
            )

        if streak == 2:
            return (
                prefix
                + "Now continue the task substantively. "
                "Think further, or return one valid <action>, or return a final plain-text answer if enough is already known. "
                "Avoid another memory-tags-only reply immediately."
            )

        return (
            prefix
            + "Now continue the current task. "
            "Think further, or return the next valid <action> if tool use is needed, or answer plainly if enough is already known."
        )
    
    async def apply(self, ctx, response: str) -> MemoryBoardDecision:
        board_result = None
        clean_response = response

        self._safe_setattr("last_memory_board_parsed_count", 0)
        self._safe_setattr("last_memory_board_accepted_count", 0)
        self._safe_setattr("last_memory_board_rejected_count", 0)
        self._safe_setattr("last_memory_update_done", False)
        self._set_memory_checkpoint_state(False)

        if self.memory_board_engine is not None:
            try:
                board_result = self.memory_board_engine.apply_response_text(
                    response,
                    active_intent_id=self.prompt_builder._current_active_intent_id(),
                    current_user_input=getattr(ctx, "user_input", ""),
                    source="model",
                )
                if int(self._safe_getattr(board_result, "parsed_count", 0) or 0):
                    self._safe_setattr("memory_tag_expected_next_step", False)
                    self._safe_setattr("memory_tag_reason", "")
                    self._safe_setattr("memory_tag_expected_intent_id", "")
                    clean_response = str(self._safe_getattr(board_result, "clean_text", "") or "")
                    if self.agent.log:
                        self.agent.log.debug(
                            "MemoryBoard.apply parsed=%s accepted=%s rejected=%s",
                            self._safe_getattr(board_result, "parsed_count", 0),
                            self._safe_getattr(board_result, "accepted_count", 0),
                            self._safe_getattr(board_result, "rejected_count", 0),
                        )
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Memory board apply failed: {exc}")

        update_done_present = bool(self.MEMORY_UPDATE_DONE_RE.search(str(response or "")))
        if update_done_present:
            self._safe_setattr("last_memory_update_done", True)
        clean_response = self._strip_memory_update_done(clean_response)

        if board_result is not None:
            self._safe_setattr(
                "last_memory_board_parsed_count",
                int(self._safe_getattr(board_result, "parsed_count", 0) or 0),
            )
            self._safe_setattr(
                "last_memory_board_accepted_count",
                int(self._safe_getattr(board_result, "accepted_count", 0) or 0),
            )
            self._safe_setattr(
                "last_memory_board_rejected_count",
                int(self._safe_getattr(board_result, "rejected_count", 0) or 0),
            )

        accepted_count = int(self._safe_getattr(board_result, "accepted_count", 0) or 0) if board_result is not None else 0
        parsed_count = int(self._safe_getattr(board_result, "parsed_count", 0) or 0) if board_result is not None else 0
        rejected_count = int(self._safe_getattr(board_result, "rejected_count", 0) or 0) if board_result is not None else 0


        if (board_result is not None and accepted_count > 0) or update_done_present:
            raw_has_action = self._response_has_action(response)
            clean_has_action = self._response_has_action(clean_response)

            # 1. Never swallow an action.
            if raw_has_action or clean_has_action:
                self._set_memory_checkpoint_state(False)
                self.stage_logger.log(
                    "memory_board",
                    "pass",
                    reason="memory_checkpoint_and_action",
                    parsed_count=parsed_count,
                    accepted_count=accepted_count,
                    rejected_count=rejected_count,
                )
                return MemoryBoardDecision.pass_through(
                    response_text=clean_response,
                    reason="memory_checkpoint_and_action",
                    source="memory_board",
                    memory_checkpoint_only=False,
                    memory_checkpoint_and_text=False,
                    memory_checkpoint_and_action=True,
                )

            clean_visible = self._strip_control_blocks_for_visible_text(clean_response)

            # 2. If clean_text has real visible text, pass it through.
            if clean_visible:
                self._set_memory_checkpoint_state(False)
                self.stage_logger.log(
                    "memory_board",
                    "pass",
                    reason="memory_checkpoint_and_text",
                    parsed_count=parsed_count,
                    accepted_count=accepted_count,
                    rejected_count=rejected_count,
                )
                return MemoryBoardDecision.pass_through(
                    response_text=clean_response,
                    reason="memory_checkpoint_and_text",
                    source="memory_board",
                    memory_checkpoint_only=False,
                    memory_checkpoint_and_text=True,
                )

            raw_has_memory_tag = bool(self.MEMORY_BLOCK_RE.search(str(response or "")))
            raw_visible = self._strip_control_blocks_for_visible_text(response) if raw_has_memory_tag else ""

            # 3. If clean_text is empty and raw response itself contained memory tags
            # plus real visible text, pass raw text through. Do not treat arbitrary
            # dummy raw text such as "ignored raw response" as user-facing text.
            if not str(clean_response or "").strip() and raw_visible:
                self._set_memory_checkpoint_state(False)
                self.stage_logger.log(
                    "memory_board",
                    "pass",
                    reason="memory_checkpoint_and_text",
                    parsed_count=parsed_count,
                    accepted_count=accepted_count,
                    rejected_count=rejected_count,
                )
                return MemoryBoardDecision.pass_through(
                    response_text=response,
                    reason="memory_checkpoint_and_text",
                    source="memory_board",
                    memory_checkpoint_only=False,
                    memory_checkpoint_and_text=True,
                )

            # 4. Otherwise this is memory-only checkpoint. Consume it and ask
            # the model to continue with substantive output.
            streak = self._set_memory_checkpoint_state(True)
            next_query = self._build_checkpoint_followup_query(streak)
            self.stage_logger.log(
                "memory_board",
                "continue",
                reason="memory_checkpoint_only",
                parsed_count=parsed_count,
                accepted_count=accepted_count,
                rejected_count=rejected_count,
                streak=streak,
            )
            return MemoryBoardDecision.continue_with(
                next_query,
                response_text=clean_response,
                reason="memory_checkpoint_only",
                source="memory_board",
                memory_checkpoint_only=True,
                memory_checkpoint_and_text=False,
            )

        if self.agent.log and board_result is not None:
            self.agent.log.debug(
                "Orchestrator.memory_board_processed parsed=%s accepted=%s rejected=%s clean_chars=%s",
                parsed_count,
                accepted_count,
                rejected_count,
                len(clean_response or ""),
            )
            self.agent.log.debug("Orchestrator.step.response.after_memory_board\n%s", clean_response)

        self.stage_logger.log(
            "memory_board",
            "pass",
            parsed_count=parsed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
        )
        return MemoryBoardDecision.pass_through(
            response_text=clean_response,
            reason="memory_board_pass",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
        )
