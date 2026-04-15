import json
import os
import tempfile
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from modules.session import SessionManager


class TestSessionManager(unittest.IsolatedAsyncioTestCase):
    async def test_load_session_emits_notice_for_non_empty_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                session_path = os.path.join(tmpdir, ".angelica_session.json")
                data = {
                    "history": [{"role": "user", "content": "hello"}],
                    "context": ["README.md"],
                }
                with open(session_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                history = MagicMock()
                history.messages = []
                context = MagicMock()
                ui = MagicMock()
                ui.print_system = AsyncMock()

                manager = SessionManager(history, context, ui)
                manager.load_session()

                # allow scheduled create_task callback to run
                await asyncio.sleep(0)

                self.assertTrue(manager.loaded_session)
                self.assertEqual(manager.loaded_messages_count, 1)
                self.assertEqual(manager.loaded_context_count, 1)
                ui.print_system.assert_called_once()
            finally:
                os.chdir(original_dir)
