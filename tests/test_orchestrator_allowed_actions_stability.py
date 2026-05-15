import unittest
from types import SimpleNamespace

from modules.agent.allowed_actions_resolver import AllowedActionsContext, AllowedActionsResolver
from modules.agent.orchestration.runtime.core import Orchestrator
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder


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


def _make_prompt_builder(active_intent):
    return OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=active_intent),
            config=SimpleNamespace(),
            memory_board_store=None,
            log=None,
        )
    )


class OrchestratorAllowedActionsStabilityTests(unittest.TestCase):
    def setUp(self):
        self.active_intent = SimpleNamespace(
            intent_id="activity_tracker_edit",
            intent_type="INVESTIGATE",
            goal="determine how to allow moving today's activity to yesterday via the edit dialog in ActivityTrackerScreen",
            allowed_actions=["read_chunk", "read_file", "search_content"],
        )
        self.prompt_builder = _make_prompt_builder(self.active_intent)

    def test_current_intent_contract_recovery_keeps_read_only_actions_stable_after_soft_limit(self):
        stop_info = {
            "reason": "intent_step_limit_soft_exceeded",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent contract: read_chunk, read_file, search_content.", out)
        self.assertIn("Current contract goal remains the same", out)
        self.assertIn("Do not restart the task from the beginning", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_user_approved_more_steps_keeps_same_current_intent_contract_actions(self):
        stop_info = {
            "reason": "user_approved_more_steps_after_hard_limit",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent contract: read_chunk, read_file, search_content.", out)
        self.assertIn("User approved additional budget for this same intent contract.", out)
        self.assertIn("Continue from current evidence under the same contract.", out)
        self.assertIn("Return the next valid output.", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_same_intent_action_not_allowed_in_phase_should_not_jump_to_write_actions(self):
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)
        self.assertNotIn("Required next actions: search_content, edit_file, write_file.", out)
        self.assertNotIn("Allowed actions under the CURRENT intent contract: search_content, edit_file, write_file.", out)
        self.assertIn("Allowed actions under the CURRENT intent contract: read_chunk, read_file, search_content.", out)
        self.assertIn("Use the CURRENT intent contract action family instead of switching to a conflicting legacy recovery action set.", out)

    def test_same_intent_recommended_actions_are_filtered_before_rendering(self):
        stop_info = {
            "reason": "retry_or_continuation_after_failure",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertNotIn("Recommended next actions: search_content, edit_file, write_file.", out)
        self.assertIn("Allowed actions under the CURRENT intent contract: read_chunk, read_file, search_content.", out)

    def test_blocked_action_keeps_current_intent_contract_read_family(self):
        stop_info = {
            "reason": "intent_blocked_action_signature",
            "recoverable": True,
            "message_key": "blocked_action_keep_current_intent",
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent contract: read_chunk, read_file, search_content.", out)
        self.assertIn("The current intent contract remains valid", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_blocked_action_signature_uses_scoped_recovery_text(self):
        stop_info = {
            "reason": "intent_blocked_action_signature",
            "recoverable": True,
            "message_key": "blocked_action_keep_current_intent",
            "next_actions": ["read_chunk", "read_file", "search_content"],
            "policy_metadata": {"blocked_reason": "planned_full_read_too_large"},
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("The blocked action pattern failed because of: planned_full_read_too_large.", out)
        self.assertNotIn("Do NOT retry the same action with cosmetic changes.", out)
        self.assertNotIn("Prefer one materially different next <action> only if tool use is still needed.", out)
        self.assertIn("[RECOVERY_SCOPE]", out)
        self.assertIn("This instruction applies only to the next corrective step after a blocked action pattern under the current intent.", out)
        self.assertIn("[NEXT_STEP_RULE]", out)
        self.assertIn("Avoid repeating the blocked action shape.", out)
        self.assertIn("Choose one allowed action that materially changes the evidence path, or answer directly if current evidence is sufficient.", out)
        self.assertIn("[EXIT_CONDITION]", out)
        self.assertIn("After one successful progress-making step or a final answer, resume normal intent execution.", out)

    def test_modify_recovery_may_offer_write_actions_after_real_intent_switch(self):
        self.active_intent = SimpleNamespace(
            intent_id="activity_tracker_doc_write",
            intent_type="MODIFY",
            goal="write documentation file with findings",
            allowed_actions=["search_content", "edit_file", "write_file"],
        )
        self.prompt_builder = _make_prompt_builder(self.active_intent)
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
            "next_actions_source": "recommended",
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Runtime-suggested next actions: search_content, edit_file, write_file.", out)

    def test_policy_violation_without_source_uses_runtime_provided_hints_label(self):
        stop_info = {
            "reason": "custom_recovery_case",
            "recoverable": True,
            "next_actions": ["search_content", "read_chunk"],
        }

        out = self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Runtime-provided next-action hints: search_content, read_chunk.", out)
        self.assertNotIn("Required next actions: search_content, read_chunk.", out)

    def test_allowed_actions_resolver_prefers_current_intent_for_conflicting_recommended_actions(self):
        resolver = AllowedActionsResolver()
        resolved = resolver.resolve_stop_info(
            AllowedActionsContext(
                reason="retry_or_continuation_after_failure",
                source="recommended",
                next_actions=["search_content", "edit_file", "write_file"],
                active_intent_allowed_actions=["read_chunk", "read_file", "search_content"],
                active_intent_type="INVESTIGATE",
            )
        )

        self.assertEqual("recommended", resolved.authoritative_source)
        self.assertEqual(["search_content"], resolved.recommended_actions)
        self.assertTrue(resolved.keep_current_intent)
        self.assertEqual(["search_content"], resolved.allowed_actions)


if __name__ == "__main__":
    unittest.main()
