"""Unit tests for ResponsePipelineStagesMixin."""

import asyncio
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.agent.orchestration.protocol import ProtocolCompiler
from modules.agent.orchestration.runtime.policy import IntentGuard
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.board_checkpoint_models import (
    BoardCheckpointKind,
    EffectiveCheckpointFlags,
    BoardCheckpointSemanticResult,
    BoardCheckpointSource,
)
from modules.agent.orchestration.responses.board_checkpoint_semantics import (
    build_board_checkpoint_semantic_result,
    resolve_plan_checkpoint_and_action_authority,
    resolve_plan_checkpoint_and_text_authority,
    resolve_plan_checkpoint_only_authority,
    resolve_legacy_derived_checkpoint_effective_flags,
    resolve_memory_checkpoint_and_action_typed_primary,
    resolve_memory_checkpoint_and_text_typed_primary,
    resolve_memory_checkpoint_only_typed_primary,
    resolve_plan_checkpoint_and_action_typed_primary,
    resolve_plan_checkpoint_and_text_typed_primary,
    resolve_plan_checkpoint_only_typed_primary,
    resolve_plan_checkpoint_only_with_compiler_switch,
)
from modules.agent.orchestration.responses.response_pipeline_stages import CheckpointStageState, ResponsePipelineStagesMixin
from modules.agent.orchestration.responses.terminal_answer_authority import TerminalAnswerAuthorityDiagnostic
from modules.agent.orchestration.responses.terminal_answer_models import TerminalAnswerKind, TerminalAnswerSemanticResult
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput, ResponsePipelineOutcome


