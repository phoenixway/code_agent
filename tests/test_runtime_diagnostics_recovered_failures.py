from types import SimpleNamespace

from modules.agent.orchestration.trace_export import OrchestrationTraceExporter


def _state(*, journal, last_error_code="NOT_FOUND", last_error_recoverable=True):
    return SimpleNamespace(
        last_error_code=last_error_code,
        last_error_recoverable=last_error_recoverable,
        consecutive_same_error_count=1,
        last_failed_action_command={
            "type": "extract_symbol",
            "path": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "symbol_name": "onProjectViewChange",
            "symbol_kind": "method",
            "container_name": "ContextScreenViewModel",
        },
        last_failed_action_result={
            "status": "error",
            "error_code": last_error_code,
            "recoverable": last_error_recoverable,
            "output": "Symbol 'onProjectViewChange' not found in container 'ContextScreenViewModel'.",
        },
        last_execution_plan=None,
        last_execution_commit=None,
        operational_journal=list(journal),
        orchestration_trace=[],
    )


def test_runtime_diagnostics_marks_recoverable_failure_resolved_by_later_same_action_success():
    journal = [
        {
            "sequence": 11,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": False,
            "system_result_recorded": True,
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "system_result_excerpt": "SYSTEM RESULT for `extract_symbol`: NOT_FOUND onProjectViewChange",
        },
        {
            "sequence": 12,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": True,
            "system_result_recorded": True,
            "system_result_excerpt": (
                "SYSTEM RESULT for `extract_symbol`: Extracted Kotlin function "
                "'onProjectViewChange' at lines 732-737."
            ),
        },
    ]

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(_state(journal=journal))

    # Legacy state is still preserved for compatibility/readback.
    assert diagnostics["last_error_code"] == "NOT_FOUND"
    assert diagnostics["last_error_recoverable"] is True

    # New fields distinguish historical failure from current blocker.
    assert diagnostics["last_failed_action_error_code"] == "NOT_FOUND"
    assert diagnostics["last_failed_action_recoverable"] is True
    assert diagnostics["last_error_resolved"] is True
    assert diagnostics["resolved_by_sequence"] == 12
    assert diagnostics["current_blocker"] is None
    assert diagnostics["last_unresolved_error_code"] is None


def test_runtime_diagnostics_keeps_unresolved_failure_as_current_blocker_without_later_success():
    journal = [
        {
            "sequence": 11,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": False,
            "system_result_recorded": True,
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "system_result_excerpt": "SYSTEM RESULT for `extract_symbol`: NOT_FOUND onProjectViewChange",
        },
    ]

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(_state(journal=journal))

    assert diagnostics["last_failed_action_error_code"] == "NOT_FOUND"
    assert diagnostics["last_failed_action_recoverable"] is True
    assert diagnostics["last_error_resolved"] is False
    assert diagnostics["resolved_by_sequence"] is None
    assert diagnostics["last_unresolved_error_code"] == "NOT_FOUND"
    assert diagnostics["current_blocker"] == {
        "sequence": 11,
        "action_type": "extract_symbol",
        "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
        "error_code": "NOT_FOUND",
        "recoverable": True,
    }


def test_runtime_diagnostics_unrelated_later_success_does_not_resolve_failure():
    journal = [
        {
            "sequence": 11,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": False,
            "system_result_recorded": True,
            "error_code": "NOT_FOUND",
            "recoverable": True,
        },
        {
            "sequence": 12,
            "kind": "tool_execution_commit",
            "action_type": "search_content",
            "target": ".",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": True,
            "system_result_recorded": True,
        },
    ]

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(_state(journal=journal))

    assert diagnostics["last_error_resolved"] is False
    assert diagnostics["resolved_by_sequence"] is None
    assert diagnostics["last_unresolved_error_code"] == "NOT_FOUND"
    assert diagnostics["current_blocker"]["sequence"] == 11
    assert diagnostics["current_blocker"]["action_type"] == "extract_symbol"


