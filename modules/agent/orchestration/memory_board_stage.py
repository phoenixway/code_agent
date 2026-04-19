"""Memory-board response application stage for orchestrator model output."""

from __future__ import annotations

from .decision_models import MemoryBoardDecision
from .stage_logging import OrchestrationStageLogger


class MemoryBoardStageHandler:
    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.memory_board_engine = getattr(agent, "memory_board_engine", None)
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    async def apply(self, ctx, response: str) -> MemoryBoardDecision:
        board_result = None
        clean_response = response

        if self.memory_board_engine is not None:
            try:
                board_result = self.memory_board_engine.apply_response_text(
                    response,
                    active_intent_id=self.prompt_builder._current_active_intent_id(),
                    current_user_input=ctx.user_input,
                    source="model",
                )
                if board_result.parsed_count:
                    clean_response = board_result.clean_text
                    if self.agent.log:
                        self.agent.log.debug(
                            "MemoryBoard.apply parsed=%s accepted=%s rejected=%s",
                            board_result.parsed_count,
                            board_result.accepted_count,
                            board_result.rejected_count,
                        )
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Memory board apply failed: {exc}")

        if board_result is not None and board_result.parsed_count > 0 and not str(clean_response or "").strip():
            next_query = (
                "SYSTEM: Memory updates were recorded. Now continue the current task. "
                "Return the next valid <action> if tool use is needed, or answer plainly if enough is already known."
            )
            self.stage_logger.log(
                "memory_board",
                "continue",
                reason="memory_board_consumed_response",
                parsed_count=board_result.parsed_count,
                accepted_count=board_result.accepted_count,
                rejected_count=board_result.rejected_count,
            )
            return MemoryBoardDecision.continue_with(
                next_query,
                response_text=clean_response,
                reason="memory_board_consumed_response",
                source="memory_board",
            )

        if self.agent.log and board_result is not None:
            self.agent.log.debug(
                "Orchestrator.memory_board_processed parsed=%s accepted=%s rejected=%s clean_chars=%s",
                board_result.parsed_count,
                board_result.accepted_count,
                board_result.rejected_count,
                len(clean_response or ""),
            )
            self.agent.log.debug("Orchestrator.step.response.after_memory_board\n%s", clean_response)

        self.stage_logger.log(
            "memory_board",
            "pass",
            parsed_count=getattr(board_result, "parsed_count", 0) if board_result is not None else 0,
        )
        return MemoryBoardDecision.pass_through(
            response_text=clean_response,
            reason="memory_board_pass",
            source="memory_board",
        )
