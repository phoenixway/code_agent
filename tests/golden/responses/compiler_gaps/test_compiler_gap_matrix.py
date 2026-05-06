"""
Test suite for documenting and tracking coverage gaps between the legacy
response handling and the new protocol compiler.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Add project root to path to allow imports of 'modules'
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.protocol.models import CompilerAnalysis


def get_shape(analysis: CompilerAnalysis) -> str | None:
    """Safely get the shape name from a compiler analysis object."""
    shape = analysis.shape
    return shape.name if hasattr(shape, "name") else str(shape)


def get_error_code(analysis: CompilerAnalysis) -> str | None:
    """Safely get the error code from a compiler analysis object."""
    return analysis.error.code if analysis.error else None


CASES_DIR = Path(__file__).parent / "cases"
CASE_FILES = list(CASES_DIR.glob("*.yaml"))
compiler = ProtocolCompiler()


@pytest.mark.parametrize("case_file", CASE_FILES, ids=[f.name for f in CASE_FILES])
def test_compiler_gap_matrix_case(case_file: Path):
    """
    Runs a single compiler gap-matrix test case.

    This test does not fail if a feature is 'missing' or 'partial'. It only
    fails if the compiler's current behavior deviates from what is documented
    in the 'compiler_expectation' block of the YAML file.
    """
    content = case_file.read_text(encoding="utf-8")
    case = yaml.safe_load(content)
    case_name = case_file.name

    input_text = case["input"]
    compiler_expectation = case["compiler_expectation"]

    # Run the compiler
    analysis = compiler.analyze(input_text)

    # Assert against the documented current state
    if "expected_shape" in compiler_expectation:
        actual_shape = get_shape(analysis)
        expected_shape = compiler_expectation["expected_shape"]
        assert actual_shape == expected_shape, f"[{case_name}] Shape mismatch: expected '{expected_shape}', got '{actual_shape}'"

    if "expected_error_code" in compiler_expectation:
        actual_error_code = get_error_code(analysis)
        expected_error_code = compiler_expectation["expected_error_code"]
        assert (
            actual_error_code == expected_error_code
        ), f"[{case_name}] Error code mismatch: expected '{expected_error_code}', got '{actual_error_code}'"
