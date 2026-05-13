from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.agent.orchestration.config.switch_registry import get_switch, _load_registry
from modules.agent.orchestration.protocol import ProtocolCompiler
from modules.agent.orchestration.responses.memory_commit_authority import (
    build_memory_checkpoint_only_commit_candidate,
    build_memory_checkpoint_with_action_commit_candidate,
    build_memory_checkpoint_with_text_commit_candidate,
    build_memory_content_with_action_commit_candidate,
    resolve_memory_checkpoint_only_commit_authority,
    resolve_memory_checkpoint_with_action_commit_authority,
    resolve_memory_checkpoint_with_text_commit_authority,
    resolve_memory_content_with_action_commit_authority,
)
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
    visible_text_before_memory_stage: str | None = None
    visible_text_after_memory_stage: str | None = None
    checkpoint_removed_from_visible_response: bool | None = None
    visible_text_preserved: bool | None = None
    pass_through_preserved: bool | None = None
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


SMOKE_REGISTRY_PATH = "modules/agent/orchestration/config/refactor_switches.smoke.toml"


@pytest.fixture
def smoke_registry_override():
    """Fixture to override the switch registry with the smoke profile for a test."""
    original_env = os.environ.get("ANGELICA_REFACTOR_SWITCH_REGISTRY")
    os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = SMOKE_REGISTRY_PATH
    _load_registry.cache_clear()
    try:
        yield
    finally:
        if original_env is None:
            os.environ.pop("ANGELICA_REFACTOR_SWITCH_REGISTRY", None)
        else:
            os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = original_env
        _load_registry.cache_clear()


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
        memory_commit_accepted_count = int(getattr(harness.state, "last_memory_board_accepted_count", 0) or 0)
        memory_commit_rejected_count = int(getattr(harness.state, "last_memory_board_rejected_count", 0) or 0)
        is_mct = getattr(getattr(semantic_result, "kind", None), "name", "") == "MEMORY_CHECKPOINT_WITH_TEXT"
        is_mca = getattr(getattr(semantic_result, "kind", None), "name", "") == "MEMORY_CHECKPOINT_WITH_ACTION"
        if (
            (is_mct or is_mca)
            and memory_commit_accepted_count == 0
            and memory_commit_rejected_count == 0
        ):
            memory_commit_attempted = False
        elif engine:
            memory_commit_attempted = bool(getattr(getattr(engine, "apply_response_text", None), "called", False))
        else:
            memory_commit_attempted = False

    temp_handler = MemoryBoardStageHandler(SimpleNamespace(state=SimpleNamespace(), log=None), None)
    visible_text_before_memory_stage = response
    visible_text_after_memory_stage = str(
        getattr(memory_board_decision, "response_text", "")
        or getattr(outcome, "response_text", "")
        or getattr(state, "response", "")
        or ""
    )
    checkpoint_removed = (
        "<memory_update_done />" in str(visible_text_before_memory_stage or "").lower()
        and "<memory_update_done />" not in str(visible_text_after_memory_stage or "").lower()
    )
    stripped_before = temp_handler._strip_control_blocks_for_visible_text(visible_text_before_memory_stage).strip()
    stripped_after = temp_handler._strip_control_blocks_for_visible_text(visible_text_after_memory_stage).strip()
    visible_text_preserved = stripped_before == stripped_after

    is_memory_checkpoint_with_text = (
        getattr(getattr(semantic_result, "kind", None), "name", "") == "MEMORY_CHECKPOINT_WITH_TEXT"
    )
    if is_memory_checkpoint_with_text:
        handled_value = bool(getattr(outcome, "handled", False))
        pass_through_preserved = (not handled_value) and bool(visible_text_after_memory_stage.strip())
        dispatch_preserved = pass_through_preserved
        final_answer_preserved = pass_through_preserved
    else:
        pass_through_preserved = outcome is None
        dispatch_preserved = outcome is None
        final_answer_preserved = outcome is None

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
        response_text=visible_text_after_memory_stage,
        next_query=getattr(outcome, "next_query", None),
        memory_checkpoint_only=bool(getattr(outcome, "memory_checkpoint_only", False)),
        memory_checkpoint_and_text=bool(getattr(outcome, "memory_checkpoint_and_text", False)),
        memory_checkpoint_and_action=bool(getattr(outcome, "memory_checkpoint_and_action", False)),
        memory_commit_attempted=memory_commit_attempted,
        memory_commit_accepted_count=memory_commit_accepted_count,
        memory_commit_rejected_count=memory_commit_rejected_count,
        last_memory_update_done=bool(getattr(harness.state, "last_memory_update_done", False)),
        dispatch_preserved=dispatch_preserved,
        final_answer_preserved=final_answer_preserved,
        snapshot_source=snapshot_source,
        memory_commit_mode=memory_commit_mode,
        pass_through_preserved=pass_through_preserved,
        visible_text_before_memory_stage=visible_text_before_memory_stage,
        visible_text_after_memory_stage=visible_text_after_memory_stage,
        checkpoint_removed_from_visible_response=checkpoint_removed,
        visible_text_preserved=visible_text_preserved,
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
    # A marker-only response does not result in a memory commit, so counts are 0.
    mock_board_result = SimpleNamespace(
        parsed_count=0,
        accepted_count=0,
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
    assert snapshot.memory_commit_accepted_count == 0
    assert snapshot.memory_commit_rejected_count == 0
    assert snapshot.last_memory_update_done is True
    assert snapshot.handled is True
    assert snapshot.reason == "memory_checkpoint_only"
    assert snapshot.source == "memory_board"
    assert snapshot.memory_checkpoint_only is True
    assert snapshot.dispatch_preserved is False
    assert snapshot.final_answer_preserved is False

    mock_agent.memory_board_engine.apply_response_text.assert_called_once()


def test_memory_checkpoint_with_text_real_handler_snapshot():
    response = "<memory_update_done />\nDone."
    mock_agent = SimpleNamespace(
        state=SimpleNamespace(),
        memory_board_engine=MagicMock(),
        log=None,
    )
    mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
    mock_board_result = SimpleNamespace(
        parsed_count=0,
        accepted_count=0,
        rejected_count=0,
        clean_text="Done.",
    )
    mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
    real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(response, memory_board_stage=real_handler)

    assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_TEXT"
    assert snapshot.compiler_shape in {"MEMORY_TEXT", "PURE_PLAINTEXT"}
    assert snapshot.compiler_has_memory_checkpoint is True
    assert snapshot.compiler_has_visible_answer is True
    assert snapshot.compiler_has_action is False
    assert snapshot.legacy_memory_outcome == "checkpoint_and_text"
    assert snapshot.parity_aligned is True
    assert snapshot.visible_text_after_memory_stage == "Done."
    assert snapshot.visible_text_preserved is True
    assert snapshot.checkpoint_removed_from_visible_response is True
    assert snapshot.memory_commit_attempted is False
    assert snapshot.memory_commit_accepted_count == 0
    assert snapshot.memory_commit_rejected_count == 0
    assert snapshot.last_memory_update_done is True
    assert snapshot.handled is False
    assert snapshot.pass_through_preserved is True
    assert snapshot.dispatch_preserved is True
    assert snapshot.final_answer_preserved is True


@pytest.mark.parametrize(
    "response",
    [
        "<memory_update_done />",
        '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>',
        "Done.",
        '<subgoal action="mark_in_progress" id="sg_1" />\nDone.',
    ],
    ids=[
        "marker_only_mco",
        "mco_with_action",
        "plaintext_only",
        "plan_checkpoint_with_text",
    ],
)
def test_memory_checkpoint_with_text_harness_negative_controls(response):
    harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
    assert snapshot.branch != "MEMORY_CHECKPOINT_WITH_TEXT"


def test_memory_checkpoint_with_action_real_handler_snapshot():
    """Characterizes a real-handler-backed snapshot with a mocked board engine result."""
    response = '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>'
    mock_agent = SimpleNamespace(
        state=SimpleNamespace(),
        memory_board_engine=MagicMock(),
        log=None,
    )
    mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
    # For MCTA, the handler strips the marker and returns the action.
    # The commit is for the marker only, so counts are 0.
    mock_board_result = SimpleNamespace(
        parsed_count=0,
        accepted_count=0,
        rejected_count=0,
        clean_text='<action>{"type":"read_file","path":"README.md"}</action>',
    )
    mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
    real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(response, memory_board_stage=real_handler)

    assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_ACTION"
    # The compiler prepass runs on the raw response, so it sees the memory marker.
    assert snapshot.compiler_has_memory_checkpoint is True
    assert snapshot.compiler_has_action is True
    # The compiler may classify a response with a memory marker and an action as
    # ACTION_ONLY, treating the marker as metadata. This is an observation-
    # boundary issue to be aware of, not necessarily a bug.
    assert snapshot.compiler_shape == "ACTION_ONLY"
    assert snapshot.legacy_memory_outcome == "checkpoint_and_action"
    assert snapshot.parity_aligned is True
    assert snapshot.response_text == '<action>{"type":"read_file","path":"README.md"}</action>'
    assert snapshot.visible_text_preserved is True
    assert snapshot.checkpoint_removed_from_visible_response is True
    # A commit is not considered "attempted" for a marker-only checkpoint with action,
    # as no content is committed.
    assert snapshot.memory_commit_attempted is False
    assert snapshot.memory_commit_accepted_count == 0
    assert snapshot.memory_commit_rejected_count == 0
    assert snapshot.last_memory_update_done is True
    # handled=False means pass-through to dispatch.
    assert snapshot.handled is False
    assert snapshot.pass_through_preserved is True
    assert snapshot.dispatch_preserved is True
    assert snapshot.final_answer_preserved is True


@pytest.mark.parametrize(
    "response",
    [
        "<memory_update_done />",
        '<action>{"type":"read_file","path":"README.md"}</action>',
        "Done.",
        '<subgoal action="mark_in_progress" id="sg_1" />\n<action>{"type":"read_file","path":"README.md"}</action>',
        "<memory_update_done />\nDone.",
    ],
    ids=[
        "marker_only_mco",
        "action_only",
        "plaintext_only",
        "plan_checkpoint_with_action",
        "memory_checkpoint_with_text",
    ],
)
def test_memory_checkpoint_with_action_harness_negative_controls(response):
    harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
    assert snapshot.branch != "MEMORY_CHECKPOINT_WITH_ACTION"


def test_memory_content_with_action_real_handler_snapshot():
    """Characterizes a real-handler-backed snapshot for memory content + action."""
    response = '<fact>some fact</fact>\n<action>{"type":"read_file","path":"README.md"}</action>'
    mock_agent = SimpleNamespace(
        state=SimpleNamespace(),
        memory_board_engine=MagicMock(),
        log=None,
    )
    mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
    # For MCTA with content, the handler strips the memory tag and returns the action.
    # The commit is for the content, so counts are 1.
    mock_board_result = SimpleNamespace(
        parsed_count=1,
        accepted_count=1,
        rejected_count=0,
        clean_text='<action>{"type":"read_file","path":"README.md"}</action>',
    )
    mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
    real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

    harness, state, outcome, snapshot = _run_commit_equivalence_harness(response, memory_board_stage=real_handler)

    assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_ACTION"
    # <fact>...</fact> is durable memory content, not the bare <memory_update_done /> marker.
    # The legacy memory board classifies this as checkpoint_and_action, but
    # compiler_has_memory_checkpoint remains False because it is specific to the marker.
    assert snapshot.compiler_has_memory_checkpoint is False
    assert snapshot.compiler_has_action is True
    assert snapshot.legacy_memory_outcome == "checkpoint_and_action"
    assert snapshot.parity_aligned is True
    assert snapshot.response_text == '<action>{"type":"read_file","path":"README.md"}</action>'
    assert snapshot.visible_text_preserved is True
    assert snapshot.checkpoint_removed_from_visible_response is False  # No <memory_update_done />
    assert snapshot.memory_commit_attempted is True
    assert snapshot.memory_commit_accepted_count == 1
    assert snapshot.memory_commit_rejected_count == 0
    assert snapshot.last_memory_update_done is False  # No <memory_update_done />
    assert snapshot.handled is False
    assert snapshot.pass_through_preserved is True
    assert snapshot.dispatch_preserved is True
    assert snapshot.final_answer_preserved is True


class TestMemoryCommitAuthority:
    def test_candidate_builder_for_real_handler_mco(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        candidate = build_memory_checkpoint_only_commit_candidate(state.board_checkpoint_semantic_result)

        assert candidate.candidate_available is True
        assert candidate.branch == "MEMORY_CHECKPOINT_ONLY"
        assert candidate.has_memory_checkpoint is True
        assert candidate.has_plan_checkpoint is False
        assert candidate.has_action is False
        assert candidate.has_visible_text is False
        assert candidate.compiler_error_code == ""
        assert candidate.expected_handled is True
        assert candidate.expected_reason == "memory_checkpoint_only"
        assert candidate.expected_source == "memory_board"
        assert candidate.expected_commit_attempted is True
        assert candidate.expected_commit_accepted_count == 0  # Not predicted
        assert candidate.expected_commit_rejected_count == 0  # Not predicted
        assert candidate.expected_last_memory_update_done is True
        assert candidate.blocking_reasons == ("commit_counts_not_typed", "next_query_not_typed")

    @pytest.mark.parametrize(
        "response",
        [
            "Done.",
            '<action>{"type":"read_file","path":"README.md"}</action>',
            '<subgoal action="mark_in_progress" id="sg_1" />',
            "<memory_update_done />\nDone.",
            '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>',
        ],
        ids=[
            "plaintext_only",
            "action_only",
            "plan_checkpoint_only",
            "memory_checkpoint_with_text",
            "memory_checkpoint_with_action",
        ],
    )
    def test_candidate_builder_unavailable_for_negative_controls(self, response):
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
        candidate = build_memory_checkpoint_only_commit_candidate(state.board_checkpoint_semantic_result)
        assert candidate.candidate_available is False

    def test_resolver_legacy_mode_preserves_legacy_decision(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value="legacy",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_only"
        assert diag.switch_value == "legacy"
        assert diag.authority_source == "legacy"
        assert diag.selected_by_switch is False
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False
        assert decision.effective_commit.handled == snapshot.handled
        assert decision.effective_commit.reason == snapshot.reason

    def test_resolver_compiler_mode_falls_back_when_equivalence_unproven(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        # Create a mismatch in accepted_count
        mock_board_result = SimpleNamespace(parsed_count=1, accepted_count=1, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value="compiler",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_only"
        assert diag.switch_value == "compiler"
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.candidate_available is True
        assert diag.fallback_used is True
        assert diag.behavior_changed is False


@pytest.mark.usefixtures("smoke_registry_override")
class TestMemoryCheckpointWithActionSmokeValidation:
    def _get_mcta_snapshot(self):
        return _get_mcta_snapshot_for_test()

    def test_smoke_compiler_authority_selected_for_mcta(self):
        state, snapshot = self._get_mcta_snapshot()
        switch_value = get_switch("board_memory.memory_checkpoint_with_action")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_with_action"
        assert diag.switch_value == "compiler"
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False

    def test_smoke_compiler_authority_falls_back_on_mismatch_for_mcta(self):
        state, snapshot = self._get_mcta_snapshot()
        switch_value = get_switch("board_memory.memory_checkpoint_with_action")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text="mismatched text",
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.commit_equivalent is False
        assert diag.response_text_agreement is False
        assert diag.fallback_used is True
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "response",
        [
            "<memory_update_done />",
            "Done.",
            '<subgoal action="mark_in_progress" id="sg_1" />\nDone.',
        ],
        ids=[
            "marker_only_mco",
            "plaintext_only",
            "plan_checkpoint_with_text",
        ],
    )
    def test_smoke_compiler_authority_not_used_for_mcta_negative_controls(self, response):
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
        switch_value = get_switch("board_memory.memory_checkpoint_with_action")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.candidate_available is False
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.fallback_used is True
        assert diag.commit_equivalent is False
        assert diag.behavior_changed is False

    def test_candidate_builder_has_no_runtime_handler_dependency(self):
        """The candidate builder must not import or instantiate MemoryBoardStageHandler."""
        import modules.agent.orchestration.responses.memory_commit_authority as authority_module

        assert not hasattr(authority_module, "MemoryBoardStageHandler")


@pytest.mark.usefixtures("smoke_registry_override")
class TestMemoryCheckpointWithTextSmokeValidation:
    def test_smoke_compiler_authority_selected_for_mct(self):
        response = "<memory_update_done />\nDone."
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="Done.")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        switch_value = get_switch("board_memory.memory_checkpoint_with_text")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_visible_text_preserved=snapshot.visible_text_preserved,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_with_text"
        assert diag.switch_value == "compiler"
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.commit_attempted_agreement is True
        assert diag.reason_agreement is True
        assert diag.source_agreement is True
        assert diag.response_text_agreement is True
        assert diag.checkpoint_removed_agreement is True
        assert diag.visible_text_preserved_agreement is True
        assert diag.pass_through_agreement is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "mismatch_kwargs, expected_mismatch_field",
        [
            ({"legacy_response_text": ""}, "response_text_agreement"),
            ({"legacy_checkpoint_removed": False}, "checkpoint_removed_agreement"),
            ({"legacy_visible_text_preserved": False}, "visible_text_preserved_agreement"),
            ({"legacy_pass_through_preserved": False}, "pass_through_agreement"),
            ({"legacy_accepted_count": 1}, "accepted_count_agreement"),
        ],
        ids=[
            "response_text_mismatch",
            "checkpoint_removed_mismatch",
            "visible_text_preserved_mismatch",
            "pass_through_mismatch",
            "accepted_count_mismatch",
        ],
    )
    def test_smoke_compiler_authority_falls_back_on_mismatch_for_mct(
        self, mismatch_kwargs, expected_mismatch_field
    ):
        response = "<memory_update_done />\nDone."
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="Done.")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        switch_value = get_switch("board_memory.memory_checkpoint_with_text")
        assert switch_value == "compiler"

        legacy_kwargs = {
            "legacy_branch": snapshot.branch,
            "legacy_handled": snapshot.handled,
            "legacy_reason": snapshot.reason,
            "legacy_source": snapshot.source,
            "legacy_response_text": snapshot.response_text,
            "legacy_next_query": snapshot.next_query,
            "legacy_commit_attempted": snapshot.memory_commit_attempted,
            "legacy_accepted_count": snapshot.memory_commit_accepted_count,
            "legacy_rejected_count": snapshot.memory_commit_rejected_count,
            "legacy_last_memory_update_done": snapshot.last_memory_update_done,
            "legacy_visible_text_preserved": snapshot.visible_text_preserved,
            "legacy_pass_through_preserved": snapshot.pass_through_preserved,
            "legacy_checkpoint_removed": snapshot.checkpoint_removed_from_visible_response,
        }
        legacy_kwargs.update(mismatch_kwargs)

        decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            switch_value=switch_value,
            **legacy_kwargs,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.commit_equivalent is False
        assert getattr(diag, expected_mismatch_field) is False
        assert diag.fallback_used is True
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "response",
        [
            "<memory_update_done />",
            '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>',
            "Done.",
            '<subgoal action="mark_in_progress" id="sg_1" />\nDone.',
        ],
        ids=[
            "marker_only_mco",
            "mco_with_action",
            "plaintext_only",
            "plan_checkpoint_with_text",
        ],
    )
    def test_smoke_compiler_authority_not_used_for_mct_negative_controls(self, response):
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)

        switch_value = get_switch("board_memory.memory_checkpoint_with_text")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_visible_text_preserved=snapshot.visible_text_preserved,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.candidate_available is False
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.fallback_used is True
        assert diag.commit_equivalent is False
        assert diag.behavior_changed is False


