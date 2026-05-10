from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestration.parsers.parsing import IntentResponseParser
from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.responses.response_semantics import ResponseSemantics
from modules.agent.orchestration.responses.terminal_answer_models import TerminalAnswerKind
from modules.parser import ResponseParser


class _RecoverySmokeHarness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
    COMPILER_DRIVEN_INVALID_KINDS = {
        "malformed_incomplete_think",
        "action_inside_think",
        "intent_inside_think",
        "file_content_inside_think",
        "malformed_incomplete_file_content",
        "mixed_visible_text_and_control_protocol",
        "mixed_intent_transition_and_visible_answer",
        "action_payload_array",
        "action_payload_xml_fields",
        "action_payload_tool_code",
        "action_payload_not_object",
        "protocol_tag_in_json_string",
        "multiple_actions",
        "file_content_must_follow_action",
        "conflicting_intent_transitions",
        "intent_complete_with_action_not_allowed",
    }
    STRUCTURAL_INVALID_KINDS = {
        "malformed_incomplete_think",
        "action_inside_think",
        "intent_inside_think",
        "file_content_inside_think",
        "malformed_incomplete_file_content",
        "mixed_visible_text_and_control_protocol",
        "mixed_intent_transition_and_visible_answer",
        "multiple_actions",
    }

    def __init__(self):
        self.protocol_compiler = ProtocolCompiler()
        self.parser = ResponseParser()
        self.intent_response_parser = IntentResponseParser()
        self.semantics = ResponseSemantics()
        self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
        self.prompt_builder = SimpleNamespace(
            build_leaked_system_result_recovery_prompt=MagicMock(return_value="leak_recovery_prompt"),
            build_missing_action_or_answer_prompt=MagicMock(return_value="missing_action_or_answer_prompt"),
            build_multiple_actions_prompt=MagicMock(return_value="multiple_actions_prompt"),
            build_reflection_repair_accepted_prompt=MagicMock(return_value="reflection_repair_prompt"),
            build_durable_state_repair_prompt=MagicMock(return_value="durable_state_repair_prompt"),
            build_repeated_thinking_without_valid_output_prompt=MagicMock(return_value="thinking_guard_prompt"),
            build_plain_text_completion_prompt=MagicMock(return_value="plain_text_completion_prompt"),
            build_atomic_bundle_rejected_prompt=MagicMock(return_value="atomic_bundle_rejected_prompt"),
        )
        self.state = SimpleNamespace(
            active_intent=None,
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
            last_memory_update_done=False,
        )
        self.guards = SimpleNamespace(
            set_reflection_repair_pending=MagicMock(),
            set_nonproductive_thinking_state=MagicMock(return_value=0),
            is_nonproductive_thinking_turn=MagicMock(return_value=False),
            clear_terminal_plaintext_completion=MagicMock(),
            reflection_repair_pending=MagicMock(return_value=False),
            reflection_repair_kind=MagicMock(return_value=""),
        )
        self.output_recovery = SimpleNamespace(
            decide=AsyncMock(side_effect=self._output_recovery_decide)
        )
        self.action_policy = SimpleNamespace(decide=AsyncMock(side_effect=self._action_policy_decide))
        self.intent_transitions = SimpleNamespace(
            preview_payload_decision=MagicMock(
                return_value=SimpleNamespace(
                    applied=True,
                    active_intent=SimpleNamespace(intent_type="test_intent", allowed_actions=[]),
                )
            )
        )
        self.memory_checkpoint_hard_stop_streak = 3
        self.nonproductive_thinking_hard_stop_streak = 3

    async def _output_recovery_decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        if invalid_kind:
            return SimpleNamespace(
                handled=True,
                continue_loop=True,
                next_query=f"recover::{invalid_kind}",
                stop_loop=False,
                malformed_action_retries=malformed_action_retries,
                audit_marker_retries=audit_marker_retries,
                reason=invalid_kind,
                source="output_recovery",
            )
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            next_query=None,
            stop_loop=False,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            reason="",
            source="output_recovery",
        )

    async def _action_policy_decide(self, _ctx, segments, *, intent_payload=None, parsed_output=None):
        parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        return SimpleNamespace(
            handled=False,
            next_query=None,
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )


def _recovery_authority_calls(harness, branch: str):
    return [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "recovery_authority_resolution")
        and call.kwargs.get("branch") == branch
    ]