def test_runtime_diagnostics_has_no_current_blocker_without_failure_state_or_failed_journal_entry():
    state = SimpleNamespace(
        last_error_code=None,
        last_error_recoverable=None,
        consecutive_same_error_count=0,
        last_failed_action_command=None,
        last_failed_action_result=None,
        last_execution_plan=None,
        last_execution_commit=None,
        operational_journal=[
            {
                "sequence": 4,
                "kind": "tool_execution_commit",
                "action_type": "read_file",
                "target": "README.md",
                "tool_execution_attempted": True,
                "tool_execution_succeeded": True,
                "system_result_recorded": True,
            }
        ],
        orchestration_trace=[],
    )

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)

    assert diagnostics["last_failed_action_error_code"] is None
    assert diagnostics["last_failed_action_recoverable"] is None
    assert diagnostics["last_error_resolved"] is False
    assert diagnostics["resolved_by_sequence"] is None
    assert diagnostics["current_blocker"] is None
    assert diagnostics["last_unresolved_error_code"] is None


def test_runtime_diagnostics_same_file_different_extract_symbol_success_does_not_resolve_failure():
    journal = [
        {
            "sequence": 11,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": False,
            "system_result_recorded": True,
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "symbol_name": "onProjectViewChange",
            "container_name": "ContextScreenViewModel",
            "system_result_excerpt": "SYSTEM RESULT for `extract_symbol`: NOT_FOUND onProjectViewChange",
        },
        {
            "sequence": 12,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": True,
            "system_result_recorded": True,
            "symbol_name": "helper",
            "container_name": "ContextScreenViewModel",
            "system_result_excerpt": "SYSTEM RESULT for `extract_symbol`: Extracted Kotlin function 'helper'.",
        },
    ]

    state = _state(journal=journal)
    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)

    assert diagnostics["last_error_resolved"] is False
    assert diagnostics["resolved_by_sequence"] is None
    assert diagnostics["last_unresolved_error_code"] == "NOT_FOUND"
    assert diagnostics["current_blocker"]["sequence"] == 11
    assert diagnostics["current_blocker"]["action_type"] == "extract_symbol"
    assert diagnostics["current_blocker"]["target"] == "app/src/main/java/com/example/ContextScreenViewModel.kt"


def test_runtime_diagnostics_same_file_same_extract_symbol_success_resolves_failure():
    journal = [
        {
            "sequence": 11,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": False,
            "system_result_recorded": True,
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "symbol_name": "onProjectViewChange",
            "symbol_kind": "method",
            "container_name": "ContextScreenViewModel",
            "system_result_excerpt": "SYSTEM RESULT for `extract_symbol`: NOT_FOUND onProjectViewChange",
        },
        {
            "sequence": 12,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": True,
            "system_result_recorded": True,
            "symbol_name": "onProjectViewChange",
            "symbol_kind": "function",
            "container_name": "ContextScreenViewModel",
            "system_result_excerpt": (
                "SYSTEM RESULT for `extract_symbol`: Extracted Kotlin function "
                "'onProjectViewChange' at lines 732-737."
            ),
        },
    ]

    state = _state(journal=journal)
    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)

    assert diagnostics["last_error_resolved"] is True
    assert diagnostics["resolved_by_sequence"] == 12
    assert diagnostics["current_blocker"] is None
    assert diagnostics["last_unresolved_error_code"] is None


def test_runtime_diagnostics_same_symbol_different_container_success_does_not_resolve_failure():
    journal = [
        {
            "sequence": 11,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": False,
            "system_result_recorded": True,
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "symbol_name": "onProjectViewChange",
            "container_name": "ContextScreenViewModel",
        },
        {
            "sequence": 12,
            "kind": "tool_execution_commit",
            "action_type": "extract_symbol",
            "target": "app/src/main/java/com/example/ContextScreenViewModel.kt",
            "tool_execution_attempted": True,
            "tool_execution_succeeded": True,
            "system_result_recorded": True,
            "symbol_name": "onProjectViewChange",
            "container_name": "OtherViewModel",
        },
    ]

    state = _state(journal=journal)
    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)

    assert diagnostics["last_error_resolved"] is False
    assert diagnostics["resolved_by_sequence"] is None
    assert diagnostics["last_unresolved_error_code"] == "NOT_FOUND"
    assert diagnostics["current_blocker"]["sequence"] == 11
