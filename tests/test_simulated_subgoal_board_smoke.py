from types import SimpleNamespace
import tempfile

from modules.agent.planner import TaskBoardPlanner
from modules.history import HistoryManager


class DummyChatProvider:
    pass


def _config():
    return SimpleNamespace(
        PLANNER_ENABLED=True,
        PLANNER_MODE="always",
        PLANNER_MAX_GOAL_CHARS=240,
        PLANNER_MAX_STEPS=12,
        PLANNER_MAX_STEP_TITLE_CHARS=160,
    )


def _state(*, intent_id="intent-1", goal="Implement manifest setup"):
    active_intent = SimpleNamespace(
        intent_id=intent_id,
        lineage_id=f"lineage-{intent_id}",
        goal=goal,
    )
    return SimpleNamespace(active_intent=active_intent, task_board=None)


def _planner():
    return TaskBoardPlanner(_config())


def test_p37_duplicate_in_progress_subgoals_with_same_title_are_deduped_by_active_title():
    planner = _planner()
    state = _state()

    changed, report = planner.apply_update(
        state,
        [
            {
                "op": "create",
                "step_id": "sg_4",
                "status": "in_progress",
                "title": "Create AndroidManifest.xml",
            },
            {
                "op": "create",
                "step_id": "sg_5",
                "status": "in_progress",
                "title": "Create AndroidManifest.xml",
            },
        ],
    )

    board = state.task_board

    assert changed is True
    assert report["kind"] == "plan_update"
    assert [step["id"] for step in board["steps"]] == ["sg_4"]
    assert [step["title"] for step in board["steps"]] == ["Create AndroidManifest.xml"]
    assert [step["status"] for step in board["steps"]] == ["in_progress"]
    assert board["active_step_id"] == "sg_4"
    assert report["total"] == 1
    assert report["current_title"] == "Create AndroidManifest.xml"


def test_p37_create_with_same_id_updates_existing_step_instead_of_duplicating():
    planner = _planner()
    state = _state()

    changed, report = planner.apply_update(
        state,
        [
            {
                "op": "create",
                "step_id": "sg_1",
                "status": "todo",
                "title": "Create AndroidManifest.xml",
            },
            {
                "op": "create",
                "step_id": "sg_1",
                "status": "in_progress",
                "title": "Create AndroidManifest.xml with INTERNET permission",
            },
        ],
    )

    board = state.task_board

    assert changed is True
    assert report["kind"] == "plan_update"
    assert len(board["steps"]) == 1
    assert board["steps"][0] == {
        "id": "sg_1",
        "title": "Create AndroidManifest.xml with INTERNET permission",
        "status": "in_progress",
    }
    assert board["active_step_id"] == "sg_1"


def test_p37_mark_done_without_evidence_is_rejected_at_parse_stage():
    clean_text, ops, error = _planner().extract_update_and_strip(
        '<subgoal action="mark_done" id="sg_1" />'
    )

    assert clean_text == ""
    assert ops is None
    assert error == "subgoal_mark_done_evidence_required"


def test_p37_weak_mark_done_evidence_is_currently_accepted_as_characterization():
    clean_text, ops, error = _planner().extract_update_and_strip(
        '<subgoal action="mark_done" id="sg_1" evidence="Identified insertion point for AndroidManifest.xml" />'
    )

    assert clean_text == ""
    assert error is None
    assert ops == [
        {
            "op": "mark_done",
            "step_id": "sg_1",
            "status": "done",
            "evidence": "Identified insertion point for AndroidManifest.xml",
        }
    ]


def test_p37_plan_review_done_alone_does_not_create_subgoal_ops_or_mutate_board():
    planner = _planner()
    state = _state()
    initial_board = {
        "version": 2,
        "goal": "Implement manifest setup",
        "active_step_id": "sg_1",
        "intent_id": "intent-1",
        "lineage_id": "lineage-intent-1",
        "steps": [
            {
                "id": "sg_1",
                "title": "Create AndroidManifest.xml",
                "status": "in_progress",
            }
        ],
    }
    state.task_board = initial_board

    clean_text, ops, error = planner.extract_update_and_strip("<plan_review_done />")

    assert clean_text == "<plan_review_done />"
    assert ops is None
    assert error is None
    assert state.task_board is initial_board


