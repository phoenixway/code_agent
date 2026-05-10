"""
Diagnostic-only classification of search action quality.
"""

from __future__ import annotations

import re

from .filesystem_path_validation import (
    FILESYSTEM_PATH_ACTIONS,
    validate_filesystem_action_path,
)

SEARCH_TOOLS = {"search_content", "search_files"}
EXACT_ANCHOR_RE = re.compile(r"\|")


class SearchQualityKind:
    EXACT_LOOKUP = "exact_lookup"
    BOUNDED_RECON = "bounded_recon"
    UNBOUNDED_BROAD = "unbounded_broad"
    CANDIDATE_READ = "candidate_read"
    NON_SEARCH_ACTION = "non_search_action"


class SearchQualitySeverity:
    OK = "ok"
    WARN = "warn"
    BLOCK = "block"
    RECOVERABLE_CANDIDATE = "recoverable_candidate"


def classify_search_action_quality(action_payload: object) -> dict:
    """
    Classifies the quality of a search action based on its parameters.
    This is a diagnostic-only function and does not block or recover.
    """
    if not isinstance(action_payload, dict):
        return {
            "is_search": False,
            "is_filesystem_action": False,
            "tool_type": "",
            "kind": SearchQualityKind.NON_SEARCH_ACTION,
            "severity": SearchQualitySeverity.OK,
            "reason": "not_a_dict",
            "boundedness_kind": SearchQualityKind.NON_SEARCH_ACTION,
            "boundedness_severity": SearchQualitySeverity.OK,
            "boundedness_reason": "not_a_dict",
            "path_validity": "not_applicable",
            "expected_path_kind": None,
            "actual_path_kind": None,
            "path_validation_error_code": None,
        }

    tool_type = str(action_payload.get("type") or action_payload.get("action") or "").strip()
    path_validation = validate_filesystem_action_path(action_payload)
    effective_path = path_validation.path or str(action_payload.get("path") or "").strip()
    if tool_type not in SEARCH_TOOLS:
        path_validity = "not_applicable"
        severity = SearchQualitySeverity.OK
        reason = ""
        if tool_type in FILESYSTEM_PATH_ACTIONS:
            if path_validation.error_code is None and not path_validation.ok:
                path_validity = "unknown"
                severity = SearchQualitySeverity.WARN
                reason = "path_validation_unknown"
            elif path_validation.ok:
                path_validity = "known_valid"
            else:
                path_validity = "invalid"
                severity = SearchQualitySeverity.BLOCK
                reason = "invalid_action_path"
        return {
            "is_search": False,
            "is_filesystem_action": tool_type in FILESYSTEM_PATH_ACTIONS,
            "tool_type": tool_type,
            "kind": SearchQualityKind.NON_SEARCH_ACTION,
            "severity": severity,
            "reason": reason,
            "boundedness_kind": SearchQualityKind.NON_SEARCH_ACTION,
            "boundedness_severity": SearchQualitySeverity.OK,
            "boundedness_reason": "",
            "path": effective_path,
            "path_validity": path_validity,
            "expected_path_kind": path_validation.expected_kind,
            "actual_path_kind": path_validation.actual_kind,
            "path_validation_error_code": path_validation.error_code,
        }

    path = effective_path
    pattern = str(action_payload.get("pattern") or "").strip()
    include_extensions = action_payload.get("include_extensions")
    exclude_dirs = action_payload.get("exclude_dirs")
    code_only = bool(action_payload.get("code_only", False))
    limit = action_payload.get("limit")

    def _finalize(base: dict) -> dict:
        boundedness_severity = str(base["severity"])
        boundedness_reason = str(base["reason"])
        if path_validation.error_code is None and not path_validation.ok:
            path_validity = "unknown"
            severity = SearchQualitySeverity.WARN if boundedness_severity == SearchQualitySeverity.OK else boundedness_severity
            reason = "path_validation_unknown"
        elif path_validation.ok:
            path_validity = "known_valid"
            severity = boundedness_severity
            reason = boundedness_reason
        else:
            path_validity = "invalid"
            severity = SearchQualitySeverity.BLOCK
            reason = "invalid_search_root"
        return {
            **base,
            "is_filesystem_action": True,
            "boundedness_kind": base["kind"],
            "boundedness_severity": boundedness_severity,
            "boundedness_reason": boundedness_reason,
            "path_validity": path_validity,
            "expected_path_kind": path_validation.expected_kind,
            "actual_path_kind": path_validation.actual_kind,
            "path_validation_error_code": path_validation.error_code,
            "severity": severity,
            "reason": reason,
        }

    if tool_type == "search_files":
        if pattern:
            return _finalize({
                "is_search": True,
                "tool_type": tool_type,
                "kind": SearchQualityKind.EXACT_LOOKUP,
                "severity": SearchQualitySeverity.OK,
                "reason": "specific_file_search",
                "path": path,
                "pattern": pattern,
                "has_specific_path": bool(path and path != "."),
                "has_include_extensions": bool(include_extensions),
                "has_exclude_dirs": bool(exclude_dirs),
                "code_only": code_only,
                "limit": limit,
                "bound_count": 1,
                "missing_bounds": [],
            })

    # search_content logic
    has_specific_path = bool(path and path != ".")
    has_specific_pattern = bool(pattern and "*" not in pattern and "?" not in pattern)
    has_include_extensions = bool(include_extensions)
    has_exclude_dirs = bool(exclude_dirs)
    has_low_limit = isinstance(limit, int) and limit <= 10

    is_exact_anchor_unscoped = not has_specific_path and EXACT_ANCHOR_RE.search(pattern) and not has_include_extensions

    if is_exact_anchor_unscoped:
        # This is a special case where code_only is not a sufficient bound to make the search "bounded".
        # We calculate bounds for logging, but treat this case as having fewer than 2 effective bounds.
        bounds = {
            "path": has_specific_path,
            "pattern": has_specific_pattern,
            "include_extensions": has_include_extensions,
            "exclude_dirs": has_exclude_dirs,
            "code_only": code_only,
            "low_limit": has_low_limit,
        }
        # For this case, `code_only` does not count as a bound.
        effective_bound_count = sum(1 for k, v in bounds.items() if v and k != "code_only")
        return _finalize({
            "is_search": True,
            "tool_type": tool_type,
            "kind": SearchQualityKind.UNBOUNDED_BROAD,
            "severity": SearchQualitySeverity.WARN,
            "reason": "exact_anchor_unscoped",
            "path": path,
            "pattern": pattern,
            "has_specific_path": has_specific_path,
            "has_include_extensions": has_include_extensions,
            "has_exclude_dirs": has_exclude_dirs,
            "code_only": code_only,
            "limit": limit,
            "bound_count": effective_bound_count,
            "missing_bounds": [k for k, v in bounds.items() if not v],
        })

    bounds = {
        "path": has_specific_path,
        "pattern": has_specific_pattern,
        "include_extensions": has_include_extensions,
        "exclude_dirs": has_exclude_dirs,
        "code_only": code_only,
        "low_limit": has_low_limit,
    }
    bound_count = sum(1 for v in bounds.values() if v)
    missing_bounds = [k for k, v in bounds.items() if not v]

    if bound_count >= 2:
        return _finalize({
            "is_search": True,
            "tool_type": tool_type,
            "kind": SearchQualityKind.BOUNDED_RECON,
            "severity": SearchQualitySeverity.OK,
            "reason": "well_bounded_search",
            "path": path,
            "pattern": pattern,
            "has_specific_path": has_specific_path,
            "has_include_extensions": has_include_extensions,
            "has_exclude_dirs": has_exclude_dirs,
            "code_only": code_only,
            "limit": limit,
            "bound_count": bound_count,
            "missing_bounds": missing_bounds,
        })

    return _finalize({
        "is_search": True,
        "tool_type": tool_type,
        "kind": SearchQualityKind.UNBOUNDED_BROAD,
        "severity": SearchQualitySeverity.WARN,
        "reason": "root_search_without_bounds",
        "path": path,
        "pattern": pattern,
        "has_specific_path": has_specific_path,
        "has_include_extensions": has_include_extensions,
        "has_exclude_dirs": has_exclude_dirs,
        "code_only": code_only,
        "limit": limit,
        "bound_count": bound_count,
        "missing_bounds": missing_bounds,
    })
