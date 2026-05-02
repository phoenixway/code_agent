"""Architectural dependency tests for orchestration semantic subpackages."""

from __future__ import annotations

import ast
from pathlib import Path


BASE = Path(__file__).resolve().parents[1] / "modules" / "agent" / "orchestration"
SEMANTIC_PACKAGES = ("prompts", "parsers", "responses", "transitions", "shared", "runtime")


def _orchestration_import_targets(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text())
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0:
                if module.startswith("modules.agent.orchestration"):
                    targets.append(module)
                continue
            if node.level >= 2:
                prefix = "." * node.level
                targets.append(f"{prefix}{module}")
                continue
            if module:
                targets.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("modules.agent.orchestration"):
                    targets.append(alias.name)
    return targets


def _assert_no_prefix_imports(package: str, forbidden_prefixes: tuple[str, ...]) -> None:
    package_dir = BASE / package
    violations: list[str] = []
    for py_file in sorted(package_dir.glob("*.py")):
        for target in _orchestration_import_targets(py_file):
            if target.startswith("."):
                normalized = target.lstrip(".")
            elif target.startswith("modules.agent.orchestration."):
                normalized = target.removeprefix("modules.agent.orchestration.")
            else:
                normalized = target
            if normalized.startswith(package + ".") or normalized == package:
                continue
            if normalized == "shared" or normalized.startswith("shared."):
                continue
            if normalized == "transitions.intent_universe" and package == "prompts":
                continue
            if normalized == "responses.stage_logging" and package == "transitions":
                continue
            if normalized == "parsers.visible_text" and package in {"responses", "transitions"}:
                continue
            for forbidden in forbidden_prefixes:
                if normalized == forbidden or normalized.startswith(forbidden + "."):
                    violations.append(f"{py_file.name}: {target}")
                    break
    assert not violations, "\n".join(violations)


def test_prompts_do_not_import_parsers_or_responses():
    _assert_no_prefix_imports("prompts", ("parsers", "responses"))


def test_parsers_do_not_import_other_semantic_packages():
    _assert_no_prefix_imports("parsers", ("responses", "transitions", "prompts"))


def test_responses_do_not_import_prompts_or_transition_internals():
    _assert_no_prefix_imports("responses", ("prompts", "transitions"))


def test_transitions_do_not_import_prompts_or_response_internals():
    _assert_no_prefix_imports("transitions", ("prompts", "responses"))


def test_shared_does_not_import_semantic_runtime_packages():
    _assert_no_prefix_imports("shared", ("prompts", "parsers", "responses", "transitions"))


def test_runtime_does_not_import_root_helper_wrappers():
    wrapper_modules = {
        "prompting",
        "parsing",
        "response_pipeline",
        "output_recovery",
        "intent_transitions",
        "stage_logging",
        "visible_text",
        "decision_models",
        "recovery_policy",
    }
    violations: list[str] = []
    for py_file in sorted((BASE / "runtime").glob("*.py")):
        for target in _orchestration_import_targets(py_file):
            if target.startswith(".."):
                normalized = target.lstrip(".")
            elif target.startswith("modules.agent.orchestration."):
                normalized = target.removeprefix("modules.agent.orchestration.")
            else:
                continue
            if normalized in wrapper_modules:
                violations.append(f"{py_file.name}: {target}")
    assert not violations, "\n".join(violations)


def test_no_semantic_package_uses_legacy_wrapper_imports_for_other_packages():
    wrapper_modules = {
        "decision_models",
        "recovery_policy",
        "prompting",
        "parsing",
        "response_pipeline",
        "output_recovery",
        "intent_transitions",
        "stage_logging",
        "visible_text",
    }
    violations: list[str] = []
    for package in SEMANTIC_PACKAGES:
        for py_file in sorted((BASE / package).glob("*.py")):
            for target in _orchestration_import_targets(py_file):
                if target.startswith(".."):
                    normalized = target.lstrip(".")
                elif target.startswith("modules.agent.orchestration."):
                    normalized = target.removeprefix("modules.agent.orchestration.")
                else:
                    continue
                if normalized in wrapper_modules:
                    violations.append(f"{package}/{py_file.name}: {target}")
    assert not violations, "\n".join(violations)
