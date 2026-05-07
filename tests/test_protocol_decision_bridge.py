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

    def test_protocol_tag_in_json_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for protocol tags inside JSON strings.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_PROTOCOL_TAG_IN_JSON_STRING",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_action_payload_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_action_payload_not_object_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for non-object action payloads.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_ACTION_PAYLOAD_NOT_OBJECT",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_action_payload_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_action_payload_xml_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for XML-like action payloads.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_ACTION_PAYLOAD_XML_FIELDS",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_action_payload_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_action_payload_tool_code_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for tool_code action payloads.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_ACTION_PAYLOAD_TOOL_CODE",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_action_payload_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_action_inside_think_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for <action> inside <think>.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_ACTION_INSIDE_THINK",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_tag_inside_think_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_intent_inside_think_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for <intent> inside <think>.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_INTENT_INSIDE_THINK",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=0)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_tag_inside_think_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_file_content_inside_think_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for <file_content> inside <think>.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_FILE_CONTENT_INSIDE_THINK",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=0)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_tag_inside_think_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_unclosed_think_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for an unclosed <think> tag.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_UNCLOSED_THINK",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=0)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_unclosed_tag_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_visible_text_after_action_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for E_VISIBLE_TEXT_AFTER_ACTION.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_VISIBLE_TEXT_AFTER_ACTION",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_visible_text_position_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_mixed_visible_text_and_control_is_legacy_authoritative(self):
        """
        The broad E_MIXED_VISIBLE_TEXT_AND_CONTROL is not compiler-authoritative.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("legacy", decision.source)
        self.assertEqual("legacy_default", decision.reason)

    def test_compiler_invalid_kind_for_output_maps_visible_text_after_action(self):
        """
        Tests that compiler_invalid_kind_for_output correctly maps the error code.
        """
        from modules.agent.orchestration.responses.protocol_decision_bridge import compiler_invalid_kind_for_output

        parsed_output = DummyParsedOutput(
            compiler_error_code="E_VISIBLE_TEXT_AFTER_ACTION",
        )
        invalid_kind = compiler_invalid_kind_for_output(parsed_output)
        self.assertEqual("mixed_visible_text_and_control_protocol", invalid_kind)

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


    def test_missing_file_content_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for write_file_block missing file_content.
        """
        parsed_output = DummyParsedOutput(
            compiler_shape="ACTION_ONLY",
            compiler_error_code="E_FILE_CONTENT_REQUIRES_ACTION",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_file_content_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

    def test_unclosed_file_content_is_compiler_authoritative_invalid(self):
        """
        Compiler is authoritative for unclosed file_content.
        """
        parsed_output = DummyParsedOutput(
            compiler_error_code="E_FILE_CONTENT_UNCLOSED",
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        self.assertEqual("compiler", decision.source)
        self.assertEqual("compiler_file_content_diagnostic", decision.reason)
        self.assertFalse(decision.suppress_legacy_invalid_kind)
        self.assertFalse(decision.dispatch_allowed)

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
