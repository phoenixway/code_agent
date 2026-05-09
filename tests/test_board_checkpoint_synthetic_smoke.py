from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.agent.orchestration.config.switch_registry import _load_registry
from modules.agent.orchestration.protocol import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.runtime.plan_board_stage import PlanBoardStageHandler
from modules.agent.planner import TaskBoardPlanner


SMOKE_REGISTRY_PATH = "modules/agent/orchestration/config/refactor_switches.smoke.toml"


class _MemoryPassThroughStage:
    async def apply(self, _ctx, response: str):
        return SimpleNamespace(
            handled=False,
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class _CheckpointSmokeHarness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
    def __init__(self):
        self.protocol_compiler = ProtocolCompiler()
        self.state = SimpleNamespace(
            active_intent=None,
            last_memory_update_done=False,
            task_board=None,
            task_board_enabled=False,
            last_plan_subgoal_create_count=0,
        )
        self.semantics = SimpleNamespace(has_substantial_think=MagicMock(return_value=False))
        self.guards = SimpleNamespace(
            reflection_repair_pending=MagicMock(return_value=False),
            reflection_repair_kind=MagicMock(return_value=""),
            memory_checkpoint_streak=MagicMock(return_value=1),
            set_reflection_repair_pending=MagicMock(),
            set_nonproductive_thinking_state=MagicMock(),
        )
        self.stage_logger = SimpleNamespace(log=MagicMock(), log_architecture_defect=MagicMock())
        self.prompt_builder = SimpleNamespace(
            build_reflection_repair_accepted_prompt=MagicMock(return_value="repair_accepted_prompt"),
            build_durable_state_repair_prompt=MagicMock(return_value="durable_state_repair_prompt"),
            build_repeated_thinking_without_valid_output_prompt=MagicMock(return_value="repeated_thinking_prompt"),
        )
        self.ui = AsyncMock()
        self.memory_checkpoint_hard_stop_streak = 3
        self.nonproductive_thinking_hard_stop_streak = 3

        config = SimpleNamespace(
            PLANNER_ENABLED=True,
            PLANNER_MODE="always",
            PLANNER_MAX_GOAL_CHARS=240,
            PLANNER_MAX_STEPS=12,
            PLANNER_MAX_STEP_TITLE_CHARS=160,
            PLANNER_MAX_STEP_NOTES_CHARS=240,
            PLANNER_MAX_VISIBLE_STEPS=4,
        )
        agent = SimpleNamespace(
            state=self.state,
            config=config,
            planner=TaskBoardPlanner(config),
            ui=SimpleNamespace(print_plan=AsyncMock()),
            log=None,
        )
        self.plan_board_stage = PlanBoardStageHandler(agent, self.prompt_builder)
        self.memory_board_stage = _MemoryPassThroughStage()


@pytest.fixture
def smoke_registry_override():
    with patch.dict(
        os.environ,
        {"ANGELICA_REFACTOR_SWITCH_REGISTRY": SMOKE_REGISTRY_PATH},
        clear=False,
    ):
        _load_registry.cache_clear()
        try:
            yield
        finally:
            _load_registry.cache_clear()


def _run_checkpoint_stage(response: str):
    harness = _CheckpointSmokeHarness()
    state, outcome = asyncio.run(
        harness._run_checkpoint_stage(
            SimpleNamespace(),
            response,
            reflection_repair_pending=False,
            reflection_repair_kind="",
        )
    )
    return harness, state, outcome


def test_smoke_registry_file_exists():
    assert Path(SMOKE_REGISTRY_PATH).exists()


@pytest.mark.parametrize(
    "response",
    [
        '<subgoal action="mark_in_progress" id="sg_1"/>',
        '<subgoal action="mark_in_progress" id="sg_1" />',
    ],
    ids=["self_closing_no_space", "self_closing_with_space"],
)
def test_compiler_recognizes_self_closing_subgoal_checkpoint_only(response):
    analysis = ProtocolCompiler().analyze(response)

    assert analysis.error is None
    assert analysis.shape.name == "CHECKPOINT_ONLY"
    assert analysis.ir is not None
    assert analysis.ir.has_checkpoint is True
    assert analysis.ir.has_subgoal_tags is True
    assert analysis.ir.has_memory_tags is False
    assert analysis.ir.has_memory_checkpoint is False
    assert analysis.ir.has_action is False
    assert analysis.ir.has_visible_answer is False
    assert analysis.ir.visible_text_source == "NONE"


@pytest.mark.parametrize(
    "response",
    [
        '<subgoal action="mark_in_progress" id="sg_1"/>',
        '<subgoal action="mark_in_progress" id="sg_1" />',
    ],
    ids=["no_space_before_slash", "space_before_slash"],
)
def test_plan_checkpoint_only_smoke_routes_without_parity_mismatch(response, smoke_registry_override):
    harness, state, outcome = _run_checkpoint_stage(response)

    assert outcome is not None
    assert outcome.continue_loop is True
    assert outcome.reason == "plan_checkpoint_only"
    assert outcome.source in {"plan_board", "compiler_authority"}
    assert state.plan_checkpoint_only is True
    assert state.plan_checkpoint_and_text is False
    assert state.plan_checkpoint_and_action is False
    assert state.memory_checkpoint_only is False
    assert state.compiler_analysis is not None
    assert state.compiler_analysis.error is None
    assert state.compiler_analysis.shape.name == "CHECKPOINT_ONLY"
    assert state.compiler_analysis.ir.has_subgoal_tags is True
    assert state.compiler_analysis.ir.has_checkpoint is True
    assert state.compiler_analysis.ir.has_visible_answer is False
    assert state.compiler_analysis.ir.has_action is False
    assert state.board_checkpoint_semantic_result.compiler_has_subgoal_tags is True
    assert state.board_checkpoint_semantic_result.compiler_has_checkpoint is True
    assert state.board_checkpoint_semantic_result.compiler_shape == "CHECKPOINT_ONLY"
    assert state.board_checkpoint_semantic_result.parity_aligned is True
    assert state.board_checkpoint_semantic_result.parity_mismatch_reason == ""
    assert state.board_checkpoint_semantic_result.legacy_memory_outcome == "none"
    assert state.board_checkpoint_semantic_result.legacy_plan_outcome == "checkpoint_only"
    parity_calls = [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "board_checkpoint_structural_parity")
    ]
    assert len(parity_calls) == 1
    assert parity_calls[0].kwargs["compiler_has_checkpoint"] is True
    assert parity_calls[0].kwargs["compiler_has_subgoal_tags"] is True
    assert parity_calls[0].kwargs["parity_aligned"] is True
    assert parity_calls[0].kwargs["mismatch_reason"] == ""
    authority_calls = [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "board_checkpoint_authority_resolution")
    ]
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["branch"] == "board_checkpoint.plan_checkpoint_only"
    assert final_authority.kwargs["switch_value"] == "compiler"
    assert final_authority.kwargs["authority_source"] == "legacy"
    assert final_authority.kwargs["typed_kind"] == "PLAN_CHECKPOINT_ONLY"
    assert final_authority.kwargs["legacy_active"] is True
    assert final_authority.kwargs["agreement"] is True
    assert final_authority.kwargs["fallback_used"] is False
    assert final_authority.kwargs["behavior_changed"] is False


