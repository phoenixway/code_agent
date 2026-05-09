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


def test_build_execution_plan_sets_action_dispatched_false_for_generic_dispatch(
    response_pipeline_stages_mixin: ResponsePipelineStagesMixin,
):
    """
    Documents that ExecutionPlan.action_dispatched is False for generic
    dispatch-ready outcomes, as it's specific to atomic bundles.
    """
    mock_step = SimpleNamespace(intent_payload={"mode": "activate"})
    mock_ir = SimpleNamespace(
        has_pre_action_text=False,
        pre_action_text="",
        action_ops=[SimpleNamespace(action_type="test_action")],
    )
    mock_parsed_output = SimpleNamespace(compiler_shape="ACTION_ONLY", compiler_ir=mock_ir)

    plan = response_pipeline_stages_mixin._build_execution_plan(mock_step, mock_parsed_output, parsed_action_count=1)

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.action_effects) == 1
    assert not plan.action_dispatched


def test_build_execution_plan_for_atomic_bundle_is_still_false(
    response_pipeline_stages_mixin: ResponsePipelineStagesMixin,
):
    """
    Documents that ExecutionPlan.action_dispatched is False even for
    atomic bundles, as this flag is not populated by the current plan builder.
    """
    mock_step = SimpleNamespace(intent_payload={"mode": "activate"})
    mock_ir = SimpleNamespace(
        has_pre_action_text=False,
        pre_action_text="",
        action_ops=[SimpleNamespace(action_type="test_action")],
    )
    mock_parsed_output = SimpleNamespace(compiler_shape="INTENT_ACTION_BUNDLE", compiler_ir=mock_ir)

    plan = response_pipeline_stages_mixin._build_execution_plan(mock_step, mock_parsed_output, parsed_action_count=1)

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.action_effects) == 1
    assert not plan.action_dispatched


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


def test_single_action_plan_parity_probe_uses_existing_segments_for_eligible_slice(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:README.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="read_file",
                        payload={"type": "read_file", "path": "README.md"},
                        file_content=None,
                    )
                ]
            )
        ),
        segments=segments,
    )

    bridged_segments, used_bridge, reason = dispatch_pipeline._resolve_dispatch_segments(iteration)

    assert bridged_segments is segments
    assert used_bridge is True
    assert reason == "single_action_ir_parity"


def test_single_action_plan_dispatch_candidate_builds_for_eligible_read_file(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:README.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=SimpleNamespace(
                has_pre_action_text=False,
                pre_action_text="",
                action_ops=[
                    SimpleNamespace(
                        action_type="read_file",
                        payload={"type": "read_file", "path": "README.md"},
                        file_content=None,
                    )
                ],
            ),
        ),
        segments=segments,
    )

    candidate, reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is not None
    assert reason == "single_action_ir_candidate"
    assert candidate.action_type == "read_file"
    assert candidate.payload == {"type": "read_file", "path": "README.md"}
    assert candidate.action_summary == "read_file:README.md"
    assert candidate.source == "compiler_ir"
    assert candidate.matched_segment_index == 0
    assert candidate.compiler_shape == "ACTION_ONLY"
    assert candidate.transaction_kind == "atomic_intent_action_bundle"
    assert candidate.pre_action_text is None


def test_single_action_plan_parity_probe_falls_back_without_execution_plan(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=None,
        parsed_output=SimpleNamespace(
            compiler_ir=SimpleNamespace(
                action_ops=[SimpleNamespace(action_type="read_file", payload={"type": "read_file", "path": "README.md"}, file_content=None)]
            )
        ),
        segments=segments,
    )

    bridged_segments, used_bridge, reason = dispatch_pipeline._resolve_dispatch_segments(iteration)

    assert bridged_segments is segments
    assert used_bridge is False
    assert reason == "no_execution_plan"

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "no_execution_plan"


def test_single_action_plan_parity_probe_falls_back_without_compiler_ir(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:README.md"],
        ),
        parsed_output=SimpleNamespace(compiler_ir=None),
        segments=segments,
    )

    bridged_segments, used_bridge, reason = dispatch_pipeline._resolve_dispatch_segments(iteration)

    assert bridged_segments is segments
    assert used_bridge is False
    assert reason == "no_compiler_ir"

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "no_compiler_ir"


