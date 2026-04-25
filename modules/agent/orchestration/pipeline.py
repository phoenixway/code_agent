"""Unified pre-dispatch orchestration pipeline."""

from __future__ import annotations

import asyncio

from .decision_models import ModelStepResult, PipelineIterationDecision
from .stage_logging import OrchestrationStageLogger
from ..model_client import ModelTechnicalInterruptionError
from ..technical_interruptions import TechnicalInterruption


class OrchestrationPipeline:
    def __init__(self, agent, prompt_builder, intent_response_parser, loop_gate, response_pipeline):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history
        self.model = agent.model_client
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.intent_response_parser = intent_response_parser
        self.loop_gate = loop_gate
        self.response_pipeline = response_pipeline
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    @property
    def ui(self):
        return self.agent.ui

    def _close_active_intent_after_interruption(self, completion_reason: str) -> None:
        closer = getattr(self.state, "close_active_intent_as_resumable", None)
        if not callable(closer):
            return
        try:
            closer(completion_reason)
        except Exception:
            pass

    async def _handle_technical_interruption(self, ctx, interruption) -> bool:
        note = getattr(self.state, "note_technical_interruption", None)
        if callable(note):
            note(interruption, current_query=ctx.current_query)

        snapshot = getattr(self.state, "last_technical_interruption", None) or interruption
        printer = getattr(self.ui, "print_technical_interruption", None)
        if callable(printer):
            await printer(snapshot)
        else:
            message = str(getattr(interruption, "message", "") or "Model provider interruption.").strip()
            provider = str(getattr(interruption, "provider", "") or "provider").strip()
            status_code = getattr(interruption, "status_code", None)
            prefix = f"{provider}: "
            if status_code is not None:
                prefix = f"{provider} {status_code}: "
            await self.ui.print_error(prefix + message)

        self.stage_logger.log(
            "model_step",
            "stop",
            reason="technical_interruption",
            source="technical_interruption",
        )
        self._close_active_intent_after_interruption("technical_interruption")
        ctx.active_loop = False
        return False

    async def _run_model_step(self, ctx) -> ModelStepResult | None:
        if hasattr(self.prompt_builder, "_intent_universe"):
            try:
                universe = self.prompt_builder._intent_universe()
                self.stage_logger.log(
                    "intent_universe",
                    "resolved",
                    kind=getattr(universe, "kind", ""),
                    has_active_contract=getattr(universe, "has_active_contract", False),
                    intent_required_now=getattr(universe, "intent_required_now", False),
                    active_intent_type=getattr(universe, "active_intent_type", ""),
                    intentless_steps_used=getattr(universe, "intentless_steps_used", 0),
                )
            except Exception:
                pass
        self.stage_logger.log(
            "model_step",
            "request",
            step=ctx.consecutive_calls,
        )
        system_msg = self.prompt_builder.build_system_message(ctx.tools_prompt, ctx.ctx_prompt)
        injected_messages: list[dict[str, str]] = []
        build_intent_runtime_context_message = getattr(self.prompt_builder, "build_intent_runtime_context_message", None)
        if callable(build_intent_runtime_context_message):
            intent_runtime_message = build_intent_runtime_context_message()
            if intent_runtime_message:
                injected_messages.append(intent_runtime_message)
        build_plan_board_context_message = getattr(self.prompt_builder, "build_plan_board_context_message", None)
        if callable(build_plan_board_context_message):
            plan_board_message = build_plan_board_context_message()
            if plan_board_message:
                injected_messages.append(plan_board_message)
        memory_board_message = None
        build_memory_board_context_message = getattr(self.prompt_builder, "build_memory_board_context_message", None)
        if callable(build_memory_board_context_message):
            memory_board_message = build_memory_board_context_message()
            if memory_board_message:
                injected_messages.append(memory_board_message)

        while True:
            self.state.current_task = asyncio.create_task(
                self.model.get_streaming_response(
                    ctx.current_query,
                    self.history,
                    self.ui,
                    self.state,
                    system_message=system_msg,
                    injected_messages=injected_messages or None,
                )
            )
            try:
                response = await asyncio.wait_for(
                    self.state.current_task,
                    timeout=self.config.MAX_STEP_SECONDS,
                )
                clear = getattr(self.state, "clear_technical_interruption", None)
                if callable(clear):
                    clear()
                break
            except asyncio.TimeoutError:
                self.state.current_task.cancel()
                timeout_interruption = TechnicalInterruption(
                    kind="timeout",
                    provider=str(getattr(self.model.chat, "provider_name", "") or getattr(self.model.chat, "model_name", "") or "model").strip() or None,
                    message=f"Step timed out after {self.config.MAX_STEP_SECONDS}s.",
                    recoverable=True,
                    retryable=True,
                )
                await self._handle_technical_interruption(ctx, timeout_interruption)
                self.stage_logger.log(
                    "model_step",
                    "stop",
                    reason="step_timeout",
                    source="model_timeout",
                )
                return None
            except ModelTechnicalInterruptionError as exc:
                retry_now = await self._handle_technical_interruption(ctx, exc.interruption)
                if retry_now:
                    continue
                return None

        response, intent_payload, intent_error = self.intent_response_parser.extract_intent_update_and_strip(response)
        model_stop_reason = str(getattr(self.state, "last_model_response_stop_reason", "") or "").strip()
        try:
            setattr(self.state, "last_model_response_stop_reason", "")
        except Exception:
            pass
        if self.agent.log:
            self.agent.log.debug(
                "Orchestrator.step.response_received raw_chars=%s has_intent_payload=%s intent_error=%s model_stop_reason=%s",
                len(response or ""),
                intent_payload is not None,
                intent_error or "",
                model_stop_reason,
            )
            self.agent.log.debug("Orchestrator.step.response.after_initial_extract\n%s", response)
        self.stage_logger.log(
            "model_step",
            "response",
            raw_chars=len(response or ""),
            has_intent_payload=intent_payload is not None,
            intent_error=intent_error or "",
            model_stop_reason=model_stop_reason,
        )
        return ModelStepResult(
            response=response,
            intent_payload=intent_payload,
            intent_error=intent_error,
            model_stop_reason=model_stop_reason,
        )

    async def run_iteration(self, ctx) -> PipelineIterationDecision:
        self.stage_logger.log(
            "pre_dispatch_pipeline",
            "start",
            step=ctx.consecutive_calls + 1,
        )
        gate_decision = await self.loop_gate.run(ctx)
        if not gate_decision.proceed:
            self.stage_logger.log(
                "pre_dispatch_pipeline",
                "stop",
                reason=gate_decision.reason,
                source=gate_decision.source,
            )
            return PipelineIterationDecision.stop(
                reason=gate_decision.reason,
                source=gate_decision.source,
            )

        step = await self._run_model_step(ctx)
        if step is None:
            self.stage_logger.log(
                "pre_dispatch_pipeline",
                "stop",
                reason="model_step_unavailable",
                source="model_step",
            )
            return PipelineIterationDecision.stop(
                reason="model_step_unavailable",
                source="model_step",
            )

        outcome = await self.response_pipeline.run_step(ctx, step)
        if outcome.malformed_action_retries is not None:
            ctx.malformed_action_retries = outcome.malformed_action_retries
        if outcome.audit_marker_retries is not None:
            ctx.audit_marker_retries = outcome.audit_marker_retries

        if bool(getattr(self.state, "terminal_plaintext_completion_pending", False)):
            terminal_text = str(
                getattr(self.state, "terminal_plaintext_completion_text", "")
                or getattr(outcome, "response_text", "")
                or step.response
                or ""
            ).strip()

            # Keep the terminal text in state until core.py flushes it to the UI.
            if terminal_text:
                try:
                    setattr(self.state, "terminal_plaintext_completion_text", terminal_text)
                except Exception:
                    pass
                self.history.add_message("assistant", terminal_text)

            # It is safe to reset per-turn readonly counters here, but do NOT clear
            # terminal completion flags yet. core.py needs them to render the final reply.
            try:
                if hasattr(self.state, "readonly_steps_this_turn"):
                    self.state.readonly_steps_this_turn = 0
            except Exception:
                pass

            self.stage_logger.log(
                "pre_dispatch_pipeline",
                "stop",
                reason="terminal_plaintext_completion",
                source="response_pipeline",
            )
            return PipelineIterationDecision.stop(
                reason="terminal_plaintext_completion",
                source="response_pipeline",
            )

        if bool(getattr(outcome, "stop_loop", False)):
            self.stage_logger.log(
                "pre_dispatch_pipeline",
                "stop",
                reason=outcome.reason or "response_pipeline_stop",
                source=outcome.source or "response_pipeline",
            )
            return PipelineIterationDecision.stop(
                reason=outcome.reason or "response_pipeline_stop",
                source=outcome.source or "response_pipeline",
            )

        if outcome.continue_loop:
            if outcome.next_query:
                ctx.current_query = outcome.next_query
            self.stage_logger.log(
                "pre_dispatch_pipeline",
                "continue",
                reason="pre_dispatch_continue",
                source="response_pipeline",
            )
            return PipelineIterationDecision.continue_with(
                next_query=outcome.next_query,
                reason="pre_dispatch_continue",
                source="response_pipeline",
                malformed_action_retries=outcome.malformed_action_retries,
                audit_marker_retries=outcome.audit_marker_retries,
            )

        # Text-only ready path: allow downstream dispatch_outcome to finalize and stop cleanly.
        self.stage_logger.log(
            "pre_dispatch_pipeline",
            "dispatch_ready",
            action_count=outcome.parsed_action_count,
            source="response_pipeline",
        )
        return PipelineIterationDecision.dispatch_ready(
            segments=outcome.segments,
            parsed_output=outcome.parsed_output,
            parsed_action_count=outcome.parsed_action_count,
            reason="ready_for_dispatch",
            source="response_pipeline",
            malformed_action_retries=outcome.malformed_action_retries,
            audit_marker_retries=outcome.audit_marker_retries,
        )