def _get_mca_content_snapshot_for_test():
    response = '<fact>some fact</fact>\n<action>{"type":"read_file","path":"README.md"}</action>'
    mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
    mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
    mock_board_result = SimpleNamespace(
        parsed_count=1,
        accepted_count=1,
        rejected_count=0,
        clean_text='<action>{"type":"read_file","path":"README.md"}</action>',
    )
    mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
    real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
    harness, state, outcome, snapshot = _run_commit_equivalence_harness(
        response, memory_board_stage=real_handler
    )
    return state, snapshot


def _get_mcta_snapshot_for_test():
    response = '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>'
    mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
    mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
    mock_board_result = SimpleNamespace(
        parsed_count=0,
        accepted_count=0,
        rejected_count=0,
        clean_text='<action>{"type":"read_file","path":"README.md"}</action>',
    )
    mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
    real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
    harness, state, outcome, snapshot = _run_commit_equivalence_harness(
        response, memory_board_stage=real_handler
    )
    return state, snapshot


def test_default_legacy_mode_preserves_legacy_authority_for_mcta():
    state, snapshot = _get_mcta_snapshot_for_test()
    # Ensure we are not in smoke mode
    assert get_switch("board_memory.memory_checkpoint_with_action") == "legacy"

    decision = resolve_memory_checkpoint_with_action_commit_authority(
        semantic_result=state.board_checkpoint_semantic_result,
        legacy_branch=snapshot.branch,
        legacy_handled=snapshot.handled,
        legacy_reason=snapshot.reason,
        legacy_source=snapshot.source,
        legacy_response_text=snapshot.response_text,
        legacy_next_query=snapshot.next_query,
        legacy_commit_attempted=snapshot.memory_commit_attempted,
        legacy_accepted_count=snapshot.memory_commit_accepted_count,
        legacy_rejected_count=snapshot.memory_commit_rejected_count,
        legacy_last_memory_update_done=snapshot.last_memory_update_done,
        legacy_pass_through_preserved=snapshot.pass_through_preserved,
        legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
        switch_value="legacy",
    )

    diag = decision.diagnostic
    assert diag.authority_source == "legacy"
    assert diag.selected_by_switch is False
    assert diag.commit_equivalent is True
    assert diag.behavior_changed is False


