# tests/test_resume_after_forced_plaintext_completion_project.py

import inspect
import types
import unittest
from types import SimpleNamespace


def _import_recovery_coordinator():
    from modules.agent.orchestration.runtime.recovery import RecoveryCoordinator
    return RecoveryCoordinator


def _import_orchestrator():
    from modules.agent.orchestration.runtime.core import Orchestrator
    return Orchestrator


def _import_prompt_builder():
    from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
    return OrchestratorPromptBuilder


def _import_intent_runtime():
    """
    Try the most likely locations without assuming one exact project layout.
    """
    candidates = [
        "modules.agent.intent_runtime",
        "modules.agent.orchestration.intent_runtime",
        "modules.agent.intent.runtime",
    ]
    last_err = None
    for mod_name in candidates:
        try:
            mod = __import__(mod_name, fromlist=["IntentRuntime"])
            return getattr(mod, "IntentRuntime")
        except Exception as exc:  # pragma: no cover
            last_err = exc
    raise RuntimeError(f"Could not import IntentRuntime from known locations: {last_err}")


class _DummyUI:
    def __init__(self, overrun_choice="stop_and_answer"):
        self.overrun_choice = overrun_choice
        self.system_messages = []
        self.error_messages = []

    async def choose_intent_overrun_action(self, _message):
        return self.overrun_choice

    async def print_system(self, text):
        self.system_messages.append(text)

    async def print_error(self, text):
        self.error_messages.append(text)

    async def print_message(self, text, role="assistant"):
        return None

    async def stop_loading(self):
        return None


class _DummyPromptBuilder:
    def build_plain_text_completion_prompt(self, sm, stop_info):
        reason = (stop_info or {}).get("reason", "")
        return f"PLAIN_TEXT_COMPLETION::{reason}"

    def build_intent_overrun_message(self, stop_info):
        return f"OVERRUN::{(stop_info or {}).get('reason', '')}"

    def build_intent_overrun_confirmation_suffix(self):
        return "\nCONFIRM"

    def build_keep_current_intent_recovery_prompt(self, stop_info):
        reason = (stop_info or {}).get("reason", "")
        return f"KEEP_CURRENT::{reason}"

    def build_recently_completed_same_lineage_reuse_hint(self):
        return (
            "If the user is continuing the same just-finished line of work, "
            "request <intent mode=\"reuse\"> for the same lineage with refreshed steps."
        )


class _DummyRecoveryPolicyResolver:
    def normalize_context(self, stop_info, active_intent=None):
        if hasattr(stop_info, "to_stop_info"):
            return stop_info
        data = dict(stop_info or {})
        return SimpleNamespace(
            reason=str(data.get("reason") or ""),
            to_stop_info=lambda: data,
            resolved_action_policy=lambda: None,
            intent_allowed_actions=list(data.get("intent_allowed_actions") or []),
            next_actions=list(data.get("next_actions") or []),
            next_actions_source=str(data.get("next_actions_source") or ""),
        )


class _DummyState:
    def __init__(self):
        self.active_intent = None
        self.intent_runtime = None
        self.pending_loop_stop_info = None
        self.confirmation_count = 0
        self.last_completed_intent_type = ""
        self.last_resumable_intent_id = ""
        self.last_resumable_intent_type = ""
        self.last_resumable_intent_goal = ""
        self.last_resumable_intent_lineage_id = ""
        self.last_resumable_completion_reason = ""
        self.pending_finalize_after_terminal_render = False
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.readonly_steps_this_turn = 0

    def add_confirmation(self, n):
        self.confirmation_count += int(n)

    def active_intent_summary(self):
        if self.active_intent is None:
            return ""
        return f"{self.active_intent.intent_id}:{self.active_intent.intent_type}"

    def clear_active_intent(self):
        self.active_intent = None


class _DummyAgent:
    def __init__(self, ui=None):
        self.ui = ui or _DummyUI()
        self.state = _DummyState()
        self.config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        self.log = None
        self.recovery_policy_resolver = _DummyRecoveryPolicyResolver()
        self.allowed_actions_resolver = None
        self.history = SimpleNamespace(
            current_token_count=0,
            max_tokens=10000,
            check_and_summarize=_async_noop,
        )
        self.model_client = None
        self.action_dispatcher = None
        self.parser = None
        self.tool_manager = SimpleNamespace(get_tools_prompt=lambda: "")
        self.context_manager = SimpleNamespace(get_context_prompt=lambda: "")
        self.memory_board_store = None
        self.memory_board_engine = None


async def _async_noop(*args, **kwargs):
    return None


def _make_active_intent():
    return SimpleNamespace(
        intent_id="per_link_vault_e2e",
        intent_type="MODIFY",
        goal="Implement end-to-end per-link vault support",
        allowed_actions=["read_chunk", "edit_file", "search_content"],
        lineage_id="lineage-per-link-vault",
    )


