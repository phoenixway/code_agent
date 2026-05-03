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
