"""Recovery decisions for invalid or incomplete model outputs before dispatch."""

from __future__ import annotations

from .decision_models import OutputRecoveryDecision, ParsedModelOutput
from .stage_logging import OrchestrationStageLogger


class ModelOutputRecoveryHandler:
    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    @property
    def ui(self):
        return self.agent.ui

    async def decide(
        self,
        parsed_output: ParsedModelOutput,
        *,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        invalid_kind = str(parsed_output.invalid_kind or "").strip()
        if not invalid_kind:
            self.stage_logger.log("output_recovery", "pass")
            return OutputRecoveryDecision.pass_through(
                reason="no_invalid_kind",
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "malformed_action":
            next_retries = malformed_action_retries + 1
            if self.agent.log:
                self.agent.log.warning(
                    "Malformed action response detected (retry %s/1).",
                    next_retries,
                )
            if next_retries > 1:
                await self.ui.print_error(
                    "Execution stopped: model returned malformed action format repeatedly."
                )
                return OutputRecoveryDecision(
                    handled=True,
                    continue_loop=False,
                    stop_loop=True,
                    malformed_action_retries=next_retries,
                    audit_marker_retries=0,
                    reason=invalid_kind,
                )
            self.state.set_malformed_grace(self.config.MALFORMED_ACTION_GRACE_STEPS)
            self.state.forbid_next_action_fingerprint(
                getattr(self.state, "last_completed_fingerprint", None)
            )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                retries=next_retries,
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_malformed_action_strict_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=next_retries,
                audit_marker_retries=0,
            )

        if invalid_kind == "tool_history_echo":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind)
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_tool_history_echo_without_action_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "audit_marker_echo":
            next_retries = audit_marker_retries + 1
            if self.agent.log:
                self.agent.log.warning(
                    "Audit-marker echo without action detected (retry %s/1).",
                    next_retries,
                )
            if next_retries > 1:
                await self.ui.print_error(
                    "Execution stopped: model repeatedly echoed audit trail without a valid action."
                )
                self.stage_logger.log(
                    "output_recovery",
                    "stop",
                    reason=invalid_kind,
                    retries=next_retries,
                )
                return OutputRecoveryDecision(
                    handled=True,
                    continue_loop=False,
                    stop_loop=True,
                    malformed_action_retries=0,
                    audit_marker_retries=next_retries,
                    reason=invalid_kind,
                )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                retries=next_retries,
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_audit_marker_echo_strict_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=next_retries,
            )

        if invalid_kind == "missing_action_or_answer":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind)
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_missing_action_or_answer_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "intent_only_deadend":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind)
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_intent_only_deadend_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        return OutputRecoveryDecision.pass_through(
            reason="unhandled_invalid_kind",
            source="output_recovery",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