def _capture_resumable_metadata(state, completion_reason="forced_plaintext_completion"):
    active = state.active_intent
    state.last_resumable_intent_id = getattr(active, "intent_id", "") or ""
    state.last_resumable_intent_type = getattr(active, "intent_type", "") or ""
    state.last_resumable_intent_goal = getattr(active, "goal", "") or ""
    state.last_resumable_intent_lineage_id = getattr(active, "lineage_id", "") or ""
    state.last_resumable_completion_reason = completion_reason


def _maybe_finalize_after_terminal_render(state):
    if not bool(getattr(state, "pending_finalize_after_terminal_render", False)):
        return False
    active = getattr(state, "active_intent", None)
    if active is not None:
        _capture_resumable_metadata(state, completion_reason="forced_plaintext_completion")
    state.active_intent = None
    state.pending_finalize_after_terminal_render = False
    state.terminal_plaintext_completion_pending = False
    state.terminal_plaintext_completion_text = ""
    return True


def _build_resume_hint_text(state):
    intent_id = str(getattr(state, "last_resumable_intent_id", "") or "").strip()
    lineage = str(getattr(state, "last_resumable_intent_lineage_id", "") or "").strip()
    goal = str(getattr(state, "last_resumable_intent_goal", "") or "").strip()
    completion_reason = str(getattr(state, "last_resumable_completion_reason", "") or "").strip()
    if not intent_id:
        return ""
    return (
        "Recently completed resumable intent detected.\n"
        f"intent_id={intent_id}\n"
        f"lineage_id={lineage}\n"
        f"goal={goal}\n"
        f"completion_reason={completion_reason}\n"
        "If the user is continuing the same line of work, request "
        "<intent mode=\"reuse\"> for the same intent_id with refreshed steps."
    )


def _construct_intent_runtime(IntentRuntime, state, config):
    """
    Adapt to multiple possible constructor signatures.
    """
    attempts = [
        lambda: IntentRuntime(config, state),
        lambda: IntentRuntime(config=config, state=state),
        lambda: IntentRuntime(config=config),
        lambda: IntentRuntime(state=state),
        lambda: IntentRuntime(config),
        lambda: IntentRuntime(),
    ]
    last_exc = None
    runtime = None
    for ctor in attempts:
        try:
            runtime = ctor()
            break
        except TypeError as exc:
            last_exc = exc
            continue
    if runtime is None:
        raise AssertionError(f"Could not construct IntentRuntime adaptively: {last_exc}")

    if getattr(runtime, "state", None) is None:
        try:
            runtime.state = state
        except Exception:
            pass

    if getattr(runtime, "config", None) is None:
        try:
            runtime.config = config
        except Exception:
            pass
    runtime.state = state
    runtime.config = config
    return runtime


def _apply_reuse_payload_adaptively(runtime, state, payload):
    """
    Adapt to several possible runtime APIs.
    Returns a tuple: (ok, msg, transition_info, active_intent)
    """
    print("runtime.state is None:", getattr(runtime, "state", None) is None)
    print("recent meta:", runtime._recent_resumable_intent_meta())
    print("can reuse recent:", runtime._can_reuse_recently_completed_intent())
    print("state.last_resumable_intent_id:", getattr(state, "last_resumable_intent_id", None))
    print("state.last_resumable_intent_type:", getattr(state, "last_resumable_intent_type", None))
    print("state.last_resumable_intent_goal:", getattr(state, "last_resumable_intent_goal", None))
    print("state.last_resumable_intent_lineage_id:", getattr(state, "last_resumable_intent_lineage_id", None))
    print("state.last_resumable_completion_reason:", getattr(state, "last_resumable_completion_reason", None))
    print("state.last_resumable_intent_completion_reason:", getattr(state, "last_resumable_intent_completion_reason", None))
    if hasattr(runtime, "apply_payload") and callable(runtime.apply_payload):
        result = runtime.apply_payload(payload)
        transition_info = getattr(runtime, "last_transition_info", {}) or {}
        active = getattr(runtime, "active_intent", None) or getattr(state, "active_intent", None)
        if isinstance(result, tuple) and len(result) >= 2:
            return result[0], result[1], transition_info, active
        return bool(result), str(result), transition_info, active

    if hasattr(runtime, "apply_intent_contract") and callable(runtime.apply_intent_contract):
        result = runtime.apply_intent_contract(payload, getattr(runtime, "config", None))
        transition_info = getattr(runtime, "last_transition_info", {}) or {}
        active = getattr(runtime, "active_intent", None) or getattr(state, "active_intent", None)
        if isinstance(result, tuple) and len(result) >= 2:
            return result[0], result[1], transition_info, active
        return bool(result), str(result), transition_info, active

    if hasattr(state, "apply_intent_contract") and callable(state.apply_intent_contract):
        result = state.apply_intent_contract(payload, getattr(runtime, "config", None))
        transition_info = getattr(runtime, "last_transition_info", {}) or {}
        active = getattr(runtime, "active_intent", None) or getattr(state, "active_intent", None)
        if isinstance(result, tuple) and len(result) >= 2:
            return result[0], result[1], transition_info, active
        return bool(result), str(result), transition_info, active

    raise AssertionError("No adaptive apply path found for IntentRuntime/state")


class ForcedPlaintextCompletionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_hard_limit_stop_and_answer_marks_contract_for_finalize_after_render(self):
        RecoveryCoordinator = _import_recovery_coordinator()

        agent = _DummyAgent(ui=_DummyUI(overrun_choice="stop_and_answer"))
        active = _make_active_intent()
        agent.state.active_intent = active
        agent.state.intent_runtime = SimpleNamespace(
            force_current_intent_completion=lambda: None
        )

        recovery = RecoveryCoordinator(agent, _DummyPromptBuilder())

        decision = await recovery.handle_defect_detector_stop(
            {
                "reason": "intent_step_limit_exceeded",
                "recoverable": True,
                "next_actions": ["read_chunk"],
                "intent_allowed_actions": ["read_chunk"],
                "next_actions_source": "intent",
            }
        )

        self.assertTrue(decision.continue_loop)
        self.assertIn("PLAIN_TEXT_COMPLETION::user_stopped_after_hard_limit_answer_from_current_evidence", decision.next_query)
        self.assertTrue(getattr(agent.state, "pending_finalize_after_terminal_plaintext_completion", False))


class FinalizeAfterTerminalRenderTests(unittest.TestCase):
    def test_finalize_after_terminal_render_closes_contract_and_preserves_resumable_metadata(self):
        state = _DummyState()
        state.active_intent = _make_active_intent()
        state.pending_finalize_after_terminal_render = True
        state.terminal_plaintext_completion_pending = True
        state.terminal_plaintext_completion_text = "Here is the best answer from current evidence."

        changed = _maybe_finalize_after_terminal_render(state)

        self.assertTrue(changed)
        self.assertIsNone(state.active_intent)
        self.assertFalse(state.pending_finalize_after_terminal_render)
        self.assertFalse(state.terminal_plaintext_completion_pending)
        self.assertEqual("", state.terminal_plaintext_completion_text)
        self.assertEqual("per_link_vault_e2e", state.last_resumable_intent_id)
        self.assertEqual("MODIFY", state.last_resumable_intent_type)
        self.assertEqual("lineage-per-link-vault", state.last_resumable_intent_lineage_id)
        self.assertEqual("forced_plaintext_completion", state.last_resumable_completion_reason)


class PromptHintAfterForcedCompletionTests(unittest.TestCase):
    def test_prompt_hint_mentions_same_lineage_reuse_after_forced_completion(self):
        state = _DummyState()
        state.last_resumable_intent_id = "per_link_vault_e2e"
        state.last_resumable_intent_type = "MODIFY"
        state.last_resumable_intent_goal = "Implement end-to-end per-link vault support"
        state.last_resumable_intent_lineage_id = "lineage-per-link-vault"
        state.last_resumable_completion_reason = "forced_plaintext_completion"

        text = _build_resume_hint_text(state)

        self.assertIn("Recently completed resumable intent detected", text)
        self.assertIn("per_link_vault_e2e", text)
        self.assertIn("lineage-per-link-vault", text)
        self.assertIn("forced_plaintext_completion", text)
        self.assertIn('<intent mode="reuse">', text)


class IntentRuntimeReuseAfterClosedContractTests(unittest.TestCase):
    def test_reuse_reopens_recently_closed_same_lineage_contract(self):
        IntentRuntime = _import_intent_runtime()

        state = _DummyState()
        state.active_intent = None
        state.last_resumable_intent_id = "per_link_vault_e2e"
        state.last_resumable_intent_type = "MODIFY"
        state.last_resumable_intent_goal = "Implement end-to-end per-link vault support"
        state.last_resumable_intent_lineage_id = "lineage-per-link-vault"
        state.last_resumable_completion_reason = "forced_plaintext_completion"

        config = SimpleNamespace(
            INTENT_DEFAULT_SAFE_STEPS=8,
            INTENT_DEFAULT_RETRY_LIMIT=2,
        )

        runtime = _construct_intent_runtime(IntentRuntime, state, config)

        payload = {
            "intent_id": "per_link_vault_e2e",
            "intent_type": "MODIFY",
            "goal": "Implement end-to-end per-link vault support",
            "allowed_actions": ["read_chunk", "edit_file", "search_content"],
            "mode": "reuse",
            "requested_steps": 8,
            "switch_reason": "current_intent_exhausted",
            "switch_explanation": "same work direction after forced plaintext completion",
        }

        ok, msg, transition_info, active = _apply_reuse_payload_adaptively(runtime, state, payload)

        self.assertTrue(ok, msg)
        self.assertEqual("intent_reused_with_step_refresh", transition_info.get("transition"))
        self.assertIsNotNone(active)
        self.assertEqual("per_link_vault_e2e", getattr(active, "intent_id", None))
        self.assertEqual("MODIFY", str(getattr(active, "intent_type", "")))


if __name__ == "__main__":
    unittest.main()