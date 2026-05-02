"""Normalization helpers for intent-aware response parsing."""

from __future__ import annotations

from .decision_models import NormalizedModelResponse
from .think_repair import ThinkAutoRepairResult


class ParsingNormalizationMixin:
    def _debug(self, message: str, *args) -> None:
        if self.logger is not None:
            self.logger.debug(message, *args)

    def repair_unclosed_think_boundary(self, response_text: str) -> ThinkAutoRepairResult:
        return self.think_repairer.repair(response_text)

    def normalize_model_response(self, response_text: str, *, allow_think_autorepair: bool = True) -> NormalizedModelResponse:
        return self.think_repairer.normalize(
            response_text,
            allow_autorepair=allow_think_autorepair,
        )
