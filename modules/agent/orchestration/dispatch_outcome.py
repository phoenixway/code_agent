"""Post-dispatch outcome handling for orchestrator tool execution."""

from __future__ import annotations

from .decision_models import DispatchHandlingDecision
from .stage_logging import OrchestrationStageLogger


class DispatchOutcomeHandler:
    def __init__(self, agent, parser, recovery):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history
        self.parser = parser
        self.recovery = recovery
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    @property
    def ui(self):
        return self.agent.ui

    async def handle(self, ctx, processed_segs, sys_results, should_stop: bool) -> DispatchHandlingDecision:
        recon_msg = self.parser.reconstruct(processed_segs)
        if recon_msg:
            self.history.add_message("assistant", recon_msg)

        if not sys_results:
            await self.ui.print_system("Execution finished: no further actions returned by the model.")
            ctx.active_loop = False
            return DispatchHandlingDecision.stop(
                reason="no_system_results",
                source="dispatch",
            )

        self.stage_logger.log(
            "dispatch_outcome",
            "evaluate",
            system_result_count=len(sys_results),
            should_stop=should_stop,
        )
        for res in sys_results:
            self.history.add_message("system", res)

        if should_stop:
            stop_info = getattr(self.state, "pending_loop_stop_info", None)
            decision = await self.recovery.handle_dispatch_stop(stop_info, ctx.state_machine)
            if decision.handled:
                if decision.clear_pending_stop:
                    self.state.pending_loop_stop_info = None
                if decision.next_query:
                    ctx.current_query = decision.next_query
                if decision.stop_loop:
                    ctx.active_loop = False
                if decision.next_query:
                    return DispatchHandlingDecision.continue_with(
                        decision.next_query,
                        reason=decision.reason,
                        source=decision.source or "dispatch_recovery",
                        clear_pending_stop=bool(decision.clear_pending_stop),
                    )
                return DispatchHandlingDecision(
                    handled=True,
                    continue_loop=False,
                    next_query=decision.next_query,
                    stop_loop=bool(decision.stop_loop),
                    clear_pending_stop=bool(decision.clear_pending_stop),
                    reason=decision.reason,
                    source=decision.source or "dispatch_recovery",
                )

            await self.ui.print_system(
                "Execution stopped by control policy (for example, denied action)."
            )
            ctx.active_loop = False
            return DispatchHandlingDecision.stop(
                reason="control_policy_stop",
                source="dispatch",
            )

        if ctx.state_machine is not None:
            sm_decision = ctx.state_machine.decide()
            if sm_decision.decision.name == "MODEL_DIAGNOSTIC":
                ctx.current_query = sm_decision.prompt
                return DispatchHandlingDecision.continue_with(
                    sm_decision.prompt,
                    reason="model_diagnostic",
                    source="state_machine",
                )
            if sm_decision.decision.name == "USER_HANDOFF":
                decision = await self.ui.confirm_loop_recovery(
                    "Detected repeated read-only stagnation. Choose next step."
                )
                if decision in {"retry_recovery", "continue_diagnosis"}:
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    ctx.current_query = ctx.state_machine.build_diagnostic_prompt()
                    return DispatchHandlingDecision.continue_with(
                        ctx.current_query,
                        reason=str(decision),
                        source="state_machine",
                    )
                if decision == "open_search":
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    ctx.current_query = (
                        "SYSTEM: Switch strategy.\n"
                        "Do not call read_file with the same path/arguments.\n"
                        "Use search_content, read_chunk, read_file_skeleton, or edit_file with exact targeted arguments."
                    )
                    return DispatchHandlingDecision.continue_with(
                        ctx.current_query,
                        reason="open_search",
                        source="state_machine",
                    )
                if decision == "pin_target_edit":
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    if hasattr(ctx.state_machine, "build_pin_target_prompt"):
                        ctx.current_query = ctx.state_machine.build_pin_target_prompt()
                        return DispatchHandlingDecision.continue_with(
                            ctx.current_query,
                            reason="pin_target_edit",
                            source="state_machine",
                        )
                await self.ui.print_system("Execution stopped by user after stagnation warning.")
                ctx.active_loop = False
                return DispatchHandlingDecision.stop(
                    reason="user_stopped_after_stagnation_warning",
                    source="state_machine",
                )

        ctx.current_query = "\n---\n".join(sys_results)
        return DispatchHandlingDecision.pass_through(
            reason="system_results_forwarded",
            source="dispatch",
        )
