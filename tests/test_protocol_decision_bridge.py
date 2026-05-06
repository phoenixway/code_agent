import unittest
from types import SimpleNamespace

from modules.agent.orchestration.responses.protocol_decision_bridge import resolve_protocol_authority


class DummyParsedOutput:
    def __init__(self, **kwargs):
        self.invalid_kind = ""
        self.compiler_shape = ""
        self.compiler_error_code = ""
        self.has_action_segment = False
        self.compiler_ir = None
        self.__dict__.update(kwargs)


class ProtocolDecisionBridgeTests(unittest.TestCase):
    def test_simple_pre_action_text_and_action_is_compiler_authoritative(self):
        """
        Compiler is authoritative for simple pre-action text + action,
        suppressing legacy 'mixed_visible_text_and_control_protocol'.
        """
        parsed_output = DummyParsedOutput(
            invalid_kind="mixed_visible_text_and_control_protocol",
            compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
            has_action_segment=True,
            compiler_ir=SimpleNamespace(
                action_count=1,
                has_think=False,
                has_checkpoint=False,
            ),
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_valid_pre_action_text", decision.reason)
        self.assertTrue(decision.suppress_legacy_invalid_kind)
        self.assertTrue(decision.dispatch_allowed)

    def test_pre_action_text_with_think_is_legacy_authoritative(self):
        """
        If compiler sees <think> alongside pre-action text, it is not
        authoritative, and legacy recovery for mixed protocol should apply.
        """
        parsed_output = DummyParsedOutput(
            invalid_kind="mixed_visible_text_and_control_protocol",
            compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
            has_action_segment=True,
            compiler_ir=SimpleNamespace(
                action_count=1,
                has_think=True,  # The key difference
                has_checkpoint=False,
            ),
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("legacy", decision.source)
        self.assertFalse(decision.suppress_legacy_invalid_kind)

    def test_plaintext_only_is_legacy_authoritative(self):
        """
        Compiler is not yet authoritative for PLAINTEXT_ONLY, so legacy
        'missing_action_or_answer' recovery should apply.
        """
        parsed_output = DummyParsedOutput(
            invalid_kind="missing_action_or_answer",
            compiler_shape="PLAINTEXT_ONLY",
            has_action_segment=False,
            compiler_ir=SimpleNamespace(
                action_count=0,
                has_visible_answer=True,
            ),
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=0)
        self.assertEqual("legacy", decision.source)
        self.assertFalse(decision.suppress_legacy_invalid_kind)

    def test_action_payload_array_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for structural action payload errors.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_ACTION_PAYLOAD_ARRAY",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_action_payload_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_unknown_compiler_data_is_legacy_default(self):
        """
        If compiler provides no specific shape or error, legacy is default.
        """
        parsed_output = DummyParsedOutput()
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=0)
        self.assertEqual("legacy", decision.source)
        self.assertEqual("legacy_default", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertIsNone(decision.dispatch_allowed)

    def test_action_only_is_legacy_authoritative_for_now(self):
        """
        A valid ACTION_ONLY shape with no compiler error still falls back
        to legacy authority, because it may have legacy policy violations.
        """
        parsed_output = DummyParsedOutput(
            compiler_shape="ACTION_ONLY",
            has_action_segment=True,
            compiler_ir=SimpleNamespace(
                action_count=1,
                has_think=False,
                has_checkpoint=False,
            ),
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("legacy", decision.source)
        self.assertFalse(decision.suppress_legacy_invalid_kind)


if __name__ == "__main__":
    unittest.main()
