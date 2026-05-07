"""
Scaffolding for the BundleSemanticValidator.

This module provides a centralized, testable component for classifying the
structural validity and safety of action bundles.

Phase 6, Step 1: Scaffolding only.
- The `validate` method returns a default `UNKNOWN` result.
- No classification logic is implemented.
- No consumers are migrated.

Core Principles:
- Structural Evidence Only: The validator provides structural classification
  evidence. It does not grant dispatch permission, make policy decisions, or
  replace ActionPolicy.
- Behavior Preservation: Future implementation will be a behavior-preserving
  refactor, verified with parity tests before any consumer migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BundleResultKind(str, Enum):
    """Strongly-typed classification of a response's bundle structure."""

    # Not a bundle shape
    NO_BUNDLE_SHAPE = "no_bundle_shape"
    # A structurally valid atomic intent-action bundle candidate
    INTENT_ACTION_BUNDLE_CANDIDATE = "intent_action_bundle_candidate"
    # A structurally valid batch of multiple read-only actions candidate
    READONLY_ACTION_BATCH_CANDIDATE = "readonly_action_batch_candidate"
    # Multiple actions that are not a valid read-only batch
    INVALID_MULTIPLE_ACTIONS = "invalid_multiple_actions"
    # Action payload is a JSON array, not an object
    INVALID_ACTION_ARRAY = "invalid_action_array"
    # <file_content> is missing or paired with the wrong action
    INVALID_FILE_CONTENT_PAIRING = "invalid_file_content_pairing"
    # A `complete` intent is bundled with an action
    INVALID_INTENT_COMPLETE_WITH_ACTION = "invalid_intent_complete_with_action"
    # Visible text is mixed with control protocol tags.
    # DEFERRED: This classification is a placeholder and must not be implemented
    # in Phase 6 without a separate get_visible_text design.
    INVALID_MIXED_VISIBLE_TEXT = "invalid_mixed_visible_text"
    # Fallback for unclassifiable or non-bundle cases
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BundleValidationResult:
    """The strongly-typed result of a bundle validation check."""

    kind: BundleResultKind
    reason: str = ""
    details: dict[str, object] = field(default_factory=dict)


class BundleSemanticValidator:
    """
    Centralized classifier for action bundle structure and safety.

    This class is currently a scaffold. It provides evidence only and does not
    replace or grant authority to bypass ActionPolicy or DispatchPipeline.
    """

    def validate(self, parsed_output=None, segments=None, **context) -> BundleValidationResult:
        """
        Classifies the bundle structure of a model response.

        Args:
            parsed_output: The ParsedModelOutput from the response pipeline.
            segments: The parsed segments from the response pipeline.
            **context: Future-use context parameters.

        Returns:
            A BundleValidationResult with the classification.
            For Step 1, this always returns UNKNOWN.
        """
        # Phase 6, Step 1: Scaffolding only. No classification logic.
        return BundleValidationResult(kind=BundleResultKind.UNKNOWN)
