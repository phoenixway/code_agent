"""
Shadow test comparing legacy response semantics with compiler-derived semantics.

This test suite is non-blocking and intended to reveal gaps and inconsistencies
between the two systems. It reuses the golden test cases for the compiler.

A passing test does not mean both systems agree; it means all disagreements are
either absent or explicitly documented in the `expected_shadow_mismatches` list
of the corresponding YAML case file.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
import yaml

# Add project root to path to allow imports of 'modules'
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.protocol.models import (
    ActionNode,
    CompilerAnalysis,
    MarkerNode,
    MemoryNode,
    SubgoalNode,
    ThinkNode,
    VisibleTextNode,
)
from modules.agent.orchestration.responses.response_semantics import ResponseSemantics

# --- Test setup ---

CASES_DIR = Path(__file__).parent / "compiler" / "cases"
CASE_FILES = list(CASES_DIR.glob("*.yaml"))
compiler = ProtocolCompiler()
legacy_semantics_helper = ResponseSemantics()


# --- Semantic Snapshot Models and Helpers ---


@dataclass
class SemanticSnapshot:
    """A normalized view of response semantics for comparison."""

    has_think: bool | None = None
    has_action: bool | None = None
    action_count: int | None = None
    has_visible_answer: bool | None = None
    has_checkpoint: bool | None = None
    invalid_kind: str | None = None


def get_compiler_semantics(analysis: CompilerAnalysis) -> SemanticSnapshot:
    """
    Extract a semantic snapshot from a CompilerAnalysis object.
    Prefers ResponseIR fields, but falls back to AST for diagnostics.
    """
    if analysis.ir:
        # Prefer new semantic fields from IR
        return SemanticSnapshot(
            has_think=analysis.ir.has_think,
            has_action=analysis.ir.has_action,
            action_count=analysis.ir.action_count,
            has_visible_answer=analysis.ir.has_visible_answer,
            has_checkpoint=analysis.ir.has_checkpoint,
            invalid_kind=analysis.error.code if analysis.error else None,
        )

    # Fallback to AST if IR is not available.
    # This is a temporary diagnostic measure for shadow testing.
    has_think = None
    has_action = None
    action_count = None
    has_visible_answer = None
    has_checkpoint = None

    if analysis.ast:
        # TODO: Remove AST fallback once IR is always populated.
        has_think = any(isinstance(node, ThinkNode) and (node.content or "").strip() for node in analysis.ast.nodes)
        action_nodes = [node for node in analysis.ast.nodes if isinstance(node, ActionNode)]
        has_action = len(action_nodes) > 0
        action_count = len(action_nodes)
        has_visible_answer = any(isinstance(node, VisibleTextNode) and node.text.strip() for node in analysis.ast.nodes)
        has_checkpoint = any(isinstance(node, (MemoryNode, MarkerNode, SubgoalNode)) for node in analysis.ast.nodes)

    return SemanticSnapshot(
        has_think=has_think,
        has_action=has_action,
        action_count=action_count,
        has_visible_answer=has_visible_answer,
        has_checkpoint=has_checkpoint,
        invalid_kind=analysis.error.code if analysis.error else None,
    )


def get_legacy_semantics(raw_response: str) -> SemanticSnapshot:
    """Extract a semantic snapshot using the legacy ResponseSemantics helpers."""
    # Note: This is a best-effort mapping. Legacy semantics are not always
    # structured into a single snapshot object.
    has_action = bool(legacy_semantics_helper.ACTION_OPEN_RE.search(raw_response))
    action_count = len(legacy_semantics_helper.ACTION_OPEN_RE.findall(raw_response))
    has_visible_answer = bool(legacy_semantics_helper._strip_non_plaintext_control_blocks(raw_response))

    invalid_kind = None
    if legacy_semantics_helper.has_malformed_state_changing_think_before_action(raw_response):
        invalid_kind = "malformed_action_inside_think"

    return SemanticSnapshot(
        has_think=legacy_semantics_helper.has_substantial_think(raw_response),
        has_action=has_action,
        action_count=action_count,
        has_visible_answer=has_visible_answer,
        has_checkpoint=legacy_semantics_helper.has_checkpoint_tags(raw_response),
        invalid_kind=invalid_kind,
    )


def compare_snapshots(
    case_name: str,
    legacy: SemanticSnapshot,
    compiler: SemanticSnapshot,
    expected_mismatches: list[str],
):
    """Compare two snapshots and assert on unexpected differences."""
    legacy_dict = asdict(legacy)
    compiler_dict = asdict(compiler)
    errors = []

    for field in legacy_dict:
        if field in expected_mismatches:
            continue

        legacy_val = legacy_dict[field]
        compiler_val = compiler_dict[field]

        # Ignore fields that are not implemented on one side
        if legacy_val is None or compiler_val is None:
            continue

        if legacy_val != compiler_val:
            errors.append(f"  - Field '{field}': legacy='{legacy_val}', compiler='{compiler_val}'")

    if errors:
        error_message = f"[{case_name}] Unexpected semantic mismatches found:\n" + "\n".join(errors)
        pytest.fail(error_message)


# --- Test Runner ---


@pytest.mark.parametrize("case_file", CASE_FILES, ids=[f.name for f in CASE_FILES])
def test_semantic_shadow(case_file: Path):
    """
    For a given raw response, compare the semantic understanding of the legacy
    system versus the new protocol compiler.
    """
    content = case_file.read_text(encoding="utf-8")
    case = yaml.safe_load(content)
    case_name = case_file.name

    input_text = case["input"]
    expected_mismatches = case.get("expected_shadow_mismatches", [])

    # 1. Get compiler semantics
    analysis = compiler.analyze(input_text)
    compiler_snapshot = get_compiler_semantics(analysis)

    # 2. Get legacy semantics
    legacy_snapshot = get_legacy_semantics(input_text)

    # 3. Compare
    compare_snapshots(case_name, legacy_snapshot, compiler_snapshot, expected_mismatches)
