from types import SimpleNamespace

from modules.agent.orchestration.runtime.dependencies import RuntimeCollaborators


def test_runtime_collaborators_from_agent_collects_only_requested_dependencies():
    agent = SimpleNamespace(
        state="state",
        history="history",
        config="config",
        ui="ui",
        log="log",
        action_dispatcher="dispatcher",
    )

    runtime = RuntimeCollaborators.from_agent(
        agent,
        needs_history=True,
        needs_config=True,
        needs_dispatcher=True,
    )

    assert runtime.state == "state"
    assert runtime.history == "history"
    assert runtime.config == "config"
    assert runtime.ui == "ui"
    assert runtime.logger == "log"
    assert runtime.dispatcher == "dispatcher"


def test_runtime_collaborators_omit_optional_dependencies_when_not_requested():
    agent = SimpleNamespace(
        state="state",
        history="history",
        config="config",
        ui="ui",
        log="log",
        action_dispatcher="dispatcher",
    )

    runtime = RuntimeCollaborators.from_agent(agent)

    assert runtime.state == "state"
    assert runtime.history is None
    assert runtime.config is None
    assert runtime.dispatcher is None
    assert runtime.ui == "ui"
    assert runtime.logger == "log"
