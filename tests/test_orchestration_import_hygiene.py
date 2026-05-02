"""Contract tests for orchestration package exports and compatibility wrappers."""

from modules.agent import orchestration
from modules.agent.orchestration import (
    IntentResponseParser,
    IntentTransitionHandler,
    ModelOutputRecoveryHandler,
    ModelResponsePipeline,
    OrchestratorPromptBuilder,
)
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler as LegacyOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser as LegacyIntentResponseParser
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder as LegacyPromptBuilder
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline as LegacyResponsePipeline
from modules.agent.orchestration.intent_transitions import IntentTransitionHandler as LegacyIntentTransitionHandler
from modules.agent.orchestration.parsers import IntentResponseParser as ParserFacade
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder as PromptFacade
from modules.agent.orchestration.responses import (
    ModelOutputRecoveryHandler as ResponseRecoveryFacade,
    ModelResponsePipeline as ResponsePipelineFacade,
)
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


def test_legacy_wrapper_modules_still_resolve_to_same_facades():
    assert LegacyIntentResponseParser is IntentResponseParser
    assert LegacyPromptBuilder is OrchestratorPromptBuilder
    assert LegacyOutputRecoveryHandler is ModelOutputRecoveryHandler
    assert LegacyResponsePipeline is ModelResponsePipeline
    assert LegacyIntentTransitionHandler is IntentTransitionHandler
