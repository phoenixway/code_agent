from __future__ import annotations

from types import SimpleNamespace

from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.agent.orchestration.runtime.action_policy import ActionPolicyHandler
from modules.agent.orchestration.runtime.policy import IntentGuard


class _Segment:
    def __init__(self, seg_type, content):
        self.type = seg_type
        self.content = content


class _Config:
    INTENTLESS_SHORT_MODE_MAX_STEPS = 2
    INTENT_REUSE_EXTENSION_STEPS = 4


def _active_intent():
    return SimpleNamespace(
        intent_id="save_doc",
        intent_type="MODIFY",
        goal="Save analysis",
        allowed_actions=["write_file_block"],
        lineage_id="save_doc",
        retry_count=0,
        retry_limit=2,
        blocked_action_signatures=set(),
        blocked_action_reasons={},
        action_constraints={},
        original_allowed_actions=["write_file_block"],
        user_visible_note="",
        canonical_goal="Save analysis",
        goal_frozen=True,
        hard_limit_hit_count=0,
        user_step_extension=0,
        user_one_shot_steps_remaining=0,
        user_unlimited_override=False,
        force_plaintext_completion=False,
    )


def _handler():
    state = SimpleNamespace(
        active_intent=_active_intent(),
        intent_runtime=SimpleNamespace(
            intent_required_until_activated=False,
            intent_required_reason="",
        ),
        has_hard_exhausted_active_intent=lambda: False,
        build_fix_mode_requires_intent=lambda: False,
        is_build_fix_intent_active=lambda: False,
        compiler_mentioned_file_allowed=lambda path: False,
        task_board=None,
        orchestration_trace=[],
        orchestration_trace_sequence=0,
        disallowed_action_repeat_type="",
        disallowed_action_repeat_intent_id="",
        disallowed_action_repeat_count=0,
        last_blocked_action_type="",
        last_blocked_action_path="",
        pending_edit_mismatch_path="",
        pending_edit_mismatch_intent_id="",
    )
    agent = SimpleNamespace(state=state, config=_Config(), log=None)
    prompt_builder = OrchestratorPromptBuilder(
        SimpleNamespace(state=state, config=_Config(), memory_board_store=None, log=None)
    )
    return ActionPolicyHandler(agent, IntentGuard(), prompt_builder)


def test_atomic_bundle_validation_uses_compiler_ir_file_content_when_segment_payload_lacks_it():
    handler = _handler()
    ctx = SimpleNamespace(
        user_input="Save analysis",
        parsed_output=SimpleNamespace(
            compiler_shape="INTENT_ACTION_BUNDLE",
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="write_file_block",
                        payload={"type": "write_file_block", "path": "docs/out.md", "overwrite": True},
                        file_content="# Saved\n",
                        read_only=False,
                        write_like=True,
                    )
                ]
            ),
        ),
    )

    result = handler.validate_atomic_bundle_action(
        ctx,
        [_Segment("action", {"type": "write_file_block", "path": "docs/out.md", "overwrite": True})],
        proposed_active_intent=_active_intent(),
    )

    assert result.ok is True


def test_atomic_bundle_validation_uses_compiler_ir_payload_for_allowed_action_check():
    handler = _handler()
    proposed_active_intent = SimpleNamespace(
        **{**_active_intent().__dict__, "allowed_actions": ["read_chunk"]}
    )
    ctx = SimpleNamespace(
        user_input="Continue same investigation",
        parsed_output=SimpleNamespace(
            compiler_shape="INTENT_ACTION_BUNDLE",
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="write_file_block",
                        payload={"type": "write_file_block", "path": "docs/out.md", "overwrite": True},
                        file_content="# Saved\n",
                        read_only=False,
                        write_like=True,
                    )
                ]
            ),
        ),
    )

    result = handler.validate_atomic_bundle_action(
        ctx,
        [_Segment("action", {"type": "tool_call", "path": "docs/out.md"})],
        proposed_active_intent=proposed_active_intent,
    )

    assert result.ok is False
    assert result.reason == "intent_action_not_allowed"


def test_atomic_bundle_validation_can_run_from_compiler_ir_without_legacy_action_segment():
    handler = _handler()
    ctx = SimpleNamespace(
        user_input="Save analysis",
        parsed_output=SimpleNamespace(
            compiler_shape="INTENT_ACTION_BUNDLE",
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="write_file_block",
                        payload={"type": "write_file_block", "path": "docs/out.md", "overwrite": True},
                        file_content="# Saved\n",
                        read_only=False,
                        write_like=True,
                    )
                ]
            ),
        ),
    )

    result = handler.validate_atomic_bundle_action(
        ctx,
        [_Segment("text", "placeholder")],
        proposed_active_intent=_active_intent(),
    )

    assert result.ok is True


def test_atomic_bundle_validation_rejects_multiple_ir_actions_even_without_legacy_segments():
    handler = _handler()
    ctx = SimpleNamespace(
        user_input="Continue same investigation",
        parsed_output=SimpleNamespace(
            compiler_shape="INTENT_ACTION_BUNDLE",
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="read_chunk",
                        payload={"type": "read_chunk", "path": "a.py", "start_line": 1, "end_line": 5},
                        file_content=None,
                        read_only=True,
                        write_like=False,
                    ),
                    SimpleNamespace(
                        action_type="read_chunk",
                        payload={"type": "read_chunk", "path": "b.py", "start_line": 1, "end_line": 5},
                        file_content=None,
                        read_only=True,
                        write_like=False,
                    ),
                ]
            ),
        ),
    )

    result = handler.validate_atomic_bundle_action(
        ctx,
        [_Segment("text", "placeholder")],
        proposed_active_intent=SimpleNamespace(**{**_active_intent().__dict__, "allowed_actions": ["read_chunk"]}),
    )

    assert result.ok is False
    assert result.reason == "atomic_bundle_requires_exactly_one_action"


async def _decide_with_ir(handler, *, allowed_actions):
    handler.state.active_intent.allowed_actions = list(allowed_actions)
    return await handler.decide(
        SimpleNamespace(user_input="Continue"),
        [_Segment("action", {"type": "tool_call", "path": "a.py"})],
        intent_payload=None,
        parsed_output=SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="write_file_block",
                        payload={"type": "write_file_block", "path": "a.py", "overwrite": True},
                        file_content="hello\n",
                        read_only=False,
                        write_like=True,
                    )
                ]
            ),
        ),
    )


def test_disallowed_active_intent_action_can_be_driven_by_compiler_ir_payload():
    import asyncio

    handler = _handler()
    decision = asyncio.run(_decide_with_ir(handler, allowed_actions=["edit_file", "read_chunk"]))

    assert decision.handled is True
    assert decision.reason == "intent_action_not_allowed"


def test_allowed_active_intent_action_can_be_driven_by_compiler_ir_payload():
    import asyncio

    handler = _handler()
    decision = asyncio.run(_decide_with_ir(handler, allowed_actions=["write_file", "read_chunk"]))

    assert decision.handled is False
    assert decision.reason == "actions_allowed_to_proceed"