def test_single_action_plan_parity_probe_falls_back_when_ir_action_count_is_not_one(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:README.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(action_type="read_file", payload={"type": "read_file", "path": "README.md"}, file_content=None),
                    SimpleNamespace(action_type="read_chunk", payload={"type": "read_chunk", "path": "x.py"}, file_content=None),
                ]
            )
        ),
        segments=segments,
    )

    bridged_segments, used_bridge, reason = dispatch_pipeline._resolve_dispatch_segments(iteration)

    assert bridged_segments is segments
    assert used_bridge is False
    assert reason == "ir_action_count_not_one"

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "ir_action_count_not_one"


def test_single_action_plan_parity_probe_falls_back_on_payload_mismatch(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:README.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="read_file",
                        payload={"type": "read_file", "path": "OTHER.md"},
                        file_content=None,
                    )
                ]
            )
        ),
        segments=segments,
    )

    bridged_segments, used_bridge, reason = dispatch_pipeline._resolve_dispatch_segments(iteration)

    assert bridged_segments is segments
    assert used_bridge is False
    assert reason == "payload_mismatch"

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "payload_mismatch"


def test_single_action_plan_dispatch_candidate_falls_back_on_summary_mismatch(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:OTHER.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=SimpleNamespace(
                has_pre_action_text=False,
                pre_action_text="",
                action_ops=[
                    SimpleNamespace(
                        action_type="read_file",
                        payload={"type": "read_file", "path": "README.md"},
                        file_content=None,
                    )
                ],
            ),
        ),
        segments=segments,
    )

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "action_effect_mismatch"


def test_single_action_plan_parity_probe_falls_back_on_unsupported_action_shape(dispatch_pipeline: DispatchPipeline):
    segments = [
        SimpleNamespace(type="action", content={"type": "write_file_block", "path": "docs/x.md", "overwrite": True}),
        SimpleNamespace(type="file_content", content="body"),
    ]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="INTENT_ACTION_BUNDLE",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["write_file_block:docs/x.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="write_file_block",
                        payload={"type": "write_file_block", "path": "docs/x.md", "overwrite": True},
                        file_content="body",
                    )
                ]
            )
        ),
        segments=segments,
    )

    bridged_segments, used_bridge, reason = dispatch_pipeline._resolve_dispatch_segments(iteration)

    assert bridged_segments is segments
    assert used_bridge is False
    assert reason == "unsupported_action_shape"

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "unsupported_action_shape"


def test_single_action_plan_dispatch_candidate_falls_back_on_multiple_segment_actions(dispatch_pipeline: DispatchPipeline):
    segments = [
        SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"}),
        SimpleNamespace(type="action", content={"type": "read_chunk", "path": "x.py", "start_line": 1, "end_line": 5}),
    ]
    iteration = SimpleNamespace(
        execution_plan=ExecutionPlan(
            shape="ACTION_ONLY",
            transaction_kind="atomic_intent_action_bundle",
            action_effects=["read_file:README.md"],
        ),
        parsed_output=SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=SimpleNamespace(
                has_pre_action_text=False,
                pre_action_text="",
                action_ops=[
                    SimpleNamespace(
                        action_type="read_file",
                        payload={"type": "read_file", "path": "README.md"},
                        file_content=None,
                    )
                ],
            ),
        ),
        segments=segments,
    )

    candidate, candidate_reason = dispatch_pipeline._build_single_action_plan_dispatch_candidate(iteration)

    assert candidate is None
    assert candidate_reason == "no_matching_segment_action"


@pytest.mark.asyncio
async def test_dispatch_pipeline_eligible_bridge_keeps_dispatch_behavior_unchanged(dispatch_pipeline: DispatchPipeline):
    segments = [SimpleNamespace(type="action", content={"type": "read_file", "path": "README.md"})]
    mock_plan = ExecutionPlan(
        shape="ACTION_ONLY",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=["read_file:README.md"],
    )
    mock_iteration = SimpleNamespace(
        execution_plan=mock_plan,
        parsed_action_count=1,
        parsed_output=SimpleNamespace(
            compiler_ir=SimpleNamespace(
                action_ops=[
                    SimpleNamespace(
                        action_type="read_file",
                        payload={"type": "read_file", "path": "README.md"},
                        file_content=None,
                    )
                ]
            )
        ),
        segments=segments,
    )

    await dispatch_pipeline.run_iteration(MagicMock(), mock_iteration)

    dispatch_pipeline._dispatch_segments.assert_awaited_once()
    called_ctx, called_segments = dispatch_pipeline._dispatch_segments.await_args.args
    assert called_segments is segments
