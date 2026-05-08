from __future__ import annotations

import re

from .terminal_answer_models import (
    TerminalAnswerClassifierInput,
    TerminalAnswerKind,
    TerminalAnswerSemanticResult,
)


# This is a conservative regex based on the characterization test.
# It's intentionally simple to avoid pulling in ResponseSemantics.
_LEAKED_SYSTEM_RESULT_RE = re.compile(r"^\s*SYSTEM\s+RESULT", re.IGNORECASE)


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
        RuntimeProtocolSemantics. Branches that depend on legacy regex helpers
        are currently deferred.
        """
        semantics = input.runtime_semantics
        visible_text = semantics.visible_text or semantics.pre_action_text

        # Legacy helper-dependent classifications are deferred until those helpers
        # are available in the refactoring context.
        # 1. INVALID_OR_TRUNCATED_TERMINAL_TEXT (legacy_regex)

        # 2. LEAKED_SYSTEM_RESULT (legacy_regex)
        if _looks_like_leaked_system_result(input.raw_response_text):
            return TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
                source="legacy_compatible_rule",
                reason_code="looks_like_leaked_system_result",
                evidence=("raw_response_text",),
                visible_text=visible_text,
            )

        # 3. INTERNAL_SUMMARY_LIKE_TEXT (runtime_policy)

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
