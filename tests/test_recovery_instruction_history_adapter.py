from unittest.mock import MagicMock

from modules.agent.orchestration.runtime.dispatch_outcome_history import DispatchOutcomeHistoryAdapter


def test_history_adapter_adds_recovery_instruction_with_visibility_metadata():
    history = MagicMock()
    adapter = DispatchOutcomeHistoryAdapter(history)
    visibility = {
        "mode": "until_same_action_success",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "create_file",
        "target": "a.txt",
        "created_turn_id": 7,
    }

    adapter.add_recovery_instruction(
        "Retry create_file with real content.",
        recovery_visibility=visibility,
    )

    history.add_message.assert_called_once_with(
        "system",
        "Retry create_file with real content.",
        msg_type="recovery_instruction",
        recovery_visibility=visibility,
    )


def test_history_adapter_ignores_empty_recovery_instruction():
    history = MagicMock()
    adapter = DispatchOutcomeHistoryAdapter(history)

    adapter.add_recovery_instruction("", recovery_visibility={"mode": "next_turn"})
    adapter.add_recovery_instruction(None, recovery_visibility={"mode": "next_turn"})

    history.add_message.assert_not_called()