class TestResponsePipelineStages(unittest.TestCase):
    def setUp(self):
        # Minimal harness to test the mixin
        class Harness(ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.STRUCTURAL_INVALID_KINDS = set()
                self.semantics = SimpleNamespace(
                    has_any_action_proposal=MagicMock(return_value=False),
                    is_plaintext_answer_path=MagicMock(return_value=False),
                    has_memory_update_done=MagicMock(return_value=False),
                    looks_like_leaked_system_result=MagicMock(return_value=False),
                    is_reflection_only_repair_turn=MagicMock(return_value=False),
                    is_durable_state_repair_turn=MagicMock(return_value=False),
                )
                self._has_any_action_proposal = self.semantics.has_any_action_proposal
                self.guards = SimpleNamespace(
                    set_reflection_repair_pending=MagicMock(),
                    set_nonproductive_thinking_state=MagicMock(),
                    is_nonproductive_thinking_turn=MagicMock(return_value=False),
                    clear_terminal_plaintext_completion=MagicMock(),
                )
                self.stage_logger = SimpleNamespace(log=MagicMock())
                self.prompt_builder = SimpleNamespace(
                    build_leaked_system_result_recovery_prompt=MagicMock(return_value="recovery_prompt")
                )
                self.output_recovery = SimpleNamespace(
                    decide=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="other_recovery_prompt",
                            reason="other_recovery",
                            malformed_action_retries=0,
                            audit_marker_retries=0,
                        )
                    )
                )

        self.harness = Harness()

    def test_build_execution_plan_characterizes_current_field_population(self):
        self.harness.semantics.has_any_action_proposal.return_value = True
        self.harness.state.active_intent = SimpleNamespace(intent_id="intent_after")
        self.harness.state.intent_runtime = SimpleNamespace(
            last_transition_info={"before_active_intent_id": "intent_before"}
        )

        step = SimpleNamespace(intent_payload={"mode": "activate", "intent_id": "intent_payload"})
        action_payload = {"path": "README.md"}
        parsed_output = SimpleNamespace(
            compiler_shape="INTENT_ACTION_BUNDLE",
            compiler_ir=SimpleNamespace(
                has_pre_action_text=False,
                pre_action_text="",
                action_ops=[
                    SimpleNamespace(action_type="read_file", payload=action_payload),
                ],
            ),
        )

        plan = self.harness._build_execution_plan(step, parsed_output, parsed_action_count=1)

        self.assertIsNotNone(plan)
        self.assertEqual("INTENT_ACTION_BUNDLE", plan.shape)
        self.assertEqual("atomic_intent_action_bundle", plan.transaction_kind)
        self.assertEqual(["activate_intent:intent_after"], plan.state_effects)
        self.assertEqual(["read_file:README.md"], plan.action_effects)
        self.assertEqual([], plan.output_effects)
        self.assertTrue(plan.bundle_validated)
        self.assertTrue(plan.transition_applied)
        self.assertFalse(plan.action_dispatched)
        self.assertFalse(plan.active_intent_unchanged)
        self.assertEqual("intent_before", plan.before_active_intent_id)
        self.assertEqual("intent_after", plan.after_active_intent_id)

        # Phase 9 Step 6A observational enrichment
        self.assertEqual("compiler_ir", plan.plan_source)
        self.assertEqual(1, plan.action_op_count)
        self.assertEqual([action_payload], plan.action_payload_snapshot)
        self.assertIsNot(action_payload, plan.action_payload_snapshot[0])
        self.assertEqual("single_action_candidate_possible", plan.candidate_eligibility_status)
        self.assertEqual("", plan.pre_action_text_source)

    def test_build_execution_plan_returns_none_without_compiler_ir(self):
        self.harness.semantics.has_any_action_proposal.return_value = True
        step = SimpleNamespace(intent_payload={"mode": "reuse", "intent_id": "intent_1"})
        parsed_output = SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=None,
        )

        plan = self.harness._build_execution_plan(step, parsed_output, parsed_action_count=1)

        self.assertIsNone(plan)

    def test_build_execution_plan_returns_none_when_action_proposal_absent(self):
        self.harness.semantics.has_any_action_proposal.return_value = False
        step = SimpleNamespace(intent_payload={"mode": "reuse", "intent_id": "intent_1"})
        parsed_output = SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=SimpleNamespace(
                has_pre_action_text=False,
                pre_action_text="",
                action_ops=[SimpleNamespace(action_type="read_file", payload={"path": "README.md"})],
            ),
        )

        plan = self.harness._build_execution_plan(step, parsed_output, parsed_action_count=1)

        self.assertIsNone(plan)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_typed_leaked_system_result_triggers_recovery(self, mock_is_leaked):
        """Typed LEAKED_SYSTEM_RESULT is the primary signal for leaked-result recovery."""
        mock_is_leaked.return_value = False

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT: ...")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
                source="legacy_compatible_rule",
                reason_code="looks_like_leaked_system_result",
            ),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT: ...",
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_not_called()
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")
        self.harness.semantics.has_any_action_proposal.assert_called_once()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_legacy_fallback_triggers_when_typed_result_absent(self, mock_is_leaked):
        """Legacy accessor remains the fallback when no typed result is present."""
        mock_is_leaked.return_value = True

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT: ...")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT: ...",
            parsed_output=ParsedModelOutput(response=""),
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_called_once_with("SYSTEM RESULT: ...")
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")
        self.harness.semantics.has_any_action_proposal.assert_called_once()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_legacy_fallback_triggers_when_typed_result_is_not_leak(self, mock_is_leaked):
        """Legacy accessor remains fallback when typed result is present but not leaked."""
        mock_is_leaked.return_value = True

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT for tool_xyz")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
                source="compiler_fact",
                reason_code="visible_text_source_is_pure_plaintext",
            ),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT for tool_xyz",
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_called_once_with("SYSTEM RESULT for tool_xyz")
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_no_action_guard_prevents_leak_recovery(self, mock_is_leaked):
        """Leak recovery must not trigger when there is an action proposal."""
        mock_is_leaked.return_value = True
        self.harness.semantics.has_any_action_proposal.return_value = True

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT: ...")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
                source="legacy_compatible_rule",
                reason_code="looks_like_leaked_system_result",
            ),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT: ...",
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=1,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_not_called()
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "other_recovery_prompt")

    def test_non_migrated_dispatch_ready_path_still_carries_segments_without_plan(self):
        """Current fallback remains segment-driven when no authoritative compiler IR plan exists."""
        self.harness.semantics.has_any_action_proposal.return_value = True
        self.harness.output_recovery.decide = AsyncMock(
            return_value=SimpleNamespace(
                handled=False,
                next_query=None,
                reason="",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )
        )
        self.harness.action_policy = SimpleNamespace(
            decide=AsyncMock(
                return_value=SimpleNamespace(
                    handled=False,
                    next_query=None,
                    reason="actions_allowed_to_proceed",
                    source="action_policy",
                    parsed_action_count=1,
                )
            )
        )

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response='<action>{"type":"read_file","path":"README.md"}</action>', intent_payload=None)
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(memory_checkpoint_and_text=False),
        )
        action_segment = SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})
        parsed_output = ParsedModelOutput(response="", compiler_shape="ACTION_ONLY", compiler_ir=None)
        classified = SimpleNamespace(
            response=step.response,
            parsed_output=parsed_output,
            segments=[action_segment],
            parsed_action_count=1,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertFalse(outcome.continue_loop)
        self.assertFalse(outcome.stop_loop)
        self.assertEqual("dispatch_ready", outcome.reason)
        self.assertIsNone(outcome.execution_plan)
        self.assertEqual([action_segment], outcome.segments)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.get_switch", return_value="compiler")
    @patch("modules.agent.orchestration.responses.response_pipeline_stages.resolve_plaintext_terminal_answer_authority")
    def test_smoke_profile_plaintext_effective_value_is_used_by_nonproductive_guard(
        self,
        mock_resolve_plaintext,
        mock_get_switch,
    ):
        self.harness.semantics.is_plaintext_answer_path.return_value = False
        self.harness.semantics.has_any_action_proposal.return_value = False
        self.harness.output_recovery.decide = AsyncMock(
            return_value=SimpleNamespace(
                handled=False,
                next_query=None,
                reason="",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )
        )
        self.harness.action_policy = SimpleNamespace(
            decide=AsyncMock(
                return_value=SimpleNamespace(
                    handled=False,
                    next_query=None,
                    reason="actions_allowed_to_proceed",
                    source="action_policy",
                    parsed_action_count=0,
                )
            )
        )
        mock_resolve_plaintext.return_value = TerminalAnswerAuthorityDiagnostic(
            branch="terminal_answer.plaintext_terminal_answer",
            switch_value="compiler",
            authority_source="compiler",
            legacy_active=False,
            typed_kind="PLAINTEXT_TERMINAL_ANSWER",
            legacy_kind="none",
            agreement=True,
            fallback_used=False,
            behavior_changed=False,
            branch_active=True,
            typed_eligible=True,
            typed_plaintext_eligible=True,
            effective_value=True,
            clean_plaintext_candidate=True,
            blocking_reasons=(),
        )

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="Done.", intent_payload=None)
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(memory_checkpoint_and_text=False),
        )
        parsed_output = ParsedModelOutput(
            response="Done.",
            compiler_shape="PURE_PLAINTEXT",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
                source="compiler_fact",
                reason_code="visible_text_source_is_pure_plaintext",
                visible_text="Done.",
            ),
        )
        classified = SimpleNamespace(
            response=step.response,
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual("dispatch_ready", outcome.reason)
        self.harness.guards.is_nonproductive_thinking_turn.assert_called_once()
        self.assertTrue(self.harness.guards.is_nonproductive_thinking_turn.call_args.kwargs["plaintext_answer_path"])
        self.assertEqual(
            [
                (("terminal_answer.plaintext_terminal_answer",), {}),
                (("terminal_answer.checkpoint_only",), {}),
                (("recovery.invalid_truncated_terminal_text",), {}),
            ],
            [(call.args, call.kwargs) for call in mock_get_switch.call_args_list],
        )
        mock_resolve_plaintext.assert_called_once()


class TestBoardCheckpointSemanticBuilder(unittest.TestCase):
    def test_builder_memory_checkpoint_only(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY, result.kind)
        self.assertEqual(BoardCheckpointSource.COMBINED_SHADOW, result.source)
        self.assertTrue(result.legacy_has_checkpoint)
        self.assertTrue(result.compiler_has_checkpoint_like)
        self.assertFalse(result.legacy_has_visible_text)
        self.assertFalse(result.compiler_has_visible_text)
        self.assertFalse(result.legacy_has_action)
        self.assertFalse(result.compiler_has_action)

    def test_builder_memory_checkpoint_and_text(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT, result.kind)
        self.assertTrue(result.has_visible_text)
        self.assertTrue(result.legacy_has_visible_text)
        self.assertTrue(result.compiler_has_visible_text)

    def test_builder_plan_checkpoint_only(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=True,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.PLAN_CHECKPOINT_ONLY, result.kind)
        self.assertEqual("checkpoint_only", result.legacy_plan_outcome)
        self.assertEqual("none", result.legacy_memory_outcome)

    def test_builder_mixed_plan_and_memory_outcomes(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=True,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=True,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.MIXED_BOARD_CHECKPOINT, result.kind)
        self.assertEqual("checkpoint_and_text", result.legacy_plan_outcome)
        self.assertEqual("checkpoint_and_text", result.legacy_memory_outcome)

    def test_builder_no_checkpoint(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="ACTION_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                has_checkpoint=False,
                has_memory_tags=False,
                has_subgoal_tags=False,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.NONE, result.kind)
        self.assertFalse(result.legacy_has_checkpoint)
        self.assertFalse(result.compiler_has_checkpoint_like)
        self.assertTrue(result.compiler_has_action)
        self.assertTrue(result.has_action)

    def test_builder_missing_compiler_analysis(self):
        result = build_board_checkpoint_semantic_result(
            None,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.UNKNOWN, result.kind)
        self.assertEqual(BoardCheckpointSource.FALLBACK, result.source)
        self.assertFalse(result.parity_available)
        self.assertEqual("compiler_analysis_unavailable", result.parity_mismatch_reason)

    def test_builder_checkpoint_presence_mismatch(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="ACTION_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                has_checkpoint=False,
                has_memory_tags=False,
                has_subgoal_tags=False,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(result.parity_available)
        self.assertFalse(result.parity_aligned)
        self.assertEqual("checkpoint_presence_mismatch", result.parity_mismatch_reason)

    def test_builder_action_only_no_checkpoint_is_aligned(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="ACTION_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                has_checkpoint=False,
                has_memory_tags=False,
                has_subgoal_tags=False,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.NONE, result.kind)
        self.assertFalse(result.legacy_has_checkpoint)
        self.assertFalse(result.compiler_has_checkpoint_like)
        self.assertTrue(result.compiler_has_action)
        self.assertFalse(result.legacy_has_action)
        self.assertTrue(result.parity_aligned)
        self.assertEqual("", result.parity_mismatch_reason)

    def test_builder_action_and_text_no_checkpoint_is_aligned(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="PRE_ACTION_TEXT_AND_ACTION"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                has_checkpoint=False,
                has_memory_tags=False,
                has_subgoal_tags=False,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=True,
                visible_text_source="PRE_ACTION_TEXT",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(BoardCheckpointKind.NONE, result.kind)
        self.assertFalse(result.legacy_has_checkpoint)
        self.assertFalse(result.compiler_has_checkpoint_like)
        self.assertTrue(result.compiler_has_action)
        self.assertFalse(result.legacy_has_action)
        self.assertTrue(result.compiler_has_visible_text)
        self.assertFalse(result.legacy_has_visible_text)
        self.assertTrue(result.parity_aligned)
        self.assertEqual("", result.parity_mismatch_reason)

    def test_builder_checkpoint_action_mismatch_is_not_aligned(self):
        # Legacy sees checkpoint_only, compiler sees checkpoint_with_action
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),  # Shape can be misleading
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=True,  # Legacy sees checkpoint only
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(result.legacy_has_checkpoint)
        self.assertTrue(result.compiler_has_checkpoint_like)
        self.assertFalse(result.legacy_has_action)
        self.assertTrue(result.compiler_has_action)
        self.assertFalse(result.parity_aligned)
        self.assertEqual("checkpoint_action_mismatch", result.parity_mismatch_reason)

    def test_builder_checkpoint_text_mismatch_is_not_aligned(self):
        # Legacy sees checkpoint_only, compiler sees checkpoint_with_text
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )

        result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="raw",
            response_text="clean",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=True,  # Legacy sees checkpoint only
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(result.legacy_has_checkpoint)
        self.assertTrue(result.compiler_has_checkpoint_like)
        self.assertFalse(result.legacy_has_visible_text)
        self.assertTrue(result.compiler_has_visible_text)
        self.assertFalse(result.parity_aligned)
        self.assertEqual("checkpoint_text_mismatch", result.parity_mismatch_reason)

    def test_effective_flags_fall_back_to_all_false_for_compiler_only_semantic_result(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY,
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            reason_code="compiler_only",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(EffectiveCheckpointFlags(), effective)

    def test_effective_flags_none_result_falls_back_to_legacy_flags(self):
        effective = resolve_legacy_derived_checkpoint_effective_flags(
            None,
            plan_checkpoint_only=True,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=True,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(
            EffectiveCheckpointFlags(
                plan_checkpoint_only=True,
                plan_checkpoint_and_action=True,
                memory_checkpoint_and_text=True,
            ),
            effective,
        )

    def test_effective_flags_memory_checkpoint_only_matching_typed_kind(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY,
            source=BoardCheckpointSource.COMBINED_SHADOW,
            reason_code="legacy_memory_checkpoint_only",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(effective.memory_checkpoint_only)
        self.assertFalse(effective.memory_checkpoint_and_text)
        self.assertFalse(effective.memory_checkpoint_and_action)

    def test_effective_flags_memory_checkpoint_only_conflicting_typed_kind_still_falls_back_to_legacy(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT,
            source=BoardCheckpointSource.COMBINED_SHADOW,
            reason_code="forced_conflict",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(effective.memory_checkpoint_only)
        self.assertFalse(effective.memory_checkpoint_and_text)
        self.assertFalse(effective.memory_checkpoint_and_action)

    def test_effective_flags_plan_checkpoint_only_matching_typed_kind(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY,
            source=BoardCheckpointSource.COMBINED_SHADOW,
            reason_code="legacy_plan_checkpoint_only",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=True,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(effective.plan_checkpoint_only)
        self.assertFalse(effective.plan_checkpoint_and_text)
        self.assertFalse(effective.plan_checkpoint_and_action)

    def test_effective_flags_plan_checkpoint_and_text_and_action_follow_legacy(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_TEXT,
            source=BoardCheckpointSource.LEGACY_HANDLER_OUTCOME,
            reason_code="legacy_plan_checkpoint_and_text",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=True,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(effective.plan_checkpoint_and_text)
        self.assertFalse(effective.plan_checkpoint_only)
        self.assertFalse(effective.plan_checkpoint_and_action)

        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_ACTION,
            source=BoardCheckpointSource.LEGACY_HANDLER_OUTCOME,
            reason_code="legacy_plan_checkpoint_and_action",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=True,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(effective.plan_checkpoint_and_action)
        self.assertFalse(effective.plan_checkpoint_only)
        self.assertFalse(effective.plan_checkpoint_and_text)

    def test_effective_flags_memory_checkpoint_and_text_and_action_follow_legacy(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT,
            source=BoardCheckpointSource.LEGACY_HANDLER_OUTCOME,
            reason_code="legacy_memory_checkpoint_and_text",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        self.assertTrue(effective.memory_checkpoint_and_text)
        self.assertFalse(effective.memory_checkpoint_only)
        self.assertFalse(effective.memory_checkpoint_and_action)

        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_ACTION,
            source=BoardCheckpointSource.LEGACY_HANDLER_OUTCOME,
            reason_code="legacy_memory_checkpoint_and_action",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=True,
        )

        self.assertTrue(effective.memory_checkpoint_and_action)
        self.assertFalse(effective.memory_checkpoint_only)
        self.assertFalse(effective.memory_checkpoint_and_text)

    def test_effective_flags_non_legacy_source_cannot_create_flags(self):
        result = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_ACTION,
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            reason_code="compiler_only_memory_fact",
        )

        effective = resolve_legacy_derived_checkpoint_effective_flags(
            result,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        self.assertEqual(EffectiveCheckpointFlags(), effective)

    def test_resolve_memory_checkpoint_only_typed_primary(self):
        result_mco = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY, source=BoardCheckpointSource.COMBINED_SHADOW
        )
        result_mixed = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MIXED_BOARD_CHECKPOINT, source=BoardCheckpointSource.COMBINED_SHADOW
        )
        result_compiler = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY, source=BoardCheckpointSource.COMPILER_PREPASS_FACT
        )

        # Typed result cannot create a new True if legacy is False
        self.assertFalse(
            resolve_memory_checkpoint_only_typed_primary(
                result_mco, legacy_memory_checkpoint_only=False
            )
        )

        # Typed result can confirm an existing True
        self.assertTrue(
            resolve_memory_checkpoint_only_typed_primary(
                result_mco, legacy_memory_checkpoint_only=True
            )
        )

        # Typed result is ignored if another legacy memory branch is active; legacy bool wins
        self.assertFalse(
            resolve_memory_checkpoint_only_typed_primary(
                result_mco, legacy_memory_checkpoint_only=False, legacy_memory_checkpoint_and_text=True
            )
        )
        self.assertTrue(
            resolve_memory_checkpoint_only_typed_primary(
                result_mco, legacy_memory_checkpoint_only=True, legacy_memory_checkpoint_and_text=True
            )
        )
        self.assertFalse(
            resolve_memory_checkpoint_only_typed_primary(
                result_mco, legacy_memory_checkpoint_only=False, legacy_memory_checkpoint_and_action=True
            )
        )
        self.assertTrue(
            resolve_memory_checkpoint_only_typed_primary(
                result_mco, legacy_memory_checkpoint_only=True, legacy_memory_checkpoint_and_action=True
            )
        )

        # Legacy bool wins if typed result is conflicting
        self.assertTrue(
            resolve_memory_checkpoint_only_typed_primary(
                result_mixed, legacy_memory_checkpoint_only=True
            )
        )
        self.assertFalse(
            resolve_memory_checkpoint_only_typed_primary(
                result_mixed, legacy_memory_checkpoint_only=False
            )
        )

        # Legacy bool wins if result is None
        self.assertTrue(resolve_memory_checkpoint_only_typed_primary(None, legacy_memory_checkpoint_only=True))
        self.assertFalse(resolve_memory_checkpoint_only_typed_primary(None, legacy_memory_checkpoint_only=False))

        # Legacy bool wins if source is not legacy-derived
        self.assertFalse(
            resolve_memory_checkpoint_only_typed_primary(result_compiler, legacy_memory_checkpoint_only=False)
        )
        self.assertTrue(
            resolve_memory_checkpoint_only_typed_primary(result_compiler, legacy_memory_checkpoint_only=True)
        )

    def test_resolve_memory_checkpoint_and_text_typed_primary(self):
        result_mct = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT,
            source=BoardCheckpointSource.COMBINED_SHADOW,
        )
        # Typed result cannot create a new True if legacy is False
        self.assertFalse(
            resolve_memory_checkpoint_and_text_typed_primary(
                result_mct,
                legacy_memory_checkpoint_only=False,
                legacy_memory_checkpoint_and_text=False,
                legacy_memory_checkpoint_and_action=False,
            )
        )
        # Typed result can confirm an existing True
        self.assertTrue(
            resolve_memory_checkpoint_and_text_typed_primary(
                result_mct,
                legacy_memory_checkpoint_only=False,
                legacy_memory_checkpoint_and_text=True,
                legacy_memory_checkpoint_and_action=False,
            )
        )
        # Legacy bool wins if another legacy branch is active
        self.assertTrue(
            resolve_memory_checkpoint_and_text_typed_primary(
                result_mct,
                legacy_memory_checkpoint_only=True,
                legacy_memory_checkpoint_and_text=True,
                legacy_memory_checkpoint_and_action=False,
            )
        )

    def test_resolve_memory_checkpoint_and_action_typed_primary(self):
        result_mca = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_ACTION,
            source=BoardCheckpointSource.COMBINED_SHADOW,
        )
        # Typed result cannot create a new True if legacy is False
        self.assertFalse(
            resolve_memory_checkpoint_and_action_typed_primary(
                result_mca,
                legacy_memory_checkpoint_only=False,
                legacy_memory_checkpoint_and_text=False,
                legacy_memory_checkpoint_and_action=False,
            )
        )
        # Typed result can confirm an existing True
        self.assertTrue(
            resolve_memory_checkpoint_and_action_typed_primary(
                result_mca,
                legacy_memory_checkpoint_only=False,
                legacy_memory_checkpoint_and_text=False,
                legacy_memory_checkpoint_and_action=True,
            )
        )
        # Legacy bool wins if another legacy branch is active
        self.assertTrue(
            resolve_memory_checkpoint_and_action_typed_primary(
                result_mca,
                legacy_memory_checkpoint_only=True,
                legacy_memory_checkpoint_and_text=False,
                legacy_memory_checkpoint_and_action=True,
            )
        )

    def test_resolve_plan_checkpoint_only_typed_primary(self):
        result_pco = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY,
            source=BoardCheckpointSource.COMBINED_SHADOW,
        )
        # Typed result cannot create a new True if legacy is False
        self.assertFalse(
            resolve_plan_checkpoint_only_typed_primary(
                result_pco,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )
        # Typed result can confirm an existing True
        self.assertTrue(
            resolve_plan_checkpoint_only_typed_primary(
                result_pco,
                legacy_plan_checkpoint_only=True,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )
        # Legacy bool wins if another legacy branch is active
        self.assertTrue(
            resolve_plan_checkpoint_only_typed_primary(
                result_pco,
                legacy_plan_checkpoint_only=True,
                legacy_plan_checkpoint_and_text=True,
                legacy_plan_checkpoint_and_action=False,
            )
        )

        # Legacy bool wins if result is None
        self.assertTrue(
            resolve_plan_checkpoint_only_typed_primary(
                None,
                legacy_plan_checkpoint_only=True,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )

        # Legacy bool wins if source is not legacy-derived
        result_compiler = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY, source=BoardCheckpointSource.COMPILER_PREPASS_FACT
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_typed_primary(
                result_compiler,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )

        # Legacy bool wins if typed kind conflicts
        result_conflicting = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_TEXT, source=BoardCheckpointSource.COMBINED_SHADOW
        )
        self.assertTrue(
            resolve_plan_checkpoint_only_typed_primary(
                result_conflicting,
                legacy_plan_checkpoint_only=True,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )

    def test_resolve_plan_checkpoint_and_text_typed_primary(self):
        result_pct = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_TEXT,
            source=BoardCheckpointSource.COMBINED_SHADOW,
        )
        # Typed result cannot create a new True if legacy is False
        self.assertFalse(
            resolve_plan_checkpoint_and_text_typed_primary(
                result_pct,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )
        # Typed result can confirm an existing True
        self.assertTrue(
            resolve_plan_checkpoint_and_text_typed_primary(
                result_pct,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=True,
                legacy_plan_checkpoint_and_action=False,
            )
        )
        # Legacy bool wins if another legacy branch is active
        self.assertTrue(
            resolve_plan_checkpoint_and_text_typed_primary(
                result_pct,
                legacy_plan_checkpoint_only=True,
                legacy_plan_checkpoint_and_text=True,
                legacy_plan_checkpoint_and_action=False,
            )
        )

        # Legacy bool wins if result is None
        self.assertTrue(
            resolve_plan_checkpoint_and_text_typed_primary(
                None,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=True,
                legacy_plan_checkpoint_and_action=False,
            )
        )

        # Legacy bool wins if typed kind conflicts
        result_conflicting = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY, source=BoardCheckpointSource.COMBINED_SHADOW
        )
        self.assertTrue(
            resolve_plan_checkpoint_and_text_typed_primary(
                result_conflicting,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=True,
                legacy_plan_checkpoint_and_action=False,
            )
        )

    def test_resolve_plan_checkpoint_and_action_typed_primary(self):
        result_pca = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_ACTION,
            source=BoardCheckpointSource.COMBINED_SHADOW,
        )
        # Typed result cannot create a new True if legacy is False
        self.assertFalse(
            resolve_plan_checkpoint_and_action_typed_primary(
                result_pca,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=False,
            )
        )
        # Typed result can confirm an existing True
        self.assertTrue(
            resolve_plan_checkpoint_and_action_typed_primary(
                result_pca,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=True,
            )
        )
        # Legacy bool wins if another legacy branch is active
        self.assertTrue(
            resolve_plan_checkpoint_and_action_typed_primary(
                result_pca,
                legacy_plan_checkpoint_only=True,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=True,
            )
        )

        # Legacy bool wins if result is None
        self.assertTrue(
            resolve_plan_checkpoint_and_action_typed_primary(
                None,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=True,
            )
        )

        # Legacy bool wins if typed kind conflicts
        result_conflicting = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY, source=BoardCheckpointSource.COMBINED_SHADOW
        )
        self.assertTrue(
            resolve_plan_checkpoint_and_action_typed_primary(
                result_conflicting,
                legacy_plan_checkpoint_only=False,
                legacy_plan_checkpoint_and_text=False,
                legacy_plan_checkpoint_and_action=True,
            )
        )

    def test_resolve_plan_checkpoint_only_with_compiler_switch(self):
        legacy_true = True
        legacy_false = False
        result_compiler_pco = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_visible_text=False,
            compiler_has_action=False,
            compiler_has_memory_tags=False,
        )
        result_compiler_error = BoardCheckpointSemanticResult(compiler_error_code="E_SOME_ERROR")
        result_compiler_with_text = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_visible_text=True,
        )
        result_compiler_with_action = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_action=True,
        )
        result_compiler_with_memory = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=True,
        )
        result_compiler_no_checkpoint = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=False,
            compiler_has_subgoal_tags=True,
        )

        # Switch OFF
        self.assertTrue(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_pco, legacy_plan_checkpoint_only=legacy_true, switch_enabled=False
            )
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_pco, legacy_plan_checkpoint_only=legacy_false, switch_enabled=False
            )
        )

        # Switch ON
        self.assertTrue(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_pco, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )
        self.assertTrue(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_pco, legacy_plan_checkpoint_only=legacy_true, switch_enabled=True
            )
        )

        # Fallback cases with switch ON
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                None, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_error, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_with_text, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_with_action, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_with_memory, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )
        self.assertFalse(
            resolve_plan_checkpoint_only_with_compiler_switch(
                result_compiler_no_checkpoint, legacy_plan_checkpoint_only=legacy_false, switch_enabled=True
            )
        )


