"""Contracts for the supported public API of modules.agent."""

from modules import agent


EXPECTED_PUBLIC_API = (
    "AngelicaAgent",
    "TechnicalInterruption",
)


def test_agent_public_api_is_explicit_and_narrow():
    assert agent.PUBLIC_API == EXPECTED_PUBLIC_API
    assert tuple(agent.__all__) == EXPECTED_PUBLIC_API


def test_agent_public_api_exports_are_resolvable():
    for name in EXPECTED_PUBLIC_API:
        assert getattr(agent, name) is not None
