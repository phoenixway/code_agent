"""
Tests for the protocol authority decision bridge.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

# Add project root to path to allow imports of 'modules'
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from modules.agent.orchestration.responses.protocol_decision_bridge import resolve_protocol_authority


def test_pre_action_text_override():
    """Compiler is authoritative for valid PRE_ACTION_TEXT_AND_ACTION."""
    parsed_output = SimpleNamespace(
        invalid_kind="mixed_visible_text_and_control_protocol",
        compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
        compiler_error_code="",
        has_action_segment=True,
    )
    decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
    assert decision.source == "compiler"
    assert decision.reason == "compiler_valid_pre_action_text"
    assert decision.suppress_legacy_invalid_kind is True
    assert decision.dispatch_allowed is True


def test_pre_action_text_with_compiler_error_is_not_overridden():
    """Legacy remains authoritative if compiler finds an error."""
    parsed_output = SimpleNamespace(
        invalid_kind="mixed_visible_text_and_control_protocol",
        compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
        compiler_error_code="E_SOME_ERROR",
        has_action_segment=True,
    )
    decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
    assert decision.source == "legacy"
    assert decision.reason == "legacy_default"
    assert decision.suppress_legacy_invalid_kind is False
    assert decision.dispatch_allowed is None


def test_compiler_authoritative_for_action_payload_errors():
    """Compiler is authoritative for specific action payload errors."""
    error_codes = [
        "E_ACTION_PAYLOAD_ARRAY",
        "E_ACTION_PAYLOAD_NOT_OBJECT",
        "E_ACTION_PAYLOAD_XML_FIELDS",
        "E_ACTION_PAYLOAD_TOOL_CODE",
        "E_PROTOCOL_TAG_IN_JSON_STRING",
    ]
    for code in error_codes:
        parsed_output = SimpleNamespace(
            invalid_kind="",
            compiler_shape="INVALID",
            compiler_error_code=code,
            has_action_segment=True,
        )
        decision = resolve_protocol_authority(parsed_output, parsed_action_count=1)
        assert decision.source == "compiler"
        assert decision.reason == "compiler_action_payload_diagnostic"
        assert decision.suppress_legacy_invalid_kind is False
        assert decision.dispatch_allowed is False


def test_fallback_to_legacy_by_default():
    """The default authority is legacy."""
    # Case 1: No compiler info
    parsed_output_1 = SimpleNamespace(
        invalid_kind="some_legacy_error",
        compiler_shape="",
        compiler_error_code="",
        has_action_segment=False,
    )
    decision_1 = resolve_protocol_authority(parsed_output_1, parsed_action_count=0)
    assert decision_1.source == "legacy"
    assert decision_1.reason == "legacy_default"

    # Case 2: Compiler is clean, but legacy finds an issue not in the matrix
    parsed_output_2 = SimpleNamespace(
        invalid_kind="another_legacy_error",
        compiler_shape="ACTION_ONLY",
        compiler_error_code="",
        has_action_segment=True,
    )
    decision_2 = resolve_protocol_authority(parsed_output_2, parsed_action_count=1)
    assert decision_2.source == "legacy"
    assert decision_2.reason == "legacy_default"
