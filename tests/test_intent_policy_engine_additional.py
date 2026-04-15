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


def make_ctx(
    *,
    active=None,
    proposed=None,
    same_lineage=False,
    goal_similarity=0.0,
    actions_overlap=0.0,
):
    return IntentPolicyContext(
        active_intent=active,
        proposed_intent=proposed,
        transition_info={
            "same_lineage": same_lineage,
            "goal_similarity": goal_similarity,
            "actions_overlap": actions_overlap,
        },
        recent_problem_actions=[],
        blocked_action_signatures=set(),
        blocked_action_reasons={},
        pending_loop_stop_info=None,
        current_user_input="",
    )


class AllowTransitionTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def test_allow_replace_for_materially_different_goal(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday in the activity tracker",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="weekly_planning_analysis",
            goal="Analyze the weekly planning screen architecture and loading flow",
            allowed_actions=["read_file", "read_chunk", "search_content"],
            mode="replace",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=False,
                goal_similarity=0.05,
                actions_overlap=0.25,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("allow_replace", decision.reason)
        self.assertEqual("ALLOW_REPLACE", decision.error_code)
        self.assertEqual("allow_replace", decision.message_key)

    def test_allow_complete_message_key(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
            mode="complete",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=1.0,
                actions_overlap=1.0,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("allow_complete", decision.reason)
        self.assertEqual("ALLOW_COMPLETE", decision.error_code)
        self.assertEqual("allow_complete", decision.message_key)

    def test_allow_activate_metadata_contains_mode(self):
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
            mode="activate",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(active=None, proposed=proposed)
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("activate", decision.metadata.get("mode"))


class RetryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def test_retry_same_goal_allowed(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
            mode="retry",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=1.0,
                actions_overlap=1.0,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("allow_retry", decision.reason)
        self.assertEqual("allow_retry", decision.message_key)
        self.assertTrue(decision.keep_current_intent)

    def test_retry_with_changed_actions_but_same_goal_allowed(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_file", "read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "read_file_skeleton"],
            mode="retry",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=1.0,
                actions_overlap=0.33,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("allow_retry", decision.reason)

    def test_retry_with_changed_goal_rejected_even_if_same_intent_id(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Read only the dialog composable lines",
            allowed_actions=["read_chunk"],
            mode="retry",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=0.2,
                actions_overlap=0.5,
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("retry_goal_change_forbidden", decision.reason)


class GoalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def test_same_goal_normalization_does_not_trigger_drift(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday!",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal=" determine how to move todays record to yesterday ",
            allowed_actions=["read_chunk", "search_content"],
            mode="activate",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=1.0,
                actions_overlap=1.0,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertNotEqual("suspect_intent_goal_drift", decision.reason)

    def test_local_probe_goal_is_rejected_as_goal_drift(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to allow moving today's activity record to yesterday in the UI via the edit dialog",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="read dialog lines",
            allowed_actions=["read_chunk", "search_content"],
            mode="activate",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=0.1,
                actions_overlap=0.66,
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("suspect_intent_goal_drift", decision.reason)

    def test_empty_goal_does_not_crash_policy(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="",
            allowed_actions=["read_chunk"],
            mode="activate",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=0.0,
                actions_overlap=0.5,
            )
        )

        self.assertFalse(decision.allowed)
        self.assertIn(
            decision.reason,
            {"suspect_intent_goal_drift", "retry_goal_change_forbidden"},
        )


class RelabelPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def test_same_lineage_similar_goal_high_action_overlap_rejected_as_relabel(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's activity record to yesterday via the edit dialog",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
        )
        proposed = make_intent(
            intent_id="investigate_edit_dialog",
            goal="Determine how to move today's record to yesterday via edit dialog",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
            mode="activate",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=0.9,
                actions_overlap=1.0,
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("suspect_intent_relabel_repeat", decision.reason)

    def test_different_intent_type_not_treated_as_same_lineage(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            intent_type="INVESTIGATE",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit_execution",
            intent_type="IMPLEMENT",
            goal="Implement support for changing activity record day in edit dialog",
            allowed_actions=["write_file", "edit_file", "read_chunk"],
            mode="replace",
        )

        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=False,
                goal_similarity=0.2,
                actions_overlap=0.2,
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("allow_replace", decision.reason)


class BlockedActionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def test_blocked_action_metadata_contains_blocked_reason(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
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

        self.assertEqual(
            "planned_full_read_too_large",
            decision.metadata.get("blocked_reason"),
        )
        self.assertEqual(
            "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt",
            decision.metadata.get("command", {}).get("path"),
        )

    def test_blocked_action_with_no_active_intent_returns_safe_recovery(self):
        ctx = BlockedActionPolicyContext(
            active_intent=None,
            command={"type": "read_file", "path": "some/file.kt"},
            blocked_reason="planned_full_read_too_large",
        )

        decision = self.engine.evaluate_blocked_action(ctx)

        self.assertFalse(decision.allowed)
        self.assertEqual("blocked_action_keep_current_intent", decision.message_key)
        self.assertEqual([], decision.next_actions)


if __name__ == "__main__":
    unittest.main()
