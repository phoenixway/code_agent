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
            "command": {"type": "edit_file", "path": "app/src/main/kotlin/Feature.kt"},
            "policy_metadata": {
                "blocked_reason": "multiple_similar_blocks",
            },
        }

        out = builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("<memory_update_done />", out)
        self.assertIn("<action>", out)
        self.assertIn("targeted edit_file", out)
        self.assertNotIn("Analyze the error in <think>", out)

    def test_retry_after_failure_without_active_intent_falls_back_to_generic_prompt(self):
        builder = self._builder(active_intent=None)

        stop_info = {
            "reason": "retry_or_continuation_after_failure",
            "recoverable": True,
            "next_actions": ["read_file", "search_content", "edit_file", "write_file"],
            "error_code": "VALIDATION_ERROR",
        }

        out = builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("<memory_update_done />", out)
        self.assertIn("<action>", out)
        self.assertIn("targeted edit_file", out)
        self.assertNotIn("Analyze the error in <think>", out)

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

        self.assertIn("<memory_update_done />", out)
        self.assertIn("<action>", out)
        self.assertIn("targeted edit_file", out)
        self.assertNotIn("think about", out)

    def test_missing_file_content_block_recovery_uses_strict_template_without_plan_language(self):
        active_intent = SimpleNamespace(
            intent_id="new_file_write",
            intent_type="MODIFY",
            goal="Create a new source file safely.",
            allowed_actions=["write_file_block", "append_file_block", "edit_file"],
        )
        builder = self._builder(active_intent)

        out = builder.build_current_intent_retry_recovery_query(
            ["write_file_block", "append_file_block", "edit_file"],
            error_code="MISSING_FILE_CONTENT_BLOCK",
            error_details={"target_exists": False, "path": "src/new_file.py"},
            command={"type": "write_file_block", "path": "src/new_file.py", "overwrite": True},
        )

        self.assertNotIn("Analyze the error in <think>", out)
        self.assertNotIn("think about", out)
        self.assertNotIn("plan", out.lower())
        self.assertTrue("<op " in out or "<think>" in out)
        self.assertIn("<memory_update_done />", out)
        self.assertIn("<file_content>\nraw content\n</file_content>", out)

    def test_existing_source_full_rewrite_failure_prefers_git_diff_and_targeted_edit(self):
        active_intent = SimpleNamespace(
            intent_id="kotlin_modify",
            intent_type="MODIFY",
            goal="Patch an existing Kotlin source file.",
            allowed_actions=["write_file_block", "edit_file", "git_diff", "read_chunk"],
        )
        builder = self._builder(active_intent)

        out = builder.build_current_intent_retry_recovery_query(
            ["write_file_block", "edit_file", "git_diff", "read_chunk"],
            error_code="MISSING_FILE_CONTENT_BLOCK",
            error_details={"target_exists": True, "path": "app/src/main/kotlin/Feature.kt"},
            command={"type": "write_file_block", "path": "app/src/main/kotlin/Feature.kt", "overwrite": True},
        )

        self.assertIn("Do not retry full-file rewrite yet", out)
        self.assertIn("git_diff", out)
        self.assertIn("targeted edit_file", out)
        self.assertNotIn('"type": "write_file_block"', out)

    def test_malformed_read_chunk_recovery_shows_valid_payload_shape(self):
        builder = self._builder(active_intent=None)

        out = builder.build_current_intent_retry_recovery_query(
            ["read_chunk"],
            error_code="MALFORMED_READ_CHUNK_PAYLOAD",
            error_details={"path": "src/main.py"},
            command={"type": "read_chunk", "path": "src/main.py"},
        )

        self.assertIn('"type":"read_chunk"', out.replace(" ", ""))
        self.assertIn('"start_line":1304', out)
        self.assertNotIn("Analyze the error in <think>", out)

    def test_build_system_message_does_not_embed_active_intent_contract_block(self):
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

        self.assertNotIn("intent_id: activity_tracker_edit", out)
        self.assertNotIn("steps_used: 2", out)
        self.assertNotIn("nominal_steps_remaining: 2", out)
        self.assertNotIn("Memory-board expectation for this contract:", out)

    def test_build_intent_runtime_context_message_contains_active_intent_contract_block(self):
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

        out = builder.build_intent_runtime_context_message()

        self.assertIsNotNone(out)
        self.assertEqual("user", out["role"])
        self.assertIn("## ACTIVE INTENT CONTRACT", out["content"])
        self.assertIn("intent_id: activity_tracker_edit", out["content"])
        self.assertIn("intent_type: INVESTIGATE", out["content"])
        self.assertIn("allowed_actions: read_chunk, search_content, run_shell, read_file_skeleton, search_files", out["content"])
        self.assertIn("steps_used: 2", out["content"])
        self.assertIn("nominal_steps_remaining: 2", out["content"])
        self.assertIn('last_action: read_file_skeleton("modules/activity_tracker.py") -> success', out["content"])
        self.assertIn("current_best_answer:", out["content"])
        self.assertIn("Memory-board expectation for this contract:", out["content"])
        self.assertIn("emit exactly ONE concise memory tag", out["content"])

    def test_build_intent_runtime_context_message_uses_exhausted_gate_prompt_when_hard_limit_reached(self):
        active_intent = SimpleNamespace(
            intent_id="activity_tracker_edit",
            intent_type="INVESTIGATE",
            goal="Understand current implementation of activity tracker sorting and edit dialog to plan changes.",
            allowed_actions=["read_chunk", "search_content", "run_shell"],
            safe_steps_limit=4,
            step_count=5,
            retry_limit=2,
            retry_count=1,
            user_step_extension=0,
        )
        builder = self._builder(active_intent)
        builder.state.has_hard_exhausted_active_intent = lambda: True

        out = builder.build_intent_runtime_context_message()

        self.assertIsNotNone(out)
        self.assertIn("Status: ACTIVE BUT HARD-EXHAUSTED", out["content"])
        self.assertIn("Normal <action> output is forbidden", out["content"])
        self.assertIn('mode="reuse"', out["content"])
        self.assertNotIn("Continue under this contract unless runtime explicitly requires a legitimate transition.", out["content"])

    def test_build_system_message_does_not_embed_no_active_intent_contract_block(self):
        builder = self._builder(active_intent=None)

        out = builder.build_system_message("TOOLS", "CTX")

        self.assertNotIn("Runtime mode: INTENTLESS_SHORT_MODE", out)
        self.assertNotIn("formal_intent_required_now: no", out)

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

        out = builder.build_intent_runtime_context_message()

        self.assertIsNotNone(out)
        self.assertIn("Memory-board follow-up from the previous step:", out["content"])
        self.assertIn("Previous step produced meaningful evidence but no memory tag was emitted.", out["content"])

    def test_build_system_message_does_not_embed_memory_board_entries(self):
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

        out = builder.build_system_message("TOOLS", "CTX")

        self.assertNotIn("[CURRENT INTENT MEMORY]", out)
        self.assertNotIn("ActivityCard renders start_time as read-only.", out)
        self.assertNotIn("Sorting currently falls back to created_at in repository query path.", out)

    def test_build_memory_board_context_message_contains_memory_board_entries(self):
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

        out = builder.build_memory_board_context_message()

        self.assertIsNotNone(out)
        self.assertEqual("user", out["role"])
        self.assertIn("## MEMORY BOARD", out["content"])
        self.assertIn("ActivityCard renders start_time as read-only.", out["content"])

    def test_build_memory_board_context_message_marks_previous_intent_memory_as_stale(self):
        board = MemoryBoardStore(storage_path=None)
        board.add_entry(
            kind="finding",
            text="Old dialog path was modules/activity_tracker/ui/legacy_dialog.py.",
            scope="intent",
            intent_id="old_intent_1",
        )
        agent = SimpleNamespace(
            state=SimpleNamespace(
                active_intent=None,
                last_resumable_intent_id="old_intent_1",
                last_resumable_intent_lineage_id="old_intent_1",
                last_action_fingerprint=None,
                last_action_status=None,
                recent_problem_actions=[],
                memory_tag_expected_next_step=False,
                memory_tag_reason="",
                memory_tag_expected_intent_id="",
            ),
            config=SimpleNamespace(),
            memory_board_store=board,
            log=None,
        )
        builder = OrchestratorPromptBuilder(agent)

        out = builder.build_memory_board_context_message()

        self.assertIsNotNone(out)
        self.assertIn("## MEMORY BOARD (STALE INTENT CONTEXT)", out["content"])
        self.assertIn("[STALE INTENT MEMORY TO REVIEW]", out["content"])
        self.assertIn("Old dialog path was modules/activity_tracker/ui/legacy_dialog.py.", out["content"])

    def test_build_intent_runtime_context_message_contains_no_active_intent_block(self):
        builder = self._builder(active_intent=None)

        out = builder.build_intent_runtime_context_message()

        self.assertIsNotNone(out)
        self.assertEqual("user", out["role"])
        self.assertIn("## INTENT MODE STATUS", out["content"])
        self.assertIn("Status: NO ACTIVE INTENT CONTRACT", out["content"])
        self.assertIn("Runtime mode: INTENTLESS_SHORT_MODE", out["content"])
        self.assertIn("formal_intent_required_now: no", out["content"])

    def test_memory_board_protocol_distinguishes_fact_from_finding(self):
        builder = self._builder(active_intent=None)

        out = builder.build_memory_board_protocol_prompt()

        self.assertRegex(out, r"Use <fact>.*directly verified")
        self.assertRegex(out, r"Use <finding>.*conclusions.*interpretations")

        self.assertIn("Use <finding> for conclusions, interpretations, suspected behavior", out)
        self.assertIn("<memory_update_done />", out)
        self.assertIn("Sufficiency Check -> State Review -> Memory/Subgoal Update -> Action or Answer", out)

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
