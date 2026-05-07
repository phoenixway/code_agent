"""
Structural validator for the followup surface after an intent transition.

This is the scaffolding for Phase 5, Step 1.
It contains only type definitions and a placeholder implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..protocol import ProtocolCompiler
from .transition_followup_semantics import TransitionFollowupSemantics


class TransitionResultKind(str, Enum):
    """Strongly-typed classification of the post-intent followup surface."""

    # Intent applied, no meaningful followup
    NO_FOLLOWUP = "no_followup"
    # Intent applied, followed by a valid single action
    FOLLOWUP_ACTION = "followup_action"
    # Intent applied, followed by a valid plaintext answer
    FOLLOWUP_PLAINTEXT = "followup_plaintext"
    # Intent applied, but followup is invalid (e.g., multiple actions)
    FOLLOWUP_CONFLICT = "followup_conflict"
    # A `transition_only` intent was bundled with an action
    TRANSITION_ONLY_VIOLATION = "transition_only_violation"
    # A `reuse_only` intent was bundled with an action
    REUSE_ONLY_VIOLATION = "reuse_only_violation"
    # A `complete` intent was bundled with an action
    COMPLETE_WITH_ACTION_VIOLATION = "complete_with_action_violation"
    # Fallback for unclassifiable cases
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TransitionValidationResult:
    """
    Strongly-typed result of a transition followup validation.

    This is a structural classification, not a policy decision.
    """

    kind: TransitionResultKind
    conflict_reason: str = ""
    reason: str = ""
    details: dict[str, object] = field(default_factory=dict)


class TransitionSemanticValidator:
    """
    Centralizes and classifies the followup surface of a model response after
    an intent transition has been applied.
    """

    # Replicated from IntentTransitionHandler for behavior preservation
    INTENT_TAG_RE = re.compile(
        r"<intent\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</intent>|(?P<selfclose>/\s*>))",
        re.IGNORECASE | re.DOTALL,
    )
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    FILE_CONTENT_TAG_RE = re.compile(r"<file_content(?:\s+[^>]*)?>.*?</file_content>", re.IGNORECASE | re.DOTALL)
    ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

    def __init__(self):
        """Initializes the validator with its own compiler and semantics instances."""
        self.protocol_compiler = ProtocolCompiler()
        self.followup_semantics = TransitionFollowupSemantics()

    # --- Private helpers replicated from IntentTransitionHandler for Step 2A ---

    def _parse_attrs(self, attrs_raw: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        if not isinstance(attrs_raw, str) or not attrs_raw.strip():
            return attrs
        for key, v1, v2 in self.ATTR_RE.findall(attrs_raw.strip()):
            attrs[str(key).strip().lower()] = str(v1 or v2 or "").strip()
        return attrs

    def _mask_file_content_blocks(self, text: str) -> str:
        def _mask(match: re.Match) -> str:
            return " " * (match.end() - match.start())

        return self.FILE_CONTENT_TAG_RE.sub(_mask, text)

    def _mask_for_followup_analysis(self, response_text: str, *, strip_intent: bool = False) -> str:
        text = str(response_text or "").strip()
        if not text:
            return ""
        masked = self.THINK_TAG_RE.sub(" ", text)
        masked = self._mask_file_content_blocks(masked)
        if strip_intent:
            masked = self.INTENT_TAG_RE.sub(" ", masked)
        return masked

    def _analyze_followup_surface(self, response_text: str):
        masked = self._mask_for_followup_analysis(response_text)
        if not masked:
            return None
        return self.protocol_compiler.analyze(masked)

    def _followup_surface_summary(self, response_text: str) -> dict[str, object]:
        analysis = self._analyze_followup_surface(response_text)
        followup = self.followup_semantics.summarize(analysis)
        has_substantive = followup.has_substantive_nodes
        if not has_substantive and analysis and getattr(analysis, "error", None):
            if getattr(analysis.error, "code", "") == "E_ACTION_PAYLOAD_ARRAY":
                has_substantive = True
        return {
            "analysis": followup.analysis,
            "intent_count": followup.intent_count,
            "action_count": followup.action_count,
            "visible_count": followup.visible_count,
            "has_substantive_nodes": has_substantive,
            "has_any_action": followup.has_any_action,
            "conflict_reason": followup.conflict_reason,
            "bundle_too_dense": followup.bundle_too_dense,
        }

    def _strip_matching_current_intent_block(self, response_text: str, intent_payload: dict | None) -> str:
        text = str(response_text or "")
        if not text or not isinstance(intent_payload, dict):
            return text
        matches = list(self.INTENT_TAG_RE.finditer(text))
        if not matches:
            return text
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        payload_id = str((intent_payload or {}).get("intent_id") or "").strip()
        payload_type = str((intent_payload or {}).get("intent_type") or "").strip().upper()
        payload_goal = str((intent_payload or {}).get("goal") or "").strip()
        for match in reversed(matches):
            attrs = self._parse_attrs(match.group("attrs") or "")
            body = str(match.group("body") or "").strip()
            block_payload = None
            if body:
                try:
                    import json
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        block_payload = parsed
                except Exception:
                    block_payload = None
            if block_payload is None:
                continue
            block_mode = str(block_payload.get("mode") or attrs.get("mode") or "").strip().lower()
            block_id = str(block_payload.get("intent_id") or "").strip()
            block_type = str(block_payload.get("intent_type") or "").strip().upper()
            block_goal = str(block_payload.get("goal") or "").strip()
            comparisons = 0
            if payload_mode:
                comparisons += 1
                if block_mode != payload_mode:
                    continue
            if payload_id:
                comparisons += 1
                if block_id != payload_id:
                    continue
            if payload_type:
                comparisons += 1
                if block_type != payload_type:
                    continue
            if payload_goal:
                comparisons += 1
                if block_goal != payload_goal:
                    continue
            if comparisons == 0:
                continue
            start, end = match.span(0)
            return (text[:start] + text[end:]).strip()
        return text

    def _get_structural_classification(self, summary: dict[str, object]) -> TransitionValidationResult:
        """Performs Step 2A core structural classification."""
        if summary["conflict_reason"]:
            return TransitionValidationResult(
                kind=TransitionResultKind.FOLLOWUP_CONFLICT,
                conflict_reason=str(summary["conflict_reason"]),
            )

        analysis = summary["analysis"]
        if analysis is not None and getattr(analysis, "ast", None) is not None:
            if getattr(analysis, "error", None) is None:
                if (
                    getattr(analysis.shape, "name", "") == "ACTION_ONLY"
                    and summary["intent_count"] == 0
                    and summary["action_count"] == 1
                    and summary["visible_count"] == 0
                ):
                    return TransitionValidationResult(kind=TransitionResultKind.FOLLOWUP_ACTION)

        if not summary["has_substantive_nodes"]:
            return TransitionValidationResult(kind=TransitionResultKind.NO_FOLLOWUP)

        # Defer plaintext to later steps.
        return TransitionValidationResult(kind=TransitionResultKind.UNKNOWN)

    def validate(
        self,
        response_text: str,
        intent_payload: dict | None = None,
        *,
        transition_only_required: bool = False,
        reuse_only_required: bool = False,
        completion_requested: bool = False,
    ) -> TransitionValidationResult:
        """
        Analyzes the followup surface and returns a typed classification.

        This implementation covers Step 2A (structural) and 2B (context-sensitive).
        """
        stripped = self._strip_matching_current_intent_block(response_text, intent_payload)
        summary = self._followup_surface_summary(stripped)

        # Step 2A: Core structural classification
        structural_result = self._get_structural_classification(summary)

        # Step 2B: Context-sensitive re-classification
        if structural_result.kind == TransitionResultKind.FOLLOWUP_ACTION:
            payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
            if transition_only_required:
                return TransitionValidationResult(kind=TransitionResultKind.TRANSITION_ONLY_VIOLATION)
            if payload_mode == "reuse" and reuse_only_required:
                return TransitionValidationResult(kind=TransitionResultKind.REUSE_ONLY_VIOLATION)
            if completion_requested:
                return TransitionValidationResult(kind=TransitionResultKind.COMPLETE_WITH_ACTION_VIOLATION)

        return structural_result
