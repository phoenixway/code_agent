import unittest
from types import SimpleNamespace

from modules.agent.orchestrator import Orchestrator


class _EnumLike:
    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return self.value


def _make_orchestrator(active_intent):
    agent = SimpleNamespace(
        ui=SimpleNamespace(),
        state=SimpleNamespace(active_intent=active_intent),
        history=SimpleNamespace(),
        model_client=SimpleNamespace(),
        action_dispatcher=SimpleNamespace(),
        parser=SimpleNamespace(),
        config=SimpleNamespace(),
    )
    return Orchestrator(agent)


class OrchestratorFinalRecoveryOutputTests(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator(
            SimpleNamespace(
                intent_id="activity_tracker_edit",
                intent_type="INVESTIGATE",
                goal="determine how to allow moving today's activity to yesterday via the edit dialog in ActivityTrackerScreen",
                allowed_actions=["read_chunk", "read_file", "search_content"],
            )
        )

    def _sm(self, *, task_kind: str = "INSPECTION", phase: str = "OBSERVE", target_file: str = "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt"):
        return SimpleNamespace(
            task_kind=_EnumLike(task_kind),
            phase=_EnumLike(phase),
            target_file=target_file,
        )

    def _final_recovery_output(self, sm, stop_info: dict) -> str:
        if self.orch._inspection_can_finish_with_text(sm, stop_info):
            return self.orch._build_plain_text_completion_prompt(sm, stop_info)
        return self.orch._build_orchestrated_recovery_prompt(stop_info)

    def test_inspection_soft_limit_prefers_plain_text_completion_over_more_actions(self):
        sm = self._sm(task_kind="INSPECTION", phase="OBSERVE")
        stop_info = {
            "reason": "intent_step_limit_soft_exceeded",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self._final_recovery_output(sm, stop_info)

        self.assertIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Return a concise plain-text answer", out)
        self.assertIn("Do not output any <action> block.", out)
        self.assertNotIn("Allowed next actions:", out)
        self.assertNotIn("Return EXACTLY ONE materially different next <action>", out)

    def test_inspection_action_not_allowed_in_phase_prefers_plain_text_completion(self):
        sm = self._sm(task_kind="INSPECTION", phase="OBSERVE")
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
        }

        out = self._final_recovery_output(sm, stop_info)

        self.assertIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Recovery reason: action_not_allowed_in_phase.", out)
        self.assertIn("Do not ask to inspect more files.", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_hybrid_action_not_allowed_in_phase_also_prefers_plain_text_completion(self):
        sm = self._sm(task_kind="HYBRID", phase="OBSERVE")
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
        }

        out = self._final_recovery_output(sm, stop_info)

        self.assertIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Task kind: HYBRID. Current phase: OBSERVE.", out)
        self.assertNotIn("Choose a different strategy and return EXACTLY ONE valid <action>.", out)

    def test_modification_mode_does_not_falsely_force_plain_text_completion(self):
        sm = self._sm(task_kind="MODIFICATION", phase="OBSERVE")
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
        }

        self.orch = _make_orchestrator(
            SimpleNamespace(
                intent_id="activity_tracker_doc_write",
                intent_type="MODIFY",
                goal="write documentation file with findings",
                allowed_actions=["search_content", "edit_file", "write_file"],
            )
        )

        out = self._final_recovery_output(sm, stop_info)

        self.assertNotIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Previous action violated orchestration policy", out)
        self.assertIn("Required next actions: search_content, edit_file, write_file.", out)

    def test_blocked_large_read_keeps_current_intent_recovery_not_plain_text(self):
        sm = self._sm(task_kind="INSPECTION", phase="OBSERVE")
        stop_info = {
            "reason": "planned_full_read_too_large",
            "recoverable": True,
            "error_code": "PLANNED_FULL_READ_TOO_LARGE",
            "next_actions": ["read_chunk", "read_file_skeleton", "search_content"],
        }

        out = self.orch._build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("The planned full read_file action is too large", out)
        self.assertIn("Do NOT send another <intent> block now.", out)
        self.assertIn("Reuse the current intent.", out)
        self.assertIn("Return EXACTLY ONE materially different read-only action.", out)


if __name__ == "__main__":
    unittest.main()