class TestResponsePipelineCheckpointStageCharacterization(unittest.TestCase):
    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None, last_memory_update_done=False)
                self.plan_board_stage = AsyncMock()
                self.memory_board_stage = AsyncMock()
                self.ui = AsyncMock()
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.guards = SimpleNamespace(
                    reflection_repair_pending=MagicMock(return_value=False),
                    reflection_repair_kind=MagicMock(return_value=""),
                    memory_checkpoint_streak=MagicMock(return_value=1),
                    set_reflection_repair_pending=MagicMock(),
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.semantics = SimpleNamespace(has_substantial_think=MagicMock(return_value=False))
                self.memory_checkpoint_hard_stop_streak = 3
                self.nonproductive_thinking_hard_stop_streak = 3
                self.prompt_builder = SimpleNamespace(
                    build_reflection_repair_accepted_prompt=MagicMock(return_value="repair_accepted_prompt"),
                    build_durable_state_repair_prompt=MagicMock(return_value="durable_state_repair_prompt"),
                    build_repeated_thinking_without_valid_output_prompt=MagicMock(return_value="repeated_thinking_prompt"),
                )
                # Mocks for prevalidation mixin
                self.protocol_compiler = SimpleNamespace(analyze=MagicMock())

        self.harness = Harness()
        self.ctx = SimpleNamespace()

    def test_checkpoint_stage_with_memory_checkpoint_only_continues(self):
        """Characterizes the behavior when the memory board handler detects a checkpoint-only response."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNotNone(state)
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_memory_board", outcome.next_query)
        self.assertEqual("memory_checkpoint_only", outcome.reason)
        self.assertTrue(outcome.memory_checkpoint_only)
        self.assertFalse(outcome.memory_checkpoint_and_text)
        self.assertEqual(BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY, state.board_checkpoint_semantic_result.kind)
        self.assertEqual(BoardCheckpointSource.COMBINED_SHADOW, state.board_checkpoint_semantic_result.source)
        parity_calls = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[:2] == ("protocol_shadow", "board_checkpoint_structural_parity")
        ]
        self.assertEqual(1, len(parity_calls))
        self.assertEqual("none", parity_calls[0].kwargs["plan_checkpoint_category"])
        self.assertEqual("checkpoint_only", parity_calls[0].kwargs["memory_checkpoint_category"])
        self.assertTrue(parity_calls[0].kwargs["parity_available"])

    def test_checkpoint_stage_with_memory_checkpoint_and_text_passes_through(self):
        """Characterizes that memory_checkpoint_and_text does not result in a handled outcome from the checkpoint stage itself, but passes state to the next stage."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,  # Note: handler considers it handled
            response_text="response",
            next_query="next_query",
            reason="memory_checkpoint_and_text",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertIsNotNone(state)
        self.assertTrue(state.memory_checkpoint_and_text)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertEqual(BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT, state.board_checkpoint_semantic_result.kind)
        self.assertTrue(state.board_checkpoint_semantic_result.has_visible_text)
        # The logic inside _run_checkpoint_stage specifically un-handles this case
        # to let it flow to post-classification.
        self.assertFalse(state.memory_board_decision.handled)
        parity_calls = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[:2] == ("protocol_shadow", "board_checkpoint_structural_parity")
        ]
        self.assertEqual(1, len(parity_calls))
        self.assertEqual("checkpoint_and_text", parity_calls[0].kwargs["memory_checkpoint_category"])
        self.assertEqual("CHECKPOINT_ACCOMPANYING_TEXT", parity_calls[0].kwargs["compiler_visible_text_source"])

    def test_checkpoint_stage_with_memory_checkpoint_and_action_passes_through(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                action_count=1,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query",
            reason="memory_checkpoint_and_action",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=True,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertIsNotNone(state)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertFalse(state.memory_checkpoint_and_text)
        self.assertTrue(state.memory_checkpoint_and_action)
        self.assertFalse(state.memory_board_decision.handled)

    def test_checkpoint_stage_memory_checkpoint_only_route_with_typed_primary_fallback(self):
        """
        Characterizes that memory_checkpoint_only routing is unchanged by typed-primary
        logic, because legacy fallback is preserved.
        """
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"), error=None, ir=SimpleNamespace()
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        # Legacy handler says it's memory_checkpoint_only
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        # Mock the builder to return a conflicting typed result
        with patch(
            "modules.agent.orchestration.responses.response_pipeline_stages.build_board_checkpoint_semantic_result"
        ) as mock_build:
            mock_build.return_value = BoardCheckpointSemanticResult(
                kind=BoardCheckpointKind.MIXED_BOARD_CHECKPOINT,
                source=BoardCheckpointSource.COMBINED_SHADOW,
            )

            state, outcome = asyncio.run(
                self.harness._run_checkpoint_stage(
                    self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
                )
            )

        # Assert that the outcome is still the same as the legacy path
        self.assertIsNotNone(state)
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_memory_board", outcome.next_query)
        self.assertEqual("memory_checkpoint_only", outcome.reason)
        self.assertTrue(outcome.memory_checkpoint_only)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_checkpoint_structural_parity")
    def test_checkpoint_stage_with_plan_checkpoint_only_continues(self, mock_parity):
        """Characterizes the behavior when the plan board handler handles the response."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_plan_board",
            reason="plan_checkpoint_only",
            source="plan_board",
            plan_checkpoint_only=True,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNotNone(state)
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_plan_board", outcome.next_query)
        self.assertEqual("plan_checkpoint_only", outcome.reason)
        self.harness.memory_board_stage.apply.assert_not_called()
        self.assertEqual(BoardCheckpointKind.PLAN_CHECKPOINT_ONLY, state.board_checkpoint_semantic_result.kind)
        self.assertEqual(BoardCheckpointSource.COMBINED_SHADOW, state.board_checkpoint_semantic_result.source)
        mock_parity.assert_called_once()
        self.assertEqual(True, mock_parity.call_args.kwargs["plan_checkpoint_only"])
        self.assertEqual(False, mock_parity.call_args.kwargs["memory_checkpoint_only"])

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.build_board_checkpoint_semantic_result")
    def test_checkpoint_stage_plan_checkpoint_only_legacy_wins_when_typed_result_disagrees(self, mock_build):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_plan_board",
            reason="plan_checkpoint_only",
            source="plan_board",
            plan_checkpoint_only=True,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        mock_build.return_value = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY,
            source=BoardCheckpointSource.COMBINED_SHADOW,
            reason_code="forced_test_disagreement",
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNotNone(state)
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_plan_board", outcome.next_query)
        self.assertEqual("plan_checkpoint_only", outcome.reason)
        self.assertTrue(state.plan_checkpoint_only)
        self.harness.memory_board_stage.apply.assert_not_called()

    def test_checkpoint_stage_with_plan_checkpoint_and_text_continues(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_plan_board",
            reason="plan_checkpoint_and_text",
            source="plan_board",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=True,
            plan_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNotNone(state)
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_plan_board", outcome.next_query)
        self.assertTrue(state.plan_checkpoint_and_text)
        self.assertFalse(state.plan_checkpoint_only)
        self.assertFalse(state.plan_checkpoint_and_action)
        self.harness.memory_board_stage.apply.assert_not_called()

    def test_checkpoint_stage_with_plan_checkpoint_and_action_continues(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                action_count=1,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_plan_board",
            reason="plan_checkpoint_and_action",
            source="plan_board",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=True,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNotNone(state)
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_plan_board", outcome.next_query)
        self.assertTrue(state.plan_checkpoint_and_action)
        self.assertFalse(state.plan_checkpoint_only)
        self.assertFalse(state.plan_checkpoint_and_text)
        self.harness.memory_board_stage.apply.assert_not_called()

    def test_checkpoint_stage_with_no_checkpoints_passes_through(self):
        """Characterizes the passthrough case where no checkpoints are detected."""
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertIsNotNone(state)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertFalse(state.memory_checkpoint_and_text)
        self.assertFalse(state.plan_checkpoint_only)
        self.assertEqual(BoardCheckpointKind.NONE, state.board_checkpoint_semantic_result.kind)

    def test_checkpoint_stage_compiler_prepass_only_plan_facts_do_not_trigger_routing(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertFalse(state.plan_checkpoint_only)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertEqual(BoardCheckpointKind.NONE, state.board_checkpoint_semantic_result.kind)

    def test_checkpoint_stage_compiler_prepass_only_memory_facts_do_not_trigger_routing(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertFalse(state.memory_checkpoint_and_text)
        self.assertFalse(state.memory_checkpoint_and_action)
        self.assertEqual(BoardCheckpointKind.NONE, state.board_checkpoint_semantic_result.kind)

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.ResponsePipelinePrevalidationMixin._run_structural_diagnosis_prepass")
    def test_checkpoint_stage_runs_prepass_and_passes_analysis_in_state(self, mock_prepass):
        """Characterizes that the checkpoint stage runs the structural diagnosis prepass."""
        mock_analysis = SimpleNamespace(name="prepass_analysis")
        mock_prepass.return_value = mock_analysis

        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, _ = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "raw_response_text", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        mock_prepass.assert_called_once_with("raw_response_text")
        self.assertIsNotNone(state)
        self.assertIs(state.compiler_analysis, mock_analysis)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_checkpoint_structural_parity")
    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.ResponsePipelinePrevalidationMixin._run_structural_diagnosis_prepass")
    def test_checkpoint_stage_missing_compiler_analysis_does_not_fail(self, mock_prepass, mock_parity):
        mock_prepass.return_value = None
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "raw_response_text", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertIsNotNone(state)
        self.assertIsNone(state.compiler_analysis)
        mock_parity.assert_called_once()
        self.assertEqual(BoardCheckpointKind.UNKNOWN, state.board_checkpoint_semantic_result.kind)
        self.assertEqual(BoardCheckpointSource.FALLBACK, state.board_checkpoint_semantic_result.source)

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.ResponsePipelinePrevalidationMixin._run_structural_diagnosis_prepass")
    def test_checkpoint_stage_logger_failure_does_not_change_behavior(self, mock_prepass):
        mock_prepass.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        def log_side_effect(*args, **kwargs):
            if args[:2] == ("protocol_shadow", "board_checkpoint_structural_parity"):
                raise RuntimeError("logger failure")
            return None

        self.harness.stage_logger.log.side_effect = log_side_effect
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        _, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_memory_board", outcome.next_query)
        self.assertEqual("memory_checkpoint_only", outcome.reason)

    def test_checkpoint_stage_mixed_plan_and_memory_outcomes_attach_mixed_semantic_result(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=True,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=True,
            plan_checkpoint_and_action=False,
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query",
            reason="memory_checkpoint_and_text",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertIsNotNone(state)
        self.assertEqual(BoardCheckpointKind.MIXED_BOARD_CHECKPOINT, state.board_checkpoint_semantic_result.kind)
        self.assertEqual("checkpoint_and_text", state.board_checkpoint_semantic_result.legacy_plan_outcome)
        self.assertEqual("checkpoint_and_text", state.board_checkpoint_semantic_result.legacy_memory_outcome)

    def test_checkpoint_stage_attaches_same_result_as_pure_builder(self):
        compiler_analysis = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.protocol_compiler.analyze.return_value = compiler_analysis
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query",
            reason="memory_checkpoint_and_text",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        expected = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response="response",
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )

        self.assertIsNone(outcome)
        self.assertEqual(expected, state.board_checkpoint_semantic_result)

    def test_checkpoint_stage_semantic_result_parity_aligned_when_legacy_and_compiler_agree(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, _ = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertTrue(state.board_checkpoint_semantic_result.parity_available)
        self.assertTrue(state.board_checkpoint_semantic_result.parity_aligned)
        self.assertEqual("", state.board_checkpoint_semantic_result.parity_mismatch_reason)

    def test_checkpoint_stage_semantic_result_parity_mismatch_when_legacy_sees_checkpoint_but_compiler_does_not(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="ACTION_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                action_count=1,
                has_checkpoint=False,
                has_memory_tags=False,
                has_subgoal_tags=False,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertFalse(state.board_checkpoint_semantic_result.parity_aligned)
        self.assertEqual(
            "checkpoint_presence_mismatch",
            state.board_checkpoint_semantic_result.parity_mismatch_reason,
        )

    def test_checkpoint_stage_semantic_result_parity_mismatch_when_compiler_sees_checkpoint_but_legacy_does_not(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=False,
                has_subgoal_tags=True,
                has_memory_checkpoint=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertFalse(state.plan_checkpoint_only)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertFalse(state.board_checkpoint_semantic_result.parity_aligned)
        self.assertEqual(
            "checkpoint_presence_mismatch",
            state.board_checkpoint_semantic_result.parity_mismatch_reason,
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.build_board_checkpoint_semantic_result")
    def test_checkpoint_stage_memory_checkpoint_only_legacy_wins_when_typed_result_disagrees(self, mock_build):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )
        mock_build.return_value = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT,
            source=BoardCheckpointSource.COMBINED_SHADOW,
            reason_code="forced_test_disagreement",
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual("memory_checkpoint_only", outcome.reason)
        self.assertTrue(outcome.memory_checkpoint_only)
        self.assertFalse(outcome.memory_checkpoint_and_text)
        self.assertTrue(state.memory_checkpoint_only)
        self.assertFalse(state.memory_checkpoint_and_text)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.build_board_checkpoint_semantic_result")
    def test_checkpoint_stage_memory_checkpoint_and_text_legacy_wins_when_typed_result_disagrees(self, mock_build):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_WITH_VISIBLE_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(handled=False, response_text="response")
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query",
            reason="memory_checkpoint_and_text",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )
        mock_build.return_value = BoardCheckpointSemanticResult(
            kind=BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY,
            source=BoardCheckpointSource.COMBINED_SHADOW,
            reason_code="forced_test_disagreement",
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertTrue(state.memory_checkpoint_and_text)
        self.assertFalse(state.memory_checkpoint_only)
        self.assertFalse(state.memory_board_decision.handled)

    def test_checkpoint_stage_reflection_repair_state_uses_effective_flags_consistently(self):
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        # This test now sets legacy flags directly to test consistency,
        # since the mock on resolve_legacy_derived_checkpoint_effective_flags
        # is no longer sufficient after the Step 18/19 refactor.
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="repair_prompt",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=True,
        )
        self.harness.state.last_memory_update_done = False
        self.harness.state.last_memory_board_accepted_count = 0

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx,
                "response",
                reflection_repair_pending=True,
                reflection_repair_kind="missing_think_reflection",
            )
        )

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual("missing_think_reflection", outcome.reason)
        self.assertTrue(state.memory_checkpoint_only)
        self.assertTrue(state.memory_checkpoint_and_text)
        self.assertTrue(state.memory_checkpoint_and_action)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.get_switch")
    def test_plan_checkpoint_only_routes_with_compiler_authority_switch_on(self, mock_get_switch):
        """With switch ON, a clean compiler-only PCO signal should trigger routing."""
        mock_get_switch.return_value = "compiler"
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_subgoal_tags=True,
                has_memory_tags=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        # Legacy handlers see nothing
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertIsNone(outcome.next_query)
        self.assertEqual("plan_checkpoint_only", outcome.reason)
        self.assertEqual("compiler_authority", outcome.source)
        self.assertTrue(state.plan_checkpoint_only)
        authority_calls = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[:2] == ("protocol_shadow", "board_checkpoint_authority_resolution")
            and call.kwargs.get("branch") == "board_checkpoint.plan_checkpoint_only"
        ]
        self.assertEqual(1, len(authority_calls))
        self.assertEqual("board_checkpoint.plan_checkpoint_only", authority_calls[0].kwargs["branch"])
        self.assertEqual("compiler", authority_calls[0].kwargs["switch_value"])
        self.assertEqual("compiler", authority_calls[0].kwargs["authority_source"])
        self.assertEqual("PLAN_CHECKPOINT_ONLY", authority_calls[0].kwargs["typed_kind"])
        self.assertEqual("NONE", authority_calls[0].kwargs["legacy_kind"])
        self.assertFalse(authority_calls[0].kwargs["fallback_used"])
        self.assertTrue(authority_calls[0].kwargs["behavior_changed"])
        self.assertTrue(authority_calls[0].kwargs["branch_active"])

    def test_plan_checkpoint_only_does_not_route_with_compiler_authority_switch_off(self):
        """With switch OFF, a clean compiler-only PCO signal must not trigger routing."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_subgoal_tags=True,
                has_memory_tags=False,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        # Legacy handlers see nothing
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="response",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertFalse(state.plan_checkpoint_only)
        authority_calls = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[:2] == ("protocol_shadow", "board_checkpoint_authority_resolution")
            and call.kwargs.get("branch") == "board_checkpoint.plan_checkpoint_only"
        ]
        self.assertEqual(2, len(authority_calls))
        final_authority = authority_calls[-1]
        self.assertEqual("legacy", final_authority.kwargs["switch_value"])
        self.assertEqual("legacy", final_authority.kwargs["authority_source"])
        self.assertFalse(final_authority.kwargs["legacy_active"])
        self.assertEqual("PLAN_CHECKPOINT_ONLY", final_authority.kwargs["typed_kind"])
        self.assertFalse(final_authority.kwargs["fallback_used"])
        self.assertFalse(final_authority.kwargs["behavior_changed"])
        self.assertTrue(final_authority.kwargs["branch_active"])

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.get_switch")
    def test_plan_checkpoint_only_compiler_switch_logs_legacy_fallback_for_incompatible_typed_result(self, mock_get_switch):
        mock_get_switch.return_value = "compiler"
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="SUBGOAL_WITH_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                has_checkpoint=True,
                has_subgoal_tags=True,
                has_memory_tags=False,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="Done.",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="Done.",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsNone(outcome)
        self.assertFalse(state.plan_checkpoint_only)
        authority_calls = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[:2] == ("protocol_shadow", "board_checkpoint_authority_resolution")
            and call.kwargs.get("branch") == "board_checkpoint.plan_checkpoint_only"
        ]
        self.assertEqual(2, len(authority_calls))
        final_authority = authority_calls[-1]
        self.assertEqual("compiler", final_authority.kwargs["switch_value"])
        self.assertEqual("legacy_fallback", final_authority.kwargs["authority_source"])
        self.assertEqual("UNKNOWN", final_authority.kwargs["typed_kind"])
        self.assertTrue(final_authority.kwargs["fallback_used"])
        self.assertFalse(final_authority.kwargs["behavior_changed"])
        self.assertFalse(final_authority.kwargs["branch_active"])


