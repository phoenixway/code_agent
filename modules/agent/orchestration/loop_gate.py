"""Pre-step loop gating for summarization, session limits, and step budget warnings."""

from __future__ import annotations

import asyncio

from .decision_models import LoopGateDecision
from .stage_logging import OrchestrationStageLogger


class LoopGateHandler:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history
        self.config = agent.config
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    @property
    def ui(self):
        return self.agent.ui

    async def run(self, ctx) -> LoopGateDecision:
        try:
            await self.history.check_and_summarize(self.ui, self.state)
        except Exception as exc:
            if self.agent.log:
                self.agent.log.warning(f"Pre-step summarization check failed: {exc}")

        exhausted_checker = getattr(self.state, "has_hard_exhausted_active_intent", None)
        hard_exhausted = False
        if callable(exhausted_checker):
            try:
                hard_exhausted = bool(exhausted_checker())
            except Exception:
                hard_exhausted = False

        if hard_exhausted:
            require_intent = getattr(self.state, "require_intent", None)
            if callable(require_intent):
                require_intent("exhausted_intent_requires_reuse_or_completion")
        else:
            clear_requirement = getattr(self.state, "clear_intent_requirement", None)
            reason = str(getattr(self.state, "intent_required_reason", "") or "").strip()
            if callable(clear_requirement) and reason == "exhausted_intent_requires_reuse_or_completion":
                clear_requirement()

        if self.agent.log:
            self.agent.log.debug(
                f"Loop iteration={ctx.consecutive_calls + 1} "
                f"history_tokens={self.history.current_token_count}/{self.history.max_tokens}"
            )

        loop = asyncio.get_running_loop()
        if loop.time() - ctx.session_started_at > self.config.MAX_SESSION_SECONDS:
            await self.ui.print_error(
                f"Session time limit reached ({self.config.MAX_SESSION_SECONDS}s). Stopping."
            )
            ctx.active_loop = False
            self.stage_logger.log(
                "loop_gate",
                "stop",
                reason="session_time_limit_reached",
                source="session_limit",
            )
            return LoopGateDecision(
                proceed=False,
                reason="session_time_limit_reached",
                source="session_limit",
            )

        ctx.consecutive_calls += 1
        if ctx.consecutive_calls > self.config.MAX_CONSECUTIVE_CALLS:
            suspected_loop = (
                getattr(self.state, "consecutive_same_error_count", 0)
                >= max(2, int(getattr(self.config, "LOOP_ERROR_REPEAT_THRESHOLD", 2)))
            )
            if suspected_loop and not getattr(self.state, "suppress_step_limit_warning", False):
                await self.ui.stop_loading()
                decision = await self.ui.confirm_continue(
                    "Агент зробив багато кроків і є ознаки повторюваного циклу. Продовжити?"
                )
                if decision in (False, "stop", None):
                    await self.ui.print_system(
                        f"Execution stopped: reached max consecutive steps ({self.config.MAX_CONSECUTIVE_CALLS})."
                    )
                    ctx.active_loop = False
                    self.stage_logger.log(
                        "loop_gate",
                        "stop",
                        reason="max_consecutive_steps_reached",
                        source="step_limit",
                    )
                    return LoopGateDecision(
                        proceed=False,
                        reason="max_consecutive_steps_reached",
                        source="step_limit",
                    )
                if decision == "continue_silent":
                    self.state.suppress_step_limit_warning = True

        await self.ui.start_thinking()
        self.stage_logger.log(
            "loop_gate",
            "proceed",
            step=ctx.consecutive_calls,
            source="loop_gate",
            hard_exhausted=hard_exhausted,
        )
        return LoopGateDecision(
            proceed=True,
            reason="exhausted_intent_requires_reuse_or_completion" if hard_exhausted else "step_ready",
            source="loop_gate",
        )
