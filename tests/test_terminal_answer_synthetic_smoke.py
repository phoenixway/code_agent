from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestration.parsers.parsing import IntentResponseParser
from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.responses.response_semantics import ResponseSemantics
from modules.agent.orchestration.responses.terminal_answer_authority import (
    resolve_plaintext_terminal_answer_authority,
)
from modules.agent.orchestration.responses.terminal_answer_models import TerminalAnswerKind
from modules.parser import ResponseParser


class _TerminalAnswerSmokeHarness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
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
        )
        self.output_recovery = SimpleNamespace(
            decide=AsyncMock(
                return_value=SimpleNamespace(
                    handled=False,
                    next_query=None,
                    reason="",
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                )
            )
        )
        self.action_policy = SimpleNamespace(decide=AsyncMock(side_effect=self._action_policy_decide))
        self.STRUCTURAL_INVALID_KINDS = {
            "malformed_incomplete_think",
            "action_inside_think",
            "intent_inside_think",
            "file_content_inside_think",
            "malformed_incomplete_file_content",
            "mixed_visible_text_and_control_protocol",
            "mixed_intent_transition_and_visible_answer",
            "multiple_actions",
        }
        self.memory_checkpoint_hard_stop_streak = 3
        self.nonproductive_thinking_hard_stop_streak = 3

    async def _action_policy_decide(self, _ctx, segments, *, intent_payload=None, parsed_output=None):
        parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        return SimpleNamespace(
            handled=False,
            next_query=None,
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )


def _run_terminal_smoke(response: str):
    harness = _TerminalAnswerSmokeHarness()
    segments = harness.parser.parse(response)
    parsed_output = harness._classify_intent_output(response, segments, allow_think_autorepair=True)
    harness._apply_compiler_diagnosis(parsed_output, response)
    classified = SimpleNamespace(
        response=response,
        parsed_output=parsed_output,
        segments=segments,
        parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
    )
    checkpoint_state = SimpleNamespace(
        reflection_repair_pending=False,
        reflection_repair_kind="",
        memory_checkpoint_and_text=False,
        memory_checkpoint_and_action=False,
        memory_board_decision=SimpleNamespace(memory_checkpoint_and_text=False),
    )
    ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
    step = SimpleNamespace(response=response, intent_payload=None)
    outcome = asyncio.run(harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))
    return harness, parsed_output, classified, outcome


def _terminal_authority_calls(harness):
    return [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "terminal_answer_authority_resolution")
    ]


def test_pure_plaintext_terminal_answer_logs_legacy_authority():
    harness, parsed_output, classified, outcome = _run_terminal_smoke("The task is complete.")

    assert parsed_output.compiler_shape == "PURE_PLAINTEXT"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["branch"] == "terminal_answer.plaintext_terminal_answer"
    assert final_authority.kwargs["switch_value"] == "legacy"
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["typed_kind"] == "PLAINTEXT_TERMINAL_ANSWER"
    assert final_authority.kwargs["legacy_kind"] == "plaintext_answer_path"
    assert final_authority.kwargs["agreement"] is True
    assert final_authority.kwargs["fallback_used"] is False
    assert final_authority.kwargs["behavior_changed"] is False
    assert final_authority.kwargs["branch_active"] is True
    assert final_authority.kwargs["typed_eligible"] is True
    assert final_authority.kwargs["typed_plaintext_eligible"] is True
    assert final_authority.kwargs["has_action"] is False
    assert final_authority.kwargs["has_checkpoint"] is False
    assert final_authority.kwargs["is_leaked_system_result"] is False
    assert final_authority.kwargs["clean_plaintext_candidate"] is True
    assert final_authority.kwargs["blocking_reasons"] == ()


def test_done_single_line_characterizes_current_plaintext_blocker():
    harness, parsed_output, classified, outcome = _run_terminal_smoke("Done.")

    assert parsed_output.compiler_shape == "PURE_PLAINTEXT"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["switch_value"] == "legacy"
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["branch_active"] is True
    assert final_authority.kwargs["typed_eligible"] is False
    assert final_authority.kwargs["typed_plaintext_eligible"] is False
    assert final_authority.kwargs["typed_kind"] == "INVALID_OR_TRUNCATED_TERMINAL_TEXT"
    assert final_authority.kwargs["agreement"] is False
    assert final_authority.kwargs["invalid_or_truncated_terminal_text"] is True
    assert final_authority.kwargs["clean_plaintext_candidate"] is False
    assert "invalid_or_truncated_terminal_text" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "invalid_or_truncated_plaintext_overlap"


