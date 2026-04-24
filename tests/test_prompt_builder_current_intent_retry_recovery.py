from types import SimpleNamespace
import unittest

from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.intent_universe import IntentUniverseResolver
from modules.memory_board_store import MemoryBoardStore


class PromptBuilderCurrentIntentRetryRecoveryTests(unittest.TestCase):
    def _builder(self, active_intent):
        board = MemoryBoardStore(storage_path=None)
        if active_intent is not None:
            board.add_entry(
                kind="finding",
                text="ActivityCard renders start_time as read-only.",
                scope="intent",
                intent_id=getattr(active_intent, "intent_id", None),
            )
            board.add_entry(
                kind="progress",
                text="Sorting currently falls back to created_at in repository query path.",
                scope="intent",
                intent_id=getattr(active_intent, "intent_id", None),
            )
        agent = SimpleNamespace(
            state=SimpleNamespace(
                active_intent=active_intent,
                last_action_fingerprint='read_file_skeleton:{"path": "modules/activity_tracker.py"}',
                last_action_status="success",
                recent_problem_actions=[],
                memory_tag_expected_next_step=False,
                memory_tag_reason="",
                memory_tag_expected_intent_id="",
            ),
            config=SimpleNamespace(),
            memory_board_store=board,
            log=None,
        )
        return OrchestratorPromptBuilder(agent)

    def test_retry_after_failure_prefers_current_intent_contract_recovery_over_generic_fallback(self):
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

        self.assertIn(
            "Allowed actions under the CURRENT intent contract: edit_file, read_chunk, search_content, run_shell.",
            out,
        )
        self.assertIn("Current contract goal remains the same:", out)
        self.assertIn("Intent here means the formal runtime contract", out)
        self.assertIn("Do not restart the task from the beginning", out)
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

        self.assertIn("No active intent contract is currently in force.", out)
        self.assertIn("Continue from already gathered evidence", out)
        self.assertIn("If the next step needs governed multi-step execution, activate a formal <intent> now.", out)
        self.assertIn("Allowed next actions: read_file, search_content, edit_file, write_file.", out)

    def test_retry_after_failure_without_active_intent_marks_recommended_actions_as_hints_only(self):
        builder = self._builder(active_intent=None)

        stop_info = {
            "reason": "retry_or_continuation_after_failure",
            "recoverable": True,
            "next_actions": ["read_file", "search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
            "error_code": "VALIDATION_ERROR",
        }

        out = builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Runtime-suggested next actions: read_file, search_content, edit_file, write_file.", out)
        self.assertIn("These are recovery hints, not proof that contract-scoped tool use is already allowed.", out)
        self.assertIn("Until activation succeeds, do not assume contract-scoped permissions or allowed_actions.", out)

    def test_build_system_message_injects_active_intent_contract_block(self):
        active_intent = SimpleNamespace(
            intent_id="activity_tracker_edit",
            intent_type="INVESTIGATE",
            goal="Understand current implementation of activity tracker sorting and edit dialog to plan changes.",
            allowed_actions=["read_chunk", "search_content", "run_shell", "read_file_skeleton", "search_files"],
            safe_steps_limit=4,
            step_count=2,
            retry_limit=2,
            retry_count=1,
            user_step_extension=0,
        )
        builder = self._builder(active_intent)

        out = builder.build_system_message("TOOLS", "CTX")

        self.assertIn("## ACTIVE INTENT CONTRACT", out)
        self.assertIn("intent_id: activity_tracker_edit", out)
        self.assertIn("intent_type: INVESTIGATE", out)
        self.assertIn("allowed_actions: read_chunk, search_content, run_shell, read_file_skeleton, search_files", out)
        self.assertIn("steps_used: 2", out)
        self.assertIn("steps_remaining: 2", out)
        self.assertIn('last_action: read_file_skeleton("modules/activity_tracker.py") -> success', out)
        self.assertIn("current_best_answer:", out)
        self.assertIn("Memory-board expectation for this contract:", out)
        self.assertIn("emit exactly ONE concise memory tag", out)

    def test_build_system_message_injects_no_active_intent_contract_block(self):
        builder = self._builder(active_intent=None)

        out = builder.build_system_message("TOOLS", "CTX")

        self.assertIn("## INTENT MODE STATUS", out)
        self.assertIn("Status: NO ACTIVE INTENT CONTRACT", out)
        self.assertIn("Runtime mode: INTENTLESS_SHORT_MODE", out)
        self.assertIn("formal_intent_required_now: no", out)

    def test_build_system_message_injects_memory_followup_when_previous_step_had_no_tag(self):
        active_intent = SimpleNamespace(
            intent_id="activity_tracker_edit",
            intent_type="INVESTIGATE",
            goal="Understand current implementation of activity tracker sorting and edit dialog to plan changes.",
            allowed_actions=["read_chunk", "search_content"],
            safe_steps_limit=4,
            step_count=1,
            retry_limit=2,
            retry_count=0,
            user_step_extension=0,
        )
        builder = self._builder(active_intent)
        builder.state.memory_tag_expected_next_step = True
        builder.state.memory_tag_reason = "meaningful_evidence_gain"
        builder.state.memory_tag_expected_intent_id = "activity_tracker_edit"

        out = builder.build_system_message("TOOLS", "CTX")

        self.assertIn("Memory-board follow-up from the previous step:", out)
        self.assertIn("Previous step produced meaningful evidence but no memory tag was emitted.", out)

    def test_memory_board_protocol_distinguishes_fact_from_finding(self):
        builder = self._builder(active_intent=None)

        out = builder.build_memory_board_protocol_prompt()

        self.assertRegex(out, r"Use <fact>.*directly verified")
        self.assertRegex(out, r"Use <finding>.*conclusions.*interpretations")

        self.assertIn("Use <finding> for conclusions, interpretations, suspected behavior", out)

    def test_build_system_message_includes_skeleton_range_navigation_guidance(self):
        builder = self._builder(active_intent=None)

        out = builder.build_system_message("TOOLS", "CTX")

        self.assertIn("`read_file_skeleton` to inspect structure cheaply and obtain symbol line ranges", out)
        self.assertIn("prefer `extract_symbol` over repeated search + chunk hunting", out)
        self.assertIn("read_file_skeleton", out)
        self.assertIn("read_chunk", out)
        self.assertRegex(out, r"skeleton.*read_chunk|read_chunk.*skeleton")
        self.assertIn("Under MODIFY, investigation remains valid until edit-readiness is achieved", out)

    def test_intent_universe_resolver_reports_intentless_short_mode_without_contract(self):
        resolver = IntentUniverseResolver()
        state = SimpleNamespace(
            active_intent=None,
            readonly_steps_this_turn=2,
            intent_required_until_activated=True,
            intent_required_reason="multi_step_without_intent_contract",
        )
        config = SimpleNamespace(INTENTLESS_SHORT_MODE_MAX_STEPS=2)

        universe = resolver.resolve(state, config)

        self.assertEqual("intentless_short_mode", universe.kind)
        self.assertFalse(universe.has_active_contract)
        self.assertTrue(universe.intent_required_now)
        self.assertEqual("multi_step_without_intent_contract", universe.intent_requirement_reason)
        self.assertEqual(2, universe.intentless_steps_used)

    def test_intent_universe_resolver_reports_active_contract(self):
        resolver = IntentUniverseResolver()
        active_intent = SimpleNamespace(
            intent_id="modify_sorting",
            intent_type="MODIFY",
            goal="Change sorting to startTime",
            allowed_actions=["edit_file", "write_file"],
        )
        state = SimpleNamespace(
            active_intent=active_intent,
            readonly_steps_this_turn=1,
            intent_required_until_activated=False,
            intent_required_reason="",
        )
        config = SimpleNamespace(INTENTLESS_SHORT_MODE_MAX_STEPS=2)

        universe = resolver.resolve(state, config)

        self.assertEqual("active_contract", universe.kind)
        self.assertTrue(universe.has_active_contract)
        self.assertEqual("MODIFY", universe.active_intent_type)
        self.assertEqual(["edit_file", "write_file"], universe.allowed_actions)
        self.assertEqual(0, universe.intentless_steps_used)
