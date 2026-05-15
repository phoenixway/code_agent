import tempfile
import unittest
from types import SimpleNamespace

from modules.history import HistoryManager


class _DummyChatProvider:
    def count_tokens(self, text):
        return len(str(text or ""))


def _state(intent_id="intent-1", current_turn_id=10, successes=None):
    return SimpleNamespace(
        active_intent=SimpleNamespace(intent_id=intent_id, intent_type="MODIFY") if intent_id else None,
        current_turn_id=current_turn_id,
        recovery_visibility_successes=list(successes or []),
    )


class RecoveryInstructionOverlayTests(unittest.TestCase):
    def test_build_recovery_instruction_overlay_returns_no_messages_without_visible_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            history.add_message("user", "Fix this")
            history.add_message("assistant", "I will inspect it")

            injected = history.build_recovery_instruction_injected_messages(state=_state())

            self.assertEqual([], injected)

    def test_build_recovery_instruction_overlay_includes_visible_recovery_instruction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            history.add_message(
                "system",
                "SYSTEM: Retry search_content with literal=true.",
                msg_type="recovery_instruction",
                recovery_visibility={
                    "mode": "next_turn",
                    "intent_scope": "current_intent",
                    "intent_id": "intent-1",
                    "intent_type": "MODIFY",
                    "action_type": "search_content",
                    "target": "modules/history.py",
                    "created_turn_id": 10,
                },
            )

            injected = history.build_recovery_instruction_injected_messages(state=_state(current_turn_id=10))

            self.assertEqual(1, len(injected))
            self.assertEqual("system", injected[0]["role"])
            self.assertIn("## CURRENT RECOVERY INSTRUCTIONS", injected[0]["content"])
            self.assertIn("Retry search_content with literal=true.", injected[0]["content"])

    def test_build_recovery_instruction_overlay_hides_recovery_from_changed_intent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            history.add_message(
                "system",
                "SYSTEM: Old intent recovery should not follow the new intent.",
                msg_type="recovery_instruction",
                recovery_visibility={
                    "mode": "next_turn",
                    "intent_scope": "current_intent",
                    "intent_id": "old-intent",
                    "created_turn_id": 10,
                },
            )

            injected = history.build_recovery_instruction_injected_messages(state=_state(intent_id="new-intent", current_turn_id=10))

            self.assertEqual([], injected)

    def test_build_recovery_instruction_overlay_hides_expired_next_turn_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            history.add_message(
                "system",
                "SYSTEM: Expired regex recovery.",
                msg_type="recovery_instruction",
                recovery_visibility={
                    "mode": "next_turn",
                    "intent_scope": "current_intent",
                    "intent_id": "intent-1",
                    "action_type": "search_content",
                    "created_turn_id": 10,
                },
            )

            injected = history.build_recovery_instruction_injected_messages(state=_state(current_turn_id=12))

            self.assertEqual([], injected)

    def test_build_recovery_instruction_overlay_preserves_raw_history_when_hidden(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            history.add_message(
                "system",
                "SYSTEM: Hidden from model-facing overlay, preserved in raw history.",
                msg_type="recovery_instruction",
                recovery_visibility={
                    "mode": "next_turn",
                    "intent_scope": "current_intent",
                    "intent_id": "old-intent",
                    "created_turn_id": 10,
                },
            )

            injected = history.build_recovery_instruction_injected_messages(state=_state(intent_id="new-intent", current_turn_id=10))

            self.assertEqual([], injected)
            self.assertEqual(1, len(history.messages))
            self.assertIn("Hidden from model-facing overlay", history.messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
