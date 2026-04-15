import unittest
from types import SimpleNamespace

from modules.agent.intent_policy_engine import IntentPolicyEngine
from modules.agent.intent_policy_models import IntentPolicyContext, BlockedActionPolicyContext


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


class IntentPolicyEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntentPolicyEngine(DummyConfig())

    def test_empty_intent_id_does_not_crash_and_current_behavior_allows_activate(self):
        proposed = make_intent(
            intent_id="",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
            mode="activate",
        )
        decision = self.engine.evaluate_transition(make_ctx(active=None, proposed=proposed))
        self.assertTrue(decision.allowed)
        self.assertEqual("allow_activate", decision.reason)

    def test_empty_allowed_actions_is_handled_without_crash(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=[],
            mode="retry",
        )
        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=1.0,
                actions_overlap=0.0,
            )
        )
        self.assertTrue(decision.allowed)
        self.assertEqual("allow_retry", decision.reason)

    def test_same_lineage_false_with_similar_goal_allows_replace(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday via edit dialog",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="dialog_search",
            goal="Determine how to move todays record to yesterday via edit dialog",
            allowed_actions=["search_files", "search_content"],
            mode="replace",
        )
        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=False,
                goal_similarity=0.95,
                actions_overlap=0.33,
            )
        )
        self.assertTrue(decision.allowed)
        self.assertEqual("allow_replace", decision.reason)

    def test_same_lineage_true_low_action_overlap_same_goal_still_rejected_as_cosmetic_relabel(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday via edit dialog",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
        )
        proposed = make_intent(
            intent_id="investigate_dialog",
            goal="Determine how to move today's record to yesterday via edit dialog",
            allowed_actions=["run_shell"],
            mode="activate",
        )
        decision = self.engine.evaluate_transition(
            make_ctx(
                active=active,
                proposed=proposed,
                same_lineage=True,
                goal_similarity=1.0,
                actions_overlap=0.0,
            )
        )
        self.assertFalse(decision.allowed)
        self.assertEqual("suspect_intent_relabel_repeat", decision.reason)

    def test_ukrainian_local_probe_goal_rejected_as_drift(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Визначити як переносити сьогоднішній запис на вчора через діалог редагування",
            allowed_actions=["read_chunk", "search_content", "read_file_skeleton"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal="прочитати діалог",
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

    def test_normalization_regression_same_goal_allowed(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday.",
            allowed_actions=["read_chunk", "search_content"],
        )
        proposed = make_intent(
            intent_id="activity_tracker_edit",
            goal=" determine how to move today s record to yesterday ",
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

    def test_blocked_action_with_empty_reason_keeps_safe_metadata(self):
        active = make_intent(
            intent_id="activity_tracker_edit",
            goal="Determine how to move today's record to yesterday",
            allowed_actions=["read_chunk", "search_content"],
        )
        decision = self.engine.evaluate_blocked_action(
            BlockedActionPolicyContext(
                active_intent=active,
                command={"type": "read_file", "path": "a.kt"},
                blocked_reason="",
            )
        )
        self.assertFalse(decision.allowed)
        self.assertEqual("", decision.metadata.get("blocked_reason", ""))
        self.assertEqual("a.kt", decision.metadata.get("command", {}).get("path"))

    def test_complete_same_goal_allowed(self):
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


if __name__ == "__main__":
    unittest.main()
