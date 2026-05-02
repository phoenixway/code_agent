import unittest
from types import SimpleNamespace

from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.agent.orchestration.runtime.recovery import RecoveryCoordinator


class _EnumLike:
    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return self.value


def _make_components(active_intent):
    state = SimpleNamespace(active_intent=active_intent)
    prompt_builder = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=state,
            config=SimpleNamespace(),
            memory_board_store=None,
            log=None,
        )
    )
    recovery = RecoveryCoordinator(
        SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(
                RECOVERABLE_ERROR_RETRY_BUDGET=2,
                CRITICAL_ERROR_RETRY_BUDGET=1,
            ),
            log=None,
        ),
        prompt_builder,
    )
    return prompt_builder, recovery


class OrchestratorFinalRecoveryOutputTests(unittest.TestCase):
    def setUp(self):
        self.active_intent = SimpleNamespace(
            intent_id="activity_tracker_edit",
            intent_type="INVESTIGATE",
            goal="determine how to allow moving today's activity to yesterday via the edit dialog in ActivityTrackerScreen",
            allowed_actions=["read_chunk", "read_file", "search_content"],
        )
        self.prompt_builder, self.recovery = _make_components(self.active_intent)

    def _sm(self, *, task_kind: str = "INSPECTION", target_file: str = "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt"):
        return SimpleNamespace(
            task_kind=_EnumLike(task_kind),
            target_file=target_file,
        )

    def _final_recovery_output(self, sm, stop_info: dict) -> str:
        if self.recovery.inspection_can_finish_with_text(sm, stop_info):
            return self.prompt_builder.build_plain_text_completion_prompt(sm, stop_info)
        return self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

    def test_inspection_soft_limit_prefers_plain_text_completion_over_more_actions(self):
        sm = self._sm(task_kind="INSPECTION")
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
        sm = self._sm(task_kind="INSPECTION")
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
        }

        out = self._final_recovery_output(sm, stop_info)

        self.assertIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Recovery reason: action_not_allowed_in_phase.", out)
        self.assertIn("Do not ask to inspect more files.", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_hybrid_action_not_allowed_in_phase_also_prefers_plain_text_completion(self):
        sm = self._sm(task_kind="HYBRID")
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
        }

        out = self._final_recovery_output(sm, stop_info)

        self.assertIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Task kind: HYBRID.", out)
        self.assertNotIn("Choose a different strategy and return EXACTLY ONE valid <action>.", out)

    def test_modification_mode_does_not_falsely_force_plain_text_completion(self):
        sm = self._sm(task_kind="MODIFICATION")
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
        }

        self.active_intent = SimpleNamespace(
            intent_id="activity_tracker_doc_write",
            intent_type="MODIFY",
            goal="write documentation file with findings",
            allowed_actions=["search_content", "edit_file", "write_file"],
        )
        self.prompt_builder, self.recovery = _make_components(self.active_intent)

        out = self._final_recovery_output(sm, stop_info)

        self.assertNotIn("SYSTEM: Stop tool use now.", out)
        self.assertIn("Previous action violated orchestration policy", out)
        self.assertIn("Runtime-suggested next actions: search_content, edit_file, write_file.", out)
        self.assertIn("Use these only as recovery hints, not as a replacement for the current contract.", out)

    def test_blocked_large_read_keeps_current_intent_contract_recovery_not_plain_text(self):
        sm = self._sm(task_kind="INSPECTION")
        stop_info = {
            "reason": "planned_full_read_too_large",
            "recoverable": True,
            "error_code": "PLANNED_FULL_READ_TOO_LARGE",
            "next_actions": ["read_chunk", "read_file_skeleton", "search_content"],
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("The planned full read_file action is too large", out)
        self.assertIn("Do NOT send another <intent> block now.", out)
        self.assertIn("Continue under the current intent contract.", out)
        self.assertIn("Do not restart the task from the beginning.", out)
        self.assertIn("Return EXACTLY ONE materially different read-only action.", out)

    def test_hard_limit_reuse_prompt_forbids_continuing_under_current_contract(self):
        out = self.prompt_builder.build_limit_aware_reuse_prompt(
            "intent_step_limit_exceeded",
            ["read_chunk", "search_content"],
            goal=self.active_intent.goal,
        )

        self.assertIn("Current intent step budget is exhausted.", out)
        self.assertIn("Normal actions are forbidden", out)
        self.assertIn('mode="reuse"', out)
        self.assertIn('mode="complete"', out)
        self.assertIn("plain handoff/answer", out)
        self.assertNotIn("Continue under the current intent contract.", out)


if __name__ == "__main__":
    unittest.main()
