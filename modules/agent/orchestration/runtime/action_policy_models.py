"""Typed models for ActionPolicy validation results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AtomicBundlePolicyResultKind(str, Enum):
    """Categorizes the outcome of an atomic bundle policy validation."""

    OK = "ok"
    REJECTED_MULTIPLE_ACTIONS = "rejected_multiple_actions"
    REJECTED_INVALID_SHAPE = "rejected_invalid_shape"
    REJECTED_MISSING_FILE_CONTENT = "rejected_missing_file_content"
    REJECTED_INTENT_REQUIRED = "rejected_intent_required"
    REJECTED_INTENT_ACTION_NOT_ALLOWED = "rejected_intent_action_not_allowed"
    REJECTED_PRE_ACTION_CHECK = "rejected_pre_action_check"
    UNKNOWN = "unknown"


@dataclass
class AtomicBundleActionValidationResult:
    """
    Represents the result of validating an atomic bundle action against runtime policy.

    This is a transitional object. It will eventually replace the legacy boolean-based
    result and untyped `details` dictionary.
    """

    kind: AtomicBundlePolicyResultKind
    ok: bool
    reason: str = ""
    details: dict[str, object] | None = None
