"""
Tests the runtime flow for PRE_ACTION_TEXT_AND_ACTION, ensuring pre-action
text is correctly planned and emitted before action dispatch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add project root to path to allow imports of 'modules'
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.runtime.dispatch_pipeline import DispatchPipeline
from modules.agent.orchestration.shared.decision_models import ExecutionPlan


class SimpleNamespace:
    """A simple namespace for creating mock objects."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# --- Tests for _build_execution_plan ---


@pytest.fixture
def response_pipeline_stages_mixin() -> ResponsePipelineStagesMixin:
    """Provides a mocked mixin for testing execution plan creation."""
    mixin = ResponsePipelineStagesMixin()
    mixin.state = SimpleNamespace(active_intent=None, intent_runtime=None)
    mixin.semantics = MagicMock()
    mixin.semantics.has_any_action_proposal.return_value = True
    return mixin


def test_build_execution_plan_for_pre_action_text(response_pipeline_stages_mixin: ResponsePipelineStagesMixin):
    """
    Tests that _build_execution_plan creates a plan with output_effects for PRE_ACTION_TEXT_AND_ACTION.
    """
    mock_step = SimpleNamespace(intent_payload={"mode": "activate"})
    mock_ir = SimpleNamespace(
        has_pre_action_text=True,
        pre_action_text="Hello, I will now perform the action.",
        action_ops=[SimpleNamespace(action_type="test_action")],
    )
    mock_parsed_output = SimpleNamespace(compiler_shape="PRE_ACTION_TEXT_AND_ACTION", compiler_ir=mock_ir)

    plan = response_pipeline_stages_mixin._build_execution_plan(
        mock_step, mock_parsed_output, parsed_action_count=1
    )

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.action_effects) == 1
    assert len(plan.output_effects) == 1
    assert plan.output_effects[0] == "pre_action_text:Hello, I will now perform the action."
    assert not plan.action_dispatched


def test_build_execution_plan_for_action_only(response_pipeline_stages_mixin: ResponsePipelineStagesMixin):
    """
    Tests that _build_execution_plan creates a plan with empty output_effects for ACTION_ONLY.
    """
    mock_step = SimpleNamespace(intent_payload={"mode": "activate"})
    mock_ir = SimpleNamespace(
        has_pre_action_text=False,
        pre_action_text="",
        action_ops=[SimpleNamespace(action_type="test_action")],
    )
    mock_parsed_output = SimpleNamespace(compiler_shape="ACTION_ONLY", compiler_ir=mock_ir)

    plan = response_pipeline_stages_mixin._build_execution_plan(
        mock_step, mock_parsed_output, parsed_action_count=1
    )

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.action_effects) == 1
    assert len(plan.output_effects) == 0


# --- Tests for DispatchPipeline.run_iteration ---


@pytest.fixture
def dispatch_pipeline() -> DispatchPipeline:
    """Provides a mocked dispatch pipeline for testing."""
    mock_agent = SimpleNamespace(ui=AsyncMock())
    mock_dispatch_outcome = MagicMock()
    pipeline = DispatchPipeline(mock_agent, mock_dispatch_outcome)
    # Mock the parts we don't want to test
    pipeline._dispatch_segments = AsyncMock(return_value=([], [], False))
    pipeline.dispatch_outcome.handle = AsyncMock()
    pipeline.stage_logger = MagicMock()
    pipeline.execution_commit_observer = MagicMock()
    return pipeline


@pytest.mark.asyncio
async def test_dispatch_pipeline_emits_pre_action_text(dispatch_pipeline: DispatchPipeline):
    """
    Tests that DispatchPipeline.run_iteration calls ui.print_message for pre_action_text effects.
    """
    mock_plan = ExecutionPlan(
        shape="PRE_ACTION_TEXT_AND_ACTION",
        transaction_kind="atomic",
        output_effects=["pre_action_text:Hello there!"],
    )
    mock_iteration = SimpleNamespace(execution_plan=mock_plan, parsed_action_count=1, segments=[])

    await dispatch_pipeline.run_iteration(MagicMock(), mock_iteration)

    # Verify UI was called correctly
    assert dispatch_pipeline.ui.print_message.await_count == 1
    dispatch_pipeline.ui.print_message.assert_awaited_with("Hello there!", role="assistant")

    # Verify the action dispatch was still called
    assert dispatch_pipeline._dispatch_segments.await_count == 1


@pytest.mark.asyncio
async def test_dispatch_pipeline_no_ui_no_crash(dispatch_pipeline: DispatchPipeline):
    """
    Tests that DispatchPipeline.run_iteration does not crash if the UI is not present.
    """
    # Remove the UI from the mock agent
    dispatch_pipeline.agent.ui = None

    mock_plan = ExecutionPlan(
        shape="PRE_ACTION_TEXT_AND_ACTION",
        transaction_kind="atomic",
        output_effects=["pre_action_text:Hello there!"],
    )
    mock_iteration = SimpleNamespace(execution_plan=mock_plan, parsed_action_count=1, segments=[])

    # This should run without raising an exception
    await dispatch_pipeline.run_iteration(MagicMock(), mock_iteration)

    # Verify the action dispatch was still called
    assert dispatch_pipeline._dispatch_segments.await_count == 1


def test_compiler_valid_pre_action_text_override():
    """
    Tests the narrow override for compiler-valid PRE_ACTION_TEXT_AND_ACTION
    that is flagged as mixed_visible_text_and_control_protocol by legacy logic.
    """
    mixin = ResponsePipelineStagesMixin()

    # Positive case: compiler-valid pre-action text should be overridden
    positive_case = SimpleNamespace(
        invalid_kind="mixed_visible_text_and_control_protocol",
        compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
        compiler_error_code="",
        has_action_segment=True,
        compiler_ir=SimpleNamespace(
            action_count=1,
            has_pre_action_text=True,
            pre_action_text="I will inspect the file first.",
        ),
    )
    assert mixin._is_compiler_valid_pre_action_text(positive_case, parsed_action_count=1) is True

    # Negative case: different compiler shape
    negative_shape = SimpleNamespace(
        invalid_kind="mixed_visible_text_and_control_protocol",
        compiler_shape="ACTION_ONLY",
        compiler_error_code="",
        has_action_segment=True,
    )
    assert mixin._is_compiler_valid_pre_action_text(negative_shape, parsed_action_count=1) is False

    # Negative case: compiler error exists
    negative_error = SimpleNamespace(
        invalid_kind="mixed_visible_text_and_control_protocol",
        compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
        compiler_error_code="E_SOME_ERROR",
        has_action_segment=True,
    )
    assert mixin._is_compiler_valid_pre_action_text(negative_error, parsed_action_count=1) is False

    # Negative case: not a mixed protocol error
    negative_kind = SimpleNamespace(
        invalid_kind="some_other_error",
        compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
        compiler_error_code="",
        has_action_segment=True,
    )
    assert mixin._is_compiler_valid_pre_action_text(negative_kind, parsed_action_count=1) is False

    # Negative case: no action
    negative_no_action = SimpleNamespace(
        invalid_kind="mixed_visible_text_and_control_protocol",
        compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
        compiler_error_code="",
        has_action_segment=False,
    )
    assert mixin._is_compiler_valid_pre_action_text(negative_no_action, parsed_action_count=0) is False
