import unittest
from types import SimpleNamespace

from modules.agent.orchestration.responses.stage_logging import OrchestrationStageLogger


class _DummyLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg, *args):
        self.messages.append(msg % args if args else msg)


class OrchestrationTraceSchemaTests(unittest.TestCase):
    def _state(self):
        return SimpleNamespace(
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )

    def test_trace_entry_gets_canonical_defaults_even_when_log_fields_are_sparse(self):
        state = self._state()
        logger = OrchestrationStageLogger(_DummyLogger(), state)

        logger.log("response_pipeline", "pass")

        entry = state.orchestration_trace[-1]
        fields = entry.fields
        self.assertEqual("", fields["reason"])
        self.assertEqual("", fields["source"])
        self.assertEqual("", fields["universe"])
        self.assertEqual("", fields["invalid_kind"])
        self.assertEqual("", fields["transition"])
        self.assertIsNone(fields["transition_applied"])
        self.assertEqual(0, fields["repeat_count"])
        self.assertFalse(fields["think_repair_applied"])
        self.assertEqual("", fields["think_repair_reason"])
        self.assertEqual("", fields["think_repair_confidence"])
        self.assertEqual("", fields["think_repair_tag"])
        self.assertIsNone(fields["execution_plan"])
        self.assertIsNone(fields["execution_commit"])
        self.assertIsNone(fields["plan_review_required_after_state_change"])
        self.assertEqual("", fields["plan_review_required_reason"])
        self.assertEqual("", fields["plan_review_required_action_type"])
        self.assertEqual("", fields["plan_review_required_target"])
        self.assertIsNone(fields["plan_review_required_action_effects"])
        self.assertIsNone(fields["fallback_commit_used"])
        self.assertEqual("", fields["fallback_commit_reason"])
        self.assertIsNone(fields["model_action_present"])
        self.assertIsNone(fields["action_validated"])
        self.assertIsNone(fields["execution_plan_dispatched"])
        self.assertIsNone(fields["atomic_bundle_validated"])
        self.assertIsNone(fields["fallback_dispatch_used"])
        self.assertIsNone(fields["tool_execution_attempted"])
        self.assertIsNone(fields["tool_execution_succeeded"])
        self.assertIsNone(fields["system_result_recorded"])
        self.assertIsNone(fields["state_change_effect_recorded"])
        self.assertIsNone(fields["state_change_applied"])

    def test_stage_logger_preserves_semantic_decision_record_field(self):
        state = self._state()
        logger = OrchestrationStageLogger(_DummyLogger(), state)
        semantic_decision_record = {
            "domain": "output_recovery",
            "stage": "output_recovery",
            "decision": "compiler_strategy_resolved",
            "reason": "file_content_must_follow_action",
            "source": "compiler_recovery_strategy",
            "diagnostic_only": True,
            "authority_affecting": False,
            "behavior_affecting": False,
            "compiler_metadata": {
                "error_code": "E_FILE_CONTENT_ACTION_MISMATCH",
                "recovery_id": "file_content_must_follow_action",
                "invalid_kind": "file_content_must_follow_action",
                "source": "runtime_protocol_semantics",
            },
            "registry_resolution": {
                "resolved": True,
                "strategy_id": "file_content_action_mismatch",
                "handler_key": "file_content_order",
                "allowed_next_shapes": [],
            },
        }

        logger.log(
            "output_recovery",
            "diagnostic",
            reason="file_content_must_follow_action",
            source="semantic_decision_record",
            semantic_decision_record=semantic_decision_record,
        )

        entry = state.orchestration_trace[-1]
        fields = entry.fields
        self.assertEqual("output_recovery", entry.stage)
        self.assertEqual("diagnostic", entry.decision)
        self.assertEqual("semantic_decision_record", fields["source"])
        self.assertEqual(semantic_decision_record, fields["semantic_decision_record"])
        self.assertTrue(fields["semantic_decision_record"]["diagnostic_only"])
        self.assertEqual(
            "file_content_action_mismatch",
            fields["semantic_decision_record"]["registry_resolution"]["strategy_id"],
        )

    def test_explicit_trace_fields_override_defaults(self):
        state = self._state()
        logger = OrchestrationStageLogger(_DummyLogger(), state)

        logger.log(
            "intent_transition",
            "continue",
            reason="conflicting_intent_transitions",
            source="intent_runtime",
            universe="transition_in_progress",
            transition="rejected",
            transition_applied=False,
            repeat_count=3,
        )

        entry = state.orchestration_trace[-1]
        fields = entry.fields
        self.assertEqual("conflicting_intent_transitions", fields["reason"])
        self.assertEqual("intent_runtime", fields["source"])
        self.assertEqual("transition_in_progress", fields["universe"])
        self.assertEqual("rejected", fields["transition"])
        self.assertFalse(fields["transition_applied"])
        self.assertEqual(3, fields["repeat_count"])

    def test_text_logger_remains_compact_and_does_not_render_empty_defaults(self):
        state = self._state()
        sink = _DummyLogger()
        logger = OrchestrationStageLogger(sink, state)

        logger.log("response_pipeline", "pass")

        rendered = sink.messages[-1]
        self.assertIn("stage=response_pipeline", rendered)
        self.assertIn("decision=pass", rendered)
        self.assertNotIn("reason=", rendered)
        self.assertNotIn("universe=", rendered)
