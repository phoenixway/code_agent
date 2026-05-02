"""Plan-board response application stage for flat XML subgoal mutations."""

from __future__ import annotations

import re

from ..responses.stage_logging import OrchestrationStageLogger
from ..shared.decision_models import PlanBoardDecision


class PlanBoardStageHandler:
    ACTION_TAG_RE = re.compile(r"<action\b", re.IGNORECASE)
    THINK_BLOCK_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    PLAN_TAG_RE = re.compile(
        r"<subgoal\b[^>]*?(?:>.*?</subgoal>|/\s*>)",
        re.IGNORECASE | re.DOTALL,
    )
    GENERIC_TAG_RE = re.compile(r"</?[^>]+>", re.IGNORECASE)

    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.planner = getattr(agent, "planner", None)
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def _strip_control_blocks_for_visible_text(self, text: str) -> str:
        value = str(text or "")
        if not value.strip():
            return ""
        value = self.THINK_BLOCK_RE.sub(" ", value)
        value = self.PLAN_TAG_RE.sub(" ", value)
        value = self.GENERIC_TAG_RE.sub(" ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _response_has_action(self, response_text: str) -> bool:
        return bool(self.ACTION_TAG_RE.search(str(response_text or "")))

    def _build_followup_query(self) -> str:
        return (
            "SYSTEM: Plan updates were recorded. "
            "Now continue substantively. "
            "Return exactly one of: "
            "(1) one valid <action>, "
            "(2) a brief plain-text continuation, "
            "or (3) a final plain-text answer if current evidence is enough."
        )

    async def apply(self, ctx, response: str) -> PlanBoardDecision:
        if self.planner is None:
            return PlanBoardDecision.pass_through(
                reason="planner_unavailable",
                source="plan_board",
                response_text=response,
            )

        clean_response, update_ops, error = self.planner.extract_update_and_strip(response)
        if error:
            self.stage_logger.log(
                "plan_board",
                "continue",
                reason=error,
                source="plan_board",
            )
            return PlanBoardDecision.continue_with(
                "SYSTEM: Your last subgoal-board XML was invalid. Return corrected flat <subgoal ...> tags or continue without subgoal changes.",
                reason=error,
                source="plan_board",
                response_text=clean_response,
            )

        if not update_ops:
            try:
                setattr(self.state, "last_plan_subgoal_create_count", 0)
            except Exception:
                pass
            self.stage_logger.log(
                "plan_board",
                "pass",
                reason="no_plan_updates",
                source="plan_board",
            )
            return PlanBoardDecision.pass_through(
                reason="no_plan_updates",
                source="plan_board",
                response_text=clean_response,
            )

        applied, summary = self.planner.apply_update(self.state, update_ops)
        try:
            create_count = sum(1 for op in update_ops if str(op.get("op") or "").strip().lower() == "create")
            setattr(self.state, "last_plan_subgoal_create_count", create_count)
        except Exception:
            pass
        if applied and summary:
            printer = getattr(self.agent.ui, "print_plan", None)
            if callable(printer):
                try:
                    await printer(summary)
                except Exception:
                    pass

        raw_has_action = self._response_has_action(response)
        clean_has_action = self._response_has_action(clean_response)
        clean_visible = self._strip_control_blocks_for_visible_text(clean_response)

        if raw_has_action or clean_has_action:
            self.stage_logger.log(
                "plan_board",
                "pass",
                reason="plan_checkpoint_and_action",
                source="plan_board",
                op_count=len(update_ops),
            )
            return PlanBoardDecision.pass_through(
                reason="plan_checkpoint_and_action",
                source="plan_board",
                response_text=clean_response,
                plan_checkpoint_only=False,
                plan_checkpoint_and_text=False,
                plan_checkpoint_and_action=True,
            )

        if clean_visible or str(clean_response or "").strip():
            self.stage_logger.log(
                "plan_board",
                "pass",
                reason="plan_checkpoint_and_text",
                source="plan_board",
                op_count=len(update_ops),
            )
            return PlanBoardDecision.pass_through(
                reason="plan_checkpoint_and_text",
                source="plan_board",
                response_text=clean_response,
                plan_checkpoint_only=False,
                plan_checkpoint_and_text=True,
                plan_checkpoint_and_action=False,
            )

        self.stage_logger.log(
            "plan_board",
            "continue",
            reason="plan_checkpoint_only",
            source="plan_board",
            op_count=len(update_ops),
        )
        return PlanBoardDecision.continue_with(
            self._build_followup_query(),
            response_text=clean_response,
            reason="plan_checkpoint_only",
            source="plan_board",
            plan_checkpoint_only=True,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
