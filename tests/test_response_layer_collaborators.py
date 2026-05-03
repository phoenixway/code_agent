from types import SimpleNamespace

from modules.agent.orchestration.responses.dependencies import ResponseLayerCollaborators


def test_response_layer_collaborators_from_agent_collects_requested_fields():
    agent = SimpleNamespace(
        state="state",
        config="config",
        ui="ui",
        log="log",
    )

    collaborators = ResponseLayerCollaborators.from_agent(agent, needs_config=True)

    assert collaborators.state == "state"
    assert collaborators.config == "config"
    assert collaborators.ui == "ui"
    assert collaborators.logger == "log"


def test_response_layer_collaborators_can_omit_config():
    agent = SimpleNamespace(
        state="state",
        config="config",
        ui="ui",
        log="log",
    )

    collaborators = ResponseLayerCollaborators.from_agent(agent)

    assert collaborators.state == "state"
    assert collaborators.config is None
    assert collaborators.ui == "ui"
    assert collaborators.logger == "log"