class TestMemoryCheckpointWithActionAuthority:
    def _get_mcta_snapshot(self):
        return _get_mcta_snapshot_for_test()

    def test_candidate_builder_for_real_handler_mcta(self):
        state, snapshot = self._get_mcta_snapshot()
        candidate = build_memory_checkpoint_with_action_commit_candidate(state.board_checkpoint_semantic_result)

        assert candidate.candidate_available is True
        assert candidate.branch == "MEMORY_CHECKPOINT_WITH_ACTION"
        assert candidate.has_memory_checkpoint is True
        assert candidate.has_action is True
        assert candidate.has_visible_text is False
        assert candidate.expected_handled is False
        assert candidate.expected_reason == "memory_checkpoint_and_action"
        assert candidate.expected_source == "memory_board"
        assert candidate.expected_commit_attempted is False
        assert candidate.expected_commit_accepted_count == 0
        assert candidate.expected_commit_rejected_count == 0
        assert candidate.expected_last_memory_update_done is True
        assert candidate.expected_pass_through_preserved is True

    @pytest.mark.parametrize(
        "response",
        [
            None,
            "",
            "<think>oops",
            "<memory_update_done />",
            "<memory_update_done />\nDone.",
            '<action>{"type":"read_file","path":"README.md"}</action>',
            '<subgoal action="mark_in_progress" id="sg_1" />\n<action>{"type":"read_file","path":"README.md"}</action>',
        ],
        ids=[
            "none_response",
            "empty_response",
            "compiler_error",
            "mco",
            "mct",
            "action_only",
            "plan_checkpoint_with_action",
        ],
    )
    def test_candidate_builder_unavailable_for_mcta_negative_controls(self, response):
        if response is None:
            candidate = build_memory_checkpoint_with_action_commit_candidate(None)
            assert candidate.candidate_available is False
            assert "no_semantic_result" in candidate.blocking_reasons
            return

        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
        candidate = build_memory_checkpoint_with_action_commit_candidate(state.board_checkpoint_semantic_result)
        assert candidate.candidate_available is False

    def test_resolver_legacy_mode_preserves_legacy_snapshot_for_mcta(self):
        state, snapshot = self._get_mcta_snapshot()
        decision = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="legacy",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_with_action"
        assert diag.switch_value == "legacy"
        assert diag.authority_source == "legacy"
        assert diag.selected_by_switch is False
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False

    def test_resolver_compiler_mode_selects_compiler_on_agreement(self):
        state, snapshot = self._get_mcta_snapshot()
        decision = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="compiler",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_with_action"
        assert diag.switch_value == "compiler"
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "mismatch_kwargs, expected_mismatch_field",
        [
            ({"legacy_pass_through_preserved": False}, "pass_through_agreement"),
            ({"legacy_checkpoint_removed": False}, "checkpoint_removed_agreement"),
            ({"legacy_commit_attempted": True}, "commit_attempted_agreement"),
            ({"legacy_accepted_count": 1}, "accepted_count_agreement"),
            ({"legacy_rejected_count": 1}, "rejected_count_agreement"),
            ({"legacy_last_memory_update_done": False}, "state_flags_agreement"),
            ({"legacy_branch": "something_else"}, "commit_equivalent"),
            ({"legacy_response_text": "Done."}, "response_text_agreement"),
            ({"legacy_response_text": "<action>malformed"}, "response_text_agreement"),
            ({"legacy_handled": True}, "handled_agreement"),
        ],
        ids=[
            "pass_through_mismatch",
            "checkpoint_removed_mismatch",
            "commit_attempted_mismatch",
            "accepted_count_mismatch",
            "rejected_count_mismatch",
            "last_memory_update_done_mismatch",
            "branch_mismatch",
            "response_text_plaintext_mismatch",
            "response_text_malformed_action_mismatch",
            "handled_mismatch",
        ],
    )
    def test_resolver_compiler_mode_falls_back_on_mismatch_for_mcta(
        self, mismatch_kwargs, expected_mismatch_field
    ):
        state, snapshot = self._get_mcta_snapshot()
        legacy_kwargs = {
            "legacy_branch": snapshot.branch,
            "legacy_handled": snapshot.handled,
            "legacy_reason": snapshot.reason,
            "legacy_source": snapshot.source,
            "legacy_response_text": snapshot.response_text,
            "legacy_next_query": snapshot.next_query,
            "legacy_commit_attempted": snapshot.memory_commit_attempted,
            "legacy_accepted_count": snapshot.memory_commit_accepted_count,
            "legacy_rejected_count": snapshot.memory_commit_rejected_count,
            "legacy_last_memory_update_done": snapshot.last_memory_update_done,
            "legacy_pass_through_preserved": snapshot.pass_through_preserved,
            "legacy_checkpoint_removed": snapshot.checkpoint_removed_from_visible_response,
        }
        legacy_kwargs.update(mismatch_kwargs)

        decision = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            switch_value="compiler",
            **legacy_kwargs,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.commit_equivalent is False
        if expected_mismatch_field != "commit_equivalent":
            assert getattr(diag, expected_mismatch_field) is False
        assert diag.fallback_used is True
        assert diag.behavior_changed is False

    def test_mcta_marker_only_action_does_not_attempt_content_commit(self):
        """
        Bare memory checkpoint marker + action does not imply durable memory content commit attempt.
        A live-equivalent legacy snapshot should result in commit_equivalent=True.
        A legacy snapshot where commit was attempted should result in fallback.
        """
        state, snapshot = self._get_mcta_snapshot()
        assert snapshot.memory_commit_attempted is False

        # Compiler mode should select compiler when legacy matches live semantics
        decision_equivalent = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=False,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="compiler",
        )
        diag_eq = decision_equivalent.diagnostic
        assert diag_eq.authority_source == "compiler"
        assert diag_eq.commit_equivalent is True
        assert diag_eq.commit_attempted_agreement is True

        # Compiler mode should fall back when legacy commit was attempted
        decision_fallback = resolve_memory_checkpoint_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=True,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="compiler",
        )
        diag_fb = decision_fallback.diagnostic
        assert diag_fb.authority_source == "legacy_fallback"
        assert diag_fb.commit_equivalent is False
        assert diag_fb.commit_attempted_agreement is False


