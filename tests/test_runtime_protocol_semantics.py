import unittest
from types import SimpleNamespace

from modules.agent.orchestration.protocol import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.compiler_recovery_registry import CompilerRecoveryRegistry
from modules.agent.orchestration.responses.output_recovery_routing import OutputRecoveryRoutingMixin
from modules.agent.orchestration.responses.runtime_protocol_semantics import (
    RuntimeProtocolSemantics,
    compact_runtime_protocol_semantics,
    output_recovery_compiler_metadata,
    output_recovery_structural_parity,
    runtime_semantics_from_compiler_analysis,
    runtime_semantics_from_output_or_none,
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

    def test_runtime_semantics_from_output_or_none_returns_existing(self):
        existing_snapshot = RuntimeProtocolSemantics(
            source="existing",
            shape="TEST",
            is_valid=True,
            error_code="",
            recovery_id="",
            invalid_kind="",
            action_count=1,
            has_action=True,
            action_ops=(),
            intent_ops=(),
            visible_text="",
            has_visible_answer=False,
            pre_action_text="",
            has_pre_action_text=False,
            memory_ops=(),
            subgoal_ops=(),
            has_file_content=False,
            file_content="",
            effects_preview=(),
        )
        parsed_output = ParsedModelOutput(response="", runtime_protocol_semantics=existing_snapshot)
        snapshot = runtime_semantics_from_output_or_none(parsed_output)
        self.assertIs(snapshot, existing_snapshot)

    def test_runtime_semantics_from_output_or_none_builds_new(self):
        analysis = self.compiler.analyze('<action>{"type":"read_file","path":"a.py"}</action>')
        parsed_output = ParsedModelOutput(
            response="",
            compiler_shape=analysis.shape.name,
            compiler_ir=analysis.ir,
        )
        snapshot = runtime_semantics_from_output_or_none(parsed_output)
        self.assertIsNotNone(snapshot)
        self.assertEqual("compiler", snapshot.source)
        self.assertEqual("ACTION_ONLY", snapshot.shape)

    def test_runtime_semantics_from_output_or_none_returns_none(self):
        parsed_output = ParsedModelOutput(response="text only")
        snapshot = runtime_semantics_from_output_or_none(parsed_output)
        self.assertIsNone(snapshot)

    def test_output_recovery_structural_parity_handles_none(self):
        parsed_output = ParsedModelOutput(response="text only")
        parity = output_recovery_structural_parity(parsed_output)
        self.assertFalse(parity["has_snapshot"])

    def test_output_recovery_structural_parity_compares_fields(self):
        analysis = self.compiler.analyze('<action>{"type":"read_file","path":"a.py"}</action>')
        parsed_output = ParsedModelOutput(
            response="",
            has_action_segment=True,
            invalid_kind="some_kind",
            runtime_protocol_semantics=runtime_semantics_from_compiler_analysis(analysis, invalid_kind="some_kind"),
        )
        parity = output_recovery_structural_parity(parsed_output, parsed_action_count=1)
        self.assertTrue(parity["has_snapshot"])
        self.assertEqual("ACTION_ONLY", parity["snapshot_shape"])
        self.assertEqual("some_kind", parity["snapshot_invalid_kind"])
        self.assertEqual("some_kind", parity["parsed_invalid_kind"])
        self.assertTrue(parity["invalid_kind_matches"])
        self.assertEqual(1, parity["snapshot_action_count"])
        self.assertEqual(1, parity["parsed_action_count"])
        self.assertTrue(parity["action_count_matches"])
        self.assertTrue(parity["snapshot_has_action"])
        self.assertTrue(parity["parsed_has_action_segment"])
        self.assertTrue(parity["has_action_matches"])
        self.assertEqual("", parity.get("mismatch_kind", ""))
        self.assertFalse(parity.get("expected_mismatch", False))

    def test_output_recovery_structural_parity_mismatch(self):
        analysis = self.compiler.analyze("just text")
        parsed_output = ParsedModelOutput(
            response="",
            has_action_segment=True,  # Mismatch
            invalid_kind="legacy_kind",  # Mismatch
            runtime_protocol_semantics=runtime_semantics_from_compiler_analysis(analysis, invalid_kind="compiler_kind"),
        )
        parity = output_recovery_structural_parity(parsed_output, parsed_action_count=1)
        self.assertFalse(parity["invalid_kind_matches"])
        self.assertFalse(parity["action_count_matches"])
        self.assertFalse(parity["has_action_matches"])
        self.assertEqual("", parity.get("mismatch_kind", ""))
        self.assertFalse(parity.get("expected_mismatch", False))

    def test_output_recovery_structural_parity_expected_mismatch(self):
        analysis = self.compiler.analyze("<think>oops<action>x</action>")
        snapshot = runtime_semantics_from_compiler_analysis(analysis, invalid_kind="malformed_incomplete_think")
        self.assertEqual("INVALID", snapshot.shape)
        self.assertEqual("E_UNCLOSED_THINK", snapshot.error_code)
        self.assertEqual(0, snapshot.action_count)
        self.assertFalse(snapshot.has_action)

        parsed_output = ParsedModelOutput(
            response="",
            has_action_segment=True,
            invalid_kind="malformed_incomplete_think",
            runtime_protocol_semantics=snapshot,
        )
        parity = output_recovery_structural_parity(parsed_output, parsed_action_count=1)

        self.assertFalse(parity["action_count_matches"])
        self.assertFalse(parity["has_action_matches"])
        self.assertTrue(parity["expected_mismatch"])
        self.assertEqual("legacy_action_in_compiler_invalid_response", parity["mismatch_kind"])

    def test_output_recovery_compiler_metadata_prefers_snapshot(self):
        snapshot = RuntimeProtocolSemantics(
            source="compiler",
            shape="INVALID",
            is_valid=False,
            error_code="E_TEST_A",
            recovery_id="test_a",
            invalid_kind="snapshot_kind",
            action_count=0,
            has_action=False,
            action_ops=(),
            intent_ops=(),
            visible_text="",
            has_visible_answer=False,
            pre_action_text="",
            has_pre_action_text=False,
            memory_ops=(),
            subgoal_ops=(),
            has_file_content=False,
            file_content="",
            effects_preview=(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            compiler_error_code="E_DIFFERENT",
            invalid_kind="legacy_kind",
        )
        meta = output_recovery_compiler_metadata(parsed_output)
        self.assertEqual("runtime_protocol_semantics", meta["source"])
        self.assertEqual("E_TEST_A", meta["error_code"])
        self.assertEqual("test_a", meta["recovery_id"])
        self.assertEqual("snapshot_kind", meta["invalid_kind"])

    def test_output_recovery_compiler_metadata_fallback_to_parsed_output(self):
        parsed_output = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=None,
            compiler_error_code="E_TEST_B",
            compiler_recovery_id="test_b",
            invalid_kind="legacy_kind",
        )
        meta = output_recovery_compiler_metadata(parsed_output)
        self.assertEqual("parsed_output_compiler_fields", meta["source"])
        self.assertEqual("E_TEST_B", meta["error_code"])
        self.assertEqual("test_b", meta["recovery_id"])
        self.assertEqual("legacy_kind", meta["invalid_kind"])

    def test_output_recovery_compiler_metadata_handles_empty(self):
        parsed_output = ParsedModelOutput(response="", invalid_kind="legacy_kind")
        meta = output_recovery_compiler_metadata(parsed_output)
        self.assertEqual("missing", meta["source"])
        self.assertEqual("", meta["error_code"])
        self.assertEqual("", meta["recovery_id"])
        self.assertEqual("legacy_kind", meta["invalid_kind"])

    def test_output_recovery_compiler_strategy_routing_with_snapshot(self):
        class MockRegistry:
            def __init__(self):
                self.last_call = None

            def resolve(self, *, error_code, recovery_id, invalid_kind):
                self.last_call = {
                    "error_code": error_code,
                    "recovery_id": recovery_id,
                    "invalid_kind": invalid_kind,
                }
                if error_code == "E_ACTION_INSIDE_THINK":
                    return SimpleNamespace(handler_key="malformed_think")
                return None

        class Harness(OutputRecoveryRoutingMixin):
            def __init__(self, registry):
                self.compiler_recovery_registry = registry

            def _compiler_strategy_malformed_think(self, *args, **kwargs):
                return "malformed_think_decision"

        registry = MockRegistry()
        harness = Harness(registry)
        analysis = self.compiler.analyze("<think><action>x</action></think>")
        snapshot = runtime_semantics_from_compiler_analysis(analysis, invalid_kind="action_inside_think")
        parsed_output = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            invalid_kind="action_inside_think",
        )

        decision = harness._compiler_strategy_decision(
            parsed_output,
            invalid_kind="action_inside_think",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertEqual("malformed_think_decision", decision)
        self.assertEqual("E_ACTION_INSIDE_THINK", registry.last_call["error_code"])
        self.assertEqual("action_inside_think", registry.last_call["recovery_id"])

    def test_output_recovery_compiler_strategy_routing_with_fallback(self):
        class MockRegistry:
            def __init__(self):
                self.last_call = None

            def resolve(self, *, error_code, recovery_id, invalid_kind):
                self.last_call = {
                    "error_code": error_code,
                    "recovery_id": recovery_id,
                    "invalid_kind": invalid_kind,
                }
                if error_code == "E_ACTION_INSIDE_THINK":
                    return SimpleNamespace(handler_key="malformed_think")
                return None

        class Harness(OutputRecoveryRoutingMixin):
            def __init__(self, registry):
                self.compiler_recovery_registry = registry

            def _compiler_strategy_malformed_think(self, *args, **kwargs):
                return "malformed_think_decision"

        registry = MockRegistry()
        harness = Harness(registry)
        parsed_output_fallback = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=None,
            compiler_error_code="E_ACTION_INSIDE_THINK",
            compiler_recovery_id="action_inside_think",
            invalid_kind="action_inside_think",
        )
        decision_fallback = harness._compiler_strategy_decision(
            parsed_output_fallback,
            invalid_kind="action_inside_think",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
        self.assertEqual("malformed_think_decision", decision_fallback)
        self.assertEqual("E_ACTION_INSIDE_THINK", registry.last_call["error_code"])
        self.assertEqual("action_inside_think", registry.last_call["recovery_id"])

    def test_output_recovery_compiler_metadata_fallback_to_parsed_output_invalid_kind(self):
        snapshot = RuntimeProtocolSemantics(
            source="compiler",
            shape="INVALID",
            is_valid=False,
            error_code="E_TEST_A",
            recovery_id="test_a",
            invalid_kind="",
            action_count=0,
            has_action=False,
            action_ops=(),
            intent_ops=(),
            visible_text="",
            has_visible_answer=False,
            pre_action_text="",
            has_pre_action_text=False,
            memory_ops=(),
            subgoal_ops=(),
            has_file_content=False,
            file_content="",
            effects_preview=(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            invalid_kind="legacy_kind",
        )
        meta = output_recovery_compiler_metadata(parsed_output)
        self.assertEqual("runtime_protocol_semantics", meta["source"])
        self.assertEqual("legacy_kind", meta["invalid_kind"])

    def test_output_recovery_compiler_strategy_routing_prefers_snapshot_invalid_kind(self):
        class MockRegistry:
            def __init__(self):
                self.last_call = None

            def resolve(self, *, error_code, recovery_id, invalid_kind):
                self.last_call = {
                    "error_code": error_code,
                    "recovery_id": recovery_id,
                    "invalid_kind": invalid_kind,
                }
                if error_code == "E_TEST":
                    return SimpleNamespace(handler_key="test_handler")
                return None

        class Harness(OutputRecoveryRoutingMixin):
            def __init__(self, registry):
                self.compiler_recovery_registry = registry

            def _compiler_strategy_test_handler(self, *args, **kwargs):
                return "test_decision"

        registry = MockRegistry()
        harness = Harness(registry)
        snapshot = RuntimeProtocolSemantics(
            source="compiler",
            shape="INVALID",
            is_valid=False,
            error_code="E_TEST",
            recovery_id="test",
            invalid_kind="snapshot_kind",
            action_count=0,
            has_action=False,
            action_ops=(),
            intent_ops=(),
            visible_text="",
            has_visible_answer=False,
            pre_action_text="",
            has_pre_action_text=False,
            memory_ops=(),
            subgoal_ops=(),
            has_file_content=False,
            file_content="",
            effects_preview=(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            invalid_kind="legacy_kind",
        )

        harness._compiler_strategy_decision(
            parsed_output,
            invalid_kind="legacy_kind",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertEqual("snapshot_kind", registry.last_call["invalid_kind"])

    def test_output_recovery_compiler_strategy_routing_fallback_invalid_kind(self):
        class MockRegistry:
            def __init__(self):
                self.last_call = None

            def resolve(self, *, error_code, recovery_id, invalid_kind):
                self.last_call = {
                    "error_code": error_code,
                    "recovery_id": recovery_id,
                    "invalid_kind": invalid_kind,
                }
                if error_code == "E_TEST":
                    return SimpleNamespace(handler_key="test_handler")
                return None

        class Harness(OutputRecoveryRoutingMixin):
            def __init__(self, registry):
                self.compiler_recovery_registry = registry

            def _compiler_strategy_test_handler(self, *args, **kwargs):
                return "test_decision"

        registry = MockRegistry()
        harness = Harness(registry)
        snapshot = RuntimeProtocolSemantics(
            source="compiler",
            shape="INVALID",
            is_valid=False,
            error_code="E_TEST",
            recovery_id="test",
            invalid_kind="",
            action_count=0,
            has_action=False,
            action_ops=(),
            intent_ops=(),
            visible_text="",
            has_visible_answer=False,
            pre_action_text="",
            has_pre_action_text=False,
            memory_ops=(),
            subgoal_ops=(),
            has_file_content=False,
            file_content="",
            effects_preview=(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            invalid_kind="legacy_kind",
        )

        harness._compiler_strategy_decision(
            parsed_output,
            invalid_kind="legacy_kind",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertEqual("legacy_kind", registry.last_call["invalid_kind"])
