from types import SimpleNamespace

import pytest

from modules.agent.orchestration.responses.runtime_protocol_semantics import (
    output_recovery_compiler_metadata,
)
from modules.agent.orchestration.responses.semantic_accessors import get_compiler_metadata


@pytest.mark.parametrize(
    "parsed_output",
    [
        pytest.param(
            SimpleNamespace(
                invalid_kind="missing_action_or_answer",
            ),
            id="legacy_invalid_kind_only",
        ),
        pytest.param(
            SimpleNamespace(
                compiler_error_code="E_MALFORMED_ACTION_JSON",
                compiler_recovery_id="malformed_action_json",
                invalid_kind="malformed_action",
            ),
            id="compiler_metadata_with_legacy_invalid_kind",
        ),
        pytest.param(
            SimpleNamespace(
                compiler_error_code="",
                compiler_recovery_id="",
                invalid_kind="",
            ),
            id="empty_metadata",
        ),
    ],
)
def test_get_compiler_metadata_matches_output_recovery_helper_for_legacy_fallbacks(parsed_output):
    """Characterizes parity before consolidating the deprecated output-recovery helper."""
    assert get_compiler_metadata(parsed_output) == output_recovery_compiler_metadata(parsed_output)
