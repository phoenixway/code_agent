from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


STRUCTURAL_SOURCE_SUFFIXES = {".kt", ".py"}

READ_ONLY_EVIDENCE_ACTIONS = (
    "read_chunk",
    "read_file_skeleton",
    "extract_symbol",
    "read_file",
    "search_content",
)

EDIT_FILE_STRUCTURAL_MODIFY_ACTIONS = (
    "read_chunk",
    "read_file_skeleton",
    "extract_symbol",
    "replace_symbol",
    "edit_file",
    "write_file_block",
)

EDIT_FILE_FUZZY_MODIFY_ACTIONS = (
    "read_chunk",
    "read_file_skeleton",
    "extract_symbol",
    "replace_symbol",
    "fuzzy_edit_file",
    "replace_line_range",
    "edit_file",
    "write_file_block",
)

EDIT_FILE_LEGACY_MODIFY_ACTIONS = (
    "read_chunk",
    "read_file_skeleton",
    "extract_symbol",
    "edit_file",
    "write_file_block",
)

EDIT_FILE_INVESTIGATE_ACTIONS = (
    "read_chunk",
    "read_file_skeleton",
    "extract_symbol",
    "search_content",
    "read_file",
)

EDIT_FILE_GENERIC_ACTIONS = (
    "read_chunk",
    "read_file_skeleton",
    "extract_symbol",
    "search_content",
    "edit_file",
    "write_file_block",
)

EDIT_FILE_SEARCH_MISMATCH_TYPES = {
    "empty_search_text",
    "line_ending_mismatch",
    "whitespace_mismatch",
    "multiple_similar_blocks",
    "indentation_or_partial_block_mismatch",
    "search_text_stale_or_block_modified",
    "no_similar_block_found",
}


@dataclass(frozen=True)
class EditFileRecoveryContext:
    reason: str = ""
    error_code: str = ""
    mismatch_type: str = ""
    path: str = ""
    active_intent_type: str = ""
    active_allowed_actions: tuple[str, ...] = ()
    replace_symbol_available: bool = True
    fuzzy_unique_candidate: bool = False


@dataclass(frozen=True)
class EditFileRecoveryPlan:
    next_actions: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    prompt_hint: str
    prefer_structural_recovery: bool = False
    is_search_mismatch: bool = False


def resolve_edit_file_recovery(ctx: EditFileRecoveryContext | None = None) -> EditFileRecoveryPlan:
    ctx = ctx or EditFileRecoveryContext()
    active_type = str(ctx.active_intent_type or "").strip().upper()
    mismatch_type = str(ctx.mismatch_type or "").strip()
    suffix = Path(str(ctx.path or "")).suffix.lower()
    is_structural_source = suffix in STRUCTURAL_SOURCE_SUFFIXES
    is_search_mismatch = _is_search_mismatch(ctx)

    if active_type == "INVESTIGATE":
        actions = EDIT_FILE_INVESTIGATE_ACTIONS
        return EditFileRecoveryPlan(
            next_actions=actions,
            recommended_actions=actions,
            prompt_hint=(
                "Recover from the failed edit by gathering narrower read-only evidence. "
                "Do not use state-changing tools under an INVESTIGATE intent."
            ),
            prefer_structural_recovery=False,
            is_search_mismatch=is_search_mismatch,
        )

    if active_type == "MODIFY":
        # If path is unknown, keep structural recovery available. Schema-level malformed
        # edit_file validation often has incomplete payload context, and the runtime/intent
        # layer will still filter actions against the active contract.
        path_unknown = not str(ctx.path or "").strip()
        prefer_structural = bool(
            ctx.replace_symbol_available
            and (is_structural_source or path_unknown)
            and is_search_mismatch
        )
        actions = (
            EDIT_FILE_FUZZY_MODIFY_ACTIONS
            if ctx.fuzzy_unique_candidate
            else EDIT_FILE_STRUCTURAL_MODIFY_ACTIONS
            if prefer_structural
            else EDIT_FILE_LEGACY_MODIFY_ACTIONS
        )
        actions = _merge_allowed_recovery_actions(actions, ctx.active_allowed_actions, active_type=active_type)
        suppress_edit_file = _should_suppress_edit_file_retry(ctx)
        if suppress_edit_file:
            actions = tuple(action for action in actions if action != "edit_file")
        hint = (
            "Recover from the edit_file mismatch with the unique indentation-normalized fuzzy candidate: "
            "use fuzzy_edit_file only with the same path, search_text, and replace_text from the failed edit. "
            "If fuzzy_edit_file is unavailable or fails, use extract_symbol/replace_symbol or read a fresh exact range."
            if ctx.fuzzy_unique_candidate
            else "Recover from the edit_file mismatch with a structural path when possible: "
            "use extract_symbol to resolve the current symbol body, then replace_symbol for supported .kt/.py symbol-sized changes. "
            "Use edit_file only for a small exact block freshly read in the current turn."
            if prefer_structural
            else "Recover from the failed edit by reading the smaller current target block and retrying only a targeted edit, or use write_file_block when a broader rewrite is explicitly intended."
        )
        if suppress_edit_file:
            hint = "Repeated edit_file mismatch detected. Do not retry edit_file with another hand-written search_text. " + hint
        return EditFileRecoveryPlan(
            next_actions=actions,
            recommended_actions=actions,
            prompt_hint=hint,
            prefer_structural_recovery=prefer_structural,
            is_search_mismatch=is_search_mismatch,
        )

    actions = EDIT_FILE_GENERIC_ACTIONS
    return EditFileRecoveryPlan(
        next_actions=actions,
        recommended_actions=actions,
        prompt_hint="Recover from the failed edit by switching to narrower evidence before retrying a targeted edit.",
        prefer_structural_recovery=False,
        is_search_mismatch=is_search_mismatch,
    )


