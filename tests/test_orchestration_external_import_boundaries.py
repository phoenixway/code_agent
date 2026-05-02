"""Architectural tests for orchestration imports outside the package itself."""

from __future__ import annotations

import ast
from pathlib import Path


MODULES_DIR = Path(__file__).resolve().parents[1] / "modules"
ALLOWED_PREFIXES = (
    "modules.agent.orchestration",
    "modules.agent.orchestration.runtime",
    "modules.agent.orchestration.prompts",
    "modules.agent.orchestration.parsers",
    "modules.agent.orchestration.responses",
    "modules.agent.orchestration.transitions",
    "modules.agent.orchestration.shared",
    "modules.agent.orchestration.trace_export",
)
DISALLOWED_ROOT_WRAPPERS = {
    "modules.agent.orchestration.core",
    "modules.agent.orchestration.pipeline",
    "modules.agent.orchestration.recovery",
    "modules.agent.orchestration.action_policy",
    "modules.agent.orchestration.dispatch_pipeline",
    "modules.agent.orchestration.dispatch_outcome",
    "modules.agent.orchestration.loop_gate",
    "modules.agent.orchestration.memory_board_stage",
    "modules.agent.orchestration.plan_board_stage",
    "modules.agent.orchestration.lifecycle",
    "modules.agent.orchestration.policy",
    "modules.agent.orchestration.prompting",
    "modules.agent.orchestration.parsing",
    "modules.agent.orchestration.response_pipeline",
    "modules.agent.orchestration.output_recovery",
    "modules.agent.orchestration.intent_transitions",
    "modules.agent.orchestration.decision_models",
    "modules.agent.orchestration.recovery_policy",
}


def test_non_orchestration_modules_use_only_supported_orchestration_import_surfaces():
    violations: list[str] = []
    for path in sorted(MODULES_DIR.rglob("*.py")):
        if "orchestration" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        try:
            tree = ast.parse(text)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                module = node.module or ""
                if not module.startswith("modules.agent.orchestration"):
                    continue
                if module in DISALLOWED_ROOT_WRAPPERS:
                    violations.append(f"{path}: {module}")
                    continue
                if not any(module == prefix or module.startswith(prefix + ".") for prefix in ALLOWED_PREFIXES):
                    violations.append(f"{path}: {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if not module.startswith("modules.agent.orchestration"):
                        continue
                    if module in DISALLOWED_ROOT_WRAPPERS:
                        violations.append(f"{path}: {module}")
                        continue
                    if not any(module == prefix or module.startswith(prefix + ".") for prefix in ALLOWED_PREFIXES):
                        violations.append(f"{path}: {module}")
    assert not violations, "\n".join(violations)
