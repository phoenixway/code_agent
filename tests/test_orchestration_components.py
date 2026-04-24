import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.model_client import ModelTechnicalInterruption, ModelTechnicalInterruptionError
from modules.agent.core import AngelicaAgent
from modules.agent.intent_runtime import IntentContract
from modules.agent.technical_interruptions import TechnicalInterruption
from modules.agent.orchestration.action_policy import ActionPolicyHandler
from modules.agent.orchestration.decision_models import DispatchHandlingDecision, MemoryBoardDecision, ModelStepResult, OrchestrationTraceEntry, ParsedModelOutput, RecoveryDecision
from modules.agent.orchestration.loop_gate import LoopGateHandler
from modules.agent.orchestration.lifecycle import TurnLifecycle
from modules.agent.orchestration.core import LoopContext, Orchestrator
from modules.agent.orchestration.dispatch_pipeline import DispatchPipeline
from modules.agent.orchestration.dispatch_outcome import DispatchOutcomeHandler
from modules.agent.orchestration.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.memory_board_stage import MemoryBoardStageHandler
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.pipeline import OrchestrationPipeline
from modules.agent.orchestration.policy import IntentGuard
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline
from modules.agent.orchestration.recovery import RecoveryCoordinator, StopHandlingDecision
from modules.agent.orchestration.trace_export import OrchestrationTraceExporter
from modules.command_handler import CommandHandler
from modules.memory_board_engine import MemoryBoardEngine
from modules.memory_board_store import MemoryBoardStore
from modules.agent.state_manager import AgentState


class _Segment:
    def __init__(self, seg_type: str, content=None):
        self.type = seg_type
        self.content = content


class IntentGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = IntentGuard()

    def test_allowed_action_under_active_intent_does_not_require_new_intent(self):
        state = SimpleNamespace(
            active_intent=SimpleNamespace(allowed_actions=["read_file"]),
            intent_required_until_activated=False,
            readonly_steps_this_turn=1,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
        )

        required, reason = self.guard.action_requires_intent(
            {"type": "read_file", "path": "a.py"},
            state,
            batch_size=1,
            current_user_input="Open a.py",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_second_read_only_step_without_intent_no_longer_requires_intent_just_for_ordinality(self):
        state = SimpleNamespace(
            active_intent=None,
            intent_required_until_activated=False,
            readonly_steps_this_turn=1,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
        )

        required, reason = self.guard.action_requires_intent(
            {"type": "read_file", "path": "a.py"},
            state,
            batch_size=1,
            current_user_input="Open a.py",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_read_only_batch_without_intent_still_requires_intent(self):
        state = SimpleNamespace(
            active_intent=None,
            intent_required_until_activated=False,
            readonly_steps_this_turn=0,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
        )

        required, reason = self.guard.action_requires_intent(
            {"type": "read_file", "path": "a.py"},
            state,
            batch_size=2,
            current_user_input="Need to inspect a couple of files to understand the structure.",
        )

        self.assertTrue(required)
        self.assertEqual("multi_step_without_intent_contract", reason)


class IntentResponseParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = IntentResponseParser()

    def test_extract_intent_update_and_strip_returns_clean_text_and_payload(self):
        clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent>{"goal":"inspect","allowed_actions":["read_file"]}</intent>\n<action>{"type":"read_file","path":"a.py"}</action>'
        )

        self.assertEqual('<action>{"type":"read_file","path":"a.py"}</action>', clean_text)
        self.assertEqual("inspect", payload["goal"])
        self.assertIsNone(error)

    def test_extract_intent_update_and_strip_supports_intent_tag_attributes(self):
        clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="activate">{"goal":"inspect","allowed_actions":["read_file"]}</intent>\n'
            '<action>{"type":"read_file","path":"a.py"}</action>'
        )

        self.assertEqual('<action>{"type":"read_file","path":"a.py"}</action>', clean_text)
        self.assertEqual("inspect", payload["goal"])
        self.assertIsNone(error)

    def test_extract_intent_update_and_strip_falls_back_to_xml_attributes_for_reuse(self):
        clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse" intent_id="per_link_vault_e2e" requested_steps="5" switch_reason="current_intent_exhausted"></intent>\n'
            '<action>{"type":"read_chunk","path":"a.py","start_line":1,"end_line":20}</action>'
        )

        self.assertEqual('<action>{"type":"read_chunk","path":"a.py","start_line":1,"end_line":20}</action>', clean_text)
        self.assertEqual("reuse", payload["mode"])
        self.assertEqual("per_link_vault_e2e", payload["intent_id"])
        self.assertEqual(5, payload["requested_steps"])
        self.assertEqual("current_intent_exhausted", payload["switch_reason"])
        self.assertIsNone(error)

    def test_extract_intent_update_and_strip_supports_self_closing_xml_attribute_intent(self):
        clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse" intent_id="per_link_vault_e2e" requested_steps="5" switch_reason="current_intent_exhausted" />'
        )

        self.assertEqual("", clean_text)
        self.assertEqual("reuse", payload["mode"])
        self.assertEqual("per_link_vault_e2e", payload["intent_id"])
        self.assertEqual(5, payload["requested_steps"])
        self.assertIsNone(error)

    def test_extract_intent_update_and_strip_parses_allowed_actions_attribute_variants(self):
        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="activate" intent_id="inspect_activity" intent_type="INVESTIGATE" goal="Inspect code path" '
            'allowed_actions="read_file, read_chunk, edit_file"></intent>'
        )
        self.assertEqual(["read_file", "read_chunk", "edit_file"], payload["allowed_actions"])
        self.assertIsNone(error)

        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            "<intent mode='activate' intent_id='inspect_activity' intent_type='INVESTIGATE' goal='Inspect code path' "
            "allowed_actions='[\"read_file\", \"read_chunk\", \"edit_file\"]'></intent>"
        )
        self.assertEqual(["read_file", "read_chunk", "edit_file"], payload["allowed_actions"])
        self.assertIsNone(error)

        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="activate" intent_id="inspect_activity" intent_type="INVESTIGATE" goal="Inspect code path" '
            'allowed_actions="[read_file, read_chunk, edit_file]"></intent>'
        )
        self.assertEqual(["read_file", "read_chunk", "edit_file"], payload["allowed_actions"])
        self.assertIsNone(error)

    def test_extract_intent_update_and_strip_reports_invalid_numeric_attribute_value(self):
        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse" intent_id="per_link_vault_e2e" requested_steps="five" switch_reason="current_intent_exhausted"></intent>'
        )

        self.assertIsNone(payload)
        self.assertEqual("invalid_intent_numeric_field_requested_steps", error)

    def test_extract_intent_update_and_strip_ignores_intent_markup_inside_think_block(self):
        response = (
            "<think>\n"
            'We may need to emit <intent mode="retry">{"goal":"inspect"}</intent> later.\n'
            "</think>\n"
            '<action>{"type":"search_content","pattern":"ActivityRecord","path":"."}</action>'
        )

        clean_text, payload, error = self.parser.extract_intent_update_and_strip(response)

        self.assertEqual(response, clean_text)
        self.assertIsNone(payload)
        self.assertIsNone(error)

    def test_extract_intent_update_and_strip_still_parses_real_intent_after_think_block(self):
        response = (
            "<think>\n"
            'We may need to emit <intent mode="retry">{"goal":"inspect"}</intent> later.\n'
            "</think>\n"
            '<intent mode="activate">{"goal":"inspect","allowed_actions":["read_file"]}</intent>\n'
            '<action>{"type":"read_file","path":"a.py"}</action>'
        )

        clean_text, payload, error = self.parser.extract_intent_update_and_strip(response)

        self.assertEqual(
            "<think>\nWe may need to emit <intent mode=\"retry\">{\"goal\":\"inspect\"}</intent> later.\n</think>\n\n"
            '<action>{"type":"read_file","path":"a.py"}</action>',
            clean_text,
        )
        self.assertEqual("inspect", payload["goal"])
        self.assertIsNone(error)

    def test_needs_action_or_answer_recovery_when_only_thought_present(self):
        needs = self.parser.needs_action_or_answer_recovery(
            "<think>analyzing</think>",
            [_Segment("thought", "analyzing")],
        )

        self.assertTrue(needs)

    def test_tool_history_echo_without_action_detected(self):
        is_echo = self.parser.is_tool_history_echo_without_action(
            'TOOL_HISTORY {"type":"search_content","path":"a.py"}',
            [_Segment("text", 'TOOL_HISTORY {"type":"search_content","path":"a.py"}')],
        )

        self.assertTrue(is_echo)

    def test_intent_only_response_detected(self):
        is_intent_only = self.parser.is_intent_only_response(
            '<intent>{"goal":"inspect"}</intent>',
            [_Segment("intent", {"goal": "inspect"})],
        )

        self.assertTrue(is_intent_only)

    def test_intent_only_response_detected_with_tag_attributes(self):
        is_intent_only = self.parser.is_intent_only_response(
            '<intent mode="activate">{"goal":"inspect"}</intent>',
            [_Segment("intent", {"goal": "inspect"})],
        )

        self.assertTrue(is_intent_only)

    def test_classify_model_output_detects_tool_history_echo(self):
        parsed = self.parser.classify(
            'TOOL_HISTORY {"type":"search_content","path":"a.py"}',
            [_Segment("text", 'TOOL_HISTORY {"type":"search_content","path":"a.py"}')],
        )

        self.assertEqual("tool_history_echo", parsed.invalid_kind)

    def test_classify_model_output_detects_intent_only_deadend(self):
        parsed = self.parser.classify(
            '<intent mode="activate">{"goal":"inspect"}</intent>',
            [_Segment("intent", {"goal": "inspect"})],
        )

        self.assertEqual("intent_only_without_next_step", parsed.invalid_kind)

    def test_classify_model_output_detects_transition_bundle_too_dense(self):
        parsed = self.parser.classify(
            '<intent mode="complete">{"mode":"complete"}</intent>\n'
            '<intent mode="activate">{"goal":"inspect"}</intent>\n'
            '<action>{"type":"read_chunk","path":"a.py","start_line":1,"end_line":10}</action>',
            [
                _Segment("intent", {"mode": "complete"}),
                _Segment("intent", {"goal": "inspect"}),
                _Segment("action", {"type": "read_chunk", "path": "a.py", "start_line": 1, "end_line": 10}),
            ],
        )

        self.assertEqual("transition_bundle_too_dense", parsed.invalid_kind)

    def test_classify_model_output_ignores_plain_think_prefix_before_valid_intent(self):
        parsed = self.parser.classify(
            'think\n! Need to reuse.\n<intent mode="reuse">{"intent_id":"abc","requested_steps":3}</intent>',
            [_Segment("intent", {"intent_id": "abc", "requested_steps": 3})],
        )

        self.assertEqual("", parsed.visible_text)
        self.assertTrue(parsed.has_intent_segment)
        self.assertEqual("intent_only_without_next_step", parsed.invalid_kind)