def malformed_edit_file_recovery_actions(*, active_intent_type: str = "", active_allowed_actions: tuple[str, ...] = ()) -> tuple[str, ...]:
    return resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="malformed_edit_file_payload",
            error_code="MALFORMED_EDIT_FILE_PAYLOAD",
            mismatch_type="malformed_payload",
            active_intent_type=active_intent_type,
            active_allowed_actions=active_allowed_actions,
        )
    ).next_actions


def search_mismatch_recovery_actions(
    *,
    path: str = "",
    mismatch_type: str = "",
    active_intent_type: str = "",
    active_allowed_actions: tuple[str, ...] = (),
    replace_symbol_available: bool = True,
    reason: str = "edit_file_search_mismatch",
    fuzzy_unique_candidate: bool = False,
) -> tuple[str, ...]:
    return resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason=reason,
            error_code="VALIDATION_ERROR",
            mismatch_type=mismatch_type,
            path=path,
            active_intent_type=active_intent_type,
            active_allowed_actions=active_allowed_actions,
            replace_symbol_available=replace_symbol_available,
            fuzzy_unique_candidate=fuzzy_unique_candidate,
        )
    ).next_actions


def _should_suppress_edit_file_retry(ctx: EditFileRecoveryContext) -> bool:
    reason = str(ctx.reason or "").strip()
    return reason in {"repeated_edit_failure_hard_stop", "repeating_failure"}


def _is_search_mismatch(ctx: EditFileRecoveryContext) -> bool:
    mismatch_type = str(ctx.mismatch_type or "").strip()
    reason = str(ctx.reason or "").strip()
    error_code = str(ctx.error_code or "").strip().upper()
    return (
        mismatch_type in EDIT_FILE_SEARCH_MISMATCH_TYPES
        or reason in {"edit_file_search_mismatch", "repeated_edit_failure_hard_stop", "repeating_failure"}
        or error_code in {"VALIDATION_ERROR", "MALFORMED_EDIT_FILE_PAYLOAD"}
    )


def _merge_allowed_recovery_actions(
    preferred: tuple[str, ...],
    active_allowed_actions: tuple[str, ...],
    *,
    active_type: str,
) -> tuple[str, ...]:
    normalized_allowed = _unique(active_allowed_actions)
    if not normalized_allowed:
        return preferred

    allowed = list(normalized_allowed)
    if active_type == "MODIFY":
        for action in ("extract_symbol", "replace_symbol", "fuzzy_edit_file", "replace_line_range", "write_file_block"):
            if action in preferred and action not in allowed:
                allowed.append(action)

    filtered = tuple(action for action in preferred if action in allowed)
    return filtered or tuple(allowed)


def _unique(actions: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for action in actions or ():
        value = str(action or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)
