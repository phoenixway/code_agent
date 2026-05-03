"""Post-migration contracts for removed orchestration wrapper modules."""

from __future__ import annotations

import ast
from pathlib import Path


BASE = Path(__file__).resolve().parents[1] / "modules" / "agent" / "orchestration"
TESTS_DIR = Path(__file__).resolve().parents[1] / "tests"
REMOVED_WRAPPERS = {
    "action_policy",
    "core",
    "decision_models",
    "dispatch_outcome",
    "dispatch_pipeline",
    "intent_transitions",
    "lifecycle",
    "loop_gate",
    "memory_board_stage",
    "output_recovery",
    "parsing",
    "pipeline",
    "plan_board_stage",
    "policy",
    "prompting",
    "recovery",
    "recovery_policy",
    "response_pipeline",
}


def test_removed_wrapper_files_are_absent():
    for module_name in REMOVED_WRAPPERS:
        assert not (BASE / f"{module_name}.py").exists(), module_name


def test_tests_do_not_import_removed_wrapper_modules():
    violations: list[str] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                module = node.module or ""
                for wrapper_name in REMOVED_WRAPPERS:
                    if module == f"modules.agent.orchestration.{wrapper_name}":
                        violations.append(f"{path.name}: {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for wrapper_name in REMOVED_WRAPPERS:
                        if alias.name == f"modules.agent.orchestration.{wrapper_name}":
                            violations.append(f"{path.name}: {alias.name}")
    assert not violations, "\n".join(violations)
