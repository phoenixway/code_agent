from modules.agent.orchestration.responses.compiler_recovery_registry import CompilerRecoveryRegistry


def test_registry_resolves_unclosed_think_strategy():
    registry = CompilerRecoveryRegistry()

    strategy = registry.resolve(
        error_code="E_UNCLOSED_THINK",
        recovery_id="unclosed_think",
        invalid_kind="malformed_incomplete_think",
    )

    assert strategy is not None
    assert strategy.handler_key == "malformed_think"
    assert strategy.id == "unclosed_think"


def test_registry_resolves_mixed_intent_transition_visible_answer_strategy():
    registry = CompilerRecoveryRegistry()

    strategy = registry.resolve(
        error_code="E_VISIBLE_TEXT_AFTER_INTENT",
        recovery_id="mixed_intent_transition_and_visible_answer",
        invalid_kind="mixed_intent_transition_and_visible_answer",
    )

    assert strategy is not None
    assert strategy.id == "mixed_intent_transition_visible_answer"
    assert strategy.handler_key == "mixed_intent_transition_visible_answer"


def test_registry_resolves_transition_conflict_strategies():
    registry = CompilerRecoveryRegistry()

    conflicting = registry.resolve(
        error_code="E_MULTIPLE_INTENTS",
        recovery_id="conflicting_intent_transitions",
        invalid_kind="conflicting_intent_transitions",
    )
    complete_with_action = registry.resolve(
        error_code="E_INTENT_COMPLETE_WITH_ACTION",
        recovery_id="intent_complete_with_action_not_allowed",
        invalid_kind="intent_complete_with_action_not_allowed",
    )

    assert conflicting is not None
    assert conflicting.id == "conflicting_intent_transitions"
    assert conflicting.handler_key == "conflicting_intent_transitions"
    assert complete_with_action is not None
    assert complete_with_action.id == "intent_complete_with_action_not_allowed"
    assert complete_with_action.handler_key == "intent_complete_with_action_not_allowed"


def test_registry_resolves_file_content_action_mismatch_strategy():
    registry = CompilerRecoveryRegistry()

    strategy = registry.resolve(
        error_code="E_FILE_CONTENT_ACTION_MISMATCH",
        recovery_id="file_content_must_follow_action",
        invalid_kind="file_content_must_follow_action",
    )

    assert strategy is not None
    assert strategy.id == "file_content_action_mismatch"
    assert strategy.handler_key == "file_content_order"


def test_registry_resolves_action_array_and_multiple_actions_separately():
    registry = CompilerRecoveryRegistry()

    action_array = registry.resolve(
        error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        recovery_id="atomic_bundle_exactly_one_action",
        invalid_kind="action_payload_array",
    )
    multiple = registry.resolve(
        error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        recovery_id="atomic_bundle_exactly_one_action",
        invalid_kind="multiple_actions",
    )

    assert action_array is not None
    assert action_array.handler_key == "action_array"
    assert multiple is not None
    assert multiple.handler_key == "multiple_actions"
