from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.history import HistoryManager


class _DummyChatProvider:
    async def get_streaming_response(self, *_args, **_kwargs):
        if False:
            yield ""


@pytest.mark.asyncio
async def test_working_material_emergency_prompt_uses_scoped_recovery_text():
    history = HistoryManager(_DummyChatProvider(), max_tokens=1000)
    history.SUMMARY_PROMPT_RATIO = 0.1
    history.EMERGENCY_SUMMARY_RATIO = 0.9
    history.TURN_WORKING_MATERIAL_SAFE_RATIO = 0.01

    history.add_message("user", "trigger summary pressure " * 50)
    history.current_turn_working_material_token_count = lambda *_args, **_kwargs: 999
    history._enforce_working_material_caps = lambda: None
    ui = SimpleNamespace(print_error=AsyncMock())

    result = await history.check_and_summarize(ui=ui)

    assert result is not None
    assert result["reason"] == "turn_working_material_too_large"
    assert result["error_code"] == "TURN_WORKING_MATERIAL_TOO_LARGE"
    assert "Protected working material is too large" in result["prompt"]
    assert "Return EXACTLY ONE" not in result["prompt"]
    assert "[RECOVERY_SCOPE]" in result["prompt"]
    assert "[NEXT_STEP_RULE]" in result["prompt"]
    assert "[EXIT_CONDITION]" in result["prompt"]
    ui.print_error.assert_awaited_once()
