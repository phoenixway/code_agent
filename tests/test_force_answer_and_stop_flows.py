import unittest
from types import SimpleNamespace

from modules.agent.orchestration.runtime.recovery import RecoveryCoordinator
from modules.agent.orchestration.runtime.core import Orchestrator
from modules.agent.state_manager import AgentState


class DummyPromptBuilder:
    def build_plain_text_completion_prompt(self, sm, stop_info):
        reason = (stop_info or {}).get("reason", "")
        return f"PLAIN::{reason}"

    def build_intent_overrun_message(self, stop_info):
        return "overrun"

    def build_intent_overrun_confirmation_suffix(self):
        return ""

    def build_keep_current_intent_recovery_prompt(self, stop_info):
        return f"KEEP::{(stop_info or {}).get('reason', '')}"

    def build_keep_original_goal_prompt(self, reason, allowed, goal=""):
        return f"KEEP_GOAL::{reason}::{goal}"

    def build_approved_changed_goal_prompt(self):
        return "APPROVED_CHANGED_GOAL"

    def build_intent_transition_rejected_prompt(self, reason, allowed, goal=""):
        return f"REJECT::{reason}::{goal}"

    def build_reuse_current_intent_prompt(self, reason, allowed, goal=""):
        return f"REUSE::{reason}::{goal}"

    def build_orchestrated_recovery_prompt(self, stop_info):
        return "ORCH_RECOVERY"

    def build_malformed_read_chunk_payload_prompt(self):
        return "MALFORMED_READ_CHUNK"

    def build_repeated_malformed_read_chunk_payload_prompt(self, allowed, goal=""):
        return "REPEATED_MALFORMED_READ_CHUNK"

    def build_malformed_read_file_payload_prompt(self):
        return "MALFORMED_READ_FILE"

    def build_malformed_read_file_skeleton_payload_prompt(self):
        return "MALFORMED_SKELETON"

    def build_suspect_intent_change_message(self, stop_info):
        return "suspect intent change"

    def build_suspect_intent_change_confirmation_suffix(self):
        return "\nconfirm?"


class DummyUI:
    def __init__(self, overrun_choice="stop_and_answer", suspect_choice="stop_and_answer"):
        self.overrun_choice = overrun_choice
        self.suspect_choice = suspect_choice
        self.system_messages = []

    async def choose_intent_overrun_action(self, message):
        return self.overrun_choice

    async def choose_suspect_intent_change_action(self, message):
        return self.suspect_choice

    async def confirm_continue(self, message):
        return False

    async def confirm_loop_recovery(self, message):
        return False

    async def print_system(self, text):
        self.system_messages.append(text)

    async def print_error(self, text):
        self.system_messages.append(text)

    async def stop_loading(self):
        return None

    async def print_message(self, text, role="assistant"):
        self.system_messages.append(f"{role}:{text}")


class FakeRuntime:
    def __init__(self, active_intent=None):
        self.active_intent = active_intent
        self.force_calls = 0
        self.finalize_calls = 0
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def force_current_intent_completion(self):
        self.force_calls += 1
        if self.active_intent is not None:
            self.active_intent.force_plaintext_completion = True
        return True

    def finalize_current_intent_completion(self):
        self.finalize_calls += 1
        had = self.active_intent is not None
        self.active_intent = None
        return had

    def clear_requirement(self):
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def can_continue_current_intent_after_failure(self):
        return False

    def can_soft_continue_after_step_limit(self):
        return False


