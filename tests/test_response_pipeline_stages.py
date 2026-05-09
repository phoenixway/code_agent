"""Unit tests for ResponsePipelineStagesMixin."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.response_pipeline_stages import CheckpointStageState, ResponsePipelineStagesMixin
from modules.agent.orchestration.responses.board_checkpoint_models import BoardCheckpointKind, BoardCheckpointSource
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


if __name__ == "__main__":
    unittest.main()
