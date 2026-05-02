"""Architectural tests for modules.agent imports outside the package."""

from __future__ import annotations

import ast
from pathlib import Path


MODULES_DIR = Path(__file__).resolve().parents[1] / "modules"
ALLOWED_PREFIXES = (
    "modules.agent",
    "modules.agent.core",
    "modules.agent.technical_interruptions",
    "modules.agent.orchestration.runtime",
    "modules.agent.orchestration.prompts",
    "modules.agent.orchestration.parsers",
    "modules.agent.orchestration.responses",
    "modules.agent.orchestration.transitions",
    "modules.agent.orchestration.shared",
    "modules.agent.orchestration.trace_export",
)
DISALLOWED_AGENT_WRAPPERS = {
    "modules.agent.orchestrator",
    "modules.agent.recovery_coordinator",
    "modules.agent.orchestrator_prompt_builder",
    "modules.agent.turn_lifecycle",
    "modules.agent.intent_response_parser",
    "modules.agent.intent_guard",
}


def test_non_agent_modules_do_not_use_removed_agent_wrappers():
    violations: list[str] = []
    for path in sorted(MODULES_DIR.rglob("*.py")):
        if path.parts[:2] == ("modules", "agent"):
            continue
        text = path.read_text(errors="ignore")
        try:
            tree = ast.parse(text)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                module = node.module or ""
                if not module.startswith("modules.agent"):
                    continue
                if module in DISALLOWED_AGENT_WRAPPERS:
                    violations.append(f"{path}: {module}")
                    continue
                if not any(module == prefix or module.startswith(prefix + ".") for prefix in ALLOWED_PREFIXES):
                    violations.append(f"{path}: {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if not module.startswith("modules.agent"):
                        continue
                    if module in DISALLOWED_AGENT_WRAPPERS:
                        violations.append(f"{path}: {module}")
                        continue
                    if not any(module == prefix or module.startswith(prefix + ".") for prefix in ALLOWED_PREFIXES):
                        violations.append(f"{path}: {module}")
    assert not violations, "\n".join(violations)
