import unittest
from types import SimpleNamespace

from modules.agent.planner import TaskBoardPlanner
from modules.agent.state_manager import AgentState


class TestPlannerProtocol(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            PLANNER_ENABLED=True,
            PLANNER_MODE="auto",
            PLANNER_MAX_STEPS=12,
            PLANNER_MAX_VISIBLE_STEPS=4,
            PLANNER_MAX_GOAL_CHARS=240,
            PLANNER_MAX_STEP_TITLE_CHARS=160,
            PLANNER_MAX_STEP_NOTES_CHARS=240,
        )
        self.planner = TaskBoardPlanner(self.config)

    def test_extract_and_strip_valid_taskboard(self):
        text = (
            '<taskboard>{"version":1,"goal":"Ship feature","planner_enabled":true,'
            '"active_step_id":"s1","steps":[{"id":"s1","title":"Read file","status":"in_progress"}]}</taskboard>'
            '<action type="read_file">{"path":"a.txt"}</action>'
        )
        cleaned, update, error = self.planner.extract_update_and_strip(text)
        self.assertIsNone(error)
        self.assertIsNotNone(update)
        self.assertNotIn("<taskboard>", cleaned.lower())
        self.assertIn("<action", cleaned.lower())

    def test_reject_invalid_status(self):
        text = (
            '<taskboard>{"version":1,"goal":"x","planner_enabled":true,'
            '"active_step_id":"s1","steps":[{"id":"s1","title":"t","status":"doing"}]}</taskboard>'
        )
        _cleaned, update, error = self.planner.extract_update_and_strip(text)
        self.assertIsNone(update)
        self.assertIn("bad_status", error)

    def test_apply_and_render_snapshot(self):
        update = {
            "version": 1,
            "goal": "Refactor module",
            "planner_enabled": True,
            "active_step_id": "s2",
            "steps": [
                {"id": "s1", "title": "Inspect files", "status": "done"},
                {"id": "s2", "title": "Edit implementation", "status": "in_progress"},
                {"id": "s3", "title": "Run tests", "status": "todo"},
            ],
        }
        state = AgentState()
        applied, _msg = self.planner.apply_update(state, update)
        self.assertTrue(applied)
        self.assertTrue(state.task_board_enabled)
        snapshot = self.planner.render_runtime_snapshot(state.task_board)
        self.assertIn("SYSTEM TASKBOARD SNAPSHOT", snapshot)
        self.assertIn("s2 [in_progress]", snapshot)
        self.assertIn("initialized", self.planner.render_update_delta(None, state.task_board))

        next_update = {
            "version": 1,
            "goal": "Refactor module",
            "planner_enabled": True,
            "active_step_id": "s3",
            "steps": [
                {"id": "s1", "title": "Inspect files", "status": "done"},
                {"id": "s2", "title": "Edit implementation", "status": "done"},
                {"id": "s3", "title": "Run tests", "status": "in_progress"},
            ],
        }
        self.planner.apply_update(state, next_update)
        delta = self.planner.render_update_delta(update, next_update)
        self.assertIn("status_changes=", delta)
        self.assertIn("active=s2->s3", delta)


if __name__ == "__main__":
    unittest.main()
