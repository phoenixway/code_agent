
import json
from types import SimpleNamespace

import pytest

from modules.agent.orchestration.runtime.action_policy import ActionPolicyHandler
from modules.agent.orchestration.shared.decision_models import (
    MemoryBoardDecision,
    OutputRecoveryDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.transitions import IntentTransitionHandler
from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline
from modules.agent.orchestration.shared.trace import snapshot_trace
from modules.parser import ResponseParser


class DummySegment:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content


class DummyParser:
    ACTION_RE = IntentResponseParser.ACTION_TAG_RE

    def parse(self, response):
        segments = []
        for match in self.ACTION_RE.finditer(str(response or "")):
            body = match.group(0)
            inner = body[body.find(">") + 1 : body.lower().rfind("</action>")].strip()
            try:
                payload = json.loads(inner)
            except Exception:
                payload = {}
            segments.append(DummySegment("action", payload))
        text = IntentResponseParser().extract_visible_non_action_text(str(response or ""))
        if text.strip():
            segments.append(DummySegment("text", text.strip()))
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
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action="<action" in str(response or "").lower(),
        )


class RecordingOutputRecovery:
    def __init__(self):
        self.calls = []

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls.append(parsed_output)
        invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        if not invalid_kind:
            return OutputRecoveryDecision.pass_through(
                reason="no_invalid_kind",
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )
        return OutputRecoveryDecision.continue_with(
            "recover malformed followup",
            reason=invalid_kind,
            source="output_recovery",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )


class DummyRecovery:
    async def handle_defect_detector_stop(self, stop_info):
        return OutputRecoveryDecision.pass_through(reason="no_defect_recovery")


class DummyIntentGuard:
    def action_requires_intent(self, command, state, *, batch_size, current_user_input):
        active = getattr(state, "active_intent", None)
        if active is None:
            return False, ""
        action_type = str(command.get("type") or command.get("action") or "").strip()
        allowed = set(getattr(active, "allowed_actions", []) or [])
        if allowed and action_type not in allowed:
            return True, "intent_action_not_allowed"
        return False, ""


class DummyPromptBuilder:
    def build_intent_required_prompt(self, *args, **kwargs):
        return "intent required"

    def build_intent_accepted_without_followup_prompt(self, goal):
        return "intent accepted"

    def build_intent_completed_prompt(self):
        return "intent completed"

    def build_intent_transition_rejected_prompt(self, *args, **kwargs):
        return "intent rejected"

    def build_followup_conflict_prompt(self, reason):
        return f"followup conflict: {reason}"

    def build_completion_with_action_not_allowed_prompt(self):
        return "completion with action not allowed"

    def build_limit_aware_reuse_prompt(self, *args, **kwargs):
        return "reuse required"

    def build_intent_payload_inside_action_prompt(self):
        return "intent payload inside action"

    def build_noop_edit_prompt(self):
        return "noop edit"

    def build_edit_retry_requires_fresh_read_prompt(self, *args, **kwargs):
        return "fresh read required"

    def build_intent_action_not_allowed_prompt(self, **kwargs):
        return "action not allowed"

    def build_terminal_repeated_disallowed_action_handoff_text(self, **kwargs):
        return "terminal handoff"

    def build_reflection_repair_accepted_prompt(self):
        return "reflection repair accepted"

    def build_durable_state_repair_prompt(self, *args, **kwargs):
        return "durable state repair"

    def build_repeated_thinking_without_valid_output_prompt(self, *args, **kwargs):
        return "repeated thinking"

    def build_leaked_system_result_recovery_prompt(self):
        return "leaked system result"

    def build_malformed_action_strict_recovery_prompt(self):
        return "malformed action"

    def build_incomplete_think_recovery_prompt(self):
        return "incomplete think"

    def build_strict_compact_think_prompt(self):
        return "strict compact think"

    def build_exact_think_skeleton_prompt(self):
        return "exact think skeleton"

    def build_malformed_verbose_or_nested_think_prompt(self):
        return "malformed verbose think"

    def build_malformed_think_limit_prompt(self):
        return "malformed think limit"

    def build_atomic_bundle_rejected_prompt(self, *, invalid_part, reason, blocked_action="", proposed_allowed_actions=None, goal=""):
        return f"bundle invalid: {invalid_part}: {reason}: {blocked_action}"


