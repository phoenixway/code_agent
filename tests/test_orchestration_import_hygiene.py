"""Contract tests for orchestration package exports and semantic imports."""

from modules.agent import orchestration
from modules.agent.orchestration import (
    IntentResponseParser,
    IntentTransitionHandler,
    ModelOutputRecoveryHandler,
    ModelResponsePipeline,
    OrchestratorPromptBuilder,
)
from modules.agent.orchestration.parsers import IntentResponseParser as ParserFacade
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder as PromptFacade
from modules.agent.orchestration.responses import (
    ModelOutputRecoveryHandler as ResponseRecoveryFacade,
    ModelResponsePipeline as ResponsePipelineFacade,
)
from modules.agent.orchestration.shared import RecoveryPolicyResolver
from modules.agent.orchestration.shared import RecoveryContext
from modules.agent.orchestration.transitions import IntentTransitionHandler as TransitionFacade


def test_root_package_reexports_public_facades():
    assert orchestration.IntentResponseParser is IntentResponseParser
    assert orchestration.IntentTransitionHandler is IntentTransitionHandler
    assert orchestration.ModelOutputRecoveryHandler is ModelOutputRecoveryHandler
    assert orchestration.ModelResponsePipeline is ModelResponsePipeline
    assert orchestration.OrchestratorPromptBuilder is OrchestratorPromptBuilder
    assert "Orchestrator" in orchestration.__all__
    assert "LoopContext" in orchestration.__all__


def test_semantic_subpackages_export_expected_entry_points():
    assert ParserFacade is IntentResponseParser
    assert PromptFacade is OrchestratorPromptBuilder
    assert ResponseRecoveryFacade is ModelOutputRecoveryHandler
    assert ResponsePipelineFacade is ModelResponsePipeline
    assert TransitionFacade is IntentTransitionHandler
    assert RecoveryPolicyResolver is not None
    assert RecoveryContext is not None


def test_removed_root_wrapper_modules_are_absent():
    removed = [
        "modules.agent.orchestration.parsing",
        "modules.agent.orchestration.prompting",
        "modules.agent.orchestration.output_recovery",
        "modules.agent.orchestration.response_pipeline",
        "modules.agent.orchestration.intent_transitions",
        "modules.agent.orchestration.decision_models",
        "modules.agent.orchestration.recovery_policy",
    ]
    for module_name in removed:
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module_name} should be removed")