def test_plan_checkpoint_with_text_is_not_treated_as_checkpoint_only(smoke_registry_override):
    response = '<subgoal action="mark_in_progress" id="sg_1" />\nDone.'

    harness, state, outcome = _run_checkpoint_stage(response)

    assert state.compiler_analysis is not None
    assert state.compiler_analysis.error is None
    assert state.compiler_analysis.shape.name == "SUBGOAL_WITH_TEXT"
    assert state.compiler_analysis.ir.has_subgoal_tags is True
    assert state.compiler_analysis.ir.has_visible_answer is True
    assert state.plan_checkpoint_only is False
    assert state.plan_checkpoint_and_text is True
    assert state.plan_checkpoint_and_action is False
    assert outcome is None
    assert state.board_checkpoint_semantic_result.parity_aligned is True


def test_plan_checkpoint_with_action_is_not_treated_as_checkpoint_only(smoke_registry_override):
    response = (
        '<subgoal action="mark_in_progress" id="sg_1" />\n'
        '<action>{"type":"read_file","path":"README.md"}</action>'
    )

    harness, state, outcome = _run_checkpoint_stage(response)

    assert state.compiler_analysis is not None
    assert state.compiler_analysis.error is None
    assert state.compiler_analysis.shape.name == "ACTION_ONLY"
    assert state.compiler_analysis.ir.has_subgoal_tags is True
    assert state.compiler_analysis.ir.has_action is True
    assert state.plan_checkpoint_only is False
    assert state.plan_checkpoint_and_action is True
    assert outcome is None
    assert state.board_checkpoint_semantic_result.parity_aligned is True
    assert state.board_checkpoint_semantic_result.parity_mismatch_reason == ""
    parity_calls = [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "board_checkpoint_structural_parity")
    ]
    assert len(parity_calls) == 1
    assert parity_calls[0].kwargs["legacy_checkpoint_with_action"] is True
    assert parity_calls[0].kwargs["compiler_has_action"] is True


def test_action_only_negative_control_has_no_checkpoint_mismatch(smoke_registry_override):
    response = '<action>{"type":"read_file","path":"README.md"}</action>'

    harness, state, outcome = _run_checkpoint_stage(response)

    assert outcome is None
    assert state.plan_checkpoint_only is False
    assert state.plan_checkpoint_and_text is False
    assert state.plan_checkpoint_and_action is False
    assert state.memory_checkpoint_only is False
    assert state.compiler_analysis is not None
    assert state.compiler_analysis.error is None
    assert state.compiler_analysis.shape.name == "ACTION_ONLY"
    assert state.compiler_analysis.ir.has_checkpoint is False
    assert state.compiler_analysis.ir.has_subgoal_tags is False
    assert state.board_checkpoint_semantic_result.kind.name == "NONE"
    assert state.board_checkpoint_semantic_result.parity_aligned is True
    assert state.board_checkpoint_semantic_result.parity_mismatch_reason == ""
    parity_calls = [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "board_checkpoint_structural_parity")
    ]
    assert len(parity_calls) == 1
    assert parity_calls[0].kwargs["compiler_has_checkpoint"] is False
    assert parity_calls[0].kwargs["mismatch_reason"] == ""
    authority_calls = [
        call
        for call in harness.stage_logger.log.call_args_list
        if call.args[:2] == ("protocol_shadow", "board_checkpoint_authority_resolution")
    ]
    assert len(authority_calls) >= 1
    final_authority = authority_calls[-1]
    assert final_authority.kwargs["branch"] == "board_checkpoint.plan_checkpoint_only"
    assert final_authority.kwargs["switch_value"] == "compiler"
    assert final_authority.kwargs["authority_source"] == "legacy_fallback"
    assert final_authority.kwargs["branch_active"] is False
    assert final_authority.kwargs["fallback_used"] is True
    assert final_authority.kwargs["behavior_changed"] is False
