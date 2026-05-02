"""Contracts for supported orchestration public API surfaces."""

from modules.agent import orchestration


EXPECTED_PUBLIC_API = (
    "IntentResponseParser",
    "IntentTransitionHandler",
    "LoopContext",
    "ModelOutputRecoveryHandler",
    "ModelResponsePipeline",
    "Orchestrator",
    "OrchestratorPromptBuilder",
)


def test_root_public_api_is_explicit_and_narrow():
    assert orchestration.PUBLIC_API == EXPECTED_PUBLIC_API
    assert tuple(orchestration.__all__) == EXPECTED_PUBLIC_API


def test_root_public_api_exports_are_resolvable():
    for name in EXPECTED_PUBLIC_API:
        assert getattr(orchestration, name) is not None


def test_root_package_does_not_claim_semantic_subpackages_as_public_api():
    forbidden = {"runtime", "prompts", "parsers", "responses", "transitions", "shared"}
    assert forbidden.isdisjoint(set(orchestration.__all__))
