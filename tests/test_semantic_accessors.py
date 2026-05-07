"""Unit tests for semantic_accessors.py."""

import unittest
from dataclasses import dataclass, field, replace
from typing import Any

from modules.agent.orchestration.responses.runtime_protocol_semantics import RuntimeProtocolSemantics
from modules.agent.orchestration.responses.semantic_accessors import (
    get_compiler_metadata,
    has_any_action_proposal_compat,
    is_compiler_invalid,
    is_compiler_invalid_with_legacy_action,
)
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


# Minimal test doubles for nested objects
@dataclass
class _MockOp:
    kind: str


@dataclass
class _MockCompilerIR:
    action_ops: tuple[Any, ...] = ()


class SemanticAccessorTests(unittest.TestCase):
    """Tests for the initial set of semantic accessors."""

    def _empty_snapshot(self) -> RuntimeProtocolSemantics:
        return RuntimeProtocolSemantics(
            source="test",
            shape="",
            is_valid=False,
            error_code="",
            recovery_id="",
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

    # --- Tests for get_compiler_metadata ---

    def test_get_compiler_metadata_from_snapshot(self):
        """Tests that metadata is read from RuntimeProtocolSemantics when present."""
        snapshot = replace(self._empty_snapshot(), error_code="E1", recovery_id="R1", invalid_kind="K1")
        p_out = ParsedModelOutput(response="", runtime_protocol_semantics=snapshot)

        meta = get_compiler_metadata(p_out)

        self.assertEqual(meta["source"], "runtime_protocol_semantics")
        self.assertEqual(meta["error_code"], "E1")
        self.assertEqual(meta["recovery_id"], "R1")
        self.assertEqual(meta["invalid_kind"], "K1")

    def test_get_compiler_metadata_snapshot_overrides_legacy_invalid_kind(self):
        """Tests that snapshot invalid_kind takes precedence over legacy field."""
        snapshot = replace(self._empty_snapshot(), invalid_kind="snapshot_kind")
        p_out = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            invalid_kind="legacy_kind",
        )
        meta = get_compiler_metadata(p_out)
        self.assertEqual(meta["invalid_kind"], "snapshot_kind")

    def test_get_compiler_metadata_snapshot_uses_legacy_invalid_kind_if_blank(self):
        """Tests that legacy invalid_kind is used if snapshot's is blank."""
        snapshot = replace(self._empty_snapshot(), invalid_kind="")
        p_out = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=snapshot,
            invalid_kind="legacy_kind",
        )
        meta = get_compiler_metadata(p_out)
        self.assertEqual(meta["invalid_kind"], "legacy_kind")

    def test_get_compiler_metadata_fallback_to_legacy_fields(self):
        """Tests fallback to parsed_output.compiler_* fields when snapshot is missing."""
        p_out = ParsedModelOutput(
            response="",
            runtime_protocol_semantics=None,
            compiler_error_code="E2",
            compiler_recovery_id="R2",
            invalid_kind="K2",
        )

        meta = get_compiler_metadata(p_out)

        self.assertEqual(meta["source"], "parsed_output_compiler_fields")
        self.assertEqual(meta["error_code"], "E2")
        self.assertEqual(meta["recovery_id"], "R2")
        self.assertEqual(meta["invalid_kind"], "K2")

    def test_get_compiler_metadata_missing_data_preserves_legacy_invalid_kind(self):
        """Tests that legacy invalid_kind is preserved when no compiler data exists."""
        p_out = ParsedModelOutput(response="", invalid_kind="only_legacy")
        meta = get_compiler_metadata(p_out)
        self.assertEqual(meta["source"], "missing")
        self.assertEqual(meta["error_code"], "")
        self.assertEqual(meta["recovery_id"], "")
        self.assertEqual(meta["invalid_kind"], "only_legacy")

    def test_get_compiler_metadata_with_none_input(self):
        """Tests that None input is handled gracefully."""
        meta = get_compiler_metadata(None)
        self.assertEqual(meta["source"], "missing")
        self.assertEqual(meta["error_code"], "")
        self.assertEqual(meta["recovery_id"], "")
        self.assertEqual(meta["invalid_kind"], "")

    # --- Tests for has_any_action_proposal_compat ---

    def test_has_any_action_proposal_true_from_legacy_count(self):
        """Returns True if parsed_action_count > 0."""
        p_out = ParsedModelOutput(response="")
        # This accessor does not grant dispatch permission. It is for recovery evidence.
        self.assertTrue(has_any_action_proposal_compat(p_out, parsed_action_count=1))

    def test_has_any_action_proposal_true_from_compiler_ir(self):
        """Returns True if compiler_ir.action_ops is non-empty (critical shim)."""
        p_out = ParsedModelOutput(response="", compiler_ir=_MockCompilerIR(action_ops=(_MockOp("tool"),)))
        # This accessor does not grant dispatch permission. It is for recovery evidence.
        self.assertTrue(has_any_action_proposal_compat(p_out))

    def test_has_any_action_proposal_true_from_legacy_segment(self):
        """Returns True if has_action_segment is True."""
        p_out = ParsedModelOutput(response="", has_action_segment=True)
        # This accessor does not grant dispatch permission. It is for recovery evidence.
        self.assertTrue(has_any_action_proposal_compat(p_out))

    def test_has_any_action_proposal_false_when_no_evidence(self):
        """Returns False if there is no evidence of an action proposal."""
        p_out = ParsedModelOutput(response="")
        self.assertFalse(has_any_action_proposal_compat(p_out, parsed_action_count=0))

    def test_has_any_action_proposal_with_none_input(self):
        """Tests that None input is handled gracefully."""
        self.assertFalse(has_any_action_proposal_compat(None))

    # --- Tests for is_compiler_invalid ---

    def test_is_compiler_invalid_true_from_snapshot(self):
        """Returns True if snapshot.is_valid is False."""
        snapshot = replace(self._empty_snapshot(), is_valid=False)
        p_out = ParsedModelOutput(response="", runtime_protocol_semantics=snapshot)
        self.assertTrue(is_compiler_invalid(p_out))

    def test_is_compiler_invalid_true_from_legacy_shape(self):
        """Returns True on fallback to compiler_shape == 'INVALID'."""
        p_out = ParsedModelOutput(response="", compiler_shape="INVALID")
        self.assertTrue(is_compiler_invalid(p_out))

    def test_is_compiler_invalid_true_from_legacy_error_code(self):
        """Returns True on fallback to a non-empty compiler_error_code."""
        p_out = ParsedModelOutput(response="", compiler_error_code="some_error")
        self.assertTrue(is_compiler_invalid(p_out))

    def test_is_compiler_invalid_false_when_valid(self):
        """Returns False if the response is valid according to compiler data."""
        snapshot = replace(self._empty_snapshot(), is_valid=True)
        p_out = ParsedModelOutput(response="", runtime_protocol_semantics=snapshot)
        self.assertFalse(is_compiler_invalid(p_out))

    def test_is_compiler_invalid_false_when_no_compiler_data(self):
        """Returns False if no compiler information is available at all."""
        p_out = ParsedModelOutput(response="")
        self.assertFalse(is_compiler_invalid(p_out))

    def test_is_compiler_invalid_with_none_input(self):
        """Tests that None input is handled gracefully."""
        self.assertFalse(is_compiler_invalid(None))

    # --- Tests for is_compiler_invalid_with_legacy_action ---

    def test_is_compiler_invalid_with_legacy_action_true_for_core_invariant(self):
        """Returns True for compiler-invalid response with any action proposal."""
        # This is the core safety invariant: compiler says INVALID, but some
        # parser found an action. This content is recovery evidence only.
        p_out_invalid = ParsedModelOutput(response="", compiler_shape="INVALID")

        # Test with each kind of action proposal
        self.assertTrue(
            is_compiler_invalid_with_legacy_action(p_out_invalid, parsed_action_count=1),
            "Failed with parsed_action_count",
        )

        p_out_with_ir = replace(p_out_invalid, compiler_ir=_MockCompilerIR(action_ops=(_MockOp("tool"),)))
        self.assertTrue(
            is_compiler_invalid_with_legacy_action(p_out_with_ir),
            "Failed with compiler_ir.action_ops",
        )

        p_out_with_segment = replace(p_out_invalid, has_action_segment=True)
        self.assertTrue(
            is_compiler_invalid_with_legacy_action(p_out_with_segment),
            "Failed with has_action_segment",
        )

    def test_is_compiler_invalid_with_legacy_action_false_if_compiler_valid(self):
        """Returns False if the compiler did not find the response invalid."""
        snapshot = replace(self._empty_snapshot(), is_valid=True)
        p_out_valid = ParsedModelOutput(response="", runtime_protocol_semantics=snapshot)
        self.assertFalse(is_compiler_invalid_with_legacy_action(p_out_valid, parsed_action_count=1))

    def test_is_compiler_invalid_with_legacy_action_false_if_no_action(self):
        """Returns False if there is no action proposal, even if compiler-invalid."""
        p_out_invalid = ParsedModelOutput(response="", compiler_shape="INVALID")
        self.assertFalse(is_compiler_invalid_with_legacy_action(p_out_invalid, parsed_action_count=0))

    def test_is_compiler_invalid_with_legacy_action_with_none_input(self):
        """Tests that None input is handled gracefully."""
        self.assertFalse(is_compiler_invalid_with_legacy_action(None))


if __name__ == "__main__":
    unittest.main()
