"""Contract/status prompt builder for orchestration."""

from __future__ import annotations

from .prompt_builder_shared import PromptBuilderSharedMixin


class ContractPromptBuilder(PromptBuilderSharedMixin):
    def __init__(self, agent):
        self._init_prompt_builder_shared(agent)

        def build_active_intent_contract_prompt(self) -> str:
            universe = self._intent_universe()
            active_intent = self._current_active_intent()
            if active_intent is None or not universe.has_active_contract:
                return ""

            intent_id = str(getattr(active_intent, "intent_id", "") or "").strip() or "<none>"
            intent_type = str(getattr(active_intent, "intent_type", "") or "").strip() or "<none>"
            goal = str(getattr(active_intent, "goal", "") or "").strip() or "<none>"
            allowed_actions = list(getattr(active_intent, "allowed_actions", []) or [])
            safe_steps_limit = int(getattr(active_intent, "safe_steps_limit", 0) or 0)
            steps_used = int(getattr(active_intent, "step_count", 0) or 0)
            steps_remaining = self._intent_steps_remaining(active_intent)
            hard_steps_remaining = self._intent_hard_steps_remaining(active_intent)
            effective_hard_limit = self._effective_intent_hard_limit(active_intent)
            retry_limit = int(getattr(active_intent, "retry_limit", 0) or 0)
            retry_count = int(getattr(active_intent, "retry_count", 0) or 0)
            last_action = self._summarize_last_action()
            current_best_answer = self._derive_current_best_answer(active_intent)
            accepted = "yes"
            mode = "active"

            lines = [
                "## ACTIVE INTENT CONTRACT",
                "Status: ACTIVE",
                f"Accepted by runtime: {accepted}",
                "This contract remains active until runtime explicitly completes, replaces, rejects, or closes it.",
                "Do not emit another <intent mode=\"activate\"> for the same ongoing work.",
                "Continue under this contract unless runtime explicitly requires a legitimate transition.",
                "",
                "VALID REASONS TO CHANGE THE ACTIVE INTENT CONTRACT:",
                "- user_requested_new_task",
                "- current_intent_completed",
                "- current_intent_exhausted",
                "- work_type_changed",
                "- current_intent_no_longer_fits",
                "If none of these reasons applies, do NOT emit <intent mode=\"activate\"> or <intent mode=\"replace\"> again for this same ongoing work.",
                "",
                f"intent_id: {intent_id}",
                f"intent_type: {intent_type}",
                f"goal: {goal}",
                f"allowed_actions: {', '.join(allowed_actions) if allowed_actions else 'none'}",
                f"safe_steps_limit: {safe_steps_limit}",
                f"effective_nominal_step_limit: {self._effective_intent_step_limit(active_intent)}",
                f"effective_hard_step_limit: {effective_hard_limit}",
                f"steps_used: {steps_used}",
                f"nominal_steps_remaining: {steps_remaining}",
                f"hard_steps_remaining: {hard_steps_remaining}",
                ("step_budget_status: nominal" if steps_remaining > 0 else ("step_budget_status: nominal limit reached but hard-limit completion allowance remains" if hard_steps_remaining > 0 else "step_budget_status: hard limit reached")),
                f"retry_limit: {retry_limit}",
                f"retry_count: {retry_count}",
                f"mode: {mode}",
                "",
                f"last_action: {last_action}",
                f"current_best_answer: {current_best_answer}",
                "",
                "Memory-board expectation for this contract:",
                "- After each meaningful evidence gain, emit exactly ONE concise memory tag if the new fact, finding, decision, or milestone would matter after history compression.",
                "- Prefer <finding scope=\"intent\"> for newly established conclusions and <progress scope=\"intent\"> for milestone-level continuation state.",
                "- Do not emit a memory tag for routine tool usage with no durable insight.",
            ]
            lines.extend(self._memory_tag_followup_lines())
            lines.extend([
                "",
                "Next valid behaviors:",
                "- return exactly one allowed action to advance the current work",
                "- or return a plain-text answer if current evidence is already sufficient",
                "- or emit <intent mode=\"complete\"> followed by a plain-text answer if the goal is achieved",
                "",
                "Do NOT:",
                "- emit a new <intent mode=\"activate\"> or <intent mode=\"replace\"> for the same goal",
                "- restart reconnaissance from the beginning",
                "- ignore already established current_best_answer and intent-scoped memory without new evidence",
            ])
            return "\n".join(lines)

        def build_no_active_intent_contract_prompt(self) -> str:
            universe = self._intent_universe()
            active_intent = self._current_active_intent()
            if active_intent is not None or universe.has_active_contract:
                return ""

            steps_used = universe.intentless_steps_used
            steps_limit = universe.intentless_steps_limit
            intent_required = universe.intent_required_now
            intent_required_reason = str(universe.intent_requirement_reason or "").strip() or "none"
            last_action = self._summarize_last_action()

            lines = [
                "## INTENT MODE STATUS",
                "Status: NO ACTIVE INTENT CONTRACT",
                "Runtime mode: INTENTLESS_SHORT_MODE",
                "Accepted by runtime: no active contract",
                "There is currently NO active accepted formal intent contract for this work.",
                "This mode is only for short unguided continuation before a formal contract is required.",
                "Do not claim that a current intent contract remains active, because none exists.",
                "",
                f"intentless_steps_used: {steps_used}",
                f"intentless_steps_limit: {steps_limit}",
                f"formal_intent_required_now: {'yes' if intent_required else 'no'}",
                f"intent_requirement_reason: {intent_required_reason}",
                f"last_action: {last_action}",
                "",
                "Rules in this mode:",
                "- continue from already gathered evidence; do not restart from zero",
                "- if the next step needs governed multi-step execution, emit a formal <intent> now",
                "- until activation succeeds, do not assume contract-scoped permissions or allowed_actions",
                "- if a formal intent is already required, do not return another bare <action> first",
                "- if current evidence is already sufficient, answer directly in plain text",
            ]
            lines.extend(self._memory_tag_followup_lines())
            lines.extend(self._recent_resumable_intent_lines())
            return "\n".join(lines)

        def build_system_message(self, tools_prompt: str, ctx_prompt: str) -> str:
            prompt = DEFAULT_SYSTEM_PROMPT.replace("__TOOLS_DESCRIPTION__", tools_prompt)
            blocks = [prompt, ctx_prompt]

            memory_board = getattr(self.agent, "memory_board_store", None)
            active_intent_id = self._current_active_intent_id()
            active_intent_lineage_ids = self._active_intent_lineage_ids()

            active_intent_prompt = self.build_active_intent_contract_prompt()
            if active_intent_prompt:
                blocks.append(active_intent_prompt)
                if self.agent.log:
                    self.agent.log.debug(
                        "PromptBuilder.active_intent_contract_prompt active_intent_id=%s chars=%s\n%s",
                        active_intent_id or "",
                        len(active_intent_prompt),
                        active_intent_prompt,
                    )
            else:
                no_active_prompt = self.build_no_active_intent_contract_prompt()
                if no_active_prompt:
                    blocks.append(no_active_prompt)
                    if self.agent.log:
                        self.agent.log.debug(
                            "PromptBuilder.no_active_intent_contract_prompt chars=%s\n%s",
                            len(no_active_prompt),
                            no_active_prompt,
                        )

            if memory_board is not None and hasattr(memory_board, "to_system_prompt"):
                try:
                    memory_prompt = memory_board.to_system_prompt(
                        active_intent_id=active_intent_id,
                        lineage_intent_ids=active_intent_lineage_ids,
                    )
                    blocks.append(memory_prompt)
                    if self.agent.log and isinstance(memory_prompt, str) and memory_prompt.strip():
                        self.agent.log.debug(
                            "PromptBuilder.memory_board_prompt active_intent_id=%s chars=%s\n%s",
                            active_intent_id or "",
                            len(memory_prompt),
                            memory_prompt,
                        )
                except Exception as exc:
                    if self.agent.log:
                        self.agent.log.warning(f"Memory board prompt build failed: {exc}")

            blocks.append(self.build_memory_board_protocol_prompt())
            system_message = "\n\n".join(block for block in blocks if isinstance(block, str) and block.strip())
            if self.agent.log:
                self.agent.log.debug(
                    "PromptBuilder.system_message built blocks=%s tools_chars=%s ctx_chars=%s total_chars=%s",
                    len([block for block in blocks if isinstance(block, str) and block.strip()]),
                    len(tools_prompt or ""),
                    len(ctx_prompt or ""),
                    len(system_message or ""),
                )
                self.agent.log.debug("PromptBuilder.system_message.full\n%s", system_message)
            return system_message

        def build_memory_board_protocol_prompt(self) -> str:
            return dedent(
                """
                ## MEMORY BOARD PROTOCOL
                Memory tags are part of working continuity, not decoration.
                Supported tags:
                - <fact scope="intent|session|project">...</fact>
                - <finding scope="intent|session|project">...</finding>
                - <decision scope="intent|session|project">...</decision>
                - <preference scope="intent|session|project">...</preference>
                - <progress scope="intent">...</progress>

                THINK REFLECTION RULE:
                - After every <think> containing 5 or more words, emit a formal reflection of that thinking using one or more memory tags.
                - Put the tags immediately after </think> and before any <action> or plain-text continuation.
                - This reflection is REQUIRED for substantial thinking.
                - Capture ALL valuable results of the thinking, not just one.
                - If the thinking produced multiple valuable outcomes, emit multiple tags.
                - Long <think> + one tiny tag is usually incomplete.

                Tag selection:
                - Use <fact> for information directly verified by tool output, code, or runtime state already visible in history.
                - Use <finding> for conclusions, interpretations, suspected behavior, or any statement that is not directly quoted or directly observable from tool output.
                - Use <decision> for chosen plans, strategy choices, or explicit working decisions.
                - Use <progress> for milestone-level continuation state.
                - Use <preference> only for durable preference-like guidance that actually matters later.

                Scope rules:
                - Use scope="intent" for information useful for continuing the current line of work.
                - Use scope="session" for information useful later in the current session.
                - Use scope="project" only for durable project-wide facts, decisions, or preferences.
                - Prefer the narrowest correct scope.

                What to preserve:
                - all verified facts established during thinking
                - all real conclusions reached during thinking
                - all chosen decisions made during thinking
                - milestone-level progress that would matter after compression
                - recovery consequences that change the continuation rules
                - current-best-answer updates when they materially changed

                What NOT to do:
                - Do not log routine actions, tool calls, or noisy low-level observations.
                - Do not emit one arbitrary tag when the thinking produced several durable outcomes.
                - Do not silently contradict previously committed memory; if new evidence changes something important, emit a new explicit correcting tag.

                Good examples:
                <think>
                The handler reads planIdFlow and mutates links through getPlanById(planId), so the current Today links behavior is still bound to a specific day plan. The clean direction is to remove the day-plan dependency at the handler boundary.
                </think>
                <finding scope="intent">DayPlanScopeLinksHandler is day-specific because it reads planIdFlow and mutates links through getPlanById(planId).</finding>
                <decision scope="intent">Remove the day-plan dependency at the handler boundary instead of preserving planIdFlow semantics for Today links.</decision>

                <think>
                The sheet derives displayed links from DayPlanUiState.dayPlan linked IDs. That means the rendering layer is also day-specific, not only the mutation layer. We now know there are at least two binding points to replace.
                </think>
                <fact scope="intent">DayScopeLinksSheet derives displayed links from DayPlanUiState.dayPlan linked IDs.</fact>
                <finding scope="intent">The current Today links flow is day-specific in both mutation logic and rendering logic.</finding>
                <progress scope="intent">Identified the main per-day binding points that must be replaced.</progress>

                <think>
                The last file read failed because the path was wrong, but runtime provided a reliable parent directory. I should not retry the same missing path. I should inspect the suggested directory and locate the correct file from there.
                </think>
                <finding scope="intent">The previous file-read failure was caused by a wrong path, not by proof that the repository logic is absent.</finding>
                <decision scope="intent">Do not retry the same missing-file read; inspect the suggested parent directory and locate the correct file from there.</decision>

                Format:
                - Prefer 1-4 sentences per tag.
                - Use compact wording.
                - Preserve the conclusion, rule, fact, decision, or milestone rather than the whole reasoning chain.
                """
            ).strip()