def test_p37_plan_board_summary_reflects_runtime_board_as_is_after_dedupe():
    state = _state()
    state.task_board = {
        "version": 2,
        "goal": "Implement manifest setup",
        "active_step_id": "sg_4",
        "intent_id": "intent-1",
        "lineage_id": "lineage-intent-1",
        "steps": [
            {
                "id": "sg_4",
                "title": "Create AndroidManifest.xml",
                "status": "in_progress",
            },
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(DummyChatProvider(), storage_dir=tmpdir)
        summary = history._build_plan_board_summary_block(state)

    assert "## CURRENT PLAN BOARD (CANONICAL)" in summary
    assert "active_step_id: sg_4" in summary
    assert summary.count("Create AndroidManifest.xml") == 1
    assert "- sg_4 [in_progress] Create AndroidManifest.xml" in summary
    assert "- sg_5 [in_progress] Create AndroidManifest.xml" not in summary


def test_p38_stale_other_lineage_board_is_not_normalized_for_active_intent():
    planner = _planner()
    state = _state(intent_id="new-intent", goal="New active work")
    stale_board = {
        "version": 2,
        "goal": "Old work",
        "active_step_id": "sg_old",
        "intent_id": "old-intent",
        "lineage_id": "lineage-old-intent",
        "steps": [
            {
                "id": "sg_old",
                "title": "Old stale step",
                "status": "in_progress",
            }
        ],
    }

    assert planner.board_matches_active_intent(state, stale_board) is False
    assert planner.normalize_board_for_active_intent(state, stale_board) is None


def test_p38_apply_update_under_new_intent_replaces_stale_board_with_fresh_bound_board():
    planner = _planner()
    state = _state(intent_id="new-intent", goal="New active work")
    state.task_board = {
        "version": 2,
        "goal": "Old work",
        "active_step_id": "sg_old",
        "intent_id": "old-intent",
        "lineage_id": "lineage-old-intent",
        "steps": [
            {
                "id": "sg_old",
                "title": "Old stale step",
                "status": "in_progress",
            }
        ],
    }

    changed, report = planner.apply_update(
        state,
        [
            {
                "op": "create",
                "step_id": "sg_new",
                "status": "in_progress",
                "title": "Create fresh board for new intent",
            }
        ],
    )

    board = state.task_board

    assert changed is True
    assert report["kind"] == "plan_update"
    assert board["goal"] == "New active work"
    assert board["intent_id"] == "new-intent"
    assert board["lineage_id"] == "lineage-new-intent"
    assert board["active_step_id"] == "sg_new"
    assert board["steps"] == [
        {
            "id": "sg_new",
            "title": "Create fresh board for new intent",
            "status": "in_progress",
        }
    ]


def test_p38_bind_board_to_active_intent_sets_intent_and_lineage_ids():
    planner = _planner()
    state = _state(intent_id="intent-bind", goal="Bind board")
    board = {
        "version": 2,
        "goal": "Bind board",
        "active_step_id": None,
        "steps": [],
    }

    returned = planner.bind_board_to_active_intent(state, board)

    assert returned is board
    assert board["intent_id"] == "intent-bind"
    assert board["lineage_id"] == "lineage-intent-bind"


def test_p38_matching_lineage_allows_board_even_when_intent_id_differs():
    planner = _planner()
    state = _state(intent_id="retry-intent", goal="Retry same lineage")
    state.active_intent.lineage_id = "shared-lineage"
    board = {
        "version": 2,
        "goal": "Previous retry attempt",
        "active_step_id": "sg_1",
        "intent_id": "previous-intent-id",
        "lineage_id": "shared-lineage",
        "steps": [
            {
                "id": "sg_1",
                "title": "Carry useful same-lineage step forward",
                "status": "in_progress",
            }
        ],
    }

    normalized = planner.normalize_board_for_active_intent(state, board)

    assert normalized is not None
    assert normalized is not board
    assert normalized["intent_id"] == "retry-intent"
    assert normalized["lineage_id"] == "shared-lineage"
    assert normalized["steps"] == board["steps"]


def test_p38_history_plan_board_summary_is_projection_only_and_does_not_filter_lineage():
    state = _state(intent_id="new-intent", goal="New active work")
    state.task_board = {
        "version": 2,
        "goal": "Old board still present in state",
        "active_step_id": "sg_old",
        "intent_id": "old-intent",
        "lineage_id": "lineage-old-intent",
        "steps": [
            {
                "id": "sg_old",
                "title": "Old stale step",
                "status": "in_progress",
            }
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(DummyChatProvider(), storage_dir=tmpdir)
        summary = history._build_plan_board_summary_block(state)

    assert "## CURRENT PLAN BOARD (CANONICAL)" in summary
    assert "goal: Old board still present in state" in summary
    assert "active_step_id: sg_old" in summary
    assert "- sg_old [in_progress] Old stale step" in summary
