import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules.agent.model_client import ModelClient
from modules.history import HistoryManager


class _DummyChatProvider:
    def count_tokens(self, text):
        return len(str(text or ""))


class RecoveryVisibilityCharacterizationTests(unittest.TestCase):
    def test_recovery_instruction_metadata_is_preserved_in_raw_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            visibility = {
                "mode": "next_turn",
                "intent_scope": "current_intent",
                "intent_id": "intent-1",
                "intent_type": "MODIFY",
                "action_type": "search_content",
                "target": "modules/history.py",
                "created_turn_id": 7,
            }

            history.add_message(
                "system",
                "SYSTEM: retry search_content with literal=true",
                msg_type="recovery_instruction",
                recovery_visibility=visibility,
            )

            self.assertEqual(1, len(history.messages))
            stored = history.messages[0]
            self.assertEqual("system", stored["role"])
            self.assertEqual("recovery_instruction", stored["type"])
            self.assertEqual(visibility, stored["recovery_visibility"])
            self.assertIn("literal=true", stored["content"])

    def test_recovery_like_system_messages_without_visibility_metadata_remain_model_visible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            recovery_text = "SYSTEM: Return only a corrected compact recovery step."

            history.add_message("user", "Fix the failed edit")
            history.add_message("system", recovery_text)

            api_history = history.get_history_for_api()
            rendered = [msg["content"] for msg in api_history]

            self.assertIn("Fix the failed edit", rendered)
            self.assertIn(recovery_text, rendered)

    def test_recovery_instruction_message_type_is_legacy_visible_until_filtering_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
            recovery_text = "SYSTEM: create_file requires file body in content or file_content."

            history.add_message(
                "system",
                recovery_text,
                msg_type="recovery_instruction",
                recovery_visibility={
                    "mode": "until_same_action_success",
                    "intent_scope": "current_intent",
                    "intent_id": "intent-1",
                    "intent_type": "MODIFY",
                    "action_type": "create_file",
                    "target": "app/build.gradle.kts",
                    "created_turn_id": 3,
                },
            )

            api_history = history.get_history_for_api()
            rendered = [msg["content"] for msg in api_history]

            self.assertIn(recovery_text, rendered)

    def test_model_client_injected_messages_are_runtime_overlay_after_stable_system_and_history(self):
        captured = {}

        class DummyChat:
            async def get_streaming_response(self, prompt, history):
                captured["prompt"] = prompt
                captured["history"] = history
                if False:
                    yield ""

        class DummyHistory:
            def get_history_for_api(self):
                return [{"role": "assistant", "content": "older history"}]

        cfg = SimpleNamespace(default_model="dummy")
        with patch("modules.agent.model_client.get_chat_provider", return_value=DummyChat()):
            client = ModelClient(cfg)

        async def _run():
            return await client.get_streaming_response(
                "current user query",
                DummyHistory(),
                system_message="stable system prompt",
                injected_messages=[
                    {
                        "role": "system",
                        "content": "## CURRENT RECOVERY INSTRUCTIONS\nRetry search_content with literal=true.",
                    }
                ],
            )

        result = asyncio.run(_run())

        self.assertEqual("", result)
        self.assertEqual("current user query", captured["prompt"])
        self.assertEqual(
            [
                {"role": "system", "content": "stable system prompt"},
                {"role": "assistant", "content": "older history"},
                {
                    "role": "system",
                    "content": "## CURRENT RECOVERY INSTRUCTIONS\nRetry search_content with literal=true.",
                },
            ],
            captured["history"],
        )


if __name__ == "__main__":
    unittest.main()