class TurnLifecycleTests(unittest.TestCase):
    def test_start_turn_initializes_state_machine_and_history(self):
        sm = SimpleNamespace(
            start_turn=MagicMock(),
            intent_runtime=None,
        )
        state = SimpleNamespace(
            state_machine=sm,
            intent_runtime=SimpleNamespace(),
            clear_intent_requirement=MagicMock(),
            start_turn_runtime=MagicMock(),
            current_turn_id=3,
        )
        history = SimpleNamespace(
            add_message=MagicMock(),
            start_turn=MagicMock(),
        )
        agent = SimpleNamespace(
            state=state,
            history=history,
            log=None,
        )

        lifecycle = TurnLifecycle(agent)
        returned_sm = lifecycle.start_turn("inspect this")

        self.assertIs(returned_sm, sm)
        history.add_message.assert_called_once_with("user", "inspect this")
        sm.start_turn.assert_called_once_with("inspect this")
        state.clear_intent_requirement.assert_called_once()
        state.start_turn_runtime.assert_called_once()
        history.start_turn.assert_called_once_with(3)


class RecoveryCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_dispatch_stop_returns_structured_decision_for_malformed_read_file(self):
        ui = SimpleNamespace(
            confirm_continue=AsyncMock(),
            confirm_loop_recovery=AsyncMock(),
            print_system=AsyncMock(),
        )
        state = SimpleNamespace(
            last_error_code=None,
            last_error_message=None,
            set_retry_budgets=MagicMock(),
        )
        config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, state=state, config=config)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )

        coordinator = RecoveryCoordinator(agent, prompt_builder)
        decision = await coordinator.handle_dispatch_stop(
            {"reason": "malformed_read_file_payload", "recoverable": True},
            sm=None,
        )

        self.assertIsInstance(decision, StopHandlingDecision)
        self.assertTrue(decision.handled)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIn("Your last read_file call used invalid payload.", decision.next_query)

    async def test_handle_dispatch_stop_returns_retry_query_for_repeating_failure(self):
        ui = SimpleNamespace(
            confirm_continue=AsyncMock(),
            confirm_loop_recovery=AsyncMock(return_value="retry_recovery"),
            print_system=AsyncMock(),
        )
        state = SimpleNamespace(
            last_error_code=None,
            last_error_message=None,
            set_retry_budgets=MagicMock(),
        )
        config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, state=state, config=config)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )

        coordinator = RecoveryCoordinator(agent, prompt_builder)
        decision = await coordinator.handle_dispatch_stop(
            {"reason": "repeating_failure", "next_actions": ["search_content"]},
            sm=SimpleNamespace(on_user_recovery_choice=MagicMock()),
        )

        self.assertTrue(decision.handled)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIn("Retry with recovery strategy.", decision.next_query)


class DispatchPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_iteration_handles_no_results_stop(self):
        ui = SimpleNamespace(
            print_system=AsyncMock(),
        )
        history = SimpleNamespace(add_message=MagicMock(), current_token_count=0, max_tokens=4096)
        state = SimpleNamespace(orchestration_trace=[], orchestration_trace_sequence=0)
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=history,
            action_dispatcher=SimpleNamespace(),
            log=None,
        )
        dispatch_outcome = SimpleNamespace(
            handle=AsyncMock(
                return_value=DispatchHandlingDecision(
                    handled=True,
                    stop_loop=True,
                    reason="no_system_results",
                    source="dispatch",
                )
            )
        )
        pipeline = DispatchPipeline(agent, dispatch_outcome)
        pipeline._dispatch_segments = AsyncMock(return_value=([], [], False))
        ctx = LoopContext(
            user_input="x",
            tools_prompt="",
            ctx_prompt="",
            state_machine=None,
            current_query="x",
            consecutive_calls=1,
            malformed_action_retries=0,
            audit_marker_retries=0,
            active_loop=True,
            session_started_at=0.0,
        )
        iteration = SimpleNamespace(
            segments=[],
            parsed_action_count=0,
        )

        decision = await pipeline.run_iteration(ctx, iteration)

        self.assertIsInstance(decision, DispatchHandlingDecision)
        self.assertTrue(decision.handled)
        self.assertTrue(decision.stop_loop)
        dispatch_outcome.handle.assert_awaited_once()
        self.assertEqual("post_dispatch_pipeline", state.orchestration_trace[0].stage)


class ActionPolicyHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_intent_for_multi_step_without_active_intent_and_sets_sticky_requirement(self):
        required_reasons = []
        state = SimpleNamespace(
            active_intent=None,
            readonly_steps_this_turn=2,
            intent_required_until_activated=False,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
            require_intent=lambda reason: required_reasons.append(reason),
        )
        agent = SimpleNamespace(
            state=state,
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ActionPolicyHandler(agent, IntentGuard(), prompt_builder)
        ctx = SimpleNamespace(
            user_input="Need to investigate the current implementation in more detail.",
        )
        segments = [_Segment("action", {"type": "read_file", "path": "a.py"})]

        decision = await handler.decide(ctx, segments, intent_payload=None)

        self.assertTrue(decision.handled)
        self.assertEqual("multi_step_without_intent_contract", decision.reason)
        self.assertIn("formal intent contract is required", decision.next_query.lower())
        self.assertEqual(["multi_step_without_intent_contract"], required_reasons)

    async def test_blocks_normal_action_when_active_intent_is_hard_exhausted(self):
        required_reasons = []
        state = SimpleNamespace(
            active_intent=SimpleNamespace(
                intent_id="intent_1",
                goal="Continue same work",
                allowed_actions=["read_chunk", "search_content"],
            ),
            readonly_steps_this_turn=0,
            intent_required_until_activated=False,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
            has_hard_exhausted_active_intent=lambda: True,
            require_intent=lambda reason: required_reasons.append(reason),
        )
        agent = SimpleNamespace(
            state=state,
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ActionPolicyHandler(agent, IntentGuard(), prompt_builder)
        ctx = SimpleNamespace(user_input="Continue same work")
        segments = [_Segment("action", {"type": "read_chunk", "path": "a.py"})]

        decision = await handler.decide(ctx, segments, intent_payload=None)

        self.assertTrue(decision.handled)
        self.assertEqual("exhausted_intent_normal_action_blocked", decision.reason)
        self.assertIn('mode="reuse"', decision.next_query)
        self.assertEqual(["exhausted_intent_requires_reuse_or_completion"], required_reasons)


class ResponsePipelineForcePlaintextGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_force_plaintext_completion_blocks_actions_before_dispatch(self):
        state = SimpleNamespace(
            active_intent=SimpleNamespace(
                intent_id="fix_dialog",
                intent_type="MODIFY",
                goal="Fix dialog behavior",
                force_plaintext_completion=True,
            ),
            orchestration_trace=[],
            orchestration_trace_sequence=0,
            intent_required_until_activated=False,
        )
        agent = SimpleNamespace(
            state=state,
            log=None,
            memory_board_engine=None,
        )
        parser = SimpleNamespace(
            parse=lambda response: [_Segment("action", {"type": "search_content", "path": "a.py"})]
        )
        intent_parser = SimpleNamespace(
            classify=lambda response, segments: ParsedModelOutput(
                response=response,
                segments=segments,
                has_action_segment=True,
            )
        )
        prompt_builder = SimpleNamespace(
            build_plain_text_completion_prompt=lambda sm, stop_info: "SYSTEM: Stop tool use now.\nReturn plain text only."
        )
        intent_transitions = SimpleNamespace(
            handle_model_step=AsyncMock(return_value=RecoveryDecision.pass_through())
        )
        output_recovery = SimpleNamespace(decide=AsyncMock())
        action_policy = SimpleNamespace(decide=AsyncMock())
        memory_board_stage = SimpleNamespace(
            apply=AsyncMock(
                return_value=MemoryBoardDecision.pass_through(
                    response_text='<action>{"type":"search_content","path":"a.py"}</action>'
                )
            )
        )
        response_pipeline = ModelResponsePipeline(
            agent=agent,
            parser=parser,
            intent_response_parser=intent_parser,
            prompt_builder=prompt_builder,
            intent_transitions=intent_transitions,
            output_recovery=output_recovery,
            action_policy=action_policy,
            memory_board_stage=memory_board_stage,
        )
        ctx = SimpleNamespace(
            state_machine=SimpleNamespace(task_kind="MODIFICATION", target_file="a.py"),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
        step = SimpleNamespace(
            response='<action>{"type":"search_content","path":"a.py"}</action>',
            intent_payload=None,
            intent_error=None,
        )

        outcome = await response_pipeline.run_step(ctx, step)

        self.assertTrue(outcome.continue_loop)
        self.assertEqual("intent_force_plaintext_completion", outcome.reason)
        self.assertEqual("force_plaintext_gate", outcome.source)
        self.assertIn("Return plain text only", outcome.next_query)
        output_recovery.decide.assert_not_awaited()
        action_policy.decide.assert_not_awaited()


class LoopGateHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stops_when_session_limit_exceeded(self):
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            stop_loading=AsyncMock(),
            confirm_continue=AsyncMock(),
            start_thinking=AsyncMock(),
        )
        history = SimpleNamespace(
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        state = SimpleNamespace(
            consecutive_same_error_count=0,
            suppress_step_limit_warning=False,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=history,
            config=SimpleNamespace(MAX_SESSION_SECONDS=0, MAX_CONSECUTIVE_CALLS=10, LOOP_ERROR_REPEAT_THRESHOLD=2),
            log=None,
        )
        handler = LoopGateHandler(agent)
        ctx = SimpleNamespace(active_loop=True, consecutive_calls=0, session_started_at=0.0)

        decision = await handler.run(ctx)

        self.assertFalse(decision.proceed)
        self.assertFalse(ctx.active_loop)
        ui.print_error.assert_awaited_once()
        ui.start_thinking.assert_not_awaited()

    async def test_marks_exhausted_active_intent_as_reuse_required_before_model_step(self):
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            stop_loading=AsyncMock(),
            confirm_continue=AsyncMock(),
            start_thinking=AsyncMock(),
        )
        history = SimpleNamespace(
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        required_reasons = []
        cleared = []
        state = SimpleNamespace(
            consecutive_same_error_count=0,
            suppress_step_limit_warning=False,
            has_hard_exhausted_active_intent=lambda: True,
            require_intent=lambda reason: required_reasons.append(reason),
            clear_intent_requirement=lambda: cleared.append(True),
            intent_required_reason="",
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=history,
            config=SimpleNamespace(MAX_SESSION_SECONDS=100, MAX_CONSECUTIVE_CALLS=10, LOOP_ERROR_REPEAT_THRESHOLD=2),
            log=None,
        )
        handler = LoopGateHandler(agent)
        ctx = SimpleNamespace(active_loop=True, consecutive_calls=0, session_started_at=asyncio.get_running_loop().time())

        decision = await handler.run(ctx)

        self.assertTrue(decision.proceed)
        self.assertEqual("exhausted_intent_requires_reuse_or_completion", decision.reason)
        self.assertEqual(["exhausted_intent_requires_reuse_or_completion"], required_reasons)
        self.assertEqual([], cleared)


class MemoryBoardStageHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_consumed_memory_board_response_requests_next_query(self):
        board_engine = SimpleNamespace(
            apply_response_text=MagicMock(
                return_value=SimpleNamespace(
                    parsed_count=1,
                    accepted_count=1,
                    rejected_count=0,
                    clean_text="",
                )
            )
        )
        state = SimpleNamespace(
            last_memory_board_parsed_count=0,
            last_memory_board_accepted_count=0,
            last_memory_board_rejected_count=0,
            memory_tag_expected_next_step=False,
            memory_tag_reason="",
            memory_tag_expected_intent_id="",
        )
        agent = SimpleNamespace(
            state=state,
            memory_board_engine=board_engine,
            log=None,
        )
        prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1"))
        handler = MemoryBoardStageHandler(agent, prompt_builder)
        ctx = SimpleNamespace(user_input="Inspect current implementation")

        decision = await handler.apply(ctx, "<memory>update</memory>")

        self.assertTrue(decision.handled)
        self.assertTrue(decision.continue_loop)
        self.assertIn("Memory updates were recorded", decision.next_query)
        self.assertEqual(1, state.last_memory_board_parsed_count)
        self.assertEqual(1, state.last_memory_board_accepted_count)

    async def test_memory_tags_are_committed_to_store_and_cleaned_from_response(self):
        store = MemoryBoardStore(storage_path=None)
        board_engine = MemoryBoardEngine(store, logger=None)
        state = SimpleNamespace(
            last_memory_board_parsed_count=0,
            last_memory_board_accepted_count=0,
            last_memory_board_rejected_count=0,
            memory_tag_expected_next_step=True,
            memory_tag_reason="meaningful_evidence_gain",
            memory_tag_expected_intent_id="intent_1",
        )
        agent = SimpleNamespace(
            state=state,
            memory_board_engine=board_engine,
            log=None,
        )
        prompt_builder = SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1"))
        handler = MemoryBoardStageHandler(agent, prompt_builder)
        ctx = SimpleNamespace(user_input="Continue investigation")

        decision = await handler.apply(
            ctx,
            (
                '<finding scope="intent">ActivityRepository sorts by created_at.</finding>\n'
                '<progress scope="intent">DAO ordering path identified.</progress>\n'
                'Need one more read to confirm fallback ordering.'
            ),
        )

        self.assertFalse(decision.handled)
        self.assertFalse(decision.continue_loop)
        self.assertEqual("Need one more read to confirm fallback ordering.", decision.response_text)

        prompt = store.to_system_prompt(active_intent_id="intent_1")
        self.assertIn("ActivityRepository sorts by created_at.", prompt)
        self.assertIn("DAO ordering path identified.", prompt)
        self.assertFalse(state.memory_tag_expected_next_step)
        self.assertEqual("", state.memory_tag_reason)
        self.assertEqual("", state.memory_tag_expected_intent_id)

    async def test_memory_tag_xml_attribute_fallback_is_committed_and_cleaned(self):
        store = MemoryBoardStore(storage_path=None)
        board_engine = MemoryBoardEngine(store, logger=None)
        clean_text, tags = board_engine.parse_tags(
            '<progress scope="intent" text="Checked LinkHelpers.kt fallback logic." />\nVisible text.'
        )

        self.assertEqual("Visible text.", clean_text)
        self.assertEqual(1, len(tags))
        self.assertEqual("progress", tags[0].kind)
        self.assertEqual("intent", tags[0].scope)
        self.assertEqual("Checked LinkHelpers.kt fallback logic.", tags[0].text)

    async def test_memory_tag_xml_attribute_fallback_rejects_empty_text_cleanly(self):
        store = MemoryBoardStore(storage_path=None)
        board_engine = MemoryBoardEngine(store, logger=None)

        result = board_engine.apply_response_text(
            '<progress scope="intent" text="" />',
            active_intent_id="intent_1",
            current_user_input="Continue",
            source="model",
        )

        self.assertEqual(1, result.parsed_count)
        self.assertEqual(0, result.accepted_count)
        self.assertEqual(1, result.rejected_count)
        self.assertEqual("empty_text", result.commits[0].reason)


class ModelOutputRecoveryHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_action_or_answer_returns_unified_valid_output_prompt(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(response="<think>only</think>", invalid_kind="missing_action_or_answer"),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertFalse(decision.stop_loop)
        self.assertIn("did not include a valid next step or a final answer", decision.next_query)
        self.assertIn("Return the next valid output now.", decision.next_query)
        self.assertIn("If a tool is needed, return EXACTLY ONE valid <action>...</action> block.", decision.next_query)

    async def test_intent_only_without_next_step_returns_unified_valid_output_prompt(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(
                response='<intent mode="activate">{"goal":"inspect"}</intent>',
                invalid_kind="intent_only_without_next_step",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertFalse(decision.stop_loop)
        self.assertIn("changed or referenced intent state but did not provide a valid next step", decision.next_query)
        self.assertIn("Return the next valid output now.", decision.next_query)
        self.assertIn("If a tool is needed, return EXACTLY ONE valid <action>...</action> block.", decision.next_query)

    async def test_transition_bundle_too_dense_returns_transition_specific_prompt(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(
                response="x",
                invalid_kind="transition_bundle_too_dense",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertIn("bundled too many transition/control items together", decision.next_query)

    async def test_modify_completion_claim_without_state_change_proof_returns_recovery(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
            active_intent=SimpleNamespace(intent_type="MODIFY"),
            state_machine=SimpleNamespace(task_kind="MODIFICATION"),
            current_turn_state_change_count=0,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(
                response="Готово. Я додав автоматичне виправлення.",
                visible_text="Готово. Я додав автоматичне виправлення.",
                has_action_segment=False,
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertFalse(decision.stop_loop)
        self.assertEqual("modify_completion_claim_without_state_change_proof", decision.reason)
        self.assertIn("claimed that code changes were already applied", decision.next_query)
        self.assertIn("If a change still needs to be applied, return EXACTLY ONE valid state-changing <action>...</action> block.", decision.next_query)

    async def test_modify_completion_claim_with_state_change_proof_passes_through(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
            active_intent=SimpleNamespace(intent_type="MODIFY"),
            state_machine=SimpleNamespace(task_kind="MODIFICATION"),
            current_turn_state_change_count=1,
            last_completed_intent_type="",
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(
                response="Готово. Я додав автоматичне виправлення.",
                visible_text="Готово. Я додав автоматичне виправлення.",
                has_action_segment=False,
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_investigate_answer_with_implemented_in_text_is_not_treated_as_modify_completion_claim(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
            active_intent=SimpleNamespace(intent_type="INVESTIGATE"),
            state_machine=SimpleNamespace(task_kind="INSPECTION"),
            current_turn_state_change_count=0,
            last_completed_intent_type="",
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(
                response="Today tab is implemented in modules/ui/today.py. Bottom panel is implemented in modules/ui/bottom_panel.py.",
                visible_text="Today tab is implemented in modules/ui/today.py. Bottom panel is implemented in modules/ui/bottom_panel.py.",
                has_action_segment=False,
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_last_completed_modify_intent_still_enforces_unproven_completion_claim(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
            active_intent=None,
            state_machine=SimpleNamespace(task_kind="INSPECTION"),
            current_turn_state_change_count=0,
            last_completed_intent_type="MODIFY",
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(
                response="Done. I fixed the dialog wiring.",
                visible_text="Done. I fixed the dialog wiring.",
                has_action_segment=False,
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("modify_completion_claim_without_state_change_proof", decision.reason)


class ForcePlaintextCompletionStateTests(unittest.TestCase):
    def test_start_turn_clears_force_plaintext_completion_on_active_intent(self):
        from modules.agent.state_manager import AgentState

        state = AgentState()
        state.intent_runtime = SimpleNamespace(
            active_intent=SimpleNamespace(force_plaintext_completion=True)
        )

        state.start_turn_runtime()

        self.assertFalse(state.intent_runtime.active_intent.force_plaintext_completion)

    def test_start_turn_clears_hard_limit_hit_count_on_active_intent(self):
        from modules.agent.state_manager import AgentState

        state = AgentState()
        state.intent_runtime = SimpleNamespace(
            active_intent=SimpleNamespace(
                force_plaintext_completion=False,
                hard_limit_hit_count=3,
            )
        )

        state.start_turn_runtime()

        self.assertEqual(0, state.intent_runtime.active_intent.hard_limit_hit_count)


class OrchestrationPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_iteration_returns_dispatch_ready_decision(self):
        loop_gate = SimpleNamespace(
            run=AsyncMock(return_value=SimpleNamespace(proceed=True, reason="step_ready", source="loop_gate"))
        )
        response_pipeline = SimpleNamespace(
            run_step=AsyncMock(
                return_value=SimpleNamespace(
                    continue_loop=False,
                    next_query=None,
                    segments=[_Segment("action", {"type": "read_file", "path": "a.py"})],
                    parsed_output=None,
                    parsed_action_count=1,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                )
            )
        )
        state = SimpleNamespace(current_task=None, orchestration_trace=[], orchestration_trace_sequence=0)
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            history=SimpleNamespace(),
            model_client=SimpleNamespace(),
            config=SimpleNamespace(),
            log=None,
        )
        pipeline = OrchestrationPipeline(
            agent,
            prompt_builder=SimpleNamespace(),
            intent_response_parser=SimpleNamespace(),
            loop_gate=loop_gate,
            response_pipeline=response_pipeline,
        )
        pipeline._run_model_step = AsyncMock(
            return_value=ModelStepResult(
                response="<action>{}</action>",
                intent_payload=None,
                intent_error=None,
            )
        )
        ctx = SimpleNamespace(
            current_query="inspect implementation",
            malformed_action_retries=0,
            audit_marker_retries=0,
            consecutive_calls=1,
        )

        decision = await pipeline.run_iteration(ctx)

        self.assertTrue(decision.proceed_to_dispatch)
        self.assertFalse(decision.continue_loop)
        self.assertEqual(1, decision.parsed_action_count)
        response_pipeline.run_step.assert_awaited_once()
        self.assertEqual("pre_dispatch_pipeline", state.orchestration_trace[0].stage)
        self.assertEqual("dispatch_ready", state.orchestration_trace[-1].decision)


class DispatchOutcomeHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_system_results_into_next_query_when_loop_continues(self):
        history = SimpleNamespace(add_message=MagicMock())
        state = SimpleNamespace(
            pending_loop_stop_info=None,
            last_memory_board_parsed_count=0,
            memory_tag_expected_next_step=False,
            memory_tag_reason="",
            memory_tag_expected_intent_id="",
            active_intent=SimpleNamespace(intent_id="intent_1"),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(print_system=AsyncMock(), confirm_loop_recovery=AsyncMock()),
            state=state,
            history=history,
            log=None,
        )
        parser = SimpleNamespace(reconstruct=MagicMock(return_value="assistant tool rendering"))
        recovery = SimpleNamespace(handle_dispatch_stop=AsyncMock())
        handler = DispatchOutcomeHandler(agent, parser, recovery)
        ctx = SimpleNamespace(active_loop=True, current_query="", state_machine=None)

        decision = await handler.handle(
            ctx,
            processed_segs=[_Segment("action", {"type": "search_content"})],
            sys_results=["SYSTEM RESULT 1", "SYSTEM RESULT 2"],
            should_stop=False,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("SYSTEM RESULT 1\n---\nSYSTEM RESULT 2", ctx.current_query)
        history.add_message.assert_any_call("assistant", "assistant tool rendering")
        history.add_message.assert_any_call("system", "SYSTEM RESULT 1")
        history.add_message.assert_any_call("system", "SYSTEM RESULT 2")
        self.assertTrue(state.memory_tag_expected_next_step)
        self.assertEqual("meaningful_evidence_gain", state.memory_tag_reason)
        self.assertEqual("intent_1", state.memory_tag_expected_intent_id)

    async def test_does_not_request_memory_followup_when_previous_response_already_had_memory_tag(self):
        history = SimpleNamespace(add_message=MagicMock())
        state = SimpleNamespace(
            pending_loop_stop_info=None,
            last_memory_board_parsed_count=1,
            memory_tag_expected_next_step=False,
            memory_tag_reason="",
            memory_tag_expected_intent_id="",
            active_intent=SimpleNamespace(intent_id="intent_1"),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(print_system=AsyncMock(), confirm_loop_recovery=AsyncMock()),
            state=state,
            history=history,
            log=None,
        )
        parser = SimpleNamespace(reconstruct=MagicMock(return_value="assistant tool rendering"))
        recovery = SimpleNamespace(handle_dispatch_stop=AsyncMock())
        handler = DispatchOutcomeHandler(agent, parser, recovery)
        ctx = SimpleNamespace(active_loop=True, current_query="", state_machine=None)

        await handler.handle(
            ctx,
            processed_segs=[_Segment("action", {"type": "search_content"})],
            sys_results=["SYSTEM RESULT 1"],
            should_stop=False,
        )

        self.assertFalse(state.memory_tag_expected_next_step)

    async def test_suppresses_technical_text_from_assistant_history(self):
        history = SimpleNamespace(add_message=MagicMock())
        state = AgentState(SimpleNamespace(INTENT_COMPLETION_ALLOWANCE=1))
        state.pending_loop_stop_info = None
        state.last_memory_board_parsed_count = 0
        state.memory_tag_expected_next_step = False
        state.memory_tag_reason = ""
        state.memory_tag_expected_intent_id = ""
        state.terminal_plaintext_completion_pending = False
        state.terminal_plaintext_completion_text = ""
        agent = SimpleNamespace(
            ui=SimpleNamespace(
                print_system=AsyncMock(),
                confirm_loop_recovery=AsyncMock(),
                print_error=AsyncMock(),
                print_message=AsyncMock(),
                print_technical_interruption=AsyncMock(),
            ),
            state=state,
            history=history,
            log=None,
        )
        parser = SimpleNamespace(reconstruct=MagicMock(return_value="Error: Gemini API Error 503"))
        recovery = SimpleNamespace(handle_dispatch_stop=AsyncMock())
        handler = DispatchOutcomeHandler(agent, parser, recovery)
        ctx = SimpleNamespace(active_loop=True, current_query="", state_machine=None)

        decision = await handler.handle(
            ctx,
            processed_segs=[],
            sys_results=[],
            should_stop=False,
        )

        self.assertEqual("technical_text_suppressed_from_chat_history", decision.reason)
        history.add_message.assert_not_called()
        agent.ui.print_technical_interruption.assert_awaited_once()
        self.assertEqual("gemini", getattr(state.last_technical_interruption, "provider", None))

    async def test_text_only_reply_closes_exhausted_active_intent_as_resumable(self):
        history = SimpleNamespace(add_message=MagicMock())
        config = SimpleNamespace(INTENT_COMPLETION_ALLOWANCE=1)
        state = AgentState(config)
        state.intent_runtime.active_intent = IntentContract(
            intent_id="intent_1",
            intent_type="MODIFY",
            goal="Finish fix",
            allowed_actions=["read_chunk", "edit_file"],
            safe_steps_limit=2,
            retry_limit=2,
            step_count=3,
            lineage_id="lineage_1",
        )
        state.pending_loop_stop_info = {"reason": "intent_step_limit_exceeded"}
        agent = SimpleNamespace(
            ui=SimpleNamespace(
                print_system=AsyncMock(),
                confirm_loop_recovery=AsyncMock(),
                print_error=AsyncMock(),
                print_message=AsyncMock(),
            ),
            state=state,
            history=history,
            log=None,
        )
        parser = SimpleNamespace(reconstruct=MagicMock(return_value="Final answer from current evidence."))
        recovery = SimpleNamespace(handle_dispatch_stop=AsyncMock())
        handler = DispatchOutcomeHandler(agent, parser, recovery)
        ctx = SimpleNamespace(active_loop=True, current_query="", state_machine=None)

        decision = await handler.handle(
            ctx,
            processed_segs=[],
            sys_results=[],
            should_stop=False,
        )

        self.assertEqual("text_only_response_forwarded", decision.reason)
        self.assertIsNone(state.active_intent)
        self.assertEqual("intent_1", state.last_resumable_intent_id)
        self.assertEqual("intent_step_limit_exceeded", state.last_resumable_intent_completion_reason)
        history.add_message.assert_called_once_with("assistant", "Final answer from current evidence.")


class OrchestrationPipelineTechnicalInterruptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_provider_interruption_stops_without_dispatch(self):
        loop_gate = SimpleNamespace(
            run=AsyncMock(return_value=SimpleNamespace(proceed=True, reason="step_ready", source="loop_gate"))
        )
        response_pipeline = SimpleNamespace(run_step=AsyncMock())
        state = SimpleNamespace(
            current_task=None,
            orchestration_trace=[],
            orchestration_trace_sequence=0,
            note_technical_interruption=MagicMock(),
            clear_technical_interruption=MagicMock(),
        )
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            print_technical_interruption=AsyncMock(),
        )

        class FailingModel:
            async def get_streaming_response(self, *args, **kwargs):
                raise ModelTechnicalInterruptionError(
                    ModelTechnicalInterruption(
                        provider="gemini",
                        message="Gemini API temporarily unavailable",
                        status_code=503,
                        recoverable=True,
                        retryable=True,
                    )
                )

        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=SimpleNamespace(),
            model_client=FailingModel(),
            config=SimpleNamespace(MAX_STEP_SECONDS=30),
            log=None,
        )
        prompt_builder = SimpleNamespace(
            build_system_message=MagicMock(return_value="SYSTEM"),
            build_memory_board_context_message=MagicMock(return_value=None),
            _intent_universe=MagicMock(return_value=SimpleNamespace(
                kind="intentless_short_mode",
                has_active_contract=False,
                intent_required_now=False,
                active_intent_type="",
                intentless_steps_used=0,
            )),
        )
        pipeline = OrchestrationPipeline(
            agent,
            prompt_builder=prompt_builder,
            intent_response_parser=SimpleNamespace(),
            loop_gate=loop_gate,
            response_pipeline=response_pipeline,
        )
        ctx = SimpleNamespace(
            current_query="continue work",
            malformed_action_retries=0,
            audit_marker_retries=0,
            consecutive_calls=1,
            active_loop=True,
            tools_prompt="TOOLS",
            ctx_prompt="CTX",
        )

        decision = await pipeline.run_iteration(ctx)

        self.assertTrue(decision.stop_loop)
        self.assertEqual("model_step_unavailable", decision.reason)
        ui.print_technical_interruption.assert_awaited_once()
        state.note_technical_interruption.assert_called_once()
        response_pipeline.run_step.assert_not_called()

    async def test_model_provider_interruption_closes_active_intent_as_resumable(self):
        loop_gate = SimpleNamespace(
            run=AsyncMock(return_value=SimpleNamespace(proceed=True, reason="step_ready", source="loop_gate"))
        )
        response_pipeline = SimpleNamespace(run_step=AsyncMock())
        config = SimpleNamespace(MAX_STEP_SECONDS=30, INTENT_COMPLETION_ALLOWANCE=1)
        state = AgentState(config)
        state.intent_runtime.active_intent = IntentContract(
            intent_id="intent_resume",
            intent_type="MODIFY",
            goal="Continue work",
            allowed_actions=["read_chunk", "edit_file"],
            safe_steps_limit=3,
            retry_limit=2,
            lineage_id="lineage_resume",
        )
        state.clear_technical_interruption = MagicMock()
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            print_technical_interruption=AsyncMock(),
        )

        class FailingModel:
            async def get_streaming_response(self, *args, **kwargs):
                raise ModelTechnicalInterruptionError(
                    ModelTechnicalInterruption(
                        provider="gemini",
                        message="Gemini API temporarily unavailable",
                        status_code=503,
                        recoverable=True,
                        retryable=True,
                    )
                )

        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=SimpleNamespace(),
            model_client=FailingModel(),
            config=config,
            log=None,
        )
        prompt_builder = SimpleNamespace(
            build_system_message=MagicMock(return_value="SYSTEM"),
            build_memory_board_context_message=MagicMock(return_value=None),
            _intent_universe=MagicMock(return_value=SimpleNamespace(
                kind="active_contract",
                has_active_contract=True,
                intent_required_now=False,
                active_intent_type="MODIFY",
                intentless_steps_used=0,
            )),
        )
        pipeline = OrchestrationPipeline(
            agent,
            prompt_builder=prompt_builder,
            intent_response_parser=SimpleNamespace(),
            loop_gate=loop_gate,
            response_pipeline=response_pipeline,
        )
        ctx = SimpleNamespace(
            current_query="continue work",
            malformed_action_retries=0,
            audit_marker_retries=0,
            consecutive_calls=1,
            active_loop=True,
            tools_prompt="TOOLS",
            ctx_prompt="CTX",
        )

        decision = await pipeline.run_iteration(ctx)

        self.assertTrue(decision.stop_loop)
        self.assertIsNone(state.active_intent)
        self.assertEqual("intent_resume", state.last_resumable_intent_id)
        self.assertEqual("technical_interruption", state.last_resumable_intent_completion_reason)
        self.assertTrue(getattr(state.last_technical_interruption, "resumable", False))
        response_pipeline.run_step.assert_not_called()


class TechnicalInterruptionResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_interrupted_work_uses_control_path_without_user_history(self):
        agent = AngelicaAgent.__new__(AngelicaAgent)
        agent._ui = SimpleNamespace(print_system=AsyncMock())
        agent.state = SimpleNamespace(
            last_technical_interruption=TechnicalInterruption(
                kind="provider_error",
                provider="gemini",
                status_code=503,
                message="Gemini API temporarily unavailable",
                resumable=True,
                resumable_intent_id="intent_resume",
            ),
            last_resumable_intent_id="intent_resume",
            last_resumable_intent_completion_reason="technical_interruption",
            last_resumable_completion_reason="technical_interruption",
            pending_resume_query="Continue implementing the fix",
        )
        agent.orchestrator = SimpleNamespace(
            ui=None,
            process=AsyncMock(return_value=None),
        )

        resumed = await AngelicaAgent.resume_interrupted_work(agent)

        self.assertTrue(resumed)
        agent.orchestrator.process.assert_awaited_once()
        args, kwargs = agent.orchestrator.process.await_args
        self.assertIn("Resume the interrupted work from the last safe state", args[0])
        self.assertIn('mode="reuse"', args[0])
        self.assertFalse(kwargs["add_user_history"])

    async def test_resume_interrupted_work_reports_missing_resume_state(self):
        agent = AngelicaAgent.__new__(AngelicaAgent)
        agent._ui = SimpleNamespace(print_system=AsyncMock())
        agent.state = SimpleNamespace(
            last_technical_interruption=None,
            last_resumable_intent_id="",
            last_resumable_intent_completion_reason="",
            last_resumable_completion_reason="",
            pending_resume_query="",
        )
        agent.orchestrator = SimpleNamespace(
            ui=None,
            process=AsyncMock(return_value=None),
        )

        resumed = await AngelicaAgent.resume_interrupted_work(agent)

        self.assertFalse(resumed)
        agent.orchestrator.process.assert_not_awaited()
        agent._ui.print_system.assert_awaited_once()


class ModelOutputRecoveryHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_history_echo_returns_recovery_prompt(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(response="TOOL_HISTORY {}", invalid_kind="tool_history_echo"),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertFalse(decision.stop_loop)
        self.assertIn("echoed a historical tool marker instead of a valid next step", decision.next_query)
        self.assertIn("Do not output TOOL_HISTORY, history_tool, or other historical markers again.", decision.next_query)

    async def test_repeated_malformed_action_stops_loop(self):
        ui = SimpleNamespace(print_error=AsyncMock())
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint="x",
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        handler = ModelOutputRecoveryHandler(agent, prompt_builder)

        decision = await handler.decide(
            ParsedModelOutput(response="<action", invalid_kind="malformed_action"),
            malformed_action_retries=1,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertTrue(decision.stop_loop)
        ui.print_error.assert_awaited_once()


class IntentTransitionHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_intent_error_while_intent_required_returns_intent_required_prompt(self):
        state = SimpleNamespace(
            intent_required_until_activated=True,
            active_intent=None,
            require_intent=MagicMock(),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload=None,
            intent_error="invalid_intent_json",
            response_text="",
            state_machine=None,
        )

        self.assertTrue(decision.handled)
        self.assertIn("syntactically invalid", decision.next_query)
        state.require_intent.assert_called_once_with("invalid_intent_json")

    async def test_invalid_intent_with_resumable_state_requests_corrected_reuse(self):
        state = SimpleNamespace(
            intent_required_until_activated=True,
            active_intent=None,
            last_resumable_intent_id="per_link_vault_e2e",
            last_resumable_intent_type="MODIFY",
            last_resumable_intent_goal="Continue the same task",
            last_technical_interruption=None,
            require_intent=MagicMock(),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(INTENT_REUSE_EXTENSION_STEPS=4),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=agent.config,
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload=None,
            intent_error="invalid_intent_json",
            response_text="",
            state_machine=None,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("invalid_intent_resumable_available", decision.reason)
        self.assertIn("Resumable intent_id: per_link_vault_e2e", decision.next_query)
        self.assertIn('<intent mode="reuse">', decision.next_query)
        self.assertIn("Do not emit an <action> before reuse is accepted.", decision.next_query)
        state.require_intent.assert_called_once_with("invalid_intent_resumable_available")

    async def test_accepted_intent_without_followup_requests_next_step_under_same_contract(self):
        active_intent = SimpleNamespace(
            intent_id="inspect_activity_tracker",
            intent_type="INVESTIGATE",
            goal="Inspect activity tracker implementation",
            allowed_actions=["read_chunk", "search_content"],
        )
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=active_intent,
            intent_runtime=SimpleNamespace(last_apply_warning="", last_transition_info={}),
            apply_intent_contract=MagicMock(return_value=(True, "intent_activated")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="inspect_activity_tracker"),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)
        state_machine = SimpleNamespace(intent_runtime=None)

        decision = await handler.handle_model_step(
            intent_payload={"goal": "Inspect activity tracker implementation"},
            intent_error=None,
            response_text="",
            state_machine=state_machine,
        )

        self.assertTrue(decision.handled)
        self.assertIn("Intent accepted. The current contract is now active.", decision.next_query)
        self.assertIn("Current contract goal remains the same", decision.next_query)
        state.note_intent_only_response.assert_called_once()
        self.assertIs(state_machine.intent_runtime, state.intent_runtime)

    async def test_transition_bundle_after_applied_intent_requests_clean_next_output(self):
        active_intent = SimpleNamespace(
            intent_id="inspect_activity_tracker",
            intent_type="MODIFY",
            goal="Implement the planned change",
            allowed_actions=["edit_file", "read_chunk"],
        )
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=active_intent,
            intent_runtime=SimpleNamespace(
                last_apply_warning="",
                last_transition_info={
                    "transition": "intent_activated",
                    "before_active_intent_id": "",
                    "after_active_intent_id": "inspect_activity_tracker",
                },
            ),
            apply_intent_contract=MagicMock(return_value=(True, "intent_activated")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="inspect_activity_tracker"),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload={"goal": "Implement the planned change"},
            intent_error=None,
            response_text='<intent mode="complete">{"mode":"complete"}</intent>\n<action>{"type":"edit_file"}</action>',
            state_machine=None,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("transition_bundle_too_dense", decision.reason)
        self.assertIn("Return only the next valid output now", decision.next_query)

    async def test_completed_intent_with_plaintext_answer_is_allowed_to_continue_as_final_answer(self):
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=SimpleNamespace(
                intent_id="activity_tracker_edit_sort",
                intent_type="INVESTIGATE",
                goal="Understand current implementation",
                allowed_actions=["read_chunk", "search_content"],
            ),
            intent_runtime=SimpleNamespace(
                last_apply_warning="",
                last_transition_info={
                    "transition": "intent_completed",
                    "before_active_intent_id": "activity_tracker_edit_sort",
                    "after_active_intent_id": "",
                },
            ),
            apply_intent_contract=MagicMock(return_value=(True, "intent_completed")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="activity_tracker_edit_sort"),
            pending_loop_stop_info=None,
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload={"intent_id": "activity_tracker_edit_sort", "mode": "complete"},
            intent_error=None,
            response_text="Final answer from current evidence.",
            state_machine=None,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("", getattr(state, "pending_loop_stop_info", None) or "")

    async def test_completed_intent_with_followup_action_is_still_transition_bundle_too_dense(self):
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=SimpleNamespace(
                intent_id="activity_tracker_edit_sort",
                intent_type="INVESTIGATE",
                goal="Understand current implementation",
                allowed_actions=["read_chunk", "search_content"],
            ),
            intent_runtime=SimpleNamespace(
                last_apply_warning="",
                last_transition_info={
                    "transition": "intent_completed",
                    "before_active_intent_id": "activity_tracker_edit_sort",
                    "after_active_intent_id": "",
                },
            ),
            apply_intent_contract=MagicMock(return_value=(True, "intent_completed")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="activity_tracker_edit_sort"),
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload={"intent_id": "activity_tracker_edit_sort", "mode": "complete"},
            intent_error=None,
            response_text='<action>{"type":"read_chunk","path":"a.py","start_line":1,"end_line":10}</action>',
            state_machine=None,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("transition_bundle_too_dense", decision.reason)

    async def test_accepted_intent_with_followup_action_is_allowed_to_pass_through(self):
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=SimpleNamespace(
                intent_id="activity_tracker_edit_sort",
                intent_type="INVESTIGATE",
                goal="Understand current implementation",
                allowed_actions=["read_chunk", "search_content"],
            ),
            intent_runtime=SimpleNamespace(
                last_apply_warning="",
                last_transition_info={
                    "transition": "intent_activated",
                    "before_active_intent_id": "",
                    "after_active_intent_id": "activity_tracker_edit_sort",
                },
            ),
            apply_intent_contract=MagicMock(return_value=(True, "intent_activated")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="activity_tracker_edit_sort"),
            pending_loop_stop_info=None,
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload={"intent_id": "activity_tracker_edit_sort", "mode": "activate"},
            intent_error=None,
            response_text='<action>{"type":"read_chunk","path":"a.py","start_line":1,"end_line":10}</action>',
            state_machine=None,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("", getattr(state, "pending_loop_stop_info", None) or "")

    async def test_redundant_same_lineage_intent_with_followup_action_is_ignored_under_active_contract(self):
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=SimpleNamespace(
                intent_id="datetimepicker_fix",
                intent_type="MODIFY",
                goal="Add allowPastValues to DateTimePickerDialog",
                allowed_actions=["read_file", "read_chunk", "edit_file"],
            ),
            intent_runtime=SimpleNamespace(
                last_apply_warning="",
                last_transition_info={
                    "transition": "policy_rejected",
                    "reason": "unnecessary_intent_reactivation_or_replace",
                    "before_active_intent_id": "datetimepicker_fix",
                    "after_active_intent_id": "datetimepicker_fix",
                },
            ),
            apply_intent_contract=MagicMock(return_value=(False, "unnecessary_intent_reactivation_or_replace")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="datetimepicker_fix"),
            last_defect_info={
                "reason": "unnecessary_intent_reactivation_or_replace",
                "recoverable": True,
                "message_key": "unnecessary_intent_reactivation_or_replace",
                "next_actions": ["read_file", "read_chunk", "edit_file"],
            },
            pending_loop_stop_info=None,
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload={"intent_id": "datetimepicker_fix", "mode": "replace"},
            intent_error=None,
            response_text='<action>{"type":"read_file","path":"a.kt"}</action>',
            state_machine=None,
        )

        self.assertFalse(decision.handled)
        recovery.handle_defect_detector_stop.assert_not_awaited()
        self.assertEqual("", getattr(state, "pending_loop_stop_info", None) or "")

    async def test_completed_intent_with_intent_mention_inside_think_is_not_transition_bundle_too_dense(self):
        state = SimpleNamespace(
            intent_required_until_activated=False,
            active_intent=SimpleNamespace(
                intent_id="activity_tracker_edit_sort",
                intent_type="INVESTIGATE",
                goal="Understand current implementation",
                allowed_actions=["read_chunk", "search_content"],
            ),
            intent_runtime=SimpleNamespace(
                last_apply_warning="",
                last_transition_info={
                    "transition": "intent_completed",
                    "before_active_intent_id": "activity_tracker_edit_sort",
                    "after_active_intent_id": "",
                },
            ),
            apply_intent_contract=MagicMock(return_value=(True, "intent_completed")),
            note_intent_only_response=MagicMock(),
            active_intent_summary=MagicMock(return_value="activity_tracker_edit_sort"),
            pending_loop_stop_info=None,
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            config=SimpleNamespace(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )
        recovery = SimpleNamespace(handle_defect_detector_stop=AsyncMock())
        handler = IntentTransitionHandler(agent, prompt_builder, recovery)

        decision = await handler.handle_model_step(
            intent_payload={"intent_id": "activity_tracker_edit_sort", "mode": "complete"},
            intent_error=None,
            response_text=(
                "<think>\n"
                'We can now emit <intent mode="complete"> and then answer.\n'
                "</think>\n"
                "Final answer from current evidence."
            ),
            state_machine=None,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("", getattr(state, "pending_loop_stop_info", None) or "")

    async def test_suspect_intent_relabel_repeat_forces_keep_current_contract(self):
        ui = SimpleNamespace(
            confirm_continue=AsyncMock(),
            confirm_loop_recovery=AsyncMock(),
            print_system=AsyncMock(),
            choose_suspect_intent_change_action=AsyncMock(return_value="allow_changed_goal"),
        )
        state = SimpleNamespace(
            active_intent=SimpleNamespace(
                goal="Check other DAO files for ORDER BY createdAt clauses that might affect Activity Tracker sorting",
                allowed_actions=["search_content", "search_files", "read_chunk"],
            ),
            add_confirmation=MagicMock(),
        )
        config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, state=state, config=config)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )

        coordinator = RecoveryCoordinator(agent, prompt_builder)
        decision = await coordinator.handle_defect_detector_stop(
            {
                "reason": "suspect_intent_relabel_repeat",
                "recoverable": True,
                "next_actions": ["search_content", "search_files", "read_chunk"],
            }
        )

        self.assertIsInstance(decision, RecoveryDecision)
        self.assertTrue(decision.handled)
        self.assertIn("Keep the original goal.", decision.next_query)
        self.assertIn("Do NOT rewrite or narrow the current contract goal.", decision.next_query)
        self.assertIn("Allowed actions under the CURRENT intent contract: search_content, search_files, read_chunk.", decision.next_query)
        ui.choose_suspect_intent_change_action.assert_not_awaited()
        state.add_confirmation.assert_not_called()

    async def test_unnecessary_intent_reactivation_forces_continue_under_same_contract(self):
        ui = SimpleNamespace(
            confirm_continue=AsyncMock(),
            confirm_loop_recovery=AsyncMock(),
            print_system=AsyncMock(),
            choose_suspect_intent_change_action=AsyncMock(),
        )
        state = SimpleNamespace(
            active_intent=SimpleNamespace(
                goal="Check other DAO files for ORDER BY createdAt clauses that might affect Activity Tracker sorting",
                allowed_actions=["search_content", "search_files", "read_chunk"],
            ),
            add_confirmation=MagicMock(),
        )
        config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, state=state, config=config)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )

        coordinator = RecoveryCoordinator(agent, prompt_builder)
        decision = await coordinator.handle_defect_detector_stop(
            {
                "reason": "unnecessary_intent_reactivation_or_replace",
                "recoverable": True,
                "next_actions": ["search_content", "search_files", "read_chunk"],
                "message_key": "unnecessary_intent_reactivation_or_replace",
            }
        )

        self.assertIsInstance(decision, RecoveryDecision)
        self.assertTrue(decision.handled)
        self.assertIn("active intent contract is already shown in the system prompt", decision.next_query)
        self.assertIn("will remain active until runtime explicitly completes, replaces, rejects, or closes it", decision.next_query)
        self.assertIn("Do not emit another <intent mode=\"activate\"> or <intent mode=\"replace\">", decision.next_query)
        self.assertIn("Allowed actions under the CURRENT intent contract: search_content, search_files, read_chunk.", decision.next_query)
        ui.choose_suspect_intent_change_action.assert_not_awaited()
        state.add_confirmation.assert_not_called()


class OrchestratorIntentContinuationTests(unittest.IsolatedAsyncioTestCase):
    async def test_intent_only_response_continues_in_same_turn(self):
        state = SimpleNamespace(
            apply_intent_contract=MagicMock(return_value=(True, "intent_activated")),
            intent_runtime=SimpleNamespace(last_apply_warning=""),
            pending_loop_stop_info=None,
            active_intent_summary=lambda: "intent_id=inspect_activity,type=INVESTIGATE",
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            history=SimpleNamespace(),
            model_client=SimpleNamespace(),
            action_dispatcher=SimpleNamespace(),
            parser=SimpleNamespace(),
            config=SimpleNamespace(),
            memory_board_store=None,
            memory_board_engine=None,
            log=None,
        )
        orchestrator = Orchestrator(agent)
        ctx = LoopContext(
            user_input="inspect current implementation",
            tools_prompt="",
            ctx_prompt="",
            state_machine=None,
            current_query="inspect current implementation",
            consecutive_calls=1,
            malformed_action_retries=0,
            audit_marker_retries=0,
            active_loop=True,
            session_started_at=0.0,
        )
        step = ModelStepResult(
            response="",
            intent_payload={
                "intent_id": "inspect_activity",
                "intent_type": "INVESTIGATE",
                "goal": "Inspect current implementation",
                "allowed_actions": ["read_chunk"],
                "safe_steps_limit": 4,
                "retry_limit": 2,
                "mode": "activate",
            },
            intent_error=None,
        )

        outcome = await orchestrator.response_pipeline.run_step(ctx, step)

        self.assertTrue(outcome.continue_loop)
        self.assertTrue(ctx.active_loop)
        self.assertIn("Intent accepted", outcome.next_query)
        self.assertIn("return the next valid output", outcome.next_query.lower())

    async def test_response_pipeline_records_structured_trace_entries(self):
        state = SimpleNamespace(
            apply_intent_contract=MagicMock(return_value=(True, "intent_activated")),
            intent_runtime=SimpleNamespace(last_apply_warning="", last_transition_info={}),
            pending_loop_stop_info=None,
            active_intent_summary=lambda: "intent_id=inspect_activity,type=INVESTIGATE",
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(),
            state=state,
            history=SimpleNamespace(),
            model_client=SimpleNamespace(),
            action_dispatcher=SimpleNamespace(),
            parser=SimpleNamespace(),
            config=SimpleNamespace(),
            memory_board_store=None,
            memory_board_engine=None,
            log=None,
        )
        orchestrator = Orchestrator(agent)
        ctx = LoopContext(
            user_input="inspect current implementation",
            tools_prompt="",
            ctx_prompt="",
            state_machine=None,
            current_query="inspect current implementation",
            consecutive_calls=1,
            malformed_action_retries=0,
            audit_marker_retries=0,
            active_loop=True,
            session_started_at=0.0,
        )
        step = ModelStepResult(
            response="",
            intent_payload={
                "intent_id": "inspect_activity",
                "intent_type": "INVESTIGATE",
                "goal": "Inspect current implementation",
                "allowed_actions": ["read_chunk"],
                "safe_steps_limit": 4,
                "retry_limit": 2,
                "mode": "activate",
            },
            intent_error=None,
        )

        await orchestrator.response_pipeline.run_step(ctx, step)

        self.assertGreaterEqual(len(state.orchestration_trace), 2)
        self.assertTrue(all(isinstance(entry, OrchestrationTraceEntry) for entry in state.orchestration_trace))
        self.assertEqual([1, 2], [entry.sequence for entry in state.orchestration_trace[:2]])


class OrchestrationTraceExporterTests(unittest.TestCase):
    def test_render_text_outputs_trace_entries(self):
        state = SimpleNamespace(
            orchestration_trace=[
                OrchestrationTraceEntry(
                    sequence=1,
                    stage="response_pipeline",
                    decision="dispatch",
                    fields={"action_count": 2},
                )
            ]
        )

        rendered = OrchestrationTraceExporter().render_text(state)

        self.assertIn("[1] stage=response_pipeline decision=dispatch", rendered)
        self.assertIn("action_count: 2", rendered)

    def test_command_handler_runtime_diagnostics_include_orchestration_trace(self):
        state = SimpleNamespace(
            last_error_code=None,
            last_error_recoverable=None,
            consecutive_same_error_count=0,
            last_failed_action_command=None,
            last_failed_action_result=None,
            orchestration_trace=[
                OrchestrationTraceEntry(
                    sequence=1,
                    stage="intent_transition",
                    decision="continue",
                    fields={"reason": "intent_completed"},
                )
            ],
        )
        agent = SimpleNamespace(state=state, log=None)
        app = SimpleNamespace(agent=agent, ui=SimpleNamespace())
        handler = CommandHandler(app)

        import io

        out = io.StringIO()
        handler._write_runtime_diagnostics(out, full_dump=False)
        rendered = out.getvalue()

        self.assertIn("ORCHESTRATION TRACE:", rendered)
        self.assertIn("stage=intent_transition", rendered)


if __name__ == "__main__":
    unittest.main()
