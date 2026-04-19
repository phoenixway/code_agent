"""Pre-dispatch action policy gate for parsed model actions."""

from __future__ import annotations

from .decision_models import ActionPolicyDecision
from .stage_logging import OrchestrationStageLogger


class ActionPolicyHandler:
    def __init__(self, agent, intent_guard, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.intent_guard = intent_guard
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    async def decide(self, ctx, segments, *, intent_payload: dict | None) -> ActionPolicyDecision:
        action_segments = [
            seg for seg in segments if getattr(seg, "type", "") == "action" and isinstance(getattr(seg, "content", None), dict)
        ]
        parsed_action_count = len(action_segments)

        if not action_segments or intent_payload is not None:
            self.stage_logger.log(
                "action_policy",
                "pass",
                action_count=parsed_action_count,
                reason="no_action_gate_needed",
            )
            return ActionPolicyDecision.pass_through(
                reason="no_action_gate_needed",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )

        for seg in action_segments:
            required, reason = self.intent_guard.action_requires_intent(
                seg.content,
                self.state,
                batch_size=parsed_action_count,
                current_user_input=ctx.user_input,
            )
            if required:
                active_intent = getattr(self.state, "active_intent", None)
                if active_intent is None and hasattr(self.state, "require_intent"):
                    self.state.require_intent(reason)
                next_query = self.prompt_builder.build_intent_required_prompt(
                    reason,
                    [
                        "read_file",
                        "read_chunk",
                        "read_file_skeleton",
                        "extract_kotlin_function",
                        "search_content",
                        "search_files",
                        "list_directory",
                        "find_files",
                        "git_diff",
                        "run_shell",
                    ],
                )
                self.stage_logger.log(
                    "action_policy",
                    "continue",
                    reason=reason,
                    source="intent_guard",
                    action_count=parsed_action_count,
                )
                return ActionPolicyDecision.continue_with(
                    next_query,
                    reason=reason,
                    source="intent_guard",
                    parsed_action_count=parsed_action_count,
                )

        self.stage_logger.log(
            "action_policy",
            "pass",
            action_count=parsed_action_count,
            reason="actions_allowed_to_proceed",
        )
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )
