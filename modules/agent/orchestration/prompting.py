"""Prompt construction facade for orchestrator runtime and recovery flows."""

from __future__ import annotations

from .action_format_prompt_builder import ActionFormatPromptBuilderMixin
from .contract_prompt_builder import ContractPromptBuilderMixin
from .intent_prompt_builder import IntentPromptBuilderMixin
from .interactive_prompt_builder import InteractivePromptBuilderMixin
from .prompt_builder_shared import PromptBuilderSharedMixin
from .recovery_prompt_builder import RecoveryPromptBuilderMixin


class OrchestratorPromptBuilder(
    PromptBuilderSharedMixin,
    ContractPromptBuilderMixin,
    IntentPromptBuilderMixin,
    RecoveryPromptBuilderMixin,
    InteractivePromptBuilderMixin,
    ActionFormatPromptBuilderMixin,
):
    def __init__(self, agent):
        self._init_prompt_builder_shared(agent)
