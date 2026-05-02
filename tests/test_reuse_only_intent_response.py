from types import SimpleNamespace

import pytest

from modules.agent.orchestration.shared.decision_models import (
    ActionPolicyDecision,
    IntentHandlingDecision,
    MemoryBoardDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.transitions import IntentTransitionHandler
from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline


class DummyPromptBuilder:
    def build_plain_text_completion_prompt(self, *args, **kwargs):
        return "plain text completion"

    def build_control_tag_leak_recovery_prompt(self):
        return "control tag leak recovery"

    def build_intent_required_prompt(self, reason, *args, **kwargs):
        return f"intent required: {reason}"

    def build_reflection_repair_accepted_prompt(self):
        return "reflection accepted"

    def build_durable_state_repair_prompt(self, *args, **kwargs):
        return "durable repair"

    def build_repeated_thinking_without_valid_output_prompt(self, *args, **kwargs):
        return "repeated thinking"

    def build_leaked_system_result_recovery_prompt(self):
        return "leaked system result"

    def build_missing_action_or_answer_prompt(self):
        return "missing action or answer"

    def build_multiple_actions_prompt(self):
        return "multiple actions"

    def build_intent_accepted_without_followup_prompt(self, active_goal=""):
        return f"intent accepted: {active_goal}"

    def build_reuse_only_transition_cannot_bundle_action_prompt(self, *, blocked_action=""):
        return f"reuse accepted; no bundled action: {blocked_action}"

    def build_completion_with_action_not_allowed_prompt(self):
        return "completion with action not allowed"

    def build_followup_conflict_prompt(self, reason):
        return f"followup conflict: {reason}"

    def build_intent_completed_prompt(self):
        return "intent completed"


class DummyParser:
    def parse(self, response):
        text = str(response or "")
        segments = []
        if "<action" in text.lower():
            segments.append(SimpleNamespace(type="action", content={"type": "write_file_block", "path": "x.kt"}))
        return segments


class DummyPlanBoardStage:
    async def apply(self, ctx, response):
        return PlanBoardDecision.pass_through(
            reason="no_plan_updates",
            source="plan_board",
            response_text=response,
        )


class DummyMemoryBoardStage:
    async def apply(self, ctx, response):
        return MemoryBoardDecision.pass_through(
            reason="no_memory_updates",
            source="memory_board",
            response_text=response,
        )


class DummyOutputRecovery:
    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        return SimpleNamespace(handled=False, reason="no_invalid_kind", source="output_recovery")


class RecordingActionPolicy:
    def __init__(self):
        self.calls = 0

    async def decide(self, ctx, segments, *, intent_payload):
        self.calls += 1
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
        )


class RecordingIntentTransitions:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    async def handle_model_step(self, *, intent_payload, intent_error, response_text, state_machine=None):
        self.calls += 1
        if isinstance(intent_payload, dict) and str(intent_payload.get("mode") or "").lower() == "reuse":
            self.state.active_intent = SimpleNamespace(
                intent_id=intent_payload.get("intent_id"),
                intent_type=intent_payload.get("intent_type"),
                goal=intent_payload.get("goal"),
                allowed_actions=list(intent_payload.get("allowed_actions") or []),
            )
            return IntentHandlingDecision(
                handled=True,
                next_query="intent accepted without followup",
                reason="intent_accepted_without_followup",
            )
        return IntentHandlingDecision(handled=False)


def _pipeline(state, action_policy=None, intent_transitions=None):
    agent = SimpleNamespace(
        state=state,
        config=SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        ),
        memory_board_engine=None,
        log=None,
        ui=SimpleNamespace(),
    )
    return ModelResponsePipeline(
        agent=agent,
        parser=DummyParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=intent_transitions or RecordingIntentTransitions(state),
        output_recovery=DummyOutputRecovery(),
        action_policy=action_policy or RecordingActionPolicy(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )


def _reuse_payload():
    return {
        "intent_id": "bookmark_import_export",
        "intent_type": "MODIFY",
        "goal": "Add bookmark import/export functionality.",
        "allowed_actions": ["read_file", "write_file_block"],
        "mode": "reuse",
        "requested_steps": 5,
        "switch_reason": "work_type_changed",
        "switch_explanation": "Need write_file_block.",
    }


@pytest.mark.asyncio
async def test_reuse_only_intent_is_valid_next_step():
    state = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="bookmark_import_export",
            intent_type="MODIFY",
            goal="Add bookmark import/export functionality.",
            allowed_actions=["read_file"],
        ),
        intent_required_until_activated=False,
        intent_required_reason="",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
    )
    transitions = RecordingIntentTransitions(state)
    action_policy = RecordingActionPolicy()
    pipeline = _pipeline(state, action_policy=action_policy, intent_transitions=transitions)
    response = (
        '<intent mode="reuse">\n'
        "{\n"
        '  "intent_id": "bookmark_import_export",\n'
        '  "intent_type": "MODIFY",\n'
        '  "goal": "Add bookmark import/export functionality.",\n'
        '  "allowed_actions": ["read_file", "write_file_block"],\n'
        '  "mode": "reuse",\n'
        '  "requested_steps": 5,\n'
        '  "switch_reason": "work_type_changed",\n'
        '  "switch_explanation": "Need write_file_block."\n'
        "}\n"
        "</intent>"
    )

    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0, user_input="continue"),
        SimpleNamespace(response=response, intent_payload=_reuse_payload(), intent_error=None, model_stop_reason=""),
    )

    assert outcome.continue_loop is True
    assert outcome.reason == "intent_accepted_without_followup"
    assert transitions.calls == 1
    assert action_policy.calls == 0
    assert "write_file_block" in state.active_intent.allowed_actions


