import json

from modules.agent.orchestration.responses.semantic_decision_record import (
    AuthorityResolutionSnapshot,
    CompilerMetadataSnapshot,
    EffectiveDecisionSnapshot,
    RegistryResolutionSnapshot,
    SemanticDecisionRecord,
)


def test_semantic_decision_record_defaults_are_diagnostic_safe():
    record = SemanticDecisionRecord(
        domain="output_recovery",
        stage="output_recovery",
        decision="compiler_strategy_resolved",
    )

    assert record.diagnostic_only is True
    assert record.authority_affecting is False
    assert record.behavior_affecting is False

    out = record.to_dict()
    assert out["domain"] == "output_recovery"
    assert out["stage"] == "output_recovery"
    assert out["decision"] == "compiler_strategy_resolved"
    assert "compiler_metadata" not in out
    assert "registry_resolution" not in out
    assert "effective_decision" not in out
    assert "authority_resolution" not in out


def test_semantic_decision_record_represents_compiler_registry_and_effective_decision():
    record = SemanticDecisionRecord(
        domain="output_recovery",
        stage="output_recovery",
        decision="continue",
        reason="file_content_must_follow_action",
        source="compiler_recovery_strategy",
        compiler_metadata=CompilerMetadataSnapshot(
            error_code="E_FILE_CONTENT_ACTION_MISMATCH",
            recovery_id="file_content_must_follow_action",
            invalid_kind="file_content_must_follow_action",
            source="runtime_protocol_semantics",
        ),
        registry_resolution=RegistryResolutionSnapshot(
            resolved=True,
            strategy_id="file_content_action_mismatch",
            handler_key="file_content_order",
            allowed_next_shapes=("ACTION_ONLY",),
        ),
        effective_decision=EffectiveDecisionSnapshot(
            outcome_kind="continue",
            reason="file_content_must_follow_action",
            source="compiler_recovery_strategy",
            prompt_family="file_content_order",
        ),
        details={"note": "passive record only"},
    )

    out = record.to_dict()

    assert out["reason"] == "file_content_must_follow_action"
    assert out["source"] == "compiler_recovery_strategy"
    assert out["compiler_metadata"] == {
        "error_code": "E_FILE_CONTENT_ACTION_MISMATCH",
        "recovery_id": "file_content_must_follow_action",
        "invalid_kind": "file_content_must_follow_action",
        "source": "runtime_protocol_semantics",
    }
    assert out["registry_resolution"] == {
        "resolved": True,
        "strategy_id": "file_content_action_mismatch",
        "handler_key": "file_content_order",
        "allowed_next_shapes": ["ACTION_ONLY"],
    }
    assert out["effective_decision"]["prompt_family"] == "file_content_order"
    assert out["details"] == {"note": "passive record only"}


def test_semantic_decision_record_can_include_authority_resolution_snapshot():
    record = SemanticDecisionRecord(
        domain="terminal_answer",
        stage="post_classification",
        decision="legacy_fallback",
        authority_resolution=AuthorityResolutionSnapshot(
            branch="terminal_answer.plaintext_terminal_answer",
            switch_value="legacy",
            authority_source="legacy",
            selected_by_switch=False,
            fallback_reason="switch_not_enabled",
        ),
    )

    out = record.to_dict()

    assert out["authority_resolution"] == {
        "branch": "terminal_answer.plaintext_terminal_answer",
        "switch_value": "legacy",
        "authority_source": "legacy",
        "selected_by_switch": False,
        "fallback_reason": "switch_not_enabled",
    }


def test_semantic_decision_record_to_dict_is_json_serializable():
    record = SemanticDecisionRecord(
        domain="output_recovery",
        stage="output_recovery",
        decision="strategy_missing",
        registry_resolution=RegistryResolutionSnapshot(
            resolved=False,
            allowed_next_shapes=("PLAINTEXT_ONLY", "ACTION_ONLY"),
        ),
        details={"attempt": 1, "safe": True, "tags": ["semantic", "diagnostic"]},
    )

    encoded = json.dumps(record.to_dict(), sort_keys=True)

    assert "strategy_missing" in encoded
    assert "PLAINTEXT_ONLY" in encoded