class TestMemoryContentWithActionAuthority:
    def _get_mca_content_snapshot(self):
        return _get_mca_content_snapshot_for_test()

    def test_candidate_builder_for_real_handler_mca_content(self):
        state, snapshot = self._get_mca_content_snapshot()
        candidate = build_memory_content_with_action_commit_candidate(state.board_checkpoint_semantic_result)

        assert candidate.candidate_available is True
        assert candidate.branch == "MEMORY_CONTENT_WITH_ACTION"
        assert candidate.has_memory_checkpoint is False
        assert candidate.has_action is True
        assert candidate.has_visible_text is False
        assert candidate.expected_handled is False
        assert candidate.expected_reason == "memory_checkpoint_and_action"
        assert candidate.expected_source == "memory_board"
        assert candidate.expected_commit_attempted is True
        assert candidate.expected_commit_accepted_count == 1
        assert candidate.expected_commit_rejected_count == 0
        assert candidate.expected_last_memory_update_done is False
        assert candidate.expected_pass_through_preserved is True

    @pytest.mark.parametrize(
        "response",
        [
            None,
            "",
            "<think>oops",
            "<memory_update_done />",
            "<memory_update_done />\nDone.",
            '<action>{"type":"read_file","path":"README.md"}</action>',
            '<subgoal action="mark_in_progress" id="sg_1" />\n<action>{"type":"read_file","path":"README.md"}</action>',
            '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>',
        ],
        ids=[
            "none_response",
            "empty_response",
            "compiler_error",
            "mco",
            "mct",
            "action_only",
            "plan_checkpoint_with_action",
            "bare_marker_mcta",
        ],
    )
    def test_candidate_builder_unavailable_for_mca_content_negative_controls(self, response):
        if response is None:
            candidate = build_memory_content_with_action_commit_candidate(None)
            assert candidate.candidate_available is False
            assert "no_semantic_result" in candidate.blocking_reasons
            return

        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
        candidate = build_memory_content_with_action_commit_candidate(state.board_checkpoint_semantic_result)
        assert candidate.candidate_available is False

    def test_resolver_legacy_mode_preserves_legacy_snapshot_for_mca_content(self):
        state, snapshot = self._get_mca_content_snapshot()
        decision = resolve_memory_content_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="legacy",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_content_with_action"
        assert diag.switch_value == "legacy"
        assert diag.authority_source == "legacy"
        assert diag.selected_by_switch is False
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False  # legacy branch != candidate branch

    def test_resolver_compiler_mode_selects_compiler_on_agreement_for_mca_content(self):
        state, snapshot = self._get_mca_content_snapshot()
        decision = resolve_memory_content_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="compiler",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_content_with_action"
        assert diag.switch_value == "compiler"
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        # Diagnostic-only branch-name delta: compiler-selected MCA content uses
        # candidate_branch MEMORY_CONTENT_WITH_ACTION while legacy_branch remains
        # MEMORY_CHECKPOINT_WITH_ACTION. The resolver is not wired into runtime and
        # effective_commit is not consumed, so this does not represent runtime behavior transfer.
        assert diag.behavior_changed is True

    @pytest.mark.parametrize(
        "mismatch_kwargs, expected_mismatch_field",
        [
            ({"legacy_pass_through_preserved": False}, "pass_through_agreement"),
            ({"legacy_checkpoint_removed": True}, "checkpoint_removed_agreement"),
            ({"legacy_commit_attempted": False}, "commit_attempted_agreement"),
            ({"legacy_accepted_count": 0}, "accepted_count_agreement"),
            ({"legacy_rejected_count": 1}, "rejected_count_agreement"),
            ({"legacy_last_memory_update_done": True}, "state_flags_agreement"),
            ({"legacy_branch": "something_else"}, "commit_equivalent"),
            ({"legacy_response_text": "Done."}, "response_text_agreement"),
            ({"legacy_response_text": "<action>malformed"}, "response_text_agreement"),
            ({"legacy_handled": True}, "handled_agreement"),
        ],
        ids=[
            "pass_through_mismatch",
            "checkpoint_removed_mismatch",
            "commit_attempted_mismatch",
            "accepted_count_mismatch",
            "rejected_count_mismatch",
            "last_memory_update_done_mismatch",
            "branch_mismatch",
            "response_text_plaintext_mismatch",
            "response_text_malformed_action_mismatch",
            "handled_mismatch",
        ],
    )
    def test_resolver_compiler_mode_falls_back_on_mismatch_for_mca_content(
        self, mismatch_kwargs, expected_mismatch_field
    ):
        state, snapshot = self._get_mca_content_snapshot()
        legacy_kwargs = {
            "legacy_branch": snapshot.branch,
            "legacy_handled": snapshot.handled,
            "legacy_reason": snapshot.reason,
            "legacy_source": snapshot.source,
            "legacy_response_text": snapshot.response_text,
            "legacy_next_query": snapshot.next_query,
            "legacy_commit_attempted": snapshot.memory_commit_attempted,
            "legacy_accepted_count": snapshot.memory_commit_accepted_count,
            "legacy_rejected_count": snapshot.memory_commit_rejected_count,
            "legacy_last_memory_update_done": snapshot.last_memory_update_done,
            "legacy_pass_through_preserved": snapshot.pass_through_preserved,
            "legacy_checkpoint_removed": snapshot.checkpoint_removed_from_visible_response,
        }
        legacy_kwargs.update(mismatch_kwargs)

        decision = resolve_memory_content_with_action_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            switch_value="compiler",
            **legacy_kwargs,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.commit_equivalent is False
        if expected_mismatch_field != "commit_equivalent":
            assert getattr(diag, expected_mismatch_field) is False
        assert diag.fallback_used is True
        assert diag.behavior_changed is False

    def test_bare_marker_mcta_is_not_mca_content(self):
        """Ensures the Phase 35 bare marker + action case is not misclassified as content+action."""
        state, snapshot = _get_mcta_snapshot_for_test()
        candidate = build_memory_content_with_action_commit_candidate(state.board_checkpoint_semantic_result)
        assert candidate.candidate_available is False
        assert "not_clean_memory_content_with_action" in candidate.blocking_reasons


