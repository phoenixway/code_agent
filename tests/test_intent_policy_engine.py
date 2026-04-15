import unittest
from types import SimpleNamespace

from modules.agent.intent_policy_engine import IntentPolicyEngine
from modules.agent.intent_policy_models import (
    BlockedActionPolicyContext,
    IntentPolicyContext,
)


class DummyConfig:
    INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD = 0.45
    INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD = 0.6
    INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD = 0.6


def make_intent(
    *,
    intent_id: str,
    goal: str,
    allowed_actions=None,
    mode: str = "activate",
    intent_type: str = "INVESTIGATE",
    canonical_goal: str | None = None,
):
    return SimpleNamespace(
        intent_id=intent_id,
        intent_type=intent_type,
        goal=goal,
        canonical_goal=canonical_goal if canonical_goal is not None else goal,
        allowed_actions=list(allowed_actions or []),
        mode=mode,
    )


class IntentPolicyEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def build_ctx(self, *, active=None, proposed=None, transition_info=None):
        return IntentPolicyContext(
            active_intent=active,
            proposed_intent=proposed,
            transition_info=dict(transition_info or {}),
            recent_problem_actions=[],
            blocked_action_signatures=set(),
            blocked_action_reasons={},
            pending_loop_stop_info=None,
            current_user_input="",
        )

    def test_allow_activate_when_no_active_intent(self):
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Understand how to move today's record to yesterday via edit dialog",
            allowed_actions=["read_file", "read_chunk", "search_content"],
            mode="activate",
        )
        ctx = self.build_ctx(active=None, proposed=proposed)

        decision = self.engine.evaluate_transition(ctx)

        self.assertTrue(decision.allowed)
        self.assertEqual("allow_activate", decision.reason)
        self.assertEqual("ALLOW_ACTIVATE", decision.error_code)
        self.assertEqual("allow_activate", decision.message_key)

    def test_retry_cannot_change_goal(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Understand how to move today's record to yesterday via edit dialog",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Read only the dialog composable implementation",
            allowed_actions=["read_chunk", "search_content"],
            mode="retry",
        )
        ctx = self.build_ctx(
            active=active,
            proposed=proposed,
            transition_info={
                "same_lineage": True,
                "goal_similarity": 0.25,
                "actions_overlap": 1.0,
            },
        )

        decision = self.engine.evaluate_transition(ctx)

        self.assertFalse(decision.allowed)
        self.assertEqual("retry_goal_change_forbidden", decision.reason)
        self.assertEqual("RETRY_GOAL_CHANGE_FORBIDDEN", decision.error_code)
        self.assertTrue(decision.keep_current_intent)
        self.assertTrue(decision.preserve_goal)
        self.assertTrue(decision.preserve_intent_id)

    def test_same_lineage_cosmetic_relabel_rejected(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to allow moving today's record to yesterday in the activity tracker",
            allowed_actions=["read_file", "read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="investigate_edit_dialog",
            goal="Determine how to allow moving today's record to yesterday in the activity tracker",
            allowed_actions=["read_file", "read_chunk", "search_content"],
            mode="activate",
        )
        ctx = self.build_ctx(
            active=active,
            proposed=proposed,
            transition_info={
                "same_lineage": True,
                "goal_similarity": 1.0,
                "actions_overlap": 1.0,
            },
        )

        decision = self.engine.evaluate_transition(ctx)

        self.assertFalse(decision.allowed)
        self.assertEqual("suspect_intent_relabel_repeat", decision.reason)
        self.assertEqual("SUSPECT_INTENT_RELABEL_REPEAT", decision.error_code)
        self.assertTrue(decision.keep_current_intent)
        self.assertTrue(decision.allow_user_handoff)
        self.assertEqual("allow_pending_suspect_intent_once", decision.allow_once_via_state_method)

    def test_same_lineage_goal_drift_rejected(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to allow moving today's activity record to yesterday in the UI via the edit dialog",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Read the dialog lines",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
            mode="activate",
        )
        ctx = self.build_ctx(
            active=active,
            proposed=proposed,
            transition_info={
                "same_lineage": True,
                "goal_similarity": 0.2,
                "actions_overlap": 1.0,
            },
        )

        decision = self.engine.evaluate_transition(ctx)

        self.assertFalse(decision.allowed)
        self.assertEqual("suspect_intent_goal_drift", decision.reason)
        self.assertEqual("SUSPECT_INTENT_GOAL_DRIFT", decision.error_code)
        self.assertTrue(decision.keep_current_intent)
        self.assertTrue(decision.allow_user_handoff)
        self.assertEqual("allow_pending_goal_drift_once", decision.allow_once_via_state_method)

    def test_blocked_action_keeps_current_intent_alive(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to allow moving today's record to yesterday",
            allowed_actions=["read_chunk", "search_content", "read_file_skeleton"],
        )
        ctx = BlockedActionPolicyContext(
            active_intent=active,
            command={
                "type": "read_file",
                "path": "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt",
            },
            blocked_reason="planned_full_read_too_large",
        )

        decision = self.engine.evaluate_blocked_action(ctx)

        self.assertFalse(decision.allowed)
        self.assertEqual("intent_blocked_action_signature", decision.reason)
        self.assertEqual("INTENT_BLOCKED_ACTION_SIGNATURE", decision.error_code)
        self.assertEqual("blocked_action_keep_current_intent", decision.message_key)
        self.assertTrue(decision.keep_current_intent)
        self.assertTrue(decision.preserve_goal)
        self.assertTrue(decision.preserve_intent_id)
        self.assertEqual(
            ["read_chunk", "search_content", "read_file_skeleton"],
            decision.next_actions,
        )


if __name__ == "__main__":
    unittest.main()
