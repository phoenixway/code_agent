from types import SimpleNamespace
import unittest

from modules.agent.orchestration.decision_models import RecoveryContext
from modules.agent.orchestration.recovery_policy import RecoveryPolicyResolver


class RecoveryPolicyResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = RecoveryPolicyResolver()

    def test_normalize_context_derives_policy_from_active_intent(self):
        ctx = self.resolver.normalize_context(
            {
                "reason": "retry_or_continuation_after_failure",
                "next_actions": ["search_content", "edit_file", "write_file"],
                "next_actions_source": "recommended",
            },
            active_intent=SimpleNamespace(
                intent_type="INVESTIGATE",
                allowed_actions=["read_chunk", "read_file", "search_content"],
            ),
        )

        resolved = ctx.resolved_action_policy()

        self.assertIsNotNone(resolved)
        self.assertEqual(["search_content"], resolved.allowed_actions)
        self.assertEqual(["search_content"], resolved.recommended_actions)
        self.assertEqual("recommended", resolved.authoritative_source)
        self.assertTrue(resolved.keep_current_intent)

    def test_conflicting_legacy_recovery_prefers_current_intent_for_non_modify_active_intent(self):
        ctx = self.resolver.normalize_context(
            RecoveryContext(
                reason="action_not_allowed_in_phase",
                next_actions=["search_content", "edit_file", "write_file"],
                next_actions_source="recommended",
            ),
            active_intent=SimpleNamespace(
                intent_type="INVESTIGATE",
                allowed_actions=["read_chunk", "read_file", "search_content"],
            ),
        )

        self.assertTrue(
            self.resolver.should_prefer_current_intent_recovery(
                ctx,
                active_intent=SimpleNamespace(
                    intent_type="INVESTIGATE",
                    allowed_actions=["read_chunk", "read_file", "search_content"],
                ),
            )
        )


if __name__ == "__main__":
    unittest.main()
