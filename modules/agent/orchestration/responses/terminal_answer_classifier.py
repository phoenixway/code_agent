from __future__ import annotations

import re

from ..parsers.visible_text import terminal_plaintext_completion_status
from .terminal_answer_models import (
    TerminalAnswerClassifierInput,
    TerminalAnswerKind,
    TerminalAnswerSemanticResult,
)


# This is a conservative regex based on the characterization tests.
# It intentionally requires the complete `SYSTEM RESULT:` marker and does not
# match a bare `SYSTEM RESULT` prefix.
_LEAKED_SYSTEM_RESULT_RE = re.compile(r"^\s*SYSTEM\s+RESULT\s*:", re.IGNORECASE)


def _looks_like_leaked_system_result(text: str) -> bool:
    """
    A conservative, pure-function check for leaked system results.
    Mirrors the legacy ResponseSemantics.looks_like_leaked_system_result.
    """
    return bool(_LEAKED_SYSTEM_RESULT_RE.match(text))


class TerminalAnswerClassifier:
    """
    Classifies the semantic meaning of a model's response when it contains
    user-visible text.

    This classifier is currently running in a shadow-only mode. Its results are
    logged for diagnostic purposes and do not affect production behavior.
    """

    def classify(self, input: TerminalAnswerClassifierInput) -> TerminalAnswerSemanticResult:
        """
        Classifies the terminal answer semantics based on a priority-ordered
        set of rules.

        The classification relies on compiler-derived structural facts from
        RuntimeProtocolSemantics. Some branches that depend on legacy regex
        helpers are being incrementally integrated.
        """
        semantics = input.runtime_semantics
        visible_text = semantics.visible_text or semantics.pre_action_text

        # The candidate text is the most likely source of a terminal answer.
        # It could be from structured compiler facts (visible_text) or from the raw response.
        candidate_text = visible_text or input.raw_response_text
        visible_text_source = getattr(semantics, "visible_text_source", "") or ""
        is_leaked_system_result = _looks_like_leaked_system_result(candidate_text or "")

        # Priority 1a: Pure plaintext invalid/truncated, but do not preempt a
        # complete leaked-system marker.
        if (
            visible_text_source == "PURE_PLAINTEXT"
            and candidate_text
            and not is_leaked_system_result
        ):
            valid, reason, text = terminal_plaintext_completion_status(candidate_text)
            if not valid:
                evidence = ("raw_response_text", "visible_text") if visible_text else ("raw_response_text",)
                return TerminalAnswerSemanticResult(
                    kind=TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT,
                    source="legacy_compatible_rule",
                    reason_code=f"terminal_plaintext_completion_status:{reason}",
                    evidence=evidence,
                    visible_text=text,
                )

        # Priority 1b / 2: Complete leaked system result.
        if is_leaked_system_result:
            evidence = ("raw_response_text", "visible_text") if visible_text else ("raw_response_text",)
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
                source="legacy_compatible_rule",
                reason_code="looks_like_leaked_system_result",
                evidence=evidence,
                visible_text=visible_text,
            )

        # 3. Internal summary-like text
        if input.is_internal_summary:
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.INTERNAL_SUMMARY_LIKE_TEXT,
                source="runtime_policy",
                reason_code="legacy_internal_summary_helper",
                evidence=("is_internal_summary",),
                visible_text=visible_text,
            )

        # 4. Compiler fact: Pre-action text
        if semantics.visible_text_source == "PRE_ACTION_TEXT":
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.PRE_ACTION_VISIBLE_TEXT_WITH_ACTION,
                source="compiler_fact",
                reason_code="visible_text_source_is_pre_action_text",
                evidence=("visible_text_source",),
                visible_text=semantics.pre_action_text,
            )

        # 5. Compiler fact: Intent completion text
        if semantics.visible_text_source == "INTENT_COMPLETION_TEXT":
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.INTENT_COMPLETE_WITH_VISIBLE_TEXT,
                source="compiler_fact",
                reason_code="visible_text_source_is_intent_completion_text",
                evidence=("visible_text_source",),
                visible_text=visible_text,
            )

        # 6. Compiler fact: Checkpoint accompanying text
        if semantics.visible_text_source == "CHECKPOINT_ACCOMPANYING_TEXT":
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.CHECKPOINT_WITH_VISIBLE_TEXT,
                source="compiler_fact",
                reason_code="visible_text_source_is_checkpoint_accompanying_text",
                evidence=("visible_text_source",),
                visible_text=visible_text,
            )

        # 7. Compiler fact: Checkpoint only
        if (
            semantics.has_memory_tags or semantics.has_subgoal_tags or semantics.has_memory_checkpoint
        ) and not semantics.has_visible_answer and not semantics.has_pre_action_text:
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.CHECKPOINT_ONLY,
                source="compiler_fact",
                reason_code="has_board_tags_without_visible_text",
                evidence=("has_memory_tags", "has_subgoal_tags", "has_memory_checkpoint"),
            )

        # 8. Compiler fact: Pure plaintext
        if semantics.visible_text_source == "PURE_PLAINTEXT":
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
                source="compiler_fact",
                reason_code="visible_text_source_is_pure_plaintext",
                evidence=("visible_text_source",),
                visible_text=visible_text,
            )

        # 9. Compiler fact: No visible text
        if not semantics.has_visible_answer and not semantics.has_pre_action_text:
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.NO_VISIBLE_TEXT,
                source="compiler_fact",
                reason_code="no_visible_answer_and_no_pre_action_text",
                evidence=("has_visible_answer", "has_pre_action_text"),
            )

        # 10. Fallback
        return TerminalAnswerSemanticResult(
            kind=TerminalAnswerKind.UNKNOWN,
            source="fallback",
            reason_code="no_classification_matched",
            visible_text=visible_text,
        )