def test_multiline_plaintext_characterizes_current_clean_alignment():
    response = "Done.\n\nHere is the summary."
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.compiler_shape == "PURE_PLAINTEXT"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["typed_kind"] == "PLAINTEXT_TERMINAL_ANSWER"
    assert final_authority.kwargs["agreement"] is True
    assert final_authority.kwargs["typed_eligible"] is True
    assert final_authority.kwargs["typed_plaintext_eligible"] is True
    assert final_authority.kwargs["clean_plaintext_candidate"] is True
    assert final_authority.kwargs["blocking_reasons"] == ()
    assert final_authority.kwargs["mismatch_reason"] == ""


def test_markdownish_plaintext_characterizes_current_single_line_style_blocker():
    response = "# Summary\n\nDone."
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.compiler_shape == "PURE_PLAINTEXT"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["typed_eligible"] is False
    assert final_authority.kwargs["typed_plaintext_eligible"] is False
    assert final_authority.kwargs["agreement"] is False
    assert final_authority.kwargs["invalid_or_truncated_terminal_text"] is True
    assert "invalid_or_truncated_terminal_text" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "invalid_or_truncated_plaintext_overlap"


def test_preactionish_plaintext_without_action_stays_on_current_plaintext_path():
    response = "I will inspect the file."
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.compiler_shape == "PURE_PLAINTEXT"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["typed_eligible"] is True
    assert final_authority.kwargs["typed_plaintext_eligible"] is True
    assert final_authority.kwargs["clean_plaintext_candidate"] is True
    assert final_authority.kwargs["agreement"] is True


def test_action_only_does_not_activate_plaintext_terminal_authority():
    response = '<action>{"type":"read_file","path":"README.md"}</action>'
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.compiler_shape == "ACTION_ONLY"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.NO_VISIBLE_TEXT
    assert classified.parsed_action_count == 1
    assert outcome.reason == "dispatch_ready"
    assert outcome.parsed_action_count == 1
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["legacy_active"] is False
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["typed_eligible"] is False
    assert final_authority.kwargs["fallback_used"] is True
    assert final_authority.kwargs["has_action"] is True
    assert final_authority.kwargs["has_checkpoint"] is False
    assert final_authority.kwargs["action_or_pre_action_overlap"] is True
    assert "action_or_pre_action_overlap" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "action_or_pre_action_overlap"


def test_pre_action_text_and_action_is_not_treated_as_terminal_plaintext():
    response = 'I will inspect the file.\n<action>{"type":"read_file","path":"README.md"}</action>'
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.compiler_shape == "PRE_ACTION_TEXT_AND_ACTION"
    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.PRE_ACTION_VISIBLE_TEXT_WITH_ACTION
    assert classified.parsed_action_count == 1
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["legacy_active"] is False
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["typed_kind"] == "PRE_ACTION_VISIBLE_TEXT_WITH_ACTION"
    assert final_authority.kwargs["has_action"] is True
    assert final_authority.kwargs["has_checkpoint"] is False
    assert final_authority.kwargs["action_or_pre_action_overlap"] is True
    assert "action_or_pre_action_overlap" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "action_or_pre_action_overlap"


def test_checkpoint_only_characterization_does_not_activate_plaintext_terminal_authority():
    response = "<memory_update_done />"
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.CHECKPOINT_ONLY
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["legacy_active"] is False
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["typed_kind"] == "CHECKPOINT_ONLY"
    assert final_authority.kwargs["has_checkpoint"] is True
    assert final_authority.kwargs["has_action"] is False
    assert final_authority.kwargs["checkpoint_with_visible_text_overlap"] is False


def test_checkpoint_with_visible_text_characterizes_current_plaintext_disagreement():
    response = "<memory_update_done />\nDone."
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.CHECKPOINT_WITH_VISIBLE_TEXT
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["branch_active"] is True
    assert final_authority.kwargs["agreement"] is False
    assert final_authority.kwargs["typed_kind"] == "CHECKPOINT_WITH_VISIBLE_TEXT"
    assert final_authority.kwargs["legacy_kind"] == "plaintext_answer_path"
    assert final_authority.kwargs["typed_eligible"] is False
    assert final_authority.kwargs["has_checkpoint"] is True
    assert final_authority.kwargs["checkpoint_with_visible_text_overlap"] is True
    assert "checkpoint_with_visible_text_overlap" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "checkpoint_visible_text_overlap"


