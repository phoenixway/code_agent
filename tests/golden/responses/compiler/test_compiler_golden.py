"""Golden tests for the protocol compiler."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path to allow imports of 'modules'
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


import pytest
import yaml

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.protocol.models import (
    ActionNode,
    CompilerAnalysis,
    MarkerNode,
    MemoryNode,
    ResponseAst,
    ResponseShape,
    SubgoalNode,
    ThinkNode,
    VisibleTextNode,
)


def get_shape(analysis: CompilerAnalysis) -> str:
    """Safely get the shape name from a compiler analysis object."""
    shape = analysis.shape
    return shape.name if hasattr(shape, "name") else str(shape)


def get_error_code(analysis: CompilerAnalysis) -> str | None:
    """Safely get the error code from a compiler analysis object."""
    return analysis.error.code if analysis.error else None


def get_recovery_id(analysis: CompilerAnalysis) -> str | None:
    """Safely get the recovery ID from a compiler analysis object."""
    return analysis.error.recovery_id if analysis.error else None


def has_ir(analysis: CompilerAnalysis) -> bool:
    """Check if the compiler analysis has an IR."""
    return analysis.ir is not None


def get_action_count(analysis: CompilerAnalysis) -> int:
    """
    Best-effort attempt to count actions in the IR.
    This is not guaranteed to be stable and may need updates as IR evolves.
    """
    if analysis.ir:
        return analysis.ir.action_count
    # If shape is invalid, we consider action count to be 0, even if AST has action nodes.
    if analysis.shape == ResponseShape.INVALID:
        return 0
    if not analysis.ast:
        return 0
    return len([node for node in analysis.ast.nodes if isinstance(node, ActionNode)])


def has_visible_answer(analysis: CompilerAnalysis) -> bool:
    """
    Check if there is any visible text for the user, checking IR first, then AST.
    """
    if analysis.ir:
        return analysis.ir.has_visible_answer

    # Fallback to AST if IR is not present or doesn't have a clear visible text field.
    if analysis.ast and isinstance(analysis.ast, ResponseAst):
        for node in analysis.ast.nodes:
            if isinstance(node, VisibleTextNode):
                if node.text.strip():
                    return True
    return False


def has_think(analysis: CompilerAnalysis) -> bool:
    """Check if there is any think content, checking IR first, then AST."""
    if analysis.ir:
        return analysis.ir.has_think
    if analysis.ast:
        return any(isinstance(node, ThinkNode) and (node.content or "").strip() for node in analysis.ast.nodes)
    return False


def has_checkpoint(analysis: CompilerAnalysis) -> bool:
    """Check if there are any checkpoint tags, checking IR first, then AST."""
    if analysis.ir:
        return analysis.ir.has_checkpoint
    if analysis.ast:
        return any(isinstance(node, (MemoryNode, MarkerNode, SubgoalNode)) for node in analysis.ast.nodes)
    return False


CASES_DIR = Path(__file__).parent / "cases"
CASE_FILES = list(CASES_DIR.glob("*.yaml"))
compiler = ProtocolCompiler()


@pytest.mark.parametrize("case_file", CASE_FILES, ids=[f.name for f in CASE_FILES])
def test_compiler_golden_case(case_file: Path):
    """Runs a single golden test case for the protocol compiler."""
    content = case_file.read_text(encoding="utf-8")
    case = yaml.safe_load(content)
    case_name = case_file.name

    input_text = case["input"]
    expected = case["expected"]

    analysis = compiler.analyze(input_text)

    # Assertions
    if "shape" in expected:
        actual_shape = get_shape(analysis)
        assert actual_shape == expected["shape"], f"[{case_name}] Shape mismatch"

    if "error_code" in expected:
        actual_error_code = get_error_code(analysis)
        assert actual_error_code == expected["error_code"], f"[{case_name}] Error code mismatch"

    if "recovery_id" in expected:
        actual_recovery_id = get_recovery_id(analysis)
        if expected["recovery_id"] == "not_null":
            assert actual_recovery_id is not None, f"[{case_name}] Expected non-null recovery_id"
        else:
            assert actual_recovery_id == expected["recovery_id"], f"[{case_name}] Recovery ID mismatch"

    if "has_ir" in expected:
        actual_has_ir = has_ir(analysis)
        assert actual_has_ir == expected["has_ir"], f"[{case_name}] IR presence mismatch"

    if "action_count" in expected:
        actual_action_count = get_action_count(analysis)
        assert actual_action_count == expected["action_count"], f"[{case_name}] Action count mismatch"

    if "has_visible_answer" in expected:
        actual_has_visible_answer = has_visible_answer(analysis)
        assert actual_has_visible_answer == expected["has_visible_answer"], f"[{case_name}] Visible answer mismatch"

    if "has_think" in expected:
        actual_has_think = has_think(analysis)
        assert actual_has_think == expected["has_think"], f"[{case_name}] Has think mismatch"

    if "has_checkpoint" in expected:
        actual_has_checkpoint = has_checkpoint(analysis)
        assert actual_has_checkpoint == expected["has_checkpoint"], f"[{case_name}] Has checkpoint mismatch"
