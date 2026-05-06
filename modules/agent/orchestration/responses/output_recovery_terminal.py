"""Terminal handoff helpers for output-recovery flows."""

from __future__ import annotations

from ..shared.decision_models import OutputRecoveryDecision, ParsedModelOutput


class OutputRecoveryTerminalMixin:
    def _mark_terminal_plaintext_handoff(self, text: str, reason: str) -> None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", True)
            setattr(self.state, "terminal_plaintext_completion_text", normalized_text)
        except Exception:
            pass
        marker = getattr(self.state, "mark_pending_forced_plaintext_completion_close", None)
        if callable(marker):
            try:
                marker(str(reason or "terminal_plaintext_completion").strip(), "output_recovery")
            except Exception:
                pass

    def _action_context_from_parsed_output(self, parsed_output: ParsedModelOutput) -> tuple[str, str]:
        segments = list(getattr(parsed_output, "segments", []) or [])
        for seg in segments:
            if getattr(seg, "type", "") != "action":
                continue
            content = getattr(seg, "content", None)
            if not isinstance(content, dict):
                continue
            action_type = str(content.get("type") or content.get("action") or "").strip()
            path = str(content.get("path") or "").strip()
            if action_type or path:
                return action_type, path
        blocked_action = str(getattr(self.state, "last_blocked_action_type", "") or "").strip()
        blocked_path = str(getattr(self.state, "last_blocked_action_path", "") or "").strip()
        if blocked_action or blocked_path:
            return blocked_action, blocked_path
        journal_entry = self._latest_operational_journal_action_entry()
        if journal_entry is not None:
            action_type = str(journal_entry.get("action_type") or "").strip()
            target = str(journal_entry.get("target") or "").strip()
            if action_type or target:
                return action_type, target
        return blocked_action, blocked_path

    def _latest_operational_journal_action_entry(self) -> dict | None:
        snapshotter = getattr(self.state, "operational_journal_snapshot", None)
        if callable(snapshotter):
            try:
                snapshot = snapshotter() or []
                for entry in reversed(snapshot):
                    if isinstance(entry, dict) and str(entry.get("kind") or "").strip() == "tool_execution_commit":
                        return entry
            except Exception:
                pass
        journal = list(getattr(self.state, "operational_journal", []) or [])
        for entry in reversed(journal):
            if isinstance(entry, dict) and str(entry.get("kind") or "").strip() == "tool_execution_commit":
                return entry
            if hasattr(entry, "__dict__"):
                try:
                    payload = dict(vars(entry))
                except Exception:
                    continue
                if str(payload.get("kind") or "").strip() == "tool_execution_commit":
                    return payload
        return None

    def _terminal_recovery_loop_decision(self, defect_kind: str) -> OutputRecoveryDecision:
        blocked_action, path_or_action = self._action_context_from_parsed_output(self._last_parsed_output_for_handoff)
        self._mark_terminal_plaintext_handoff(
            self.prompt_builder.build_terminal_recovery_loop_handoff_text(
                defect_kind=defect_kind,
                blocked_action=blocked_action,
                path_or_action=path_or_action,
            ),
            "terminal_recovery_loop_handoff",
        )
        self.stage_logger.log(
            "output_recovery",
            "stop",
            reason="terminal_recovery_loop_handoff",
            universe=self._intent_universe_label(),
            defect_kind=str(defect_kind or "").strip() or "recovery_loop_detected",
        )
        return OutputRecoveryDecision(
            handled=True,
            continue_loop=False,
            stop_loop=True,
            next_query=None,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason="terminal_recovery_loop_handoff",
            source="output_recovery",
        )

    def _terminal_malformed_think_handoff_decision(self, defect_kind: str) -> OutputRecoveryDecision:
        builder = getattr(self.prompt_builder, "build_terminal_malformed_think_handoff_text", None)
        if callable(builder):
            handoff_text = builder(defect_kind=defect_kind)
        else:
            handoff_text = self.prompt_builder.build_terminal_recovery_loop_handoff_text(
                defect_kind=defect_kind,
                blocked_action="internal_control_output",
                path_or_action="<think>",
            )
        self._mark_terminal_plaintext_handoff(
            handoff_text,
            "terminal_malformed_think_handoff",
        )
        self._clear_malformed_think_count()
        self.stage_logger.log(
            "output_recovery",
            "stop",
            reason="terminal_malformed_think_handoff",
            universe=self._intent_universe_label(),
            defect_kind=str(defect_kind or "").strip() or "malformed_think",
        )
        return OutputRecoveryDecision(
            handled=True,
            continue_loop=False,
            stop_loop=True,
            next_query=None,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason="terminal_malformed_think_handoff",
            source="output_recovery",
        )

    def _terminal_large_malformed_response_decision(
        self,
        *,
        invalid_kind: str,
        raw_chars: int,
        parsed_output: ParsedModelOutput,
    ) -> OutputRecoveryDecision:
        blocked_action, path_or_action = self._action_context_from_parsed_output(parsed_output)
        self._mark_terminal_plaintext_handoff(
            self.prompt_builder.build_terminal_large_malformed_response_handoff_text(
                invalid_kind=invalid_kind,
                raw_chars=raw_chars,
                blocked_action=blocked_action,
                path_or_action=path_or_action,
            ),
            "terminal_large_malformed_response_handoff",
        )
        self.stage_logger.log(
            "output_recovery",
            "stop",
            reason="terminal_large_malformed_response_handoff",
            universe=self._intent_universe_label(),
            invalid_kind=str(invalid_kind or "").strip() or "malformed_response",
            raw_chars=int(raw_chars or 0),
        )
        return OutputRecoveryDecision(
            handled=True,
            continue_loop=False,
            stop_loop=True,
            next_query=None,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason="terminal_large_malformed_response_handoff",
            source="output_recovery",
        )
