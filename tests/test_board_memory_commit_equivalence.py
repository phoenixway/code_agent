from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.agent.orchestration.protocol import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.runtime.memory_board_stage import MemoryBoardStageHandler


@dataclass
class LegacyCommitSnapshot:
    branch: str
    input_response: str
    compiler_shape: str
    compiler_error_code: str
    compiler_has_checkpoint: bool
    compiler_has_memory_checkpoint: bool
    compiler_has_action: bool
    compiler_has_visible_answer: bool
    typed_checkpoint_kind: str
    legacy_plan_outcome: str
    legacy_memory_outcome: str
    parity_aligned: bool
    handled: bool
    reason: str
    source: str
    response_text: str
    next_query: str | None
    memory_checkpoint_only: bool
    memory_checkpoint_and_text: bool
    memory_checkpoint_and_action: bool
    memory_commit_attempted: bool
    memory_commit_accepted_count: int
    memory_commit_rejected_count: int
    last_memory_update_done: bool
    dispatch_preserved: bool
    final_answer_preserved: bool
    snapshot_source: str
    memory_commit_mode: str
    blocking_reasons: list[str] = field(default_factory=list)


class _PlanPassThroughStage:
    async def apply(self, _ctx, response: str):
        return SimpleNamespace(
            handled=False,
            response_text=response,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )


class _StaticMemoryStage:
    def __init__(self, decision):
        self._decision = decision

    async def apply(self, _ctx, _response: str):
        return self._decision


