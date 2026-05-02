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
