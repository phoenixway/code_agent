import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from modules.command_handler import CommandHandler
from modules.system_prompts import discover_system_prompt_files, prompt_display_name


class TestSystemPromptDiscovery(unittest.TestCase):
    def test_discovers_markdown_prompts_recursively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "doctor").mkdir()
            (root / "doctor" / "intake.md").write_text("doctor", encoding="utf-8")
            (root / "rpg").mkdir()
            (root / "rpg" / "narrator.md").write_text("rpg", encoding="utf-8")
            (root / "ignore.txt").write_text("skip", encoding="utf-8")

            prompts = discover_system_prompt_files(
                {
                    "system_prompt_directory": str(root),
                    "current_system_prompt_path": str(root / "doctor" / "intake.md"),
                }
            )

            labels = [prompt_display_name(path, root) for path in prompts]
            self.assertEqual(labels, ["doctor/intake.md", "rpg/narrator.md"])


class TestPromptCommand(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_command_updates_active_prompt_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "doctor").mkdir()
            selected_prompt = root / "doctor" / "intake.md"
            selected_prompt.write_text("doctor", encoding="utf-8")

            app = MagicMock()
            app.agent = MagicMock()
            app.agent.config = SimpleNamespace(
                settings={
                    "system_prompt_directory": str(root),
                    "current_system_prompt_path": str(selected_prompt),
                }
            )
            app.ui = AsyncMock()
            app.ui.pick_option = AsyncMock(return_value="doctor/intake.md")

            handler = CommandHandler(app)

            with patch(
                "modules.command_handler.update_settings",
                return_value={
                    "system_prompt_directory": str(root),
                    "current_system_prompt_path": str(selected_prompt),
                },
            ) as mocked_update:
                handled = await handler.handle("/prompt")

            self.assertTrue(handled)
            mocked_update.assert_called_once_with(
                {"current_system_prompt_path": str(selected_prompt)}
            )
            app.ui.print_system.assert_called_with(
                "🧠 System prompt switched to: doctor/intake.md"
            )