class DummyState:
    def __init__(self, *, allowed_actions=None, hard_exhausted=True):
        self.apply_called = False
        self.intent_required_until_activated = hard_exhausted
        self.intent_required_reason = (
            "exhausted_intent_requires_reuse_or_completion" if hard_exhausted else ""
        )
        self.active_intent = SimpleNamespace(
            intent_id="current_intent",
            intent_type="INVESTIGATE",
            goal="Continue same investigation",
            allowed_actions=list(allowed_actions or ["read_chunk"]),
            original_allowed_actions=list(allowed_actions or ["read_chunk"]),
            step_count=99 if hard_exhausted else 0,
            safe_steps_limit=1,
            retry_limit=1,
            force_plaintext_completion=False,
            action_constraints={},
            blocked_action_signatures=set(),
            blocked_action_reasons={},
        )
        self.intent_runtime = SimpleNamespace(
            last_apply_warning="",
            last_transition_info={
                "transition": "intent_reused_with_step_refresh",
                "before_active_intent_id": "current_intent",
                "after_active_intent_id": "current_intent",
            },
        )
        self.last_memory_update_done = False
        self.consecutive_memory_checkpoint_only_count = 0
        self.consecutive_nonproductive_thinking_count = 0
        self.think_reflection_repair_pending = False
        self.think_reflection_repair_kind = ""
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.disallowed_action_repeat_type = ""
        self.disallowed_action_repeat_intent_id = ""
        self.disallowed_action_repeat_count = 0
        self.last_blocked_action_type = ""
        self.last_blocked_action_path = ""
        self.orchestration_trace_sequence = 0
        self.orchestration_trace = []

    def apply_intent_contract(self, payload, config):
        self.apply_called = True
        mode = str(payload.get("mode") or "").strip().lower()
        if mode == "reuse" and not str(payload.get("switch_reason") or "").strip():
            return False, "intent_switch_reason_required"
        if mode not in {"reuse", "activate"}:
            return False, "unsupported_test_intent_mode"
        allowed = payload.get("allowed_actions") or getattr(self.active_intent, "allowed_actions", [])
        self.active_intent = SimpleNamespace(
            intent_id=payload.get("intent_id") or "current_intent",
            intent_type=payload.get("intent_type") or ("INVESTIGATE" if mode == "reuse" else "MODIFY"),
            goal=payload.get("goal") or ("Continue same investigation" if mode == "reuse" else "Save requested document."),
            allowed_actions=list(allowed),
            original_allowed_actions=list(allowed),
            step_count=0,
            safe_steps_limit=int(payload.get("safe_steps_limit") or 4),
            retry_limit=int(payload.get("retry_limit") or 1),
            force_plaintext_completion=False,
            action_constraints={},
            blocked_action_signatures=set(),
            blocked_action_reasons={},
        )
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        return True, "intent_reused" if mode == "reuse" else "intent_activated"

    def has_hard_exhausted_active_intent(self):
        return bool(self.intent_required_until_activated)

    def require_intent(self, reason):
        self.intent_required_until_activated = True
        self.intent_required_reason = reason

    def clear_intent_requirement(self):
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def set_malformed_grace(self, steps):
        self.malformed_grace = steps

    def forbid_next_action_fingerprint(self, fingerprint):
        self.forbidden_next_action = fingerprint


class DummyAgent:
    def __init__(self, state):
        self.state = state
        self.config = SimpleNamespace(
            MALFORMED_ACTION_GRACE_STEPS=2,
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        )
        self.log = None
        self.memory_board_engine = None

        async def noop(*args, **kwargs):
            return None

        self.ui = SimpleNamespace(
            print_error=noop,
            print_system=noop,
        )


def make_pipeline(state, output_recovery=None, parser=None):
    agent = DummyAgent(state)
    prompt_builder = DummyPromptBuilder()
    return ModelResponsePipeline(
        agent=agent,
        parser=parser or DummyParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=prompt_builder,
        intent_transitions=IntentTransitionHandler(agent, prompt_builder, DummyRecovery()),
        output_recovery=output_recovery or RecordingOutputRecovery(),
        action_policy=ActionPolicyHandler(agent, DummyIntentGuard(), prompt_builder),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )


def reuse_payload(*, allowed_actions=None):
    return {
        "mode": "reuse",
        "intent_id": "current_intent",
        "intent_type": "INVESTIGATE",
        "goal": "Continue same investigation",
        "allowed_actions": list(allowed_actions or ["read_chunk"]),
        "requested_steps": 4,
        "switch_reason": "current_intent_exhausted",
        "switch_explanation": "same work direction",
    }