@pytest.mark.asyncio
async def test_reuse_only_recovery_rejects_reuse_plus_action():
    state = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="bookmark_import_export",
            intent_type="MODIFY",
            goal="Add bookmark import/export functionality.",
            allowed_actions=["read_file"],
        ),
        reuse_only_intent_required=True,
        reuse_only_blocked_action="write_file_block",
        apply_intent_contract=lambda payload, config: (True, "intent_reused"),
        intent_runtime=SimpleNamespace(last_apply_warning="", last_transition_info={}, active_intent=None),
        last_memory_update_done=False,
        orchestration_trace=[],
        orchestration_trace_sequence=0,
    )

    def _apply(payload, config):
        state.active_intent = SimpleNamespace(
            intent_id=payload.get("intent_id"),
            intent_type=payload.get("intent_type"),
            goal=payload.get("goal"),
            allowed_actions=list(payload.get("allowed_actions") or []),
        )
        state.intent_runtime.active_intent = state.active_intent
        state.intent_runtime.last_transition_info = {
            "transition": "intent_reused_with_step_refresh",
            "before_active_intent_id": "bookmark_import_export",
            "after_active_intent_id": "bookmark_import_export",
        }
        return True, "intent_reused"

    state.apply_intent_contract = _apply
    prompt_builder = DummyPromptBuilder()
    handler = IntentTransitionHandler(
        SimpleNamespace(state=state, config=SimpleNamespace(), log=None),
        prompt_builder,
        SimpleNamespace(handle_defect_detector_stop=lambda stop_info: None),
    )

    response = (
        '<intent mode="reuse">\n'
        "{\n"
        '  "intent_id": "bookmark_import_export",\n'
        '  "intent_type": "MODIFY",\n'
        '  "goal": "Add bookmark import/export functionality.",\n'
        '  "allowed_actions": ["read_file", "write_file_block"],\n'
        '  "mode": "reuse",\n'
        '  "requested_steps": 5,\n'
        '  "switch_reason": "work_type_changed",\n'
        '  "switch_explanation": "Need write_file_block."\n'
        "}\n"
        "</intent>\n"
        '<action>{"type":"write_file_block","path":"x.kt"}</action>\n'
        "<file_content>hello</file_content>"
    )

    decision = await handler.handle_model_step(
        intent_payload=_reuse_payload(),
        intent_error=None,
        response_text=response,
        state_machine=None,
    )

    assert decision.handled is True
    assert decision.reason == "reuse_only_transition_cannot_bundle_action"
    assert "no bundled action" in (decision.next_query or "")


def test_strict_reuse_recovery_prompt_says_no_think_and_no_action():
    prompt = DummyPromptBuilder()  # shape check comes from real builder below
    from modules.agent.orchestration.prompts import OrchestratorPromptBuilder

    real_prompt = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(
                active_intent=SimpleNamespace(
                    intent_id="bookmark_import_export",
                    intent_type="MODIFY",
                    goal="Add bookmark import/export functionality.",
                    allowed_actions=["read_file"],
                )
            ),
            config=SimpleNamespace(),
            memory_board_store=None,
            log=None,
        )
    ).build_repeated_disallowed_action_reuse_only_prompt(
        blocked_action="write_file_block",
        intent_id="bookmark_import_export",
        intent_type="MODIFY",
        goal="Add bookmark import/export functionality.",
        allowed_actions=["read_file"],
    )

    assert 'Return only a top-level <intent mode="reuse">...</intent>.' in real_prompt
    assert "Do not include <think> or <action>." in real_prompt


@pytest.mark.asyncio
async def test_ordinary_intent_activate_with_followup_action_still_works():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=False,
        intent_required_reason="",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
    )

    class _ActivateTransitions(RecordingIntentTransitions):
        async def handle_model_step(self, *, intent_payload, intent_error, response_text, state_machine=None):
            self.calls += 1
            self.state.active_intent = SimpleNamespace(
                intent_id="x",
                intent_type="OBSERVE",
                goal="Read file",
                allowed_actions=["read_file"],
            )
            return IntentHandlingDecision(handled=False)

    action_policy = RecordingActionPolicy()
    pipeline = _pipeline(state, action_policy=action_policy, intent_transitions=_ActivateTransitions(state))
    response = '<intent mode="activate">{"intent_id":"x","intent_type":"OBSERVE","goal":"Read file","allowed_actions":["read_file"],"mode":"activate"}</intent>\n<memory_update_done />\n<action>{"type":"read_file","path":"x.kt"}</action>'

    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0, user_input="read file"),
        SimpleNamespace(
            response=response,
            intent_payload={"intent_id": "x", "intent_type": "OBSERVE", "goal": "Read file", "allowed_actions": ["read_file"], "mode": "activate"},
            intent_error=None,
            model_stop_reason="",
        ),
    )

    assert outcome.continue_loop is False
    assert outcome.parsed_action_count >= 1
