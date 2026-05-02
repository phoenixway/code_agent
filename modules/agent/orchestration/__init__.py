"""Supported public API for orchestration entry points.

This package intentionally exposes only a small root-level facade.
All other orchestration imports should go through semantic subpackages
(`runtime`, `prompts`, `parsers`, `responses`, `transitions`, `shared`)
or explicit compatibility wrappers during migration.
"""

from .runtime import LoopContext, Orchestrator
from .parsers import IntentResponseParser
from .prompts import OrchestratorPromptBuilder
from .responses import ModelOutputRecoveryHandler, ModelResponsePipeline
from .transitions import IntentTransitionHandler

PUBLIC_API = (
    "IntentResponseParser",
    "IntentTransitionHandler",
    "LoopContext",
    "ModelOutputRecoveryHandler",
    "ModelResponsePipeline",
    "Orchestrator",
    "OrchestratorPromptBuilder",
)

__all__ = list(PUBLIC_API)