@pytest.mark.asyncio
async def test_valid_repaired_followup_applies_reuse_transition():
    """
    A malformed response that becomes valid after think-boundary repair should
    now correctly apply the reuse transition.
    """
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=True)
    recovery = RecordingOutputRecovery()
    pipeline = make_pipeline(state, recovery)

    step = SimpleNamespace(
        intent_payload=reuse_payload(allowed_actions=["read_chunk"]),
        intent_error=None,
        model_stop_reason="",
        response=(
            "<think>! Need refreshed budget. ? Need next chunk. → read_chunk\n"
            "<memory_update_done />\n"
            '<action>{"type":"read_chunk","path":"x.py","start_line":1,"end_line":5}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="continue",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is True
    assert state.intent_required_until_activated is False
    assert outcome.continue_loop is False
    assert outcome.reason == "dispatch_ready"


@pytest.mark.asyncio
async def test_valid_reuse_plus_allowed_action_bundle_is_dispatch_ready():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=True)
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload=reuse_payload(allowed_actions=["read_chunk"]),
        intent_error=None,
        model_stop_reason="",
        response=(
            "<think>! Reuse request is valid. ? Need exact chunk. → read_chunk.</think>\n"
            "<memory_update_done />\n"
            '<action>{"type":"read_chunk","path":"x.py","start_line":1,"end_line":5}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="continue",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is True
    assert state.intent_required_until_activated is False
    assert outcome.continue_loop is False
    assert outcome.stop_loop is False
    assert outcome.parsed_action_count == 1
    assert outcome.execution_plan is not None
    assert outcome.execution_plan.transaction_kind == "atomic_intent_action_bundle"
    assert outcome.execution_plan.bundle_validated is True
    assert outcome.execution_plan.transition_applied is True
    assert outcome.execution_plan.action_dispatched is False
    assert outcome.execution_plan.before_active_intent_id == "current_intent"
    assert outcome.execution_plan.after_active_intent_id == "current_intent"
    assert outcome.execution_plan.action_effects == ["read_chunk:x.py"]
    assert outcome.execution_plan.action_op_count == 1
    assert outcome.execution_plan.candidate_eligibility_status == "single_action_candidate_possible"
    assert outcome.execution_plan.plan_source == "compiler_ir"
    assert outcome.segments
    assert any(getattr(seg, "type", "") == "action" for seg in outcome.segments)
    action_seg = next(seg for seg in outcome.segments if getattr(seg, "type", "") == "action")
    assert action_seg.content["type"] == "read_chunk"
    assert action_seg.content["path"] == "x.py"
    assert outcome.execution_plan.action_effects[0] == f'{action_seg.content["type"]}:{action_seg.content["path"]}'


@pytest.mark.asyncio
async def test_valid_activate_write_bundle_is_dispatch_ready():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=False)
    state.active_intent = None
    state.intent_required_until_activated = False
    state.intent_required_reason = ""
    pipeline = make_pipeline(state, parser=ResponseParser())

    step = SimpleNamespace(
        intent_payload={
            "mode": "activate",
            "intent_id": "save_requested_document",
            "intent_type": "MODIFY",
            "goal": "Save requested document.",
            "allowed_actions": ["write_file_block"],
            "safe_steps_limit": 2,
            "retry_limit": 1,
        },
        intent_error=None,
        model_stop_reason="",
        response=(
            '<intent mode="activate">{"mode":"activate","intent_id":"save_requested_document","intent_type":"MODIFY","goal":"Save requested document.","allowed_actions":["write_file_block"],"safe_steps_limit":2,"retry_limit":1}</intent>\n'
            '<action>{"type":"write_file_block","path":"docs/x.md","overwrite":true}</action>\n'
            "<file_content>body</file_content>"
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="save the requested document",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is True
    assert state.intent_required_until_activated is False
    assert outcome.continue_loop is False
    assert outcome.stop_loop is False
    assert outcome.parsed_action_count == 1
    assert outcome.execution_plan is not None
    assert outcome.execution_plan.transaction_kind == "atomic_intent_action_bundle"
    assert outcome.execution_plan.bundle_validated is True
    assert outcome.execution_plan.transition_applied is True
    assert outcome.execution_plan.action_dispatched is False
    assert outcome.execution_plan.before_active_intent_id == "save_requested_document"
    assert outcome.execution_plan.after_active_intent_id == "save_requested_document"
    assert outcome.execution_plan.action_effects == ["write_file_block:docs/x.md"]
    assert outcome.execution_plan.action_op_count == 1
    assert outcome.execution_plan.candidate_eligibility_status == "single_action_candidate_possible"
    assert outcome.execution_plan.plan_source == "compiler_ir"
    action_seg = next(seg for seg in outcome.segments if getattr(seg, "type", "") == "action")
    assert action_seg.content["type"] == "write_file_block"
    assert action_seg.content["path"] == "docs/x.md"
    assert outcome.execution_plan.action_effects[0] == f'{action_seg.content["type"]}:{action_seg.content["path"]}'


@pytest.mark.asyncio
async def test_valid_reuse_plus_disallowed_action_is_checked_after_reuse():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=True)
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload=reuse_payload(allowed_actions=["read_chunk"]),
        intent_error=None,
        model_stop_reason="",
        response=(
            "<think>! Reuse request is valid. ? Need action. → write_file.</think>\n"
            "<memory_update_done />\n"
            '<action>{"type":"write_file","path":"x.py","content":"bad"}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="continue",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is False
    assert state.intent_required_until_activated is True
    assert outcome.continue_loop is True
    assert outcome.reason == "atomic_bundle_action_invalid"
    assert outcome.parsed_action_count == 0
    assert outcome.atomic_bundle_plan is not None
    assert outcome.atomic_bundle_plan.bundle_validated is False
    assert outcome.atomic_bundle_plan.invalid_part == "action"
    assert outcome.atomic_bundle_plan.transition_applied is False
    assert outcome.atomic_bundle_plan.action_dispatched is False
    assert outcome.atomic_bundle_plan.before_active_intent_id == "current_intent"
    assert outcome.atomic_bundle_plan.after_active_intent_id == "current_intent"


@pytest.mark.asyncio
async def test_invalid_reuse_bundle_missing_switch_reason_rejects_whole_bundle():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=False)
    state.active_intent = SimpleNamespace(
        intent_id="current_intent",
        intent_type="INVESTIGATE",
        goal="Continue same investigation",
        allowed_actions=["read_chunk"],
        original_allowed_actions=["read_chunk"],
        step_count=0,
        safe_steps_limit=4,
        retry_limit=1,
        force_plaintext_completion=False,
        action_constraints={},
        blocked_action_signatures=set(),
        blocked_action_reasons={},
    )
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload={
            "mode": "reuse",
            "intent_id": "current_intent",
            "intent_type": "MODIFY",
            "goal": "Continue same investigation",
            "allowed_actions": ["read_chunk"],
        },
        intent_error=None,
        model_stop_reason="",
        response=(
            '<intent mode="reuse">{"mode":"reuse","intent_id":"current_intent","intent_type":"MODIFY","goal":"Continue same investigation","allowed_actions":["read_chunk"]}</intent>\n'
            '<action>{"type":"read_chunk","path":"x.py","start_line":1,"end_line":5}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="continue",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is False
    assert outcome.continue_loop is True
    assert outcome.reason == "atomic_bundle_intent_invalid"
    assert outcome.atomic_bundle_plan is not None
    assert outcome.atomic_bundle_plan.bundle_validated is False
    assert outcome.atomic_bundle_plan.invalid_part == "intent"
    assert outcome.atomic_bundle_plan.transition_applied is False
    assert outcome.atomic_bundle_plan.action_dispatched is False


@pytest.mark.asyncio
async def test_missing_file_content_rejects_whole_bundle():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=False)
    state.active_intent = None
    state.intent_required_until_activated = False
    state.intent_required_reason = ""
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload={
            "mode": "activate",
            "intent_id": "save_requested_document",
            "intent_type": "MODIFY",
            "goal": "Save requested document.",
            "allowed_actions": ["write_file_block"],
            "safe_steps_limit": 2,
            "retry_limit": 1,
        },
        intent_error=None,
        model_stop_reason="",
        response=(
            '<intent mode="activate">{"mode":"activate","intent_id":"save_requested_document","intent_type":"MODIFY","goal":"Save requested document.","allowed_actions":["write_file_block"],"safe_steps_limit":2,"retry_limit":1}</intent>\n'
            '<action>{"type":"write_file_block","path":"docs/x.md","overwrite":true}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="save the document",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is False
    assert outcome.continue_loop is True
    assert outcome.reason == "atomic_bundle_file_content_invalid"
    assert outcome.atomic_bundle_plan is not None
    assert outcome.atomic_bundle_plan.bundle_validated is False
    assert outcome.atomic_bundle_plan.invalid_part == "file_content"
    assert outcome.atomic_bundle_plan.transition_applied is False
    assert outcome.atomic_bundle_plan.action_dispatched is False


@pytest.mark.asyncio
async def test_action_array_bundle_rejects_whole_transition_before_apply():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=False)
    state.active_intent = None
    state.intent_required_until_activated = False
    state.intent_required_reason = ""
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload={
            "mode": "activate",
            "intent_id": "save_requested_document",
            "intent_type": "MODIFY",
            "goal": "Save requested document.",
            "allowed_actions": ["write_file_block"],
            "safe_steps_limit": 2,
            "retry_limit": 1,
        },
        intent_error=None,
        model_stop_reason="",
        response=(
            '<intent mode="activate">{"mode":"activate","intent_id":"save_requested_document","intent_type":"MODIFY","goal":"Save requested document.","allowed_actions":["write_file_block"],"safe_steps_limit":2,"retry_limit":1}</intent>\n'
            '<action>[{"type":"read_chunk","path":"a.py","start_line":1,"end_line":5},{"type":"read_chunk","path":"b.py","start_line":1,"end_line":5}]</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="save the document",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is False
    assert outcome.continue_loop is True
    assert outcome.reason == "action_payload_array"
    assert outcome.execution_plan is None
    # Since this is a parse-level failure, the atomic bundle plan may not be created.


@pytest.mark.asyncio
async def test_multiple_action_blocks_bundle_rejects_whole_transition_before_apply():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=False)
    state.active_intent = None
    state.intent_required_until_activated = False
    state.intent_required_reason = ""
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload={
            "mode": "activate",
            "intent_id": "save_requested_document",
            "intent_type": "MODIFY",
            "goal": "Save requested document.",
            "allowed_actions": ["write_file_block"],
            "safe_steps_limit": 2,
            "retry_limit": 1,
        },
        intent_error=None,
        model_stop_reason="",
        response=(
            '<intent mode="activate">{"mode":"activate","intent_id":"save_requested_document","intent_type":"MODIFY","goal":"Save requested document.","allowed_actions":["write_file_block"],"safe_steps_limit":2,"retry_limit":1}</intent>\n'
            '<action>{"type":"read_chunk","path":"a.py","start_line":1,"end_line":5}</action>\n'
            '<action>{"type":"read_chunk","path":"b.py","start_line":1,"end_line":5}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="save the document",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.apply_called is False
    assert outcome.continue_loop is True
    assert outcome.reason == "atomic_bundle_action_invalid"
    assert outcome.atomic_bundle_plan is not None
    assert outcome.atomic_bundle_plan.bundle_validated is False
    assert outcome.atomic_bundle_plan.invalid_part == "action"
    assert outcome.atomic_bundle_plan.transition_applied is False
    assert outcome.atomic_bundle_plan.action_dispatched is False


@pytest.mark.asyncio
async def test_valid_bundle_emits_atomic_bundle_validated_trace_preview():
    state = DummyState(allowed_actions=["read_chunk"], hard_exhausted=True)
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        intent_payload=reuse_payload(allowed_actions=["read_chunk"]),
        intent_error=None,
        model_stop_reason="",
        response=(
            "<think>! Reuse request is valid. ? Need exact chunk. → read_chunk.</think>\n"
            "<memory_update_done />\n"
            '<action>{"type":"read_chunk","path":"x.py","start_line":1,"end_line":5}</action>'
        ),
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="continue",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is False
    trace = snapshot_trace(state)
    entries = [
        entry for entry in trace
        if entry["stage"] == "response_pipeline" and entry["decision"] == "pass" and entry["fields"].get("reason") == "atomic_bundle_validated"
    ]
    assert entries
    fields = entries[-1]["fields"]
    assert fields["bundle_validated"] is True
    assert fields["transition_applied"] is True
    assert fields["action_dispatched"] is True
    assert fields["before_active_intent_id"] == "current_intent"
    assert fields["after_active_intent_id"] == "current_intent"