class TestBoardCheckpointAuthorityDiagnostics(unittest.TestCase):
    def test_resolve_plan_checkpoint_only_authority_legacy_mode(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=False,
            compiler_has_visible_text=False,
            compiler_error_code="",
        )

        diagnostic = resolve_plan_checkpoint_only_authority(
            result,
            legacy_plan_checkpoint_only=False,
            switch_value="legacy",
        )

        self.assertEqual("board_checkpoint.plan_checkpoint_only", diagnostic.branch)
        self.assertEqual("legacy", diagnostic.switch_value)
        self.assertEqual("legacy", diagnostic.authority_source)
        self.assertEqual("PLAN_CHECKPOINT_ONLY", diagnostic.typed_kind)
        self.assertEqual("NONE", diagnostic.legacy_kind)
        self.assertTrue(diagnostic.agreement is False)
        self.assertFalse(diagnostic.fallback_used)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertTrue(diagnostic.branch_active)
        self.assertFalse(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_only_authority_compiler_mode(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=False,
            compiler_has_visible_text=False,
            compiler_error_code="",
        )

        diagnostic = resolve_plan_checkpoint_only_authority(
            result,
            legacy_plan_checkpoint_only=False,
            switch_value="compiler",
        )

        self.assertEqual("compiler", diagnostic.switch_value)
        self.assertEqual("compiler", diagnostic.authority_source)
        self.assertEqual("PLAN_CHECKPOINT_ONLY", diagnostic.typed_kind)
        self.assertFalse(diagnostic.fallback_used)
        self.assertTrue(diagnostic.behavior_changed)
        self.assertTrue(diagnostic.branch_active)
        self.assertTrue(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_only_authority_compiler_fallback(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=False,
            compiler_has_visible_text=True,
            compiler_error_code="",
        )

        diagnostic = resolve_plan_checkpoint_only_authority(
            result,
            legacy_plan_checkpoint_only=False,
            switch_value="compiler",
        )

        self.assertEqual("compiler", diagnostic.switch_value)
        self.assertEqual("legacy_fallback", diagnostic.authority_source)
        self.assertEqual("UNKNOWN", diagnostic.typed_kind)
        self.assertTrue(diagnostic.fallback_used)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertFalse(diagnostic.branch_active)
        self.assertFalse(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_with_text_authority_legacy_mode(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=False,
            compiler_has_visible_text=True,
            compiler_error_code="",
        )

        diagnostic = resolve_plan_checkpoint_and_text_authority(
            result,
            legacy_plan_checkpoint_and_text=False,
            switch_value="legacy",
        )

        self.assertEqual("board_checkpoint.plan_checkpoint_with_text", diagnostic.branch)
        self.assertEqual("legacy", diagnostic.switch_value)
        self.assertEqual("legacy", diagnostic.authority_source)
        self.assertEqual("PLAN_CHECKPOINT_WITH_TEXT", diagnostic.typed_kind)
        self.assertEqual("NONE", diagnostic.legacy_kind)
        self.assertFalse(diagnostic.fallback_used)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertTrue(diagnostic.branch_active)
        self.assertFalse(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_with_text_authority_compiler_mode(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=False,
            compiler_has_visible_text=True,
            compiler_error_code="",
        )

        diagnostic = resolve_plan_checkpoint_and_text_authority(
            result,
            legacy_plan_checkpoint_and_text=False,
            switch_value="compiler",
        )

        self.assertEqual("compiler", diagnostic.switch_value)
        self.assertEqual("compiler", diagnostic.authority_source)
        self.assertEqual("PLAN_CHECKPOINT_WITH_TEXT", diagnostic.typed_kind)
        self.assertFalse(diagnostic.fallback_used)
        self.assertTrue(diagnostic.behavior_changed)
        self.assertTrue(diagnostic.branch_active)
        self.assertTrue(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_with_text_authority_compiler_fallback(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=True,
            compiler_has_visible_text=True,
            compiler_error_code="",
        )

        diagnostic = resolve_plan_checkpoint_and_text_authority(
            result,
            legacy_plan_checkpoint_and_text=False,
            switch_value="compiler",
        )

        self.assertEqual("compiler", diagnostic.switch_value)
        self.assertEqual("legacy_fallback", diagnostic.authority_source)
        self.assertEqual("UNKNOWN", diagnostic.typed_kind)
        self.assertTrue(diagnostic.fallback_used)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertFalse(diagnostic.branch_active)
        self.assertFalse(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_with_action_authority_legacy_mode(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=True,
            compiler_action_count=1,
            compiler_has_visible_text=False,
            compiler_error_code="",
            legacy_memory_outcome="none",
        )

        diagnostic = resolve_plan_checkpoint_and_action_authority(
            result,
            legacy_plan_checkpoint_and_action=False,
            switch_value="legacy",
        )

        self.assertEqual("board_checkpoint.plan_checkpoint_with_action", diagnostic.branch)
        self.assertEqual("legacy", diagnostic.switch_value)
        self.assertEqual("legacy", diagnostic.authority_source)
        self.assertEqual("PLAN_CHECKPOINT_WITH_ACTION", diagnostic.typed_kind)
        self.assertEqual("NONE", diagnostic.legacy_kind)
        self.assertFalse(diagnostic.fallback_used)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertTrue(diagnostic.branch_active)
        self.assertFalse(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_with_action_authority_compiler_mode(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=True,
            compiler_action_count=1,
            compiler_has_visible_text=False,
            compiler_error_code="",
            legacy_memory_outcome="none",
        )

        diagnostic = resolve_plan_checkpoint_and_action_authority(
            result,
            legacy_plan_checkpoint_and_action=False,
            switch_value="compiler",
        )

        self.assertEqual("compiler", diagnostic.switch_value)
        self.assertEqual("compiler", diagnostic.authority_source)
        self.assertEqual("PLAN_CHECKPOINT_WITH_ACTION", diagnostic.typed_kind)
        self.assertFalse(diagnostic.fallback_used)
        self.assertTrue(diagnostic.behavior_changed)
        self.assertTrue(diagnostic.branch_active)
        self.assertTrue(diagnostic.effective_value)

    def test_resolve_plan_checkpoint_with_action_authority_compiler_fallback(self):
        result = BoardCheckpointSemanticResult(
            source=BoardCheckpointSource.COMPILER_PREPASS_FACT,
            compiler_has_checkpoint=True,
            compiler_has_subgoal_tags=True,
            compiler_has_memory_tags=False,
            compiler_has_action=True,
            compiler_action_count=1,
            compiler_has_visible_text=True,
            compiler_error_code="",
            legacy_memory_outcome="none",
        )

        diagnostic = resolve_plan_checkpoint_and_action_authority(
            result,
            legacy_plan_checkpoint_and_action=False,
            switch_value="compiler",
        )

        self.assertEqual("compiler", diagnostic.switch_value)
        self.assertEqual("legacy_fallback", diagnostic.authority_source)
        self.assertEqual("UNKNOWN", diagnostic.typed_kind)
        self.assertTrue(diagnostic.fallback_used)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertFalse(diagnostic.branch_active)
        self.assertFalse(diagnostic.effective_value)


class TestResponsePipelineCheckpointStageCharacterization(unittest.TestCase):
    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None, last_memory_update_done=False)
                self.plan_board_stage = AsyncMock()
                self.memory_board_stage = AsyncMock()
                self.ui = AsyncMock()
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.guards = SimpleNamespace(
                    reflection_repair_pending=MagicMock(return_value=False),
                    reflection_repair_kind=MagicMock(return_value=""),
                    memory_checkpoint_streak=MagicMock(return_value=1),
                    set_reflection_repair_pending=MagicMock(),
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.semantics = SimpleNamespace(has_substantial_think=MagicMock(return_value=False))
                self.memory_checkpoint_hard_stop_streak = 3
                self.nonproductive_thinking_hard_stop_streak = 3
                self.prompt_builder = SimpleNamespace(
                    build_reflection_repair_accepted_prompt=MagicMock(return_value="repair_accepted_prompt"),
                    build_durable_state_repair_prompt=MagicMock(return_value="durable_state_repair_prompt"),
                    build_repeated_thinking_without_valid_output_prompt=MagicMock(return_value="repeated_thinking_prompt"),
                )
                # Mocks for prevalidation mixin
                self.protocol_compiler = SimpleNamespace(analyze=MagicMock())

        self.harness = Harness()
        self.ctx = SimpleNamespace()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_memory_commit_authority_resolution")
    def test_checkpoint_stage_logs_memory_commit_authority(self, mock_log_commit_authority):
        """Characterizes that the checkpoint stage logs memory commit authority diagnostics."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_commit_attempted=True,
            memory_commit_accepted_count=1,
            memory_commit_rejected_count=0,
        )

        asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertGreaterEqual(mock_log_commit_authority.call_count, 2)
        mco_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_checkpoint_only"
        ]
        self.assertEqual(1, len(mco_calls))
        diagnostic = mco_calls[0].args[0]
        self.assertEqual("board_memory.memory_checkpoint_only", diagnostic.branch)

        mct_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_checkpoint_with_text"
        ]
        self.assertEqual(1, len(mct_calls))
        self.assertFalse(mct_calls[0].args[0].candidate_available)
        self.assertFalse(mct_calls[0].args[0].behavior_changed)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_memory_commit_authority_resolution")
    def test_checkpoint_stage_logs_memory_commit_authority_from_state_fields(self, mock_log_commit_authority):
        """Characterizes that commit diagnostics can be read from state fields."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="response"
        )
        # Decision object does NOT have commit fields
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text="response",
            next_query="next_query_from_memory_board",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )
        # Synthetic state-field fallback case with compiler memory tags.
        # This is not the marker-only live MCO case; accepted_count=1 is intentional.
        self.harness.state.last_memory_update_done = True
        self.harness.state.last_memory_board_parsed_count = 1
        self.harness.state.last_memory_board_accepted_count = 1
        self.harness.state.last_memory_board_rejected_count = 0

        asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertGreaterEqual(mock_log_commit_authority.call_count, 2)
        mco_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_checkpoint_only"
        ]
        self.assertEqual(1, len(mco_calls))
        diagnostic = mco_calls[0].args[0]
        self.assertEqual("board_memory.memory_checkpoint_only", diagnostic.branch)
        self.assertTrue(diagnostic.candidate_available)
        self.assertTrue(diagnostic.commit_equivalent)
        self.assertFalse(diagnostic.behavior_changed)

        mct_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_checkpoint_with_text"
        ]
        self.assertEqual(1, len(mct_calls))
        self.assertFalse(mct_calls[0].args[0].candidate_available)
        self.assertFalse(mct_calls[0].args[0].behavior_changed)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_memory_commit_authority_resolution")
    def test_checkpoint_stage_logs_memory_commit_authority_for_mct(self, mock_log_commit_authority):
        """Characterizes that the checkpoint stage logs memory commit authority diagnostics for MCT."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="MEMORY_TEXT"),
            error=None,
            ir=SimpleNamespace(
                has_action=False,
                action_count=0,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=True,
                has_pre_action_text=False,
                visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text="<memory_update_done />\nDone."
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=False,
            response_text="Done.",
            next_query=None,
            reason="memory_checkpoint_and_text",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
            memory_commit_attempted=False,
            memory_commit_accepted_count=0,
            memory_commit_rejected_count=0,
        )

        asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "<memory_update_done />\nDone.", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        mct_calls = [
            call for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_checkpoint_with_text"
        ]
        self.assertEqual(1, len(mct_calls))
        diagnostic = mct_calls[0].args[0]
        self.assertEqual("board_memory.memory_checkpoint_with_text", diagnostic.branch)
        self.assertTrue(diagnostic.candidate_available)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertEqual("legacy", diagnostic.switch_value)
        self.assertEqual("legacy", diagnostic.authority_source)
        self.assertIsInstance(diagnostic.commit_equivalent, bool)
        self.assertIsInstance(diagnostic.response_text_agreement, bool)
        self.assertIsInstance(diagnostic.checkpoint_removed_agreement, bool)
        self.assertIsInstance(diagnostic.visible_text_preserved_agreement, bool)
        self.assertIsInstance(diagnostic.pass_through_agreement, bool)
        self.assertIsInstance(diagnostic.reason_agreement, bool)
        self.assertIsInstance(diagnostic.source_agreement, bool)
        self.assertIsInstance(diagnostic.accepted_count_agreement, bool)
        self.assertIsInstance(diagnostic.rejected_count_agreement, bool)
        self.assertIsInstance(diagnostic.state_flags_agreement, bool)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_memory_commit_authority_resolution")
    def test_checkpoint_stage_logs_memory_commit_authority_for_mca_content(self, mock_log_commit_authority):
        """Characterizes that the checkpoint stage logs memory commit authority diagnostics for MCA content."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="ACTION_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                action_count=1,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=False,  # No marker
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text='<fact>some fact</fact>\n<action>{"type":"read_file","path":"a.txt"}</action>'
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text='<action>{"type":"read_file","path":"a.txt"}</action>',
            next_query=None,
            reason="memory_checkpoint_and_action",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=True,
            memory_commit_attempted=True,
            memory_commit_accepted_count=1,
            memory_commit_rejected_count=0,
        )
        self.harness.state.last_memory_update_done = False

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx,
                '<fact>some fact</fact>\n<action>{"type":"read_file","path":"a.txt"}</action>',
                reflection_repair_pending=False,
                reflection_repair_kind="",
            )
        )

        self.assertIsNone(outcome)  # Pass-through behavior is preserved

        mca_content_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_content_with_action"
        ]
        self.assertEqual(1, len(mca_content_calls))
        diagnostic = mca_content_calls[0].args[0]
        self.assertEqual("board_memory.memory_content_with_action", diagnostic.branch)
        self.assertTrue(diagnostic.candidate_available)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertEqual("legacy", diagnostic.switch_value)
        self.assertEqual("legacy", diagnostic.authority_source)
        self.assertFalse(diagnostic.selected_by_switch)
        self.assertTrue(diagnostic.commit_equivalent)
        self.assertTrue(diagnostic.commit_attempted_agreement)
        self.assertTrue(diagnostic.accepted_count_agreement)
        self.assertTrue(diagnostic.rejected_count_agreement)
        self.assertTrue(diagnostic.response_text_agreement)
        self.assertTrue(diagnostic.checkpoint_removed_agreement)
        self.assertTrue(diagnostic.pass_through_agreement)
        self.assertTrue(diagnostic.state_flags_agreement)

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.ResponsePipelineStagesMixin._log_board_memory_commit_authority_resolution")
    def test_checkpoint_stage_logs_memory_commit_authority_for_mca(self, mock_log_commit_authority):
        """Characterizes that the checkpoint stage logs memory commit authority diagnostics for MCTA."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(
            shape=SimpleNamespace(name="ACTION_ONLY"),
            error=None,
            ir=SimpleNamespace(
                has_action=True,
                action_count=1,
                has_checkpoint=True,
                has_memory_tags=True,
                has_subgoal_tags=False,
                has_memory_checkpoint=True,
                has_visible_answer=False,
                has_pre_action_text=False,
                visible_text_source="NONE",
            ),
        )
        self.harness.plan_board_stage.apply.return_value = SimpleNamespace(
            handled=False, response_text='<memory_update_done />\n<action>{"type":"read_file","path":"a.txt"}</action>'
        )
        self.harness.memory_board_stage.apply.return_value = SimpleNamespace(
            handled=True,
            response_text='<action>{"type":"read_file","path":"a.txt"}</action>',
            next_query=None,
            reason="memory_checkpoint_and_action",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=True,
            memory_commit_attempted=False,
            memory_commit_accepted_count=0,
            memory_commit_rejected_count=0,
        )

        state, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx,
                '<memory_update_done />\n<action>{"type":"read_file","path":"a.txt"}</action>',
                reflection_repair_pending=False,
                reflection_repair_kind="",
            )
        )

        self.assertIsNone(outcome)  # Pass-through behavior is preserved

        mca_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_checkpoint_with_action"
        ]
        self.assertEqual(1, len(mca_calls))
        diagnostic = mca_calls[0].args[0]
        self.assertEqual("board_memory.memory_checkpoint_with_action", diagnostic.branch)
        self.assertTrue(diagnostic.candidate_available)
        self.assertFalse(diagnostic.behavior_changed)
        self.assertEqual("legacy", diagnostic.switch_value)
        self.assertEqual("legacy", diagnostic.authority_source)
        self.assertFalse(diagnostic.selected_by_switch)
        # This test characterizes diagnostic emission and pass-through visibility.
        # After reconciliation, commit_attempted_agreement is now True.
        # The harness does not update state flags, so state_flags_agreement is
        # expected to be False, causing commit_equivalent to be False.
        self.assertTrue(diagnostic.commit_attempted_agreement)
        self.assertFalse(diagnostic.state_flags_agreement)
        self.assertFalse(diagnostic.commit_equivalent)
        self.assertTrue(diagnostic.pass_through_agreement)

        mca_content_calls = [
            call
            for call in mock_log_commit_authority.call_args_list
            if getattr(call.args[0], "branch", "") == "board_memory.memory_content_with_action"
        ]
        self.assertEqual(1, len(mca_content_calls))
        self.assertFalse(mca_content_calls[0].args[0].candidate_available)


class TestResponsePipelineClassificationStage(unittest.TestCase):
    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
                self._classify_intent_output = MagicMock(return_value=ParsedModelOutput(response=""))
                self._merge_normalization_metadata = MagicMock()
                self._normalize_response_stage = MagicMock(return_value=SimpleNamespace(normalized_response="normalized_response"))
                self.stage_logger = SimpleNamespace(log=MagicMock())
                self.semantics = SimpleNamespace(
                    has_complete_think_before_action=MagicMock(return_value=False),
                    has_memory_update_done_before_action=MagicMock(return_value=False),
                    has_checkpoint_before_action=MagicMock(return_value=False),
                )
                self.state = SimpleNamespace(last_memory_update_done=False)
                self._log_semantic_shadow_disagreements = MagicMock()
                # Mocks for prevalidation mixin
                self.protocol_compiler = SimpleNamespace(analyze=MagicMock())

        self.harness = Harness()

    def test_classification_stage_recomputes_diagnosis_on_normalized_response(self):
        """_run_classification_stage recomputes diagnosis on the normalized response."""
        self.harness.protocol_compiler.analyze.return_value = SimpleNamespace(error=None, shape=SimpleNamespace(name="shape"))

        step = SimpleNamespace(model_stop_reason="stop")
        # This checkpoint state has a precomputed analysis from the *raw* response,
        # which should be ignored by the classification stage.
        precomputed_analysis = SimpleNamespace(name="precomputed_analysis_from_raw")
        checkpoint_state = CheckpointStageState(
            response="raw_response",
            reflection_repair_pending=False,
            reflection_repair_kind="",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=None,
            compiler_analysis=precomputed_analysis,
        )

        self.harness._run_classification_stage(step, "raw_response", checkpoint_state)

        # Assert that analyze was called with the *normalized* response, not the raw one,
        # and that the precomputed analysis was ignored.
        self.harness.protocol_compiler.analyze.assert_called_once_with("normalized_response")


class TestExtractedIntentPayloadRuntimeRecoverableFailure(unittest.TestCase):
    def _setup_mocks_for_bundle_response(
        self,
        raw_response: str,
        *,
        has_intent: bool,
        has_action: bool,
        action_is_malformed: bool = False,
        invalid_kind: str | None = None,
        compiler_error_code: str | None = None,
        action_count: int = 0,
    ):
        segments = []
        action_objs = []
        if has_intent:
            # Simplified parsing for test
            intent_str = raw_response.split("<intent>")[1].split("</intent>")[0]
            segments.append(SimpleNamespace(type="intent", content=intent_str))
        if has_action:
            action_blocks = re.findall(r"<action>(.*?)</action>", raw_response, re.DOTALL)
            for action_str_content in action_blocks:
                if not action_is_malformed:
                    try:
                        action_obj = json.loads(action_str_content)
                        action_objs.append(action_obj)
                        segments.append(SimpleNamespace(type="action", content=action_obj))
                    except json.JSONDecodeError:
                        # For malformed JSON tests, we might not have a valid object
                        segments.append(SimpleNamespace(type="action", content=action_str_content))
                else:
                    segments.append(SimpleNamespace(type="action", content=action_str_content))

        parsed_output = ParsedModelOutput(
            response=raw_response,
            has_action_segment=has_action,
            invalid_kind=invalid_kind,
        )
        if compiler_error_code:
            parsed_output.compiler_error_code = compiler_error_code

        if has_action and len(action_objs) == 1:
            parsed_output.action_content = action_objs[0]

        self.harness._classify_intent_output.return_value = parsed_output
        self.harness.parser.parse.return_value = segments

    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
                self.intent_response_parser = SimpleNamespace(classify=MagicMock())
                self.protocol_compiler = ProtocolCompiler()
                self.action_policy = SimpleNamespace(
                    decide=AsyncMock(),
                    validate_atomic_bundle_action=MagicMock(return_value=SimpleNamespace(ok=True)),
                )
                self.output_recovery = SimpleNamespace(decide=AsyncMock())
                self.intent_transitions = SimpleNamespace(
                    handle_model_step=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="intent_transition_reached",
                            reason="intent_transition_reached",
                            source="intent_transition",
                        )
                    ),
                    preview_payload_decision=MagicMock(
                        return_value=SimpleNamespace(applied=True, active_intent=SimpleNamespace(intent_id="test_intent"))
                    ),
                )
                self.guards = SimpleNamespace(
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.prompt_builder = SimpleNamespace(
                    build_atomic_bundle_rejected_prompt=MagicMock(return_value="atomic_bundle_rejected_prompt"),
                    build_retry_or_continue_after_failure_prompt=MagicMock(return_value="retry_prompt"),
                )
                self.semantics = SimpleNamespace(
                    has_complete_think_before_action=MagicMock(return_value=False),
                    has_memory_update_done_before_action=MagicMock(return_value=False),
                    has_checkpoint_before_action=MagicMock(return_value=False),
                    has_any_action_proposal=MagicMock(return_value=True),
                )
                self.ui = AsyncMock()
                self.config = SimpleNamespace()
                self.history = SimpleNamespace()
                self.model = SimpleNamespace()
                self.log = None

                # Mock methods from ResponsePipelineStagesMixin that are not under test
                self._normalize_response_stage = MagicMock(
                    side_effect=lambda r, **kwargs: SimpleNamespace(normalized_response=r)
                )
                self._reject_truncated_terminal_completion_before_transition = MagicMock(return_value=None)
                self._run_initial_stages = self.run_stages_for_test

            async def run_stages_for_test(self, ctx, step):
                # This is a simplified version of the initial stages for testing.
                rejection = await self._reject_invalid_intent_followup_before_transition(
                    ctx, step.response, step, preclassified=None
                )
                if rejection:
                    return None, None, rejection

                transition_outcome = await self.intent_transitions.handle_model_step(
                    ctx, step, preclassified=None
                )
                if getattr(transition_outcome, "handled", False):
                    return None, None, ResponsePipelineOutcome(
                        continue_loop=True,
                        stop_loop=False,
                        next_query=getattr(transition_outcome, "next_query", None),
                        reason=str(getattr(transition_outcome, "reason", "") or "intent_transition"),
                        source=str(getattr(transition_outcome, "source", "") or "intent_transition"),
                    )
                return None, None, None

        self.harness = Harness()
        self.harness._classify_intent_output = MagicMock()
        self.ctx = SimpleNamespace(state_machine=SimpleNamespace(), malformed_action_retries=0, audit_marker_retries=0)

    def test_extracted_intent_payload_plus_single_search_action_uses_ctx_runtime_recoverable_failure(self):
        """After a recoverable failure from ctx, an extracted intent payload + single action bundle should not be blocked."""
        raw_response = '<action>{"type":"search_files","path":".","pattern":"capability"}</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Find the capability docs."},
            intent_error=None,
        )
        self.ctx.state_machine.last_error_recoverable = True
        self.ctx.state_machine.last_error_code = "NOT_FOUND"

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_count=1,
        )
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.assertEqual("intent_transition", outcome.source)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_extracted_intent_payload_plus_single_search_action_uses_state_runtime_recoverable_failure(self):
        """After a recoverable failure from state, an extracted intent payload + single action bundle should not be blocked."""
        raw_response = '<action>{"type":"search_files","path":".","pattern":"capability"}</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Find the capability docs."},
            intent_error=None,
        )
        self.harness.state.last_error_recoverable = True
        self.harness.state.last_error_code = "NOT_FOUND"

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_count=1,
        )
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.assertEqual("intent_transition", outcome.source)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_action_only_with_extracted_intent_but_no_recoverable_context_is_blocked(self):
        """An action-only response with an extracted intent payload but no recoverable context should be blocked."""
        raw_response = '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Find docs."},
            intent_error=None,
        )
        self.harness.state.last_error_recoverable = False
        self.ctx.state_machine.last_error_recoverable = False

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_count=1,
        )
        self.harness.action_policy.validate_atomic_bundle_action.return_value = SimpleNamespace(
            ok=False, reason="atomic_bundle_action_invalid", details={}
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()


    def test_malformed_action_with_runtime_recoverable_context_is_blocked(self):
        """A malformed action with runtime recoverable context should still be blocked."""
        raw_response = '<action>{"type":"edit_file","path":"README.md",</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Update README references."},
            intent_error=None,
        )
        self.harness.state.last_error_recoverable = True

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_is_malformed=True,
            invalid_kind="malformed_action",
            compiler_error_code="E_MALFORMED_ACTION_JSON",
            action_count=1,
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="malformed_action",
            source="output_recovery",
            malformed_action_retries=1,
            audit_marker_retries=0,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("malformed_action", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_unsupported_multi_action_with_runtime_recoverable_context_is_blocked(self):
        """An unsupported multi-action bundle with runtime recoverable context should still be blocked."""
        raw_response = (
            '<action>{"type":"read_file","path":"a.txt"}</action>'
            '<action>{"type":"edit_file","path":"b.txt","old":"","new":"x"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Read and write files."},
            intent_error=None,
        )
        self.harness.state.last_error_recoverable = True

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            invalid_kind="multiple_actions",
            compiler_error_code="E_MULTIPLE_ACTIONS",
            action_count=2,
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="atomic_bundle_action_invalid",
            source="intent_atomic_bundle_guard",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()


class TestThinkRepairAtomicityCharacterization(unittest.TestCase):
    def test_is_structure_only_think_repair_safe(self):
        harness = self.harness
        # Safe case: trailing think closure
        raw = '<intent>i</intent><action>{"a":1}</action><think>t'
        repaired = raw + "</think>"
        self.assertTrue(harness._is_structure_only_think_repair_safe(raw, repaired))

        # Unsafe: think inside action
        raw = '<action>{"a":"<think>t"}</action>'
        repaired = '<action>{"a":"<think>t</think>"}</action>'
        self.assertFalse(harness._is_structure_only_think_repair_safe(raw, repaired))

        # Unsafe: action content changed
        raw = '<action>{"a":1}</action><think>t'
        repaired = '<action>{"a":2}</action><think>t</think>'
        self.assertFalse(harness._is_structure_only_think_repair_safe(raw, repaired))

        # Unsafe: intent content changed
        raw = "<intent>i1</intent><think>t"
        repaired = "<intent>i2</intent><think>t</think>"
        self.assertFalse(harness._is_structure_only_think_repair_safe(raw, repaired))

        # Unsafe: visible text changed
        raw = "text1<think>t"
        repaired = "text2<think>t</think>"
        self.assertFalse(harness._is_structure_only_think_repair_safe(raw, repaired))

    def _setup_mocks_for_bundle_response(
        self,
        raw_response: str,
        *,
        has_intent: bool,
        has_action: bool,
        action_is_malformed: bool = False,
        invalid_kind: str | None = None,
        compiler_error_code: str | None = None,
        action_count: int = 0,
    ):
        segments = []
        action_objs = []
        if has_intent:
            # Simplified parsing for test
            intent_str = raw_response.split("<intent>")[1].split("</intent>")[0]
            segments.append(SimpleNamespace(type="intent", content=intent_str))
        if has_action:
            action_blocks = re.findall(r"<action>(.*?)</action>", raw_response, re.DOTALL)
            for action_str_content in action_blocks:
                if not action_is_malformed:
                    try:
                        action_obj = json.loads(action_str_content)
                        action_objs.append(action_obj)
                        segments.append(SimpleNamespace(type="action", content=action_obj))
                    except json.JSONDecodeError:
                        # For malformed JSON tests, we might not have a valid object
                        segments.append(SimpleNamespace(type="action", content=action_str_content))
                else:
                    segments.append(SimpleNamespace(type="action", content=action_str_content))

        parsed_output = ParsedModelOutput(
            response=raw_response,
            has_action_segment=has_action,
            invalid_kind=invalid_kind,
        )
        if compiler_error_code:
            parsed_output.compiler_error_code = compiler_error_code

        if has_action and len(action_objs) == 1:
            parsed_output.action_content = action_objs[0]

        self.harness._classify_intent_output.return_value = parsed_output
        self.harness.parser.parse.return_value = segments

    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
                self.intent_response_parser = SimpleNamespace(classify=MagicMock())
                self.protocol_compiler = ProtocolCompiler()
                self.action_policy = SimpleNamespace(
                    decide=AsyncMock(),
                    validate_atomic_bundle_action=MagicMock(return_value=SimpleNamespace(ok=True)),
                )
                self.output_recovery = SimpleNamespace(decide=AsyncMock())
                self.intent_transitions = SimpleNamespace(
                    handle_model_step=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="intent_transition_reached",
                            reason="intent_transition_reached",
                            source="intent_transition",
                        )
                    ),
                    preview_payload_decision=MagicMock(
                        return_value=SimpleNamespace(applied=True, active_intent=SimpleNamespace(intent_id="test_intent"))
                    ),
                )
                self.guards = SimpleNamespace(
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.prompt_builder = SimpleNamespace(
                    build_atomic_bundle_rejected_prompt=MagicMock(return_value="atomic_bundle_rejected_prompt"),
                    build_retry_or_continue_after_failure_prompt=MagicMock(return_value="retry_prompt"),
                )
                self.semantics = SimpleNamespace(
                    has_complete_think_before_action=MagicMock(return_value=False),
                    has_memory_update_done_before_action=MagicMock(return_value=False),
                    has_checkpoint_before_action=MagicMock(return_value=False),
                    has_any_action_proposal=MagicMock(return_value=True),
                )
                self.ui = AsyncMock()
                self.config = SimpleNamespace()
                self.history = SimpleNamespace()
                self.model = SimpleNamespace()
                self.log = None

                # Mock methods from ResponsePipelineStagesMixin that are not under test
                self._reject_truncated_terminal_completion_before_transition = MagicMock(return_value=None)
                self._run_initial_stages = self.run_stages_for_test

            async def run_stages_for_test(self, ctx, step):
                # This is a simplified version of the initial stages for testing.
                # It correctly simulates allow_autorepair=False when intent_payload is present.
                allow_autorepair = not bool(getattr(step, "intent_payload", None))
                normalized = self._normalize_response_stage(
                    step.response,
                    allow_autorepair=allow_autorepair,
                    source="response_pipeline",
                )
                self.stage_logger.log(
                    "response_normalization",
                    raw_response=step.response,
                    normalized_response=getattr(normalized, "normalized_response", step.response),
                    think_repair_insert_at=getattr(normalized, "think_repair_insert_at", -1),
                    think_repair_applied=getattr(normalized, "think_repair_applied", False),
                    think_repair_blocked_by_atomicity=getattr(normalized, "think_repair_blocked_by_atomicity", False),
                    repair_blocked_reason=getattr(normalized, "repair_blocked_reason", ""),
                )
                response = getattr(normalized, "normalized_response", step.response)

                rejection = await self._reject_invalid_intent_followup_before_transition(
                    ctx, response, step, preclassified=None
                )
                if rejection:
                    return None, None, rejection

                transition_outcome = await self.intent_transitions.handle_model_step(
                    ctx, step, preclassified=None
                )
                if getattr(transition_outcome, "handled", False):
                    return None, None, ResponsePipelineOutcome(
                        continue_loop=True,
                        stop_loop=False,
                        next_query=getattr(transition_outcome, "next_query", None),
                        reason=str(getattr(transition_outcome, "reason", "") or "intent_transition"),
                        source=str(getattr(transition_outcome, "source", "") or "intent_transition"),
                    )
                return None, None, None

        self.harness = Harness()
        self.harness._classify_intent_output = MagicMock()
        self.ctx = SimpleNamespace(state_machine=SimpleNamespace(), malformed_action_retries=0, audit_marker_retries=0)

    def test_dangerous_think_repair_remains_blocked_by_atomicity(self):
        """Characterizes that a dangerous think repair is also blocked by the atomicity guard."""
        raw_response = '<intent>do thing</intent><action>{"type":"run_shell","command":"echo <think>oops"}</action>'
        repaired_response = raw_response.replace("<think>oops", "<think>oops</think>")
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "do thing"},
            intent_error=None,
        )

        def mock_normalizer(text, allow_think_autorepair):
            if text == raw_response:
                if allow_think_autorepair:
                    return SimpleNamespace(response_text=repaired_response, applied=True, blocked_by_atomicity=False)
                else:
                    return SimpleNamespace(response_text=raw_response, applied=False, blocked_by_atomicity=True)
            return SimpleNamespace(response_text=text, applied=False, blocked_by_atomicity=False)

        self.harness.intent_response_parser.normalize_model_response = mock_normalizer

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            has_action=True,
            invalid_kind="malformed_action",
            compiler_error_code="E_MALFORMED_ACTION_JSON",
            action_count=1,
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="malformed_action",
            source="output_recovery",
            malformed_action_retries=1,
            audit_marker_retries=0,
        )

        asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        normalization_log = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[0] == "response_normalization"
        ]
        self.assertGreaterEqual(len(normalization_log), 1)
        self.assertTrue(normalization_log[0].kwargs["think_repair_blocked_by_atomicity"])
        self.assertEqual("intent_atomicity_guard", normalization_log[0].kwargs["repair_blocked_reason"])
        self.assertFalse(normalization_log[0].kwargs["think_repair_applied"])

    def test_structure_only_think_repair_is_allowed_under_atomicity_constraints(self):
        """A structure-only think repair should be allowed even with an intent payload."""
        raw_response = '<intent>do thing</intent><action>{"type":"read_file","path":"a.txt"}</action><think>oops'
        repaired_response = raw_response + "</think>"
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "do thing"},
            intent_error=None,
        )

        def mock_normalizer(text, allow_think_autorepair):
            if text == raw_response:
                if allow_think_autorepair:
                    return SimpleNamespace(response_text=repaired_response, applied=True, blocked_by_atomicity=False)
                else:
                    return SimpleNamespace(response_text=raw_response, applied=False, blocked_by_atomicity=True)
            return SimpleNamespace(response_text=text, applied=False, blocked_by_atomicity=False)

        self.harness.intent_response_parser.normalize_model_response = mock_normalizer

        self._setup_mocks_for_bundle_response(
            repaired_response,
            has_intent=True,
            has_action=True,
            invalid_kind=None,
            compiler_error_code=None,
            action_count=1,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        normalization_log = [
            call for call in self.harness.stage_logger.log.call_args_list
            if call.args[0] == "response_normalization"
        ]
        self.assertGreaterEqual(len(normalization_log), 1)
        self.assertFalse(normalization_log[0].kwargs["think_repair_blocked_by_atomicity"])
        self.assertEqual("", normalization_log[0].kwargs["repair_blocked_reason"])
        self.assertTrue(normalization_log[0].kwargs["think_repair_applied"])

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()


class TestExtractedIntentPayloadRecoveryBundle(unittest.TestCase):
    def _setup_mocks_for_bundle_response(
        self,
        raw_response: str,
        *,
        has_intent: bool,
        has_action: bool,
        action_is_malformed: bool = False,
        invalid_kind: str | None = None,
        compiler_error_code: str | None = None,
        action_count: int = 0,
    ):
        segments = []
        action_objs = []
        if has_intent:
            # Simplified parsing for test
            intent_str = raw_response.split("<intent>")[1].split("</intent>")[0]
            segments.append(SimpleNamespace(type="intent", content=intent_str))
        if has_action:
            action_blocks = re.findall(r"<action>(.*?)</action>", raw_response, re.DOTALL)
            for action_str_content in action_blocks:
                if not action_is_malformed:
                    try:
                        action_obj = json.loads(action_str_content)
                        action_objs.append(action_obj)
                        segments.append(SimpleNamespace(type="action", content=action_obj))
                    except json.JSONDecodeError:
                        # For malformed JSON tests, we might not have a valid object
                        segments.append(SimpleNamespace(type="action", content=action_str_content))
                else:
                    segments.append(SimpleNamespace(type="action", content=action_str_content))

        parsed_output = ParsedModelOutput(
            response=raw_response,
            has_action_segment=has_action,
            invalid_kind=invalid_kind,
        )
        if compiler_error_code:
            parsed_output.compiler_error_code = compiler_error_code

        if has_action and len(action_objs) == 1:
            parsed_output.action_content = action_objs[0]

        self.harness._classify_intent_output.return_value = parsed_output
        self.harness.parser.parse.return_value = segments

    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
                self.intent_response_parser = SimpleNamespace(classify=MagicMock())
                self.protocol_compiler = ProtocolCompiler()
                self.action_policy = SimpleNamespace(
                    decide=AsyncMock(),
                    validate_atomic_bundle_action=MagicMock(return_value=SimpleNamespace(ok=True)),
                )
                self.output_recovery = SimpleNamespace(decide=AsyncMock())
                self.intent_transitions = SimpleNamespace(
                    handle_model_step=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="intent_transition_reached",
                            reason="intent_transition_reached",
                            source="intent_transition",
                        )
                    ),
                    preview_payload_decision=MagicMock(
                        return_value=SimpleNamespace(applied=True, active_intent=SimpleNamespace(intent_id="test_intent"))
                    ),
                )
                self.guards = SimpleNamespace(
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.prompt_builder = SimpleNamespace(
                    build_atomic_bundle_rejected_prompt=MagicMock(return_value="atomic_bundle_rejected_prompt"),
                    build_retry_or_continue_after_failure_prompt=MagicMock(return_value="retry_prompt"),
                )
                self.semantics = SimpleNamespace(
                    has_complete_think_before_action=MagicMock(return_value=False),
                    has_memory_update_done_before_action=MagicMock(return_value=False),
                    has_checkpoint_before_action=MagicMock(return_value=False),
                    has_any_action_proposal=MagicMock(return_value=True),
                )
                self.ui = AsyncMock()
                self.config = SimpleNamespace()
                self.history = SimpleNamespace()
                self.model = SimpleNamespace()
                self.log = None

                # Mock methods from ResponsePipelineStagesMixin that are not under test
                self._normalize_response_stage = MagicMock(
                    side_effect=lambda r, **kwargs: SimpleNamespace(normalized_response=r)
                )
                self._reject_truncated_terminal_completion_before_transition = MagicMock(return_value=None)
                self._run_initial_stages = self.run_stages_for_test

            async def run_stages_for_test(self, ctx, step):
                segments, parsed_output = self._classify_response_for_prevalidation(
                    step.response, allow_think_autorepair=False
                )

                parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
                parsed_intent_count = sum(1 for seg in segments if getattr(seg, "type", "") == "intent")

                if (
                    self._is_recoverable_intent_error(getattr(step, "intent_error", None))
                    and not self._has_extracted_intent_payload(step)
                    and parsed_action_count == 1
                    and parsed_intent_count == 0
                ):
                    return None, None, ResponsePipelineOutcome(
                        continue_loop=True,
                        stop_loop=False,
                        next_query="recovery_prompt",
                        reason="retry_or_continuation_after_failure",
                        source="intent_guard",
                    )

                rejection = await self._reject_invalid_intent_followup_before_transition(
                    ctx, step.response, step, preclassified=(segments, parsed_output)
                )
                if rejection:
                    return None, None, rejection

                transition_outcome = await self.intent_transitions.handle_model_step(
                    ctx, step, preclassified=(segments, parsed_output)
                )
                if getattr(transition_outcome, "handled", False):
                    return None, None, ResponsePipelineOutcome(
                        continue_loop=True,
                        stop_loop=False,
                        next_query=getattr(transition_outcome, "next_query", None),
                        reason=str(getattr(transition_outcome, "reason", "") or "intent_transition"),
                        source=str(getattr(transition_outcome, "source", "") or "intent_transition"),
                    )
                return None, None, None

        self.harness = Harness()
        self.harness._classify_intent_output = MagicMock()
        self.ctx = SimpleNamespace(state_machine=SimpleNamespace(), malformed_action_retries=0, audit_marker_retries=0)

    def test_extracted_intent_payload_plus_single_search_action_after_recoverable_failure_is_not_blocked(self):
        """After a recoverable failure, an extracted intent payload + single action bundle should not be blocked."""
        raw_response = '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Find the actual docs location."},
            intent_error={"error_code": "INTERNAL", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_count=1,
        )
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.assertEqual("intent_transition", outcome.source)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_extracted_intent_payload_plus_single_mutating_action_after_recoverable_failure_is_not_blocked_by_atomic_guard(
        self,
    ):
        """After a recoverable failure, an extracted intent payload + single mutating action bundle should not be blocked by the atomic bundle guard."""
        raw_response = '<action>{"type":"edit_file","path":"README.md","old":"x","new":"y"}</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Update README references."},
            intent_error={"error_code": "INVALID_ACTION_PATH", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_count=1,
        )
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.assertEqual("intent_transition", outcome.source)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_action_only_without_extracted_intent_payload_after_recoverable_failure_still_blocked(self):
        """An action-only response without an extracted intent payload should still be blocked after a recoverable failure."""
        raw_response = '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload=None,
            intent_error={"error_code": "INTERNAL", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_count=1,
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="retry_or_continuation_after_failure",
            source="intent_guard",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("retry_or_continuation_after_failure", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_extracted_intent_payload_with_malformed_action_still_blocked(self):
        """An extracted intent payload with a malformed action should still be blocked."""
        raw_response = '<action>{"type":"edit_file","path":"README.md",</action>'
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Update README references."},
            intent_error={"error_code": "SOME_ERROR", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            action_is_malformed=True,
            invalid_kind="malformed_action",
            compiler_error_code="E_MALFORMED_ACTION_JSON",
            action_count=1,
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="malformed_action",
            source="output_recovery",
            malformed_action_retries=1,
            audit_marker_retries=0,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("malformed_action", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_extracted_intent_payload_with_unsupported_multi_action_still_blocked(self):
        """An extracted intent payload with an unsupported multi-action bundle should still be blocked."""
        raw_response = (
            '<action>{"type":"read_file","path":"a.txt"}</action>'
            '<action>{"type":"edit_file","path":"b.txt","old":"","new":"x"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate", "intent": "Read and write files."},
            intent_error={"error_code": "SOME_ERROR", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=False,
            has_action=True,
            invalid_kind="multiple_actions",
            compiler_error_code="E_MULTIPLE_ACTIONS",
            action_count=2,
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="atomic_bundle_action_invalid",
            source="intent_atomic_bundle_guard",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()


# Phase 32 — Step 2/8: Permit Valid Intent+Single-Action Bundles after Recoverable Failure
class TestAtomicBundleRecoveryAfterFailure(unittest.TestCase):
    def _setup_mocks_for_bundle_response(
        self,
        raw_response: str,
        *,
        has_intent: bool,
        has_action: bool,
        action_is_malformed: bool = False,
        invalid_kind: str | None = None,
        compiler_error_code: str | None = None,
    ):
        segments = []
        action_objs = []
        if has_intent:
            # Simplified parsing for test
            intent_str = raw_response.split("<intent>")[1].split("</intent>")[0]
            segments.append(SimpleNamespace(type="intent", content=intent_str))
        if has_action:
            action_blocks = re.findall(r"<action>(.*?)</action>", raw_response, re.DOTALL)
            for action_str_content in action_blocks:
                if not action_is_malformed:
                    try:
                        action_obj = json.loads(action_str_content)
                        action_objs.append(action_obj)
                        segments.append(SimpleNamespace(type="action", content=action_obj))
                    except json.JSONDecodeError:
                        # For malformed JSON tests, we might not have a valid object
                        segments.append(SimpleNamespace(type="action", content=action_str_content))
                else:
                    segments.append(SimpleNamespace(type="action", content=action_str_content))

        parsed_output = ParsedModelOutput(
            response=raw_response,
            has_action_segment=has_action,
            invalid_kind=invalid_kind,
        )
        if compiler_error_code:
            parsed_output.compiler_error_code = compiler_error_code

        if has_action and len(action_objs) == 1:
            parsed_output.action_content = action_objs[0]

        self.harness._classify_intent_output.return_value = parsed_output
        self.harness.parser.parse.return_value = segments

    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
                self.intent_response_parser = SimpleNamespace(classify=MagicMock())
                self.protocol_compiler = ProtocolCompiler()
                self.action_policy = SimpleNamespace(
                    decide=AsyncMock(),
                    validate_atomic_bundle_action=MagicMock(return_value=SimpleNamespace(ok=True)),
                )
                self.output_recovery = SimpleNamespace(decide=AsyncMock())
                self.intent_transitions = SimpleNamespace(
                    handle_model_step=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="intent_transition_reached",
                            reason="intent_transition_reached",
                        )
                    ),
                    preview_payload_decision=MagicMock(
                        return_value=SimpleNamespace(applied=True, active_intent=SimpleNamespace(intent_id="test_intent"))
                    ),
                )
                self.guards = SimpleNamespace(
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.prompt_builder = SimpleNamespace(
                    build_atomic_bundle_rejected_prompt=MagicMock(return_value="atomic_bundle_rejected_prompt"),
                    build_retry_or_continue_after_failure_prompt=MagicMock(return_value="retry_prompt"),
                )
                self.semantics = SimpleNamespace(
                    has_complete_think_before_action=MagicMock(return_value=False),
                    has_memory_update_done_before_action=MagicMock(return_value=False),
                    has_checkpoint_before_action=MagicMock(return_value=False),
                    has_any_action_proposal=MagicMock(return_value=True),
                )
                self.ui = AsyncMock()
                self.config = SimpleNamespace()
                self.history = SimpleNamespace()
                self.model = SimpleNamespace()
                self.log = None

                # Mock methods from ResponsePipelineStagesMixin that are not under test
                self._normalize_response_stage = MagicMock(
                    side_effect=lambda r, **kwargs: SimpleNamespace(normalized_response=r)
                )
                self._reject_truncated_terminal_completion_before_transition = MagicMock(return_value=None)

        self.harness = Harness()
        self.harness._classify_intent_output = MagicMock()
        self.ctx = SimpleNamespace(state_machine=SimpleNamespace(), malformed_action_retries=0, audit_marker_retries=0)

    def test_valid_intent_plus_search_action_bundle_is_not_blocked_after_recoverable_failure(self):
        """After a recoverable failure, a valid intent+search_action bundle should not be blocked."""
        raw_response = (
            "<intent>Find the actual docs location after documentation was missing.</intent>"
            '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error={"error_code": "NOT_FOUND", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            has_action=True,
        )
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.assertEqual("intent_transition", outcome.source)
        self.assertNotEqual("retry_or_continuation_after_failure", outcome.reason)
        self.assertNotEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_valid_intent_plus_mutating_action_bundle_is_not_blocked_after_recoverable_failure(self):
        """After a recoverable failure, a valid intent+mutating_action bundle should not be blocked by the atomic bundle guard."""
        raw_response = (
            "<intent>Update README references.</intent>"
            '<action>{"type":"edit_file","path":"README.md","old":"x","new":"y"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error={"error_code": "INVALID_ACTION_PATH", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(raw_response, has_intent=True, has_action=True)
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.assertEqual("intent_transition", outcome.source)
        self.assertNotEqual("retry_or_continuation_after_failure", outcome.reason)
        self.assertNotEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_malformed_action_bundle_is_blocked_after_recoverable_failure(self):
        """A bundle with malformed action JSON should be blocked."""
        raw_response = (
            "<intent>Update README references.</intent>"
            '<action>{"type":"edit_file","path":"README.md",</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error={"error_code": "SOME_ERROR", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            has_action=True,
            action_is_malformed=True,
            invalid_kind="malformed_action",
            compiler_error_code="E_MALFORMED_ACTION_JSON",
        )
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason="malformed_action",
            source="output_recovery",
            malformed_action_retries=1,
            audit_marker_retries=0,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("malformed_action", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_multi_action_bundle_is_not_blocked_after_recoverable_failure_if_valid_discovery_bundle(self):
        """A valid read-only discovery bundle should not be blocked after a recoverable failure."""
        raw_response = (
            "<intent>Read two files.</intent>"
            '<action>{"type":"read_file","path":"a.txt"}</action>'
            '<action>{"type":"read_file","path":"b.txt"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error={"error_code": "SOME_ERROR", "recoverable": True},
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            has_action=True,
            invalid_kind=None,
            compiler_error_code=None,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()


# Phase 32 — Step 3/8: E_ACTION_PAYLOAD_ARRAY / Read-only Multi-action Discovery Bundle Characterization
class TestReadonlyMultiActionDiscoveryCharacterization(unittest.TestCase):
    def _setup_mocks_for_bundle_response(
        self,
        raw_response: str,
        *,
        has_intent: bool,
        action_count: int,
        action_is_malformed: bool = False,
        invalid_kind: str | None = None,
        compiler_error_code: str | None = None,
    ):
        segments = []
        action_objs = []
        if has_intent:
            # Simplified parsing for test
            intent_str = raw_response.split("<intent>")[1].split("</intent>")[0]
            segments.append(SimpleNamespace(type="intent", content=intent_str))
        if action_count > 0:
            action_blocks = re.findall(r"<action>(.*?)</action>", raw_response, re.DOTALL)
            for action_str_content in action_blocks:
                if not action_is_malformed:
                    try:
                        action_obj = json.loads(action_str_content)
                        action_objs.append(action_obj)
                        segments.append(SimpleNamespace(type="action", content=action_obj))
                    except json.JSONDecodeError:
                        segments.append(SimpleNamespace(type="action", content=action_str_content))
                else:
                    segments.append(SimpleNamespace(type="action", content=action_str_content))

        parsed_output = ParsedModelOutput(
            response=raw_response,
            has_action_segment=action_count > 0,
            invalid_kind=invalid_kind,
        )
        if compiler_error_code:
            parsed_output.compiler_error_code = compiler_error_code

        if action_count == 1 and len(action_objs) == 1:
            parsed_output.action_content = action_objs[0]

        self.harness._classify_intent_output.return_value = parsed_output
        self.harness.parser.parse.return_value = segments

    def setUp(self):
        class Harness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
                self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
                self.intent_response_parser = SimpleNamespace(classify=MagicMock())
                self.protocol_compiler = ProtocolCompiler()
                self.action_policy = SimpleNamespace(
                    decide=AsyncMock(),
                    validate_atomic_bundle_action=MagicMock(return_value=SimpleNamespace(ok=True)),
                )
                self.output_recovery = SimpleNamespace(decide=AsyncMock())
                self.intent_transitions = SimpleNamespace(
                    handle_model_step=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="intent_transition_reached",
                            reason="intent_transition_reached",
                            source="intent_transition",
                        )
                    ),
                    preview_payload_decision=MagicMock(
                        return_value=SimpleNamespace(applied=True, active_intent=SimpleNamespace(intent_id="test_intent"))
                    ),
                )
                self.guards = SimpleNamespace(
                    set_nonproductive_thinking_state=MagicMock(),
                )
                self.prompt_builder = SimpleNamespace(
                    build_atomic_bundle_rejected_prompt=MagicMock(return_value="atomic_bundle_rejected_prompt"),
                    build_retry_or_continue_after_failure_prompt=MagicMock(return_value="retry_prompt"),
                )
                self.semantics = SimpleNamespace(
                    has_complete_think_before_action=MagicMock(return_value=False),
                    has_memory_update_done_before_action=MagicMock(return_value=False),
                    has_checkpoint_before_action=MagicMock(return_value=False),
                    has_any_action_proposal=MagicMock(return_value=True),
                )
                self.ui = AsyncMock()
                self.config = SimpleNamespace()
                self.history = SimpleNamespace()
                self.model = SimpleNamespace()
                self.log = None

                # Mock methods from ResponsePipelineStagesMixin that are not under test
                self._normalize_response_stage = MagicMock(
                    side_effect=lambda r, **kwargs: SimpleNamespace(normalized_response=r)
                )
                self._reject_truncated_terminal_completion_before_transition = MagicMock(return_value=None)
                self._run_initial_stages = self.run_stages_for_test

            async def run_stages_for_test(self, ctx, step):
                # This is a simplified version of the initial stages for testing
                rejection = await self._reject_invalid_intent_followup_before_transition(
                    ctx, step.response, step, preclassified=None
                )
                if rejection:
                    return None, None, rejection

                # This is where the transition would happen
                transition_outcome = await self.intent_transitions.handle_model_step(
                    ctx, step, preclassified=None
                )
                if getattr(transition_outcome, "handled", False):
                    return None, None, ResponsePipelineOutcome(
                        continue_loop=True,
                        stop_loop=False,
                        next_query=getattr(transition_outcome, "next_query", None),
                        reason=str(getattr(transition_outcome, "reason", "") or "intent_transition"),
                        source=str(getattr(transition_outcome, "source", "") or "intent_transition"),
                    )
                return None, None, None

        self.harness = Harness()
        self.harness._classify_intent_output = MagicMock()
        self.ctx = SimpleNamespace(state_machine=SimpleNamespace(), malformed_action_retries=0, audit_marker_retries=0)

    def _mock_output_recovery_rejection(self, reason: str = "atomic_bundle_action_invalid"):
        self.harness.output_recovery.decide.return_value = SimpleNamespace(
            handled=True,
            continue_loop=True,
            stop_loop=False,
            next_query="recovery_prompt",
            reason=reason,
            source="intent_atomic_bundle_guard",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

    def test_readonly_three_action_discovery_bundle_is_protocol_valid(self):
        """A bundle with 3 read-only actions should be protocol-valid."""
        raw_response = (
            "<intent>Inspect project documentation structure.</intent>"
            '<action>{"type":"list_directory","path":"."}</action>'
            '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
            '<action>{"type":"search_content","path":".","pattern":"README"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error=None,
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            action_count=3,
            invalid_kind=None,
            compiler_error_code=None,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_readonly_two_action_discovery_bundle_is_protocol_valid(self):
        """A bundle with 2 read-only actions should be protocol-valid."""
        raw_response = (
            "<intent>Find documentation files.</intent>"
            '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
            '<action>{"type":"search_content","path":".","pattern":"README"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error=None,
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            action_count=2,
            invalid_kind=None,
            compiler_error_code=None,
        )

        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_transition_reached", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_awaited_once()

    def test_four_readonly_actions_bundle_is_blocked(self):
        """A bundle with 4 read-only actions should be blocked (too many)."""
        raw_response = (
            "<intent>Inspect project documentation structure.</intent>"
            '<action>{"type":"list_directory","path":"."}</action>'
            '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
            '<action>{"type":"search_content","path":".","pattern":"README"}</action>'
            '<action>{"type":"read_file","path":"main.py"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error=None,
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            action_count=4,
            invalid_kind="multiple_actions",
            compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        )

        self._mock_output_recovery_rejection("atomic_bundle_action_invalid")
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_mixed_read_write_multi_action_bundle_is_blocked(self):
        """A multi-action bundle with mutating actions should be blocked."""
        raw_response = (
            "<intent>Inspect and update README.</intent>"
            '<action>{"type":"read_file","path":"README.md"}</action>'
            '<action>{"type":"edit_file","path":"README.md","old":"x","new":"y"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error=None,
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            action_count=2,
            invalid_kind="multiple_actions",
            compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        )

        self._mock_output_recovery_rejection("atomic_bundle_action_invalid")
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_run_shell_in_multi_action_bundle_is_blocked(self):
        """A multi-action bundle with run_shell should be blocked."""
        raw_response = (
            "<intent>Find docs.</intent>"
            '<action>{"type":"search_files","path":".","pattern":"doc"}</action>'
            '<action>{"type":"run_shell","cmd":"find . -name \'*doc*\'"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error=None,
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            action_count=2,
            invalid_kind="multiple_actions",
            compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        )

        self._mock_output_recovery_rejection("atomic_bundle_action_invalid")
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()

    def test_unbounded_readonly_multi_action_bundle_is_blocked(self):
        """A bundle with an unbounded action (e.g., missing pattern) should be blocked."""
        raw_response = (
            "<intent>Inspect project documentation structure.</intent>"
            '<action>{"type":"search_files","path":"."}</action>'
            '<action>{"type":"list_directory","path":"./src"}</action>'
        )
        step = SimpleNamespace(
            response=raw_response,
            model_stop_reason="",
            intent_payload={"mode": "activate"},
            intent_error=None,
        )

        self._setup_mocks_for_bundle_response(
            raw_response,
            has_intent=True,
            action_count=2,
            invalid_kind="multiple_actions",
            compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        )

        self._mock_output_recovery_rejection("atomic_bundle_action_invalid")
        _, _, outcome = asyncio.run(self.harness._run_initial_stages(self.ctx, step))

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("atomic_bundle_action_invalid", outcome.reason)
        self.harness.intent_transitions.handle_model_step.assert_not_awaited()


class TestStaleRetryGuard(unittest.TestCase):
    def setUp(self):
        self.guard = IntentGuard()
        self.command = {"type": "read_file", "path": "a.txt"}
        self.state = SimpleNamespace(
            active_intent=None,
            has_retry_context=lambda: True,
            last_error_recoverable=None,
            can_continue_current_intent_after_failure=lambda: False,
        )
        # Mock methods on guard that are not under test
        self.guard._current_intent_allows_action = MagicMock(return_value=False)
        self.guard._is_soft_recoverable_retry_context = MagicMock(return_value=False)

    def test_stale_retry_context_is_blocked(self):
        """A stale retry context (last_error_recoverable=False) should not trigger the retry guard."""
        self.state.last_error_recoverable = False

        requires_intent, reason = self.guard.action_requires_intent(
            self.command, self.state, batch_size=1, current_user_input=""
        )

        self.assertFalse(requires_intent)
        self.assertNotEqual("retry_or_continuation_after_failure", reason)

    def test_true_recoverable_failure_still_triggers_retry_guard(self):
        """A true recoverable failure (last_error_recoverable=True) should still trigger the retry guard."""
        self.state.last_error_recoverable = True

        requires_intent, reason = self.guard.action_requires_intent(
            self.command, self.state, batch_size=1, current_user_input=""
        )

        self.assertTrue(requires_intent)
        self.assertEqual("retry_or_continuation_after_failure", reason)

    def test_backward_compatibility_without_last_error_recoverable(self):
        """When last_error_recoverable is absent, has_retry_context() should be used."""
        # last_error_recoverable is None by default in setUp

        requires_intent, reason = self.guard.action_requires_intent(
            self.command, self.state, batch_size=1, current_user_input=""
        )

        self.assertTrue(requires_intent)
        self.assertEqual("retry_or_continuation_after_failure", reason)

    def test_no_retry_context_at_all(self):
        """When there is no retry context at all, the guard should not trigger."""
        self.state.has_retry_context = lambda: False
        self.state.last_error_recoverable = None

        requires_intent, reason = self.guard.action_requires_intent(
            self.command, self.state, batch_size=1, current_user_input=""
        )

        self.assertFalse(requires_intent)
        self.assertNotEqual("retry_or_continuation_after_failure", reason)


if __name__ == "__main__":
    unittest.main()
