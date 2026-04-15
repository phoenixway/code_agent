import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.command_handler import CommandHandler
from modules.context import ContextManager
from modules.files import FileModule
from modules.history import HistoryManager
from modules.policy import PermissionPolicy
from modules.processor import ResponseProcessor
from modules.tools.manager import ToolManager


class MockChatProvider:
    async def get_streaming_response(self, prompt, history):
        yield "ok"


class TestSmokeUserFlow(unittest.IsolatedAsyncioTestCase):
    async def test_add_prompt_tool_drop_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "sample.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("hello smoke")

            ui = AsyncMock()
            ui.show_diff_preview = AsyncMock(return_value=True)
            ui.confirm_action = AsyncMock(return_value=True)
            ui.confirm_truncation = AsyncMock(return_value=False)

            history = HistoryManager(
                MockChatProvider(),
                max_tokens=4000,
                storage_dir=os.path.join(tmpdir, ".angelica_test"),
            )
            context_manager = ContextManager(FileModule())

            agent = SimpleNamespace(
                context_manager=context_manager,
                history=history,
                log=MagicMock(),
                session_manager=MagicMock(clear_session=MagicMock(return_value=False)),
                config=SimpleNamespace(settings={"available_models": []}),
                chat=SimpleNamespace(model_name="mock-model"),
                history_size="small",
                set_history_size=MagicMock(),
            )
            app = SimpleNamespace(agent=agent, ui=ui)
            command_handler = CommandHandler(app)

            handled_add = await command_handler.handle(f"/add {file_path}")
            self.assertTrue(handled_add)
            self.assertIn(file_path, context_manager.basket)

            tool_manager = ToolManager()
            tool_manager.load_tools()
            policy = PermissionPolicy(ui, mode="always")
            processor = ResponseProcessor(
                ui=ui,
                tool_manager=tool_manager,
                chat=None,
                policy=policy,
                history=history,
            )

            result = await processor.process_single_action({"type": "read_file", "path": file_path})
            self.assertEqual(result["status"], "success")
            self.assertIn(file_path, history.files)

            handled_drop = await command_handler.handle(f"/drop {file_path}")
            self.assertTrue(handled_drop)
            self.assertNotIn(file_path, context_manager.basket)
            self.assertNotIn(file_path, history.files)


if __name__ == "__main__":
    unittest.main()