class TestMemoryCommitEquivalence:
    def test_resolver_proves_commit_equivalence_for_marker_only_mco(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value="compiler",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_only"
        assert diag.switch_value == "compiler"
        assert diag.candidate_available is True
        assert diag.commit_attempted_agreement is True
        assert diag.accepted_count_agreement is True
        assert diag.rejected_count_agreement is True
        assert diag.handled_agreement is True
        assert diag.reason_agreement is True
        assert diag.source_agreement is True
        assert diag.next_query_agreement is True
        assert diag.state_flags_agreement is True
        assert diag.commit_equivalent is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True


    def test_resolver_fails_commit_equivalence_on_count_mismatch(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=1, accepted_count=2, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value="compiler",
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.commit_equivalent is False
        assert diag.accepted_count_agreement is False


@pytest.mark.usefixtures("smoke_registry_override")
class TestMemoryCommitSmokeValidation:
    def test_smoke_compiler_authority_selected_for_marker_only_mco(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        switch_value = get_switch("board_memory.memory_checkpoint_only")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True
        assert diag.commit_equivalent is True
        assert diag.behavior_changed is False


    def test_smoke_compiler_authority_falls_back_on_mismatch(self):
        response = "<memory_update_done />"
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=1, accepted_count=2, rejected_count=0, clean_text="")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        switch_value = get_switch("board_memory.memory_checkpoint_only")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.commit_equivalent is False
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "response",
        [
            "Done.",
            '<action>{"type":"read_file","path":"README.md"}</action>',
            '<subgoal action="mark_in_progress" id="sg_1" />',
            "<memory_update_done />\nDone.",
            '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>',
        ],
        ids=[
            "plaintext_only",
            "action_only",
            "plan_checkpoint_only",
            "memory_checkpoint_with_text",
            "memory_checkpoint_with_action",
        ],
    )
    def test_smoke_compiler_authority_not_used_for_negative_controls(self, response):
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)

        switch_value = get_switch("board_memory.memory_checkpoint_only")
        assert switch_value == "compiler"

        decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            switch_value=switch_value,
        )

        diag = decision.diagnostic
        assert diag.candidate_available is False
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.fallback_used is True
        assert diag.commit_equivalent is False
        assert diag.behavior_changed is False


