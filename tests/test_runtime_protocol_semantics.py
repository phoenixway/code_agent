import unittest
from types import SimpleNamespace

from modules.agent.orchestration.protocol import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.runtime_protocol_semantics import (
    RuntimeProtocolSemantics,
    compact_runtime_protocol_semantics,
    runtime_semantics_from_compiler_analysis,
    runtime_semantics_from_parsed_output,
)
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


class TestRuntimeProtocolSemantics(unittest.TestCase):
    def setUp(self):
        self.compiler = ProtocolCompiler()

    def test_from_compiler_analysis_action_only(self):
        analysis = self.compiler.analyze('<action>{"type":"read_file","path":"a.py"}</action>')
        snapshot = runtime_semantics_from_compiler_analysis(analysis)

        self.assertEqual("compiler", snapshot.source)
        self.assertEqual("ACTION_ONLY", snapshot.shape)
        self.assertTrue(snapshot.is_valid)
        self.assertEqual("", snapshot.error_code)
        self.assertTrue(snapshot.has_action)
        self.assertEqual(1, snapshot.action_count)
        self.assertEqual(1, len(snapshot.action_ops))
        self.assertEqual("read_file", snapshot.action_ops[0].action_type)
        self.assertFalse(snapshot.has_visible_answer)
        self.assertEqual("", snapshot.visible_text)

    def test_from_compiler_analysis_pre_action_text(self):
        analysis = self.compiler.analyze('OK\n<action>{"type":"read_file","path":"a.py"}</action>')
        snapshot = runtime_semantics_from_compiler_analysis(analysis)

        self.assertEqual("compiler", snapshot.source)
        self.assertEqual("PRE_ACTION_TEXT_AND_ACTION", snapshot.shape)
        self.assertTrue(snapshot.is_valid)
        self.assertTrue(snapshot.has_pre_action_text)
        self.assertEqual("OK", snapshot.pre_action_text)
        self.assertTrue(snapshot.has_action)
        self.assertFalse(snapshot.has_visible_answer)
        self.assertEqual("", snapshot.visible_text)

    def test_from_compiler_analysis_plaintext_only(self):
        analysis = self.compiler.analyze("Hello world")
        snapshot = runtime_semantics_from_compiler_analysis(analysis)

        self.assertEqual("compiler", snapshot.source)
        self.assertEqual("PLAINTEXT_ONLY", snapshot.shape)
        self.assertTrue(snapshot.is_valid)
        self.assertTrue(snapshot.has_visible_answer)
        self.assertEqual("Hello world", snapshot.visible_text)
        self.assertFalse(snapshot.has_action)
        self.assertEqual(0, snapshot.action_count)

    def test_from_compiler_analysis_invalid_unclosed_think(self):
        analysis = self.compiler.analyze("<think>oops")
        snapshot = runtime_semantics_from_compiler_analysis(analysis, invalid_kind="malformed_incomplete_think")

        self.assertEqual("compiler", snapshot.source)
        self.assertEqual("INVALID", snapshot.shape)
        self.assertFalse(snapshot.is_valid)
        self.assertEqual("E_UNCLOSED_THINK", snapshot.error_code)
        self.assertEqual("unclosed_think", snapshot.recovery_id)
        self.assertEqual("malformed_incomplete_think", snapshot.invalid_kind)
        self.assertEqual(0, snapshot.action_count)
        self.assertIsInstance(snapshot.action_ops, tuple)

    def test_from_compiler_analysis_handles_none(self):
        snapshot = runtime_semantics_from_compiler_analysis(None)
        self.assertEqual("missing_compiler_analysis", snapshot.source)
        self.assertFalse(snapshot.is_valid)
        self.assertEqual("", snapshot.shape)

    def test_from_parsed_output_with_compiler_data(self):
        analysis = self.compiler.analyze('<action>{"type":"read_file","path":"a.py"}</action>')
        parsed_output = ParsedModelOutput(
            response="",
            compiler_shape=analysis.shape.name,
            compiler_error_code="",
            compiler_recovery_id="",
            compiler_ir=analysis.ir,
            invalid_kind="",
        )
        snapshot = runtime_semantics_from_parsed_output(parsed_output)

        self.assertEqual("compiler", snapshot.source)
        self.assertEqual("ACTION_ONLY", snapshot.shape)
        self.assertTrue(snapshot.is_valid)
        self.assertEqual(1, snapshot.action_count)

    def test_from_parsed_output_fallback(self):
        parsed_output = ParsedModelOutput(response="plain text")
        snapshot = runtime_semantics_from_parsed_output(parsed_output)

        self.assertEqual("legacy_fallback", snapshot.source)
        self.assertFalse(snapshot.is_valid)
        self.assertEqual(0, snapshot.action_count)

    def test_integration_with_prevalidation_mixin(self):
        class Harness(ResponsePipelinePrevalidationMixin):
            def __init__(self):
                self.protocol_compiler = ProtocolCompiler()

            def _compiler_invalid_kind(self, compiler_analysis):
                return "some_kind" if compiler_analysis.error else ""

        harness = Harness()
        parsed_output = ParsedModelOutput(response="")
        harness._apply_compiler_diagnosis(parsed_output, '<action>{"type":"read_file","path":"a.py"}</action>')

        self.assertIsNotNone(parsed_output.runtime_protocol_semantics)
        self.assertIsInstance(parsed_output.runtime_protocol_semantics, RuntimeProtocolSemantics)
        self.assertEqual("compiler", parsed_output.runtime_protocol_semantics.source)
        self.assertEqual("ACTION_ONLY", parsed_output.runtime_protocol_semantics.shape)
        self.assertEqual(1, parsed_output.runtime_protocol_semantics.action_count)
        self.assertEqual(parsed_output.compiler_shape, parsed_output.runtime_protocol_semantics.shape)
        self.assertEqual(parsed_output.compiler_error_code, parsed_output.runtime_protocol_semantics.error_code)
        self.assertEqual(parsed_output.compiler_recovery_id, parsed_output.runtime_protocol_semantics.recovery_id)
        if parsed_output.compiler_ir:
            self.assertEqual(
                parsed_output.compiler_ir.action_count,
                parsed_output.runtime_protocol_semantics.action_count,
            )

    def test_compact_snapshot_handles_none(self):
        compact = compact_runtime_protocol_semantics(None)
        self.assertEqual("not_a_snapshot", compact["source"])

    def test_compact_snapshot_includes_key_fields(self):
        analysis = self.compiler.analyze('<action>{"type":"read_file","path":"a.py"}</action>')
        snapshot = runtime_semantics_from_compiler_analysis(analysis)
        compact = compact_runtime_protocol_semantics(snapshot)

        self.assertEqual("compiler", compact["source"])
        self.assertEqual("ACTION_ONLY", compact["shape"])
        self.assertTrue(compact["is_valid"])
        self.assertEqual(1, compact["action_count"])
        self.assertTrue(compact["has_action"])
        self.assertEqual(0, compact["intent_count"])
        self.assertFalse(compact["has_visible_answer"])
        self.assertFalse(compact["has_pre_action_text"])
        self.assertFalse(compact["has_file_content"])
        self.assertEqual(1, compact["effects_preview_count"])
