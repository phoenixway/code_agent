from types import SimpleNamespace
import unittest

from modules.agent.orchestration.prompting import OrchestratorPromptBuilder


class PromptBuilderCurrentIntentRetryRecoveryTests(unittest.TestCase):
    def _builder(self, active_intent):
        agent = SimpleNamespace(
            state=SimpleNamespace(active_intent=active_intent),
            config=SimpleNamespace(),
            memory_board_store=None,
            log=None,
        )
        return OrchestratorPromptBuilder(agent)

    def test_retry_after_failure_prefers_current_intent_recovery_over_generic_fallback(self):
        active_intent = SimpleNamespace(
            intent_id="modify_sorting_and_dialog",
            intent_type="MODIFY",
            goal="Modify EditRecordDialog after recoverable edit mismatch and finish the UI change.",
            allowed_actions=["edit_file", "read_chunk", "search_content", "run_shell"],
        )
        builder = self._builder(active_intent)

        stop_info = {
            "reason": "retry_or_continuation_after_failure",
            "recoverable": True,
            "next_actions": ["edit_file", "read_chunk", "search_content", "run_shell"],
            "error_code": "VALIDATION_ERROR",
            "policy_metadata": {
                "blocked_reason": "multiple_similar_blocks",
            },
        }

        out = builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent: edit_file, read_chunk, search_content, run_shell.", out)
        self.assertIn("Current intent goal remains the same:", out)
        self.assertNotIn("Previous action violated orchestration policy.", out)

    def test_retry_after_failure_without_active_intent_falls_back_to_generic_prompt(self):
        builder = self._builder(active_intent=None)

        stop_info = {
            "reason": "retry_or_continuation_after_failure",
            "recoverable": True,
            "next_actions": ["read_file", "search_content", "edit_file", "write_file"],
            "error_code": "VALIDATION_ERROR",
        }

        out = builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Previous action violated orchestration policy.", out)
        self.assertIn("Required next actions: read_file, search_content, edit_file, write_file.", out)