class _CommitEquivalenceHarness(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
    def __init__(self, *, plan_board_stage=None, memory_board_stage=None):
        self.protocol_compiler = ProtocolCompiler()
        self.state = SimpleNamespace(
            active_intent=None,
            last_memory_update_done=False,
            last_memory_board_parsed_count=0,
            last_memory_board_accepted_count=0,
            last_memory_board_rejected_count=0,
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
        self.prompt_builder = SimpleNamespace()
        self.ui = AsyncMock()
        self.memory_checkpoint_hard_stop_streak = 3
        self.nonproductive_thinking_hard_stop_streak = 3

        self.plan_board_stage = plan_board_stage or _PlanPassThroughStage()
        self.memory_board_stage = memory_board_stage or _StaticMemoryStage(
            SimpleNamespace(handled=False, response_text="")
        )


def _run_commit_equivalence_harness(response: str, *, memory_board_stage=None):
    harness = _CommitEquivalenceHarness(memory_board_stage=memory_board_stage)
    if isinstance(harness.memory_board_stage, MemoryBoardStageHandler):
        harness.memory_board_stage.agent.state = harness.state
        harness.memory_board_stage.state = harness.state
        harness.memory_board_stage.stage_logger.state = harness.state

    state, outcome = asyncio.run(
        harness._run_checkpoint_stage(
            SimpleNamespace(),
            response,
            reflection_repair_pending=False,
            reflection_repair_kind="",
        )
    )

    semantic_result = state.board_checkpoint_semantic_result
    memory_board_decision = state.memory_board_decision

    snapshot_source = "unknown"
    memory_commit_mode = "unknown"
    memory_commit_attempted = False
    memory_commit_accepted_count = 0
    memory_commit_rejected_count = 0

    if isinstance(memory_board_stage, _StaticMemoryStage):
        snapshot_source = "static_memory_stage"
        memory_commit_mode = "controlled_static"
        memory_commit_attempted = bool(getattr(memory_board_decision, "memory_commit_attempted", False))
        memory_commit_accepted_count = int(getattr(memory_board_decision, "memory_commit_accepted_count", 0) or 0)
        memory_commit_rejected_count = int(getattr(memory_board_decision, "memory_commit_rejected_count", 0) or 0)
    elif isinstance(memory_board_stage, MemoryBoardStageHandler):
        snapshot_source = "memory_board_stage_handler"
        memory_commit_mode = "real_handler"
        engine = getattr(harness.memory_board_stage, "memory_board_engine", None)
        if engine:
            memory_commit_attempted = bool(getattr(getattr(engine, "apply_response_text", None), "called", False))
        else:
            memory_commit_attempted = False
        memory_commit_accepted_count = int(getattr(harness.state, "last_memory_board_accepted_count", 0) or 0)
        memory_commit_rejected_count = int(getattr(harness.state, "last_memory_board_rejected_count", 0) or 0)

    snapshot = LegacyCommitSnapshot(
        branch=semantic_result.kind.name,
        input_response=response,
        compiler_shape=semantic_result.compiler_shape,
        compiler_error_code=semantic_result.compiler_error_code,
        compiler_has_checkpoint=semantic_result.compiler_has_checkpoint,
        compiler_has_memory_checkpoint=semantic_result.compiler_has_memory_checkpoint,
        compiler_has_action=semantic_result.compiler_has_action,
        compiler_has_visible_answer=semantic_result.compiler_has_visible_text,
        typed_checkpoint_kind=semantic_result.kind.name,
        legacy_plan_outcome=semantic_result.legacy_plan_outcome,
        legacy_memory_outcome=semantic_result.legacy_memory_outcome,
        parity_aligned=semantic_result.parity_aligned,
        handled=bool(getattr(outcome, "handled", False)),
        reason=str(getattr(outcome, "reason", "") or ""),
        source=str(getattr(outcome, "source", "") or ""),
        response_text=str(getattr(outcome, "response_text", "") or ""),
        next_query=getattr(outcome, "next_query", None),
        memory_checkpoint_only=bool(getattr(outcome, "memory_checkpoint_only", False)),
        memory_checkpoint_and_text=bool(getattr(outcome, "memory_checkpoint_and_text", False)),
        memory_checkpoint_and_action=bool(getattr(outcome, "memory_checkpoint_and_action", False)),
        memory_commit_attempted=memory_commit_attempted,
        memory_commit_accepted_count=memory_commit_accepted_count,
        memory_commit_rejected_count=memory_commit_rejected_count,
        last_memory_update_done=bool(getattr(harness.state, "last_memory_update_done", False)),
        dispatch_preserved=outcome is None,
        final_answer_preserved=outcome is None,
        snapshot_source=snapshot_source,
        memory_commit_mode=memory_commit_mode,
    )
    return harness, state, outcome, snapshot


def test_memory_checkpoint_only_legacy_snapshot():
    response = "<memory_update_done />"
    memory_stage = _StaticMemoryStage(
        SimpleNamespace(
            handled=True,
            response_text=response,
            next_query="memory_followup",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_commit_attempted=True,
            memory_commit_accepted_count=1,
            memory_commit_rejected_count=0,
        )
    )

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(
        response, memory_board_stage=memory_stage
    )

    assert snapshot.branch == "MEMORY_CHECKPOINT_ONLY"
    assert snapshot.input_response == response
    assert snapshot.compiler_shape == "CHECKPOINT_ONLY"
    assert snapshot.compiler_error_code == ""
    assert snapshot.compiler_has_checkpoint is True
    assert snapshot.compiler_has_memory_checkpoint is True
    assert snapshot.typed_checkpoint_kind == "MEMORY_CHECKPOINT_ONLY"
    assert snapshot.legacy_memory_outcome == "checkpoint_only"
    assert snapshot.parity_aligned is True
    assert snapshot.handled is True
    assert snapshot.reason == "memory_checkpoint_only"
    assert snapshot.source == "memory_board"
    assert snapshot.next_query == "memory_followup"
    assert snapshot.memory_checkpoint_only is True
    assert snapshot.snapshot_source == "static_memory_stage"
    assert snapshot.memory_commit_mode == "controlled_static"
    assert snapshot.memory_commit_attempted is True
    assert snapshot.memory_commit_accepted_count == 1
    assert snapshot.memory_commit_rejected_count == 0
    assert snapshot.last_memory_update_done is False
    assert snapshot.dispatch_preserved is False
    assert snapshot.final_answer_preserved is False


@pytest.mark.parametrize(
    "response",
    [
        "Done.",
        '<action>{"type":"read_file","path":"README.md"}</action>',
        '<subgoal action="mark_in_progress" id="sg_1" />',
    ],
    ids=["plaintext_only", "action_only", "plan_checkpoint_only"],
)
def test_negative_controls_are_not_memory_commits(response):
    memory_stage = _StaticMemoryStage(
        SimpleNamespace(
            handled=False,
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_commit_attempted=False,
            memory_commit_accepted_count=0,
            memory_commit_rejected_count=0,
        )
    )
    harness, state, outcome, snapshot = _run_commit_equivalence_harness(
        response, memory_board_stage=memory_stage
    )

    assert snapshot.branch not in {
        "MEMORY_CHECKPOINT_ONLY",
        "MEMORY_CHECKPOINT_WITH_TEXT",
        "MEMORY_CHECKPOINT_WITH_ACTION",
    }
    assert snapshot.snapshot_source == "static_memory_stage"
    assert snapshot.memory_commit_mode == "controlled_static"
    assert snapshot.memory_commit_attempted is False
    assert snapshot.memory_commit_accepted_count == 0
    assert snapshot.last_memory_update_done is False


def test_memory_checkpoint_with_text_legacy_snapshot():
    response = "<memory_update_done />\nDone."
    memory_stage = _StaticMemoryStage(
        SimpleNamespace(
            handled=True,
            response_text="Done.",
            next_query=None,
            reason="memory_checkpoint_and_text",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
            memory_commit_attempted=True,
            memory_commit_accepted_count=1,
            memory_commit_rejected_count=0,
        )
    )

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(
        response, memory_board_stage=memory_stage
    )

    assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_TEXT"
    assert snapshot.legacy_memory_outcome == "checkpoint_and_text"
    assert snapshot.snapshot_source == "static_memory_stage"
    assert snapshot.memory_commit_mode == "controlled_static"
    assert snapshot.memory_commit_attempted is True
    assert snapshot.memory_commit_accepted_count == 1
    assert snapshot.dispatch_preserved is True
    assert snapshot.final_answer_preserved is True
    assert snapshot.handled is False


def test_memory_checkpoint_with_action_legacy_snapshot():
    response = '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>'
    memory_stage = _StaticMemoryStage(
        SimpleNamespace(
            handled=True,
            response_text='<action>{"type":"read_file","path":"README.md"}</action>',
            next_query=None,
            reason="memory_checkpoint_and_action",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=True,
            memory_commit_attempted=True,
            memory_commit_accepted_count=1,
            memory_commit_rejected_count=0,
        )
    )

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(
        response, memory_board_stage=memory_stage
    )

    assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_ACTION"
    assert snapshot.legacy_memory_outcome == "checkpoint_and_action"
    assert snapshot.snapshot_source == "static_memory_stage"
    assert snapshot.memory_commit_mode == "controlled_static"
    assert snapshot.memory_commit_attempted is True
    assert snapshot.memory_commit_accepted_count == 1
    assert snapshot.dispatch_preserved is True
    assert snapshot.final_answer_preserved is True
    assert snapshot.handled is False


def test_memory_checkpoint_only_real_handler_snapshot():
    response = "<memory_update_done />"

    mock_agent = SimpleNamespace(
        state=SimpleNamespace(),
        memory_board_engine=MagicMock(),
        log=None,
    )
    mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
    mock_board_result = SimpleNamespace(
        parsed_count=1,
        accepted_count=1,
        rejected_count=0,
        clean_text="",
    )
    mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result

    real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(response, memory_board_stage=real_handler)

    assert snapshot.branch == "MEMORY_CHECKPOINT_ONLY"
    assert snapshot.snapshot_source == "memory_board_stage_handler"
    assert snapshot.memory_commit_mode == "real_handler"
    assert snapshot.memory_commit_attempted is True
    assert snapshot.memory_commit_accepted_count == 1
    assert snapshot.memory_commit_rejected_count == 0
    assert snapshot.last_memory_update_done is True
    assert snapshot.handled is True
    assert snapshot.reason == "memory_checkpoint_only"
    assert snapshot.source == "memory_board"
    assert snapshot.memory_checkpoint_only is True
    assert snapshot.dispatch_preserved is False
    assert snapshot.final_answer_preserved is False

    mock_agent.memory_board_engine.apply_response_text.assert_called_once()