def _run_full_path_smoke(response: str):
    harness = _RecoverySmokeHarness()
    checkpoint_state = SimpleNamespace(
        response=response,
        reflection_repair_pending=False,
        reflection_repair_kind="",
        plan_checkpoint_only=False,
        plan_checkpoint_and_text=False,
        plan_checkpoint_and_action=False,
        memory_checkpoint_only=False,
        memory_checkpoint_and_text=False,
        memory_checkpoint_and_action=False,
        memory_board_decision=SimpleNamespace(memory_checkpoint_and_text=False),
    )
    step = SimpleNamespace(response=response, intent_payload=None, model_stop_reason="")
    classified = harness._run_classification_stage(step, response, checkpoint_state)
    ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0, state_machine=None)
    outcome = asyncio.run(harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))
    return harness, classified, outcome


def _run_full_path_smoke_with_harness(harness, response: str):
    checkpoint_state = SimpleNamespace(
        response=response,
        reflection_repair_pending=False,
        reflection_repair_kind="",
        plan_checkpoint_only=False,
        plan_checkpoint_and_text=False,
        plan_checkpoint_and_action=False,
        memory_checkpoint_only=False,
        memory_checkpoint_and_text=False,
        memory_checkpoint_and_action=False,
        memory_board_decision=SimpleNamespace(memory_checkpoint_and_text=False),
    )
    step = SimpleNamespace(response=response, intent_payload=None, model_stop_reason="")
    classified = harness._run_classification_stage(step, response, checkpoint_state)
    ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0, state_machine=None)
    outcome = asyncio.run(harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))
    return classified, outcome


def _run_intent_prevalidation_smoke(response: str, *, mode: str = "activate"):
    harness = _RecoverySmokeHarness()
    ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0, state_machine=None)
    step = SimpleNamespace(
        response=response,
        intent_payload={"mode": mode, "goal": "test-goal"},
        model_stop_reason="",
    )
    outcome = asyncio.run(
        harness._reject_invalid_intent_followup_before_transition(ctx, response, step)
    )
    return harness, outcome


def test_unclosed_think_logs_invalid_mapping_and_preserves_recovery_behavior():
    harness, classified, outcome = _run_full_path_smoke("<think>\nI am still thinking")

    assert classified.parsed_output.compiler_shape == "INVALID"
    assert classified.parsed_output.compiler_error_code == "E_UNCLOSED_THINK"
    assert classified.parsed_output.invalid_kind == "malformed_incomplete_think"
    assert outcome.continue_loop is True
    assert outcome.reason == "malformed_incomplete_think"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["authority_source"] == "compiler"
    assert diagnostic["effective_invalid_kind"] == "malformed_incomplete_think"
    assert diagnostic["behavior_changed"] is False
    assert diagnostic["branch_active"] is True


def test_malformed_action_json_logs_prevalidation_recovery_diagnostic():
    harness, outcome = _run_intent_prevalidation_smoke('<action>{"type":"read_file","path":</action>')

    assert outcome is not None
    assert outcome.continue_loop is True
    diagnostic = _recovery_authority_calls(harness, "recovery.prevalidation_reject_invalid_output")[-1].kwargs
    assert diagnostic["effective_invalid_kind"] == "malformed_action"
    assert diagnostic["recovery_action"] == "malformed_action"
    assert diagnostic["behavior_changed"] is False
    assert diagnostic["branch_active"] is True


def test_leaked_system_result_is_characterized_without_terminal_authority_transfer():
    harness, classified, outcome = _run_full_path_smoke("SYSTEM RESULT: The tool output is...")

    assert classified.parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
    assert outcome.continue_loop is True
    assert outcome.reason == "leaked_system_result_in_assistant_text"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["typed_kind"] == "LEAKED_SYSTEM_RESULT"
    assert diagnostic["is_leaked_system_result"] is True
    assert diagnostic["behavior_changed"] is False


def test_invalid_truncated_terminal_text_is_characterized_without_dispatch():
    harness, classified, outcome = _run_full_path_smoke("And.")

    assert classified.parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["typed_kind"] == "INVALID_OR_TRUNCATED_TERMINAL_TEXT"
    assert diagnostic["behavior_changed"] is False


def test_memory_tag_inside_think_is_characterized_as_invalid_without_checkpoint_authority():
    harness, classified, outcome = _run_full_path_smoke("<think>\n<memory_update_done />")

    assert classified.parsed_output.compiler_shape == "INVALID"
    assert classified.parsed_output.compiler_error_code
    assert outcome.continue_loop is True
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["compiler_error_code"]
    assert diagnostic["has_checkpoint"] is False
    assert diagnostic["behavior_changed"] is False


def test_checkpoint_tag_inside_think_is_characterized_as_invalid_without_checkpoint_authority():
    harness, classified, outcome = _run_full_path_smoke('<think>\n<subgoal action="mark_in_progress" id="sg_1" />')

    assert classified.parsed_output.compiler_shape == "INVALID"
    assert classified.parsed_output.compiler_error_code
    assert outcome.continue_loop is True
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["compiler_error_code"]
    assert diagnostic["has_checkpoint"] is False
    assert diagnostic["behavior_changed"] is False