def test_unclosed_think_keeps_invalid_recovery_behavior_and_no_plaintext_authority():
    response = "<think>\nI am still thinking"
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.compiler_shape == "INVALID"
    assert parsed_output.compiler_error_code == "E_UNCLOSED_THINK"
    assert outcome.continue_loop is True
    assert outcome.reason == "malformed_incomplete_think"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["legacy_active"] is False
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["invalid_kind"] == "malformed_incomplete_think"
    assert "invalid_kind" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "invalid_output"


def test_empty_output_keeps_current_behavior_without_plaintext_authority():
    harness, parsed_output, classified, outcome = _run_terminal_smoke("")

    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.NO_VISIBLE_TEXT
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["legacy_active"] is False
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["blocking_reasons"] == ()
    assert final_authority.kwargs["mismatch_reason"] == "branch_inactive"


def test_leaked_system_result_keeps_existing_recovery_path():
    response = "SYSTEM RESULT: The tool output is..."
    harness, parsed_output, classified, outcome = _run_terminal_smoke(response)

    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
    assert outcome.continue_loop is True
    assert outcome.reason == "leaked_system_result_in_assistant_text"
    authority_calls = _terminal_authority_calls(harness)
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["branch_active"] is True
    assert final_authority.kwargs["typed_eligible"] is False
    assert final_authority.kwargs["is_leaked_system_result"] is True
    assert final_authority.kwargs["leaked_system_result_overlap"] is True
    assert "leaked_system_result_overlap" in final_authority.kwargs["blocking_reasons"]
    assert final_authority.kwargs["mismatch_reason"] == "leaked_system_result_overlap"


def test_whitespace_only_output_keeps_plaintext_authority_inactive():
    harness, parsed_output, classified, outcome = _run_terminal_smoke("   \n\t")

    assert parsed_output.terminal_answer_semantic_result.kind == TerminalAnswerKind.NO_VISIBLE_TEXT
    assert classified.parsed_action_count == 0
    assert outcome.reason == "dispatch_ready"
    authority_calls = _terminal_authority_calls(harness)
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["legacy_active"] is False
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["legacy_kind"] == "none"
    assert final_authority.kwargs["blocking_reasons"] == ()
    assert final_authority.kwargs["mismatch_reason"] == "branch_inactive"


def test_plaintext_authority_resolver_directly_exposes_clean_and_blocked_buckets():
    clean = SimpleNamespace(
        terminal_answer_semantic_result=SimpleNamespace(kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER),
        compiler_ir=SimpleNamespace(
            has_action=False,
            has_checkpoint=False,
            has_memory_tags=False,
            has_subgoal_tags=False,
            has_memory_checkpoint=False,
        ),
        invalid_kind="",
        compiler_shape="PURE_PLAINTEXT",
    )
    clean_result = resolve_plaintext_terminal_answer_authority(
        clean,
        legacy_plaintext_answer_path=True,
        switch_value="legacy",
    )
    assert clean_result.clean_plaintext_candidate is True
    assert clean_result.blocking_reasons == ()
    assert clean_result.mismatch_reason == ""

    blocked = SimpleNamespace(
        terminal_answer_semantic_result=SimpleNamespace(kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT),
        compiler_ir=SimpleNamespace(
            has_action=False,
            has_checkpoint=False,
            has_memory_tags=False,
            has_subgoal_tags=False,
            has_memory_checkpoint=False,
        ),
        invalid_kind="",
        compiler_shape="PURE_PLAINTEXT",
    )
    blocked_result = resolve_plaintext_terminal_answer_authority(
        blocked,
        legacy_plaintext_answer_path=True,
        switch_value="legacy",
    )
    assert blocked_result.clean_plaintext_candidate is False
    assert blocked_result.leaked_system_result_overlap is True
    assert "leaked_system_result_overlap" in blocked_result.blocking_reasons
    assert blocked_result.mismatch_reason == "leaked_system_result_overlap"
