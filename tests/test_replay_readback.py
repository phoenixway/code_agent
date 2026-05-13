import json

from modules.agent.orchestration.replay_readback import summarize_semantic_decision_records


def _semantic_record(**overrides):
    record = {
        "domain": "output_recovery",
        "stage": "output_recovery",
        "decision": "compiler_strategy_resolved",
        "reason": "file_content_must_follow_action",
        "source": "compiler_recovery_strategy",
        "diagnostic_only": True,
        "authority_affecting": False,
        "behavior_affecting": False,
    }
    record.update(overrides)
    return record


def test_replay_readback_summarizes_trace_snapshot_list():
    trace = [
        {
            "sequence": 1,
            "stage": "output_recovery",
            "decision": "diagnostic",
            "fields": {
                "semantic_decision_record": _semantic_record(),
            },
        }
    ]

    summary = summarize_semantic_decision_records(trace)
    out = summary.to_dict()

    assert out["record_count"] == 1
    assert out["trace_entry_count"] == 1
    assert out["skipped_malformed_count"] == 0
    assert out["domains"] == ["output_recovery"]
    assert out["stages"] == ["output_recovery"]
    assert out["decisions"] == ["compiler_strategy_resolved"]
    assert out["reasons"] == ["file_content_must_follow_action"]
    assert out["sources"] == ["compiler_recovery_strategy"]
    assert out["diagnostic_only_count"] == 1
    assert out["authority_affecting_count"] == 0
    assert out["behavior_affecting_count"] == 0
    assert out["items"][0]["sequence"] == 1
    assert out["items"][0]["trace_decision"] == "diagnostic"


def test_replay_readback_accepts_runtime_artifacts_dict():
    artifacts = {
        "last_execution_plan": None,
        "orchestration_trace": [
            {
                "sequence": 2,
                "stage": "output_recovery",
                "decision": "diagnostic",
                "fields": {
                    "semantic_decision_record": _semantic_record(
                        decision="strategy_missing",
                        reason="unknown_invalid_kind",
                        source="output_recovery",
                    ),
                },
            }
        ],
    }

    summary = summarize_semantic_decision_records(artifacts)
    out = summary.to_dict()

    assert out["record_count"] == 1
    assert out["decisions"] == ["strategy_missing"]
    assert out["reasons"] == ["unknown_invalid_kind"]
    assert out["sources"] == ["output_recovery"]
    assert out["items"][0]["sequence"] == 2


def test_replay_readback_skips_missing_and_malformed_semantic_records():
    trace = [
        {"sequence": 1, "stage": "response_pipeline", "decision": "pass", "fields": {}},
        {
            "sequence": 2,
            "stage": "output_recovery",
            "decision": "diagnostic",
            "fields": {"semantic_decision_record": "not-a-dict"},
        },
        {
            "sequence": 3,
            "stage": "output_recovery",
            "decision": "diagnostic",
            "fields": {"semantic_decision_record": _semantic_record()},
        },
    ]

    summary = summarize_semantic_decision_records(trace)
    out = summary.to_dict()

    assert out["trace_entry_count"] == 3
    assert out["record_count"] == 1
    assert out["skipped_malformed_count"] == 1


def test_replay_readback_summarizes_diagnostic_safety_flags():
    trace = [
        {
            "sequence": 1,
            "stage": "output_recovery",
            "decision": "diagnostic",
            "fields": {"semantic_decision_record": _semantic_record()},
        },
        {
            "sequence": 2,
            "stage": "terminal_answer",
            "decision": "diagnostic",
            "fields": {
                "semantic_decision_record": _semantic_record(
                    domain="terminal_answer",
                    stage="terminal_answer",
                    decision="legacy_fallback",
                    diagnostic_only=False,
                    authority_affecting=True,
                    behavior_affecting=True,
                )
            },
        },
    ]

    summary = summarize_semantic_decision_records(trace)
    out = summary.to_dict()

    assert out["record_count"] == 2
    assert out["domains"] == ["output_recovery", "terminal_answer"]
    assert out["diagnostic_only_count"] == 1
    assert out["authority_affecting_count"] == 1
    assert out["behavior_affecting_count"] == 1


def test_replay_readback_summary_is_json_serializable():
    summary = summarize_semantic_decision_records(
        [
            {
                "sequence": 1,
                "stage": "output_recovery",
                "decision": "diagnostic",
                "fields": {"semantic_decision_record": _semantic_record()},
            }
        ]
    )

    encoded = json.dumps(summary.to_dict(), sort_keys=True)

    assert "compiler_strategy_resolved" in encoded
    assert "output_recovery" in encoded