class TestMemoryCheckpointWithTextAuthority:
    def test_candidate_builder_for_real_handler_mct(self):
        response = "<memory_update_done />\nDone."
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="Done.")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        candidate = build_memory_checkpoint_with_text_commit_candidate(state.board_checkpoint_semantic_result)

        assert candidate.candidate_available is True
        assert candidate.branch == "MEMORY_CHECKPOINT_WITH_TEXT"
        assert candidate.has_memory_checkpoint is True
        assert candidate.has_visible_text is True
        assert candidate.has_action is False
        assert candidate.expected_handled is False
        assert candidate.expected_reason == "memory_checkpoint_and_text"
        assert candidate.expected_source == "memory_board"
        assert candidate.expected_commit_attempted is False
        assert candidate.expected_commit_accepted_count == 0
        assert candidate.expected_commit_rejected_count == 0
        assert candidate.expected_last_memory_update_done is True
        assert candidate.expected_visible_text_preserved is True
        assert candidate.expected_pass_through_preserved is True

    def test_resolver_legacy_mode_preserves_legacy_snapshot_for_mct(self):
        response = "<memory_update_done />\nDone."
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="Done.")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_TEXT"
        assert snapshot.response_text == "Done."
        assert snapshot.visible_text_after_memory_stage == "Done."
        assert snapshot.checkpoint_removed_from_visible_response is True
        assert snapshot.visible_text_preserved is True
        assert snapshot.handled is False
        assert snapshot.dispatch_preserved is True
        assert snapshot.final_answer_preserved is True
        assert snapshot.pass_through_preserved is True

        candidate = build_memory_checkpoint_with_text_commit_candidate(
            state.board_checkpoint_semantic_result
        )
        assert candidate.candidate_available is True
        assert candidate.expected_visible_text_preserved is True
        assert candidate.expected_pass_through_preserved is True
        assert candidate.expected_last_memory_update_done is True
        assert candidate.expected_commit_accepted_count == 0
        assert candidate.expected_commit_rejected_count == 0
        assert candidate.expected_handled is False
        assert candidate.expected_reason == "memory_checkpoint_and_text"
        assert candidate.expected_source == "memory_board"

        decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_visible_text_preserved=snapshot.visible_text_preserved,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="legacy",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_with_text"
        assert diag.switch_value == "legacy"
        assert diag.authority_source == "legacy"
        assert diag.selected_by_switch is False
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.commit_attempted_agreement is True
        assert diag.reason_agreement is True
        assert diag.source_agreement is True
        assert diag.response_text_agreement is True
        assert diag.checkpoint_removed_agreement is True
        assert diag.visible_text_preserved_agreement is True
        assert diag.pass_through_agreement is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False

    def test_resolver_proves_commit_equivalence_for_mct(self):
        response = "<memory_update_done />\nDone."
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="Done.")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)

        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        assert snapshot.branch == "MEMORY_CHECKPOINT_WITH_TEXT"
        assert snapshot.response_text == "Done."
        assert snapshot.visible_text_after_memory_stage == "Done."
        assert snapshot.checkpoint_removed_from_visible_response is True
        assert snapshot.visible_text_preserved is True
        assert snapshot.handled is False
        assert snapshot.dispatch_preserved is True
        assert snapshot.final_answer_preserved is True
        assert snapshot.pass_through_preserved is True

        candidate = build_memory_checkpoint_with_text_commit_candidate(
            state.board_checkpoint_semantic_result
        )
        assert candidate.candidate_available is True
        assert candidate.expected_visible_text_preserved is True
        assert candidate.expected_pass_through_preserved is True
        assert candidate.expected_last_memory_update_done is True
        assert candidate.expected_commit_accepted_count == 0
        assert candidate.expected_commit_rejected_count == 0
        assert candidate.expected_handled is False
        assert candidate.expected_reason == "memory_checkpoint_and_text"
        assert candidate.expected_source == "memory_board"

        decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            legacy_branch=snapshot.branch,
            legacy_handled=snapshot.handled,
            legacy_reason=snapshot.reason,
            legacy_source=snapshot.source,
            legacy_response_text=snapshot.response_text,
            legacy_next_query=snapshot.next_query,
            legacy_commit_attempted=snapshot.memory_commit_attempted,
            legacy_accepted_count=snapshot.memory_commit_accepted_count,
            legacy_rejected_count=snapshot.memory_commit_rejected_count,
            legacy_last_memory_update_done=snapshot.last_memory_update_done,
            legacy_visible_text_preserved=snapshot.visible_text_preserved,
            legacy_pass_through_preserved=snapshot.pass_through_preserved,
            legacy_checkpoint_removed=snapshot.checkpoint_removed_from_visible_response,
            switch_value="compiler",
        )

        diag = decision.diagnostic
        assert diag.branch == "board_memory.memory_checkpoint_with_text"
        assert diag.switch_value == "compiler"
        assert diag.authority_source == "compiler"
        assert diag.selected_by_switch is True
        assert diag.candidate_available is True
        assert diag.commit_equivalent is True
        assert diag.commit_attempted_agreement is True
        assert diag.reason_agreement is True
        assert diag.source_agreement is True
        assert diag.response_text_agreement is True
        assert diag.checkpoint_removed_agreement is True
        assert diag.visible_text_preserved_agreement is True
        assert diag.pass_through_agreement is True
        assert diag.fallback_used is False
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "mismatch_kwargs, expected_mismatch_field",
        [
            ({"legacy_response_text": ""}, "response_text_agreement"),
            ({"legacy_checkpoint_removed": False}, "checkpoint_removed_agreement"),
            ({"legacy_visible_text_preserved": False}, "visible_text_preserved_agreement"),
            ({"legacy_pass_through_preserved": False}, "pass_through_agreement"),
            ({"legacy_accepted_count": 1}, "accepted_count_agreement"),
        ],
        ids=[
            "response_text_mismatch",
            "checkpoint_removed_mismatch",
            "visible_text_preserved_mismatch",
            "pass_through_mismatch",
            "accepted_count_mismatch",
        ],
    )
    def test_resolver_compiler_mode_falls_back_on_mismatch_for_mct(
        self, mismatch_kwargs, expected_mismatch_field
    ):
        response = "<memory_update_done />\nDone."
        mock_agent = SimpleNamespace(state=SimpleNamespace(), memory_board_engine=MagicMock(), log=None)
        mock_prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_123"))
        mock_board_result = SimpleNamespace(parsed_count=0, accepted_count=0, rejected_count=0, clean_text="Done.")
        mock_agent.memory_board_engine.apply_response_text.return_value = mock_board_result
        real_handler = MemoryBoardStageHandler(mock_agent, mock_prompt_builder)
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(
            response, memory_board_stage=real_handler
        )

        legacy_kwargs = {
            "legacy_branch": snapshot.branch,
            "legacy_handled": snapshot.handled,
            "legacy_reason": snapshot.reason,
            "legacy_source": snapshot.source,
            "legacy_response_text": snapshot.response_text,
            "legacy_next_query": snapshot.next_query,
            "legacy_commit_attempted": snapshot.memory_commit_attempted,
            "legacy_accepted_count": snapshot.memory_commit_accepted_count,
            "legacy_rejected_count": snapshot.memory_commit_rejected_count,
            "legacy_last_memory_update_done": snapshot.last_memory_update_done,
            "legacy_visible_text_preserved": snapshot.visible_text_preserved,
            "legacy_pass_through_preserved": snapshot.pass_through_preserved,
            "legacy_checkpoint_removed": snapshot.checkpoint_removed_from_visible_response,
        }
        legacy_kwargs.update(mismatch_kwargs)

        decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=state.board_checkpoint_semantic_result,
            switch_value="compiler",
            **legacy_kwargs,
        )

        diag = decision.diagnostic
        assert diag.authority_source == "legacy_fallback"
        assert diag.selected_by_switch is False
        assert diag.commit_equivalent is False
        assert getattr(diag, expected_mismatch_field) is False
        assert diag.fallback_used is True
        assert diag.behavior_changed is False

    @pytest.mark.parametrize(
        "response",
        [
            "<memory_update_done />",
            '<memory_update_done />\n<action>{"type":"read_file","path":"README.md"}</action>',
            "Done.",
            '<subgoal action="mark_in_progress" id="sg_1" />\nDone.',
        ],
        ids=[
            "marker_only_mco",
            "mco_with_action",
            "plaintext_only",
            "plan_checkpoint_with_text",
        ],
    )
    def test_candidate_builder_unavailable_for_mct_negative_controls(self, response):
        harness, state, outcome, snapshot = _run_commit_equivalence_harness(response)
        candidate = build_memory_checkpoint_with_text_commit_candidate(state.board_checkpoint_semantic_result)
        assert candidate.candidate_available is False


