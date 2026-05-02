import unittest
from types import SimpleNamespace

from modules.agent.intent_runtime import IntentRuntime, IntentContract
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder


class DummyDecision:
    allowed = True
    reason = ""
    error_code = ""
    message_key = ""
    metadata = {}


class DummyPolicyEngine:
    def __init__(self, config):
        self.config = config
    def evaluate_transition(self, ctx):
        return DummyDecision()


class ReuseGoalRefinementTests(unittest.TestCase):
    def make_runtime(self):
        config = SimpleNamespace(
            INTENT_RETRY_GOAL_SIMILARITY_THRESHOLD=0.45,
            INTENT_REUSE_GOAL_SIMILARITY_THRESHOLD=0.55,
            INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD=0.6,
            INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD=0.6,
            INTENT_DEFAULT_SAFE_STEPS=8,
            INTENT_DEFAULT_RETRY_LIMIT=2,
            INTENT_MAX_SAFE_STEPS=12,
            INTENT_MAX_RETRY_LIMIT=4,
            INTENT_REUSE_EXTENSION_STEPS=4,
        )
        state = SimpleNamespace()
        runtime = IntentRuntime(config, state=state)
        runtime.policy_engine = DummyPolicyEngine(config)
        runtime.active_intent = IntentContract(
            intent_id="per_link_vault_e2e",
            intent_type="MODIFY",
            goal="Провести per-link vault через увесь ланцюг: sync layer, creation UI, 3 ViewModel, open logic, UI display.",
            canonical_goal="Провести per-link vault через увесь ланцюг: sync layer, creation UI, 3 ViewModel, open logic, UI display.",
            allowed_actions=["read_chunk", "extract_symbol", "search_content", "read_file_skeleton", "edit_file", "run_shell"],
            original_allowed_actions=["read_chunk", "extract_symbol", "search_content", "read_file_skeleton", "edit_file", "run_shell"],
            safe_steps_limit=12,
            retry_limit=2,
            lineage_id="per_link_vault_e2e",
        )
        return runtime

    def test_reuse_allows_minor_goal_refinement_same_intent(self):
        runtime = self.make_runtime()
        payload = {
            "mode": "reuse",
            "intent_id": "per_link_vault_e2e",
            "intent_type": "MODIFY",
            "goal": "Провести per-link vault end-to-end і доробити exact ViewModel methods та LinkHelpers без втрати fallback логіки.",
            "allowed_actions": ["read_chunk", "extract_symbol", "search_content", "read_file_skeleton", "edit_file", "run_shell"],
            "requested_steps": 4,
            "switch_reason": "current_intent_exhausted",
        }
        contract, error = runtime.validate_payload(payload)
        self.assertIsNone(error)
        self.assertEqual(contract.goal, payload["goal"])

    def test_reuse_rejects_local_step_only_goal_even_same_intent(self):
        runtime = self.make_runtime()
        payload = {
            "mode": "reuse",
            "intent_id": "per_link_vault_e2e",
            "intent_type": "MODIFY",
            "goal": "Read chunk around addObsidianLink and extract symbol only",
            "allowed_actions": ["read_chunk", "extract_symbol"],
            "requested_steps": 4,
            "switch_reason": "current_intent_exhausted",
        }
        contract, error = runtime.validate_payload(payload)
        self.assertEqual(error, "intent_reuse_goal_mismatch")


class PromptBudgetSyncTests(unittest.TestCase):
    def test_active_contract_prompt_shows_nominal_and_hard_budget(self):
        config = SimpleNamespace(INTENT_COMPLETION_ALLOWANCE=1)
        active_intent = SimpleNamespace(
            intent_id="per_link_vault_e2e",
            intent_type="MODIFY",
            goal="Do thing",
            allowed_actions=["edit_file"],
            safe_steps_limit=12,
            user_step_extension=0,
            step_count=12,
            retry_limit=2,
            retry_count=0,
        )
        state = SimpleNamespace(
            active_intent=active_intent,
            intent_runtime=SimpleNamespace(get_active_intent_lineage_ids=lambda: ["per_link_vault_e2e"]),
            last_action_fingerprint="",
            last_action_status="",
        )
        agent = SimpleNamespace(
            state=state,
            config=config,
            memory_board_store=None,
            recovery_policy_resolver=None,
            allowed_actions_resolver=None,
            log=None,
        )
        builder = OrchestratorPromptBuilder(agent)
        prompt = builder.build_active_intent_contract_prompt()
        self.assertIn("nominal_steps_remaining: 0", prompt)
        self.assertIn("hard_steps_remaining: 1", prompt)
        self.assertIn("step_budget_status: nominal limit reached but hard-limit completion allowance remains", prompt)


if __name__ == "__main__":
    unittest.main()
