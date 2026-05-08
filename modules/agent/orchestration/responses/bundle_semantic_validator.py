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

from ..shared.decision_models import ParsedModelOutput
from .semantic_accessors import get_compiler_metadata


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

    def _get_normalized_shape(self, parsed_output: ParsedModelOutput) -> str:
        """
        Normalizes the compiler shape from various potential sources.
        """
        # Preferred source: runtime_protocol_semantics
        rps = getattr(parsed_output, "runtime_protocol_semantics", None)
        if rps:
            shape = getattr(rps, "shape", None)
            if hasattr(shape, "name"):
                return str(shape.name or "").strip().upper()
            if isinstance(shape, str) and shape:
                return shape.strip().upper()

        # Fallback 1: compiler_ir
        ir = getattr(parsed_output, "compiler_ir", None)
        if ir:
            shape = getattr(ir, "shape", None)
            if hasattr(shape, "name"):
                return str(shape.name or "").strip().upper()
            if isinstance(shape, str) and shape:
                return shape.strip().upper()

        # Fallback 2: legacy compiler_shape
        shape = getattr(parsed_output, "compiler_shape", None)
        if isinstance(shape, str) and shape:
            return shape.strip().upper()

        return ""

    def validate(self, parsed_output: ParsedModelOutput | None = None, segments=None, **context) -> BundleValidationResult:
        """
        Classifies the bundle structure of a model response.

        Args:
            parsed_output: The ParsedModelOutput from the response pipeline.
            segments: The parsed segments from the response pipeline.
            **context: Future-use context parameters.

        Returns:
            A BundleValidationResult with the classification.
        """
        # Phase 6, Step 2A: Error-code-driven classification.
        # Shape-driven classification and consumer migration are not yet implemented.
        if parsed_output is None:
            return BundleValidationResult(kind=BundleResultKind.UNKNOWN)

        # Use the approved accessor to ensure consistent reading of compiler metadata.
        metadata = get_compiler_metadata(parsed_output)
        error_code = metadata.get("error_code")
        invalid_kind = metadata.get("invalid_kind")

        if error_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION":
            if invalid_kind == "action_payload_array":
                return BundleValidationResult(kind=BundleResultKind.INVALID_ACTION_ARRAY)
            if invalid_kind == "multiple_actions":
                return BundleValidationResult(kind=BundleResultKind.INVALID_MULTIPLE_ACTIONS)

        if error_code in {"E_FILE_CONTENT_REQUIRES_ACTION", "E_FILE_CONTENT_ACTION_MISMATCH"}:
            return BundleValidationResult(kind=BundleResultKind.INVALID_FILE_CONTENT_PAIRING)

        # Step 2B.1: INTENT_ACTION_BUNDLE shape classification
        shape = self._get_normalized_shape(parsed_output)
        if shape == "INTENT_ACTION_BUNDLE":
            return BundleValidationResult(kind=BundleResultKind.INTENT_ACTION_BUNDLE_CANDIDATE)
        elif shape == "READ_ONLY_BATCH_CANDIDATE":
            return BundleValidationResult(kind=BundleResultKind.READONLY_ACTION_BATCH_CANDIDATE)
        elif shape == "INTENT_ONLY":
            return BundleValidationResult(kind=BundleResultKind.NO_BUNDLE_SHAPE)

        return BundleValidationResult(kind=BundleResultKind.UNKNOWN)
