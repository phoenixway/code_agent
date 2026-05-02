"""Inventory and contract tests for orchestration compatibility wrappers."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path


BASE = Path(__file__).resolve().parents[1] / "modules" / "agent" / "orchestration"
TESTS_DIR = Path(__file__).resolve().parents[1] / "tests"

WRAPPERS = {
    "decision_models": "modules.agent.orchestration.shared.decision_models",
    "intent_transitions": "modules.agent.orchestration.transitions.intent_transitions",
    "output_recovery": "modules.agent.orchestration.responses.output_recovery",
    "parsing": "modules.agent.orchestration.parsers.parsing",
    "prompting": "modules.agent.orchestration.prompts.prompting",
    "recovery_policy": "modules.agent.orchestration.shared.recovery_policy",
    "response_pipeline": "modules.agent.orchestration.responses.response_pipeline",
}


def test_wrapper_files_have_compatibility_docstrings():
    for module_name in WRAPPERS:
        path = BASE / f"{module_name}.py"
        text = path.read_text()
        assert "compatibility" in text.splitlines()[0].lower(), module_name


def test_wrapper_inventory_imports_expected_target_modules():
    for wrapper_name, target_module in WRAPPERS.items():
        wrapper = importlib.import_module(f"modules.agent.orchestration.{wrapper_name}")
        target = importlib.import_module(target_module)
        assert wrapper is not None
        assert target is not None


def test_wrapper_inventory_matches_documented_migration_scope():
    doc = (Path(__file__).resolve().parents[1] / "docs" / "ORCHESTRATION_WRAPPER_MIGRATION.md").read_text()
    for wrapper_name in WRAPPERS:
        assert f"`{wrapper_name}.py`" in doc, wrapper_name


def test_wrapper_imports_are_isolated_to_compatibility_suites():
    allowed = {
        "test_orchestration_import_hygiene.py",
        "test_orchestration_wrapper_migration.py",
    }
    violations: list[str] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                module = node.module or ""
                for wrapper_name in WRAPPERS:
                    if module == f"modules.agent.orchestration.{wrapper_name}":
                        violations.append(f"{path.name}: {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for wrapper_name in WRAPPERS:
                        if alias.name == f"modules.agent.orchestration.{wrapper_name}":
                            violations.append(f"{path.name}: {alias.name}")
    assert not violations, "\n".join(violations)
