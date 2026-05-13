from dataclasses import dataclass

from modules.agent.orchestration.responses.output_recovery_semantic_record import (
    build_output_recovery_semantic_decision_record,
)


@dataclass(frozen=True)
class DummyStrategy:
    id: str
    handler_key: str
    allowed_next_shapes: tuple[str, ...]


def test_build_output_recovery_semantic_decision_record_for_resolved_strategy():
    record = build_output_recovery_semantic_decision_record(
        decision="compiler_strategy_resolved",
        compiler_meta={
            "source": "runtime_protocol_semantics",
            "error_code": "E_FILE_CONTENT_ACTION_MISMATCH",
            "recovery_id": "file_content_must_follow_action",
            "invalid_kind": "file_content_must_follow_action",
        },
        registry_strategy=DummyStrategy(
            id="file_content_action_mismatch",
            handler_key="file_content_order",
            allowed_next_shapes=("ACTION_ONLY",),
        ),
        reason="file_content_must_follow_action",
        source="compiler_recovery_strategy",
        outcome_kind="continue",
        prompt_family="file_content_order",
        details={"repeat_count": 0},
    )

    out = record.to_dict()

    assert out["domain"] == "output_recovery"
    assert out["stage"] == "output_recovery"
    assert out["decision"] == "compiler_strategy_resolved"
    assert out["reason"] == "file_content_must_follow_action"
    assert out["source"] == "compiler_recovery_strategy"
    assert out["diagnostic_only"] is True
    assert out["authority_affecting"] is False
    assert out["behavior_affecting"] is False
    assert out["compiler_metadata"] == {
        "source": "runtime_protocol_semantics",
        "error_code": "E_FILE_CONTENT_ACTION_MISMATCH",
        "recovery_id": "file_content_must_follow_action",
        "invalid_kind": "file_content_must_follow_action",
    }
    assert out["registry_resolution"] == {
        "resolved": True,
        "strategy_id": "file_content_action_mismatch",
        "handler_key": "file_content_order",
        "allowed_next_shapes": ["ACTION_ONLY"],
    }
    assert out["effective_decision"] == {
        "outcome_kind": "continue",
        "reason": "file_content_must_follow_action",
        "source": "compiler_recovery_strategy",
        "prompt_family": "file_content_order",
    }
    assert out["details"] == {"repeat_count": 0}


def test_build_output_recovery_semantic_decision_record_for_missing_strategy():
    record = build_output_recovery_semantic_decision_record(
        decision="strategy_missing",
        compiler_meta={
            "source": "parsed_output_compiler_fields",
            "error_code": "E_UNKNOWN_TEST",
            "recovery_id": "unknown_recovery",
            "invalid_kind": "unknown_invalid_kind",
        },
        registry_strategy=None,
        source="output_recovery",
        outcome_kind="legacy_fallback",
        prompt_family="",
    )

    out = record.to_dict()

    assert out["reason"] == "unknown_invalid_kind"
    assert out["registry_resolution"] == {
        "resolved": False,
        "strategy_id": "",
        "handler_key": "",
        "allowed_next_shapes": [],
    }
    assert out["effective_decision"]["outcome_kind"] == "legacy_fallback"
    assert out["effective_decision"]["source"] == "output_recovery"


def test_build_output_recovery_semantic_decision_record_accepts_dict_strategy():
    record = build_output_recovery_semantic_decision_record(
        decision="compiler_strategy_resolved",
        compiler_meta={"invalid_kind": "action_payload_array"},
        registry_strategy={
            "id": "action_array",
            "handler_key": "action_array",
            "allowed_next_shapes": ("ACTION_ONLY", "INTENT_ACTION_BUNDLE"),
        },
        outcome_kind="continue",
    )

    out = record.to_dict()

    assert out["registry_resolution"]["resolved"] is True
    assert out["registry_resolution"]["strategy_id"] == "action_array"
    assert out["registry_resolution"]["handler_key"] == "action_array"
    assert out["registry_resolution"]["allowed_next_shapes"] == [
        "ACTION_ONLY",
        "INTENT_ACTION_BUNDLE",
    ]
    assert out["reason"] == "action_payload_array"