def test_empty_output_is_characterized_without_recovery_authority_transfer():
    harness, classified, outcome = _run_full_path_smoke("   \n\t")

    assert classified.parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.NO_VISIBLE_TEXT
    assert outcome.reason == "dispatch_ready"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["branch"] == "recovery.compiler_invalid_kind_mapping"
    assert diagnostic["behavior_changed"] is False
    assert diagnostic["effective_invalid_kind"] == ""


def test_pre_action_text_with_action_keeps_dispatch_safe_and_logs_recovery_mapping():
    response = 'I will inspect the file.\n<action>{"type":"read_file","path":"README.md"}</action>'
    harness, classified, outcome = _run_full_path_smoke(response)

    assert classified.parsed_action_count == 1
    assert outcome.reason == "dispatch_ready"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["has_action"] is True
    assert diagnostic["behavior_changed"] is False


def test_internal_summary_recovery_is_characterized_without_terminal_authority_transfer():
    harness = _RecoverySmokeHarness()
    harness._is_internal_summary_instead_of_final_answer = MagicMock(return_value=True)
    classified, outcome = _run_full_path_smoke_with_harness(
        harness,
        "ACTIVE GOAL: Refactor the file.\nCURRENT STATUS: collecting evidence.",
    )

    assert classified.parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.INTERNAL_SUMMARY_LIKE_TEXT
    assert outcome.reason == "dispatch_ready"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["typed_kind"] == "INTERNAL_SUMMARY_LIKE_TEXT"
    assert diagnostic["is_internal_summary"] is True
    assert diagnostic["branch_active"] is False
    assert diagnostic["behavior_changed"] is False


def test_mixed_visible_answer_and_invalid_protocol_is_characterized_as_recovery():
    response = "Done.\n<think>\nstill thinking"
    harness, classified, outcome = _run_full_path_smoke(response)

    assert classified.parsed_output.compiler_error_code == "E_UNCLOSED_THINK"
    assert outcome.continue_loop is True
    assert outcome.reason == "malformed_incomplete_think"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["effective_invalid_kind"] == "malformed_incomplete_think"
    assert diagnostic["has_visible_text"] is True
    assert diagnostic["behavior_changed"] is False


def test_repeated_thinking_guard_is_characterized_when_no_specific_recovery_branch_is_active():
    harness = _RecoverySmokeHarness()
    harness.guards.is_nonproductive_thinking_turn = MagicMock(return_value=True)
    harness.guards.set_nonproductive_thinking_state = MagicMock(return_value=3)
    classified, outcome = _run_full_path_smoke_with_harness(
        harness,
        "I am still thinking about the next step.",
    )

    assert classified.parsed_output.invalid_kind == ""
    assert outcome.continue_loop is True
    assert outcome.reason == "repeated_thinking_without_valid_output"
    assert outcome.source == "thinking_guard"


def test_malformed_action_with_pre_action_text_logs_visible_text_and_guard_metadata():
    response = 'I will inspect the file.\n<action>{"type":"read_file","path":</action>'
    harness, outcome = _run_intent_prevalidation_smoke(response)

    assert outcome is not None
    assert outcome.continue_loop is True
    diagnostic = _recovery_authority_calls(harness, "recovery.prevalidation_reject_invalid_output")[-1].kwargs
    assert diagnostic["effective_invalid_kind"] == "mixed_visible_text_and_control_protocol"
    assert diagnostic["has_visible_text"] is True
    assert diagnostic["recovery_reason"] == "mixed_visible_text_and_control_protocol"
    assert diagnostic["guard_name"] == "intent_atomicity_guard"
    assert diagnostic["guard_triggered"] is True


def test_action_only_valid_control_does_not_select_recovery_branch():
    harness, classified, outcome = _run_full_path_smoke('<action>{"type":"read_file","path":"README.md"}</action>')

    assert classified.parsed_action_count == 1
    assert outcome.reason == "dispatch_ready"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["branch_active"] is False
    assert diagnostic["has_action"] is True
    assert diagnostic["effective_invalid_kind"] == ""


def test_clean_plaintext_control_does_not_select_recovery_branch():
    harness, classified, outcome = _run_full_path_smoke("Done.")

    assert classified.parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
    assert outcome.reason == "dispatch_ready"
    diagnostic = _recovery_authority_calls(harness, "recovery.compiler_invalid_kind_mapping")[-1].kwargs
    assert diagnostic["branch_active"] is False
    assert diagnostic["typed_kind"] == "PLAINTEXT_TERMINAL_ANSWER"
    assert diagnostic["effective_invalid_kind"] == ""
