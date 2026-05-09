"""Unit tests for ResponsePipelineStagesMixin."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
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
        class Harness(ResponsePipelineStagesMixin):
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

        self.harness = Harness()
        self.ctx = SimpleNamespace()

    def test_checkpoint_stage_with_memory_checkpoint_only_continues(self):
        """Characterizes the behavior when the memory board handler detects a checkpoint-only response."""
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
        self.assertTrue(outcome.memory_checkpoint_only)
        self.assertFalse(outcome.memory_checkpoint_and_text)

    def test_checkpoint_stage_with_memory_checkpoint_and_text_passes_through(self):
        """Characterizes that memory_checkpoint_and_text does not result in a handled outcome from the checkpoint stage itself, but passes state to the next stage."""
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
        # The logic inside _run_checkpoint_stage specifically un-handles this case
        # to let it flow to post-classification.
        self.assertFalse(state.memory_board_decision.handled)

    def test_checkpoint_stage_with_plan_checkpoint_only_continues(self):
        """Characterizes the behavior when the plan board handler handles the response."""
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

        _, outcome = asyncio.run(
            self.harness._run_checkpoint_stage(
                self.ctx, "response", reflection_repair_pending=False, reflection_repair_kind=""
            )
        )

        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertTrue(outcome.continue_loop)
        self.assertEqual("next_query_from_plan_board", outcome.next_query)
        self.assertEqual("plan_checkpoint_only", outcome.reason)
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


if __name__ == "__main__":
    unittest.main()
