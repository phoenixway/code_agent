import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modules.policy import PermissionPolicy


class PermissionPolicyReadChunkTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_chunk_is_auto_allowed_as_read_only_action(self):
        ui = SimpleNamespace(
            confirm_action=AsyncMock(return_value=False),
            print_error=AsyncMock(),
        )
        policy = PermissionPolicy(ui, mode="ask")

        result = await policy.check(
            {
                "type": "read_chunk",
                "path": "a.py",
                "start_line": 1,
                "end_line": 20,
            }
        )

        self.assertTrue(result)
        ui.confirm_action.assert_not_awaited()

    async def test_extract_kotlin_function_is_auto_allowed_as_read_only_action(self):
        ui = SimpleNamespace(
            confirm_action=AsyncMock(return_value=False),
            print_error=AsyncMock(),
        )
        policy = PermissionPolicy(ui, mode="ask")

        result = await policy.check(
            {
                "type": "extract_kotlin_function",
                "path": "Sample.kt",
                "function_name": "renderCard",
            }
        )

        self.assertTrue(result)
        ui.confirm_action.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