class DummyAgent:
    def __init__(self, state, ui=None):
        self.state = state
        self.ui = ui or DummyUI()
        self.config = SimpleNamespace(
            INTENT_REQUIRE_ON_DEFECT=True,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        self.allowed_actions_resolver = None
        self.recovery_policy_resolver = None
        self.log = None


class RecoveryForceAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_hard_limit_stop_marks_pending_close_and_forces_completion(self):
        active = SimpleNamespace(
            intent_id="i1",
            intent_type="MODIFY",
            goal="goal",
            allowed_actions=["read_chunk"],
            safe_steps_limit=8,
            retry_limit=2,
            lineage_id="i1",
            force_plaintext_completion=False,
        )
        state = SimpleNamespace(
            active_intent=active,
            intent_runtime=FakeRuntime(active),
            confirmation_count=0,
            state_machine=None,
            pending_finalize_after_terminal_plaintext_completion=False,
            pending_finalize_completion_reason="",
            pending_finalize_completion_source="",
            add_confirmation=lambda n=1: None,
            get_stop_reason_count=lambda reason: 0,
        )

        def mark(reason, source=""):
            state.pending_finalize_after_terminal_plaintext_completion = True
            state.pending_finalize_completion_reason = reason
            state.pending_finalize_completion_source = source

        state.mark_pending_forced_plaintext_completion_close = mark
        agent = DummyAgent(state, DummyUI(overrun_choice="stop_and_answer"))
        rc = RecoveryCoordinator(agent, DummyPromptBuilder())

        decision = await rc.handle_defect_detector_stop(
            {"reason": "intent_step_limit_exceeded", "next_actions": ["read_chunk"]}
        )

        self.assertTrue(decision.continue_loop)
        self.assertIn("user_stopped_after_hard_limit_answer_from_current_evidence", decision.next_query)
        self.assertTrue(state.pending_finalize_after_terminal_plaintext_completion)
        self.assertEqual("forced_plaintext_completion_after_hard_limit", state.pending_finalize_completion_reason)
        self.assertEqual(1, state.intent_runtime.force_calls)

    async def test_suspect_goal_stop_marks_pending_close(self):
        active = SimpleNamespace(
            intent_id="i1",
            intent_type="MODIFY",
            goal="goal",
            allowed_actions=["read_chunk"],
            safe_steps_limit=8,
            retry_limit=2,
            lineage_id="i1",
            force_plaintext_completion=False,
        )
        state = SimpleNamespace(
            active_intent=active,
            intent_runtime=FakeRuntime(active),
            confirmation_count=0,
            state_machine=None,
            pending_finalize_after_terminal_plaintext_completion=False,
            pending_finalize_completion_reason="",
            pending_finalize_completion_source="",
            add_confirmation=lambda n=1: None,
            get_stop_reason_count=lambda reason: 0,
            allow_pending_goal_drift_once=None,
        )

        def mark(reason, source=""):
            state.pending_finalize_after_terminal_plaintext_completion = True
            state.pending_finalize_completion_reason = reason
            state.pending_finalize_completion_source = source

        state.mark_pending_forced_plaintext_completion_close = mark
        agent = DummyAgent(state, DummyUI(suspect_choice="stop_and_answer"))
        rc = RecoveryCoordinator(agent, DummyPromptBuilder())

        decision = await rc.handle_defect_detector_stop(
            {"reason": "suspect_intent_goal_drift", "next_actions": ["read_chunk"]}
        )

        self.assertTrue(decision.continue_loop)
        self.assertIn("user_stopped_after_suspect_goal_change", decision.next_query)
        self.assertTrue(state.pending_finalize_after_terminal_plaintext_completion)
        self.assertEqual("user_stopped_after_suspect_goal_change", state.pending_finalize_completion_reason)

    async def test_inspection_finish_with_text_marks_pending_close(self):
        active = SimpleNamespace(
            intent_id="i2",
            intent_type="INVESTIGATE",
            goal="inspect thing",
            allowed_actions=["read_chunk"],
            safe_steps_limit=8,
            retry_limit=2,
            lineage_id="i2",
            force_plaintext_completion=False,
        )
        state = SimpleNamespace(
            active_intent=active,
            intent_runtime=FakeRuntime(active),
            pending_finalize_after_terminal_plaintext_completion=False,
            pending_finalize_completion_reason="",
            pending_finalize_completion_source="",
            add_confirmation=lambda n=1: None,
            get_stop_reason_count=lambda reason: 0,
        )

        def mark(reason, source=""):
            state.pending_finalize_after_terminal_plaintext_completion = True
            state.pending_finalize_completion_reason = reason
            state.pending_finalize_completion_source = source

        state.mark_pending_forced_plaintext_completion_close = mark
        agent = DummyAgent(state, DummyUI())
        rc = RecoveryCoordinator(agent, DummyPromptBuilder())
        sm = SimpleNamespace(task_kind=SimpleNamespace(value="INSPECTION"))

        decision = await rc.handle_dispatch_stop({"reason": "observe_budget_exhausted"}, sm)

        self.assertTrue(decision.continue_loop)
        self.assertIn("observe_budget_exhausted", decision.next_query)
        self.assertTrue(state.pending_finalize_after_terminal_plaintext_completion)


class AgentStateForcedCompletionTests(unittest.TestCase):
    def test_start_turn_runtime_finalizes_stale_pending_close(self):
        state = AgentState(SimpleNamespace())
        active = SimpleNamespace(
            intent_id="i3",
            intent_type="MODIFY",
            goal="goal",
            allowed_actions=["read_chunk"],
            safe_steps_limit=5,
            retry_limit=2,
            lineage_id="lineage",
            force_plaintext_completion=True,
            hard_limit_hit_count=2,
        )
        runtime = FakeRuntime(active)
        state.intent_runtime = runtime

        state.pending_finalize_after_terminal_plaintext_completion = True
        state.pending_finalize_completion_reason = "forced_plaintext_completion_after_hard_limit"
        state.pending_finalize_completion_source = "recovery"

        state.start_turn_runtime()

        self.assertIsNone(state.active_intent)
        self.assertEqual("i3", getattr(state, "last_resumable_intent_id", ""))
        self.assertEqual(
            "forced_plaintext_completion_after_hard_limit",
            getattr(state, "last_resumable_intent_completion_reason", ""),
        )
        self.assertEqual(1, runtime.finalize_calls)


class CoreForcedCompletionFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_finalizes_after_dispatch_stops_without_terminal_buffer(self):
        orch = Orchestrator.__new__(Orchestrator)
        finalized = {"count": 0}

        state = SimpleNamespace(
            terminal_plaintext_completion_text="",
            terminal_plaintext_completion_pending=False,
            pending_finalize_after_terminal_plaintext_completion=True,
            current_task=None,
            confirmation_count=0,
            session_tokens=0,
        )

        orch.state = state
        orch.history = SimpleNamespace(
            current_token_count=0,
            max_tokens=100,
            check_and_summarize=_async_noop,
        )
        orch.agent = SimpleNamespace(log=None, ui=DummyUI())

        orch._create_loop_context = lambda user_input: SimpleNamespace(
            active_loop=True,
            session_started_at=0.0,
        )

        orch.pipeline = SimpleNamespace(
            run_iteration=_async_return(
                SimpleNamespace(stop_loop=False, continue_loop=False, proceed_to_dispatch=True)
            )
        )

        async def dispatch_run(ctx, iteration):
            ctx.active_loop = False

        orch.dispatch_pipeline = SimpleNamespace(run_iteration=dispatch_run)
        orch._flush_terminal_plaintext_completion_if_present = _async_return(False)

        def fake_finalize():
            finalized["count"] += 1

        orch._finalize_intent_after_terminal_plaintext_completion_if_needed = fake_finalize

        await Orchestrator.process(orch, "continue")
        self.assertEqual(1, finalized["count"])

    async def test_process_finalizes_on_stop_loop_even_without_terminal_text(self):
        orch = Orchestrator.__new__(Orchestrator)
        finalized = {"count": 0}

        state = SimpleNamespace(
            terminal_plaintext_completion_text="",
            terminal_plaintext_completion_pending=False,
            pending_finalize_after_terminal_plaintext_completion=True,
            current_task=None,
            confirmation_count=0,
            session_tokens=0,
        )

        orch.state = state
        orch.history = SimpleNamespace(
            current_token_count=0,
            max_tokens=100,
            check_and_summarize=_async_noop,
        )
        orch.agent = SimpleNamespace(log=None, ui=DummyUI())

        orch._create_loop_context = lambda user_input: SimpleNamespace(
            active_loop=True,
            session_started_at=0.0,
        )

        orch.pipeline = SimpleNamespace(
            run_iteration=_async_return(
                SimpleNamespace(stop_loop=True, continue_loop=False, proceed_to_dispatch=False)
            )
        )
        orch.dispatch_pipeline = SimpleNamespace(run_iteration=_async_noop)
        orch._flush_terminal_plaintext_completion_if_present = _async_return(False)

        def fake_finalize():
            finalized["count"] += 1

        orch._finalize_intent_after_terminal_plaintext_completion_if_needed = fake_finalize

        await Orchestrator.process(orch, "continue")
        self.assertEqual(1, finalized["count"])


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


async def _async_noop(*args, **kwargs):
    return None


if __name__ == "__main__":
    unittest.main()