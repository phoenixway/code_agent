from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from modules.agent.policy_engine import PolicyEngine, PreActionPolicyInput
from modules.agent.state_machine import AgentStateMachine
from modules.history import HistoryManager


class _Config(SimpleNamespace):
    RECENT_SUMMARY_REREAD_WINDOW_SEC = 90
    MAX_BROAD_RECON_BATCHES = 2
    OBSERVE_BUDGET_INSPECTION = 6
    OBSERVE_BUDGET_HYBRID = 4
    OBSERVE_BUDGET_MODIFICATION = 2


def test_read_file_same_path_fresh_in_history_returns_versioned_recovery():
    engine = PolicyEngine()
    decision = engine.evaluate_pre_action(
        PreActionPolicyInput(
            cmd_type="read_file",
            path="a.py",
            fingerprint="fp",
            target_file=None,
            forbidden_recover_fingerprint=None,
            has_cross_target_reason=False,
            already_read_current_version=True,
            reread_reason_ok=False,
            reread_after_summary=False,
            history_version=4,
        )
    )
    assert not decision.allow
    assert decision.stop_reason == "reread_already_in_history"
    assert "version v4" in decision.recovery_prompt


def test_repeated_reread_same_path_uses_loop_breaker_message():
    engine = PolicyEngine()
    decision = engine.evaluate_pre_action(
        PreActionPolicyInput(
            cmd_type="read_file",
            path="a.py",
            fingerprint="fp",
            target_file=None,
            forbidden_recover_fingerprint=None,
            has_cross_target_reason=False,
            already_read_current_version=True,
            reread_reason_ok=False,
            reread_after_summary=False,
            history_version=2,
            reread_repeat_count=2,
        )
    )
    assert not decision.allow
    assert decision.stop_reason == "reread_already_in_history_use_existing_content"
    assert "Do not call read_file again" in decision.recovery_prompt


def test_read_file_after_local_edit_is_allowed():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "sample.py"
        path.write_text("before\n", encoding="utf-8")
        history = HistoryManager(None, storage_dir=Path(tmp) / ".angelica")
        history.add_file_version(str(path), "before\n")

        sm = AgentStateMachine(_Config())
        sm.history = history

        blocked = sm.pre_action_policy({"type": "read_file", "path": str(path)})
        assert not blocked.allow

        path.write_text("after\n", encoding="utf-8")
        allowed = sm.pre_action_policy({"type": "read_file", "path": str(path)})
        assert allowed.allow


def test_read_file_after_edit_mismatch_is_allowed():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "sample.py"
        path.write_text("same\n", encoding="utf-8")
        history = HistoryManager(None, storage_dir=Path(tmp) / ".angelica")
        history.add_file_version(str(path), "same\n")

        state = SimpleNamespace(
            pending_edit_mismatch_path=str(path),
            pending_edit_mismatch_intent_id="intent_1",
            reread_blocked_path="",
            reread_blocked_intent_id="",
            reread_blocked_count=0,
        )
        intent_runtime = SimpleNamespace(
            active_intent=SimpleNamespace(intent_id="intent_1", intent_type="MODIFY", step_count=0, safe_steps_limit=4),
            state=state,
        )

        sm = AgentStateMachine(_Config())
        sm.history = history
        sm.intent_runtime = intent_runtime

        decision = sm.pre_action_policy({"type": "read_file", "path": str(path)})
        assert decision.allow
