"""Unified pre-dispatch orchestration pipeline."""

from __future__ import annotations

import asyncio

from .decision_models import ModelStepResult, PipelineIterationDecision
from .stage_logging import OrchestrationStageLogger


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

        self.state.current_task = asyncio.create_task(
            self.model.get_streaming_response(
                ctx.current_query,
                self.history,
                self.ui,
                self.state,
                system_message=system_msg,
            )
        )
        try:
            response = await asyncio.wait_for(
                self.state.current_task,
                timeout=self.config.MAX_STEP_SECONDS,
            )
        except asyncio.TimeoutError:
            self.state.current_task.cancel()
            await self.ui.print_error(
                f"Step timed out after {self.config.MAX_STEP_SECONDS}s."
            )
            ctx.active_loop = False
            self.stage_logger.log(
                "model_step",
                "stop",
                reason="step_timeout",
                source="model_timeout",
            )
            return None

        response, intent_payload, intent_error = self.intent_response_parser.extract_intent_update_and_strip(response)
        if self.agent.log:
            self.agent.log.debug(
                "Orchestrator.step.response_received raw_chars=%s has_intent_payload=%s intent_error=%s",
                len(response or ""),
                intent_payload is not None,
                intent_error or "",
            )
            self.agent.log.debug("Orchestrator.step.response.after_initial_extract\n%s", response)
        self.stage_logger.log(
            "model_step",
            "response",
            raw_chars=len(response or ""),
            has_intent_payload=intent_payload is not None,
            intent_error=intent_error or "",
        )
        return ModelStepResult(
            response=response,
            intent_payload=intent_payload,
            intent_error=intent_error,
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
