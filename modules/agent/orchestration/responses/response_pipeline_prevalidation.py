"""Normalization and prevalidation helpers for response pipeline."""

from __future__ import annotations

from ..decision_models import NormalizedModelResponse, ResponsePipelineOutcome
from ..parsers.visible_text import sanitize_visible_text_for_user, terminal_plaintext_completion_status


class ResponsePipelinePrevalidationMixin:
    def _normalize_response_if_supported(self, response: str, *, allow_autorepair: bool) -> NormalizedModelResponse:
        text = str(response or "")
        normalizer = getattr(self.intent_response_parser, "normalize_model_response", None)
        if callable(normalizer):
            try:
                result = normalizer(
                    text,
                    allow_think_autorepair=allow_autorepair,
                )
            except TypeError:
                try:
                    result = normalizer(text)
                except Exception:
                    return NormalizedModelResponse(raw_response=text, normalized_response=text)
            except Exception:
                return NormalizedModelResponse(raw_response=text, normalized_response=text)
            if isinstance(result, NormalizedModelResponse):
                return result
            repaired = str(getattr(result, "response_text", text) or "")
            return NormalizedModelResponse(
                raw_response=text,
                normalized_response=repaired,
                think_repair_applied=bool(getattr(result, "applied", False)),
                think_repair_reason=str(getattr(result, "reason", "") or ""),
                think_repair_confidence=str(getattr(result, "confidence", "") or ""),
                think_repair_tag=str(getattr(result, "tag_name", "") or ""),
                think_repair_insert_at=int(getattr(result, "insert_at", -1) or -1),
                think_repair_blocked_by_atomicity=bool(getattr(result, "blocked_by_atomicity", False)),
                repairs_applied=("auto_close_think",) if bool(getattr(result, "applied", False)) else (),
                repair_blocked_reason="intent_atomicity_guard" if bool(getattr(result, "blocked_by_atomicity", False)) else "",
                diagnostics={
                    "think_repair_candidate_tag": str(getattr(result, "tag_name", "") or ""),
                    "think_repair_insert_at": int(getattr(result, "insert_at", -1) or -1),
                },
            )
        if not allow_autorepair:
            return NormalizedModelResponse(
                raw_response=text,
                normalized_response=text,
                repair_blocked_reason="intent_atomicity_guard",
                think_repair_blocked_by_atomicity=True,
            )
        repairer = getattr(self.intent_response_parser, "repair_unclosed_think_boundary", None)
        if not callable(repairer):
            return NormalizedModelResponse(raw_response=text, normalized_response=text)
        try:
            result = repairer(text)
        except Exception:
            return NormalizedModelResponse(raw_response=text, normalized_response=text)
        repaired = str(getattr(result, "response_text", text) or "")
        return NormalizedModelResponse(
            raw_response=text,
            normalized_response=repaired,
            think_repair_applied=bool(getattr(result, "applied", False)),
            think_repair_reason=str(getattr(result, "reason", "") or ""),
            think_repair_confidence=str(getattr(result, "confidence", "") or ""),
            think_repair_tag=str(getattr(result, "tag_name", "") or ""),
            think_repair_insert_at=int(getattr(result, "insert_at", -1) or -1),
            think_repair_blocked_by_atomicity=bool(getattr(result, "blocked_by_atomicity", False)),
            repairs_applied=("auto_close_think",) if bool(getattr(result, "applied", False)) else (),
            repair_blocked_reason="intent_atomicity_guard" if bool(getattr(result, "blocked_by_atomicity", False)) else "",
            diagnostics={
                "think_repair_candidate_tag": str(getattr(result, "tag_name", "") or ""),
                "think_repair_insert_at": int(getattr(result, "insert_at", -1) or -1),
            },
        )

    def _normalize_response_stage(
        self,
        response: str,
        *,
        allow_autorepair: bool,
        source: str,
    ) -> NormalizedModelResponse:
        normalized = self._normalize_response_if_supported(
            response,
            allow_autorepair=allow_autorepair,
        )
        self.stage_logger.log(
            "response_normalization",
            "pass",
            source=source,
            response_chars=len(str(getattr(normalized, "normalized_response", "") or "")),
            think_repair_applied=bool(getattr(normalized, "think_repair_applied", False)),
            think_repair_reason=str(getattr(normalized, "think_repair_reason", "") or ""),
            think_repair_confidence=str(getattr(normalized, "think_repair_confidence", "") or ""),
            think_repair_tag=str(getattr(normalized, "think_repair_tag", "") or ""),
            think_repair_insert_at=int(getattr(normalized, "think_repair_insert_at", -1) or -1),
            think_repair_blocked_by_atomicity=bool(getattr(normalized, "think_repair_blocked_by_atomicity", False)),
            repair_blocked_reason=str(getattr(normalized, "repair_blocked_reason", "") or ""),
            repairs_applied=list(getattr(normalized, "repairs_applied", ()) or []),
        )
        return normalized

    def _classify_intent_output(self, response: str, segments, *, allow_think_autorepair: bool):
        classifier = getattr(self.intent_response_parser, "classify")
        try:
            return classifier(
                response,
                segments,
                allow_think_autorepair=allow_think_autorepair,
            )
        except TypeError:
            return classifier(response, segments)

    def _clear_terminal_plaintext_completion_state(self) -> None:
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", False)
            setattr(self.state, "terminal_plaintext_completion_text", "")
        except Exception:
            pass

    def _terminal_completion_recovery_prompt(self, *, visible_text: str, reason: str) -> str:
        if str(reason or "").strip() == "control_tag_leak_in_visible_text":
            builder = getattr(self.prompt_builder, "build_control_tag_leak_recovery_prompt", None)
            if callable(builder):
                try:
                    return builder()
                except Exception:
                    pass
            return (
                "SYSTEM: Your final answer still contains internal control tags.\n"
                "Return only the user-visible final answer.\n"
                "Do not include <think>, memory tags, subgoal tags, intent tags, action tags, or file_content."
            )
        builder = getattr(self.prompt_builder, "build_plain_text_completion_prompt", None)
        stop_info = {
            "reason": "truncated_terminal_plaintext_answer",
            "recoverable": True,
            "error_code": "TRUNCATED_TERMINAL_PLAINTEXT_ANSWER",
            "message": (
                "The intent completion was not accepted because the user-visible final answer "
                "was missing or looked truncated."
            ),
            "error_details": {
                "visible_text": visible_text,
                "terminal_plaintext_reason": reason,
            },
            "next_actions": [],
            "intent_allowed_actions": [],
            "next_actions_source": "terminal_plaintext_guard",
        }
        if callable(builder):
            try:
                return builder(None, stop_info)
            except TypeError:
                try:
                    return builder(stop_info)
                except TypeError:
                    pass
            except Exception:
                pass
        return (
            "SYSTEM: The final answer after intent completion was missing or looked truncated.\n"
            "Do not emit another <intent> block. Do not emit <action>.\n"
            "Return only a complete concise plain-text final answer for the user."
        )

    def _reject_truncated_terminal_completion_before_transition(self, raw_response: str, step):
        payload = getattr(step, "intent_payload", None)
        if not isinstance(payload, dict):
            return None
        payload_mode = str(payload.get("mode") or "").strip().lower()
        if payload_mode != "complete":
            return None

        valid, reason, visible_text = terminal_plaintext_completion_status(raw_response)
        if valid:
            return None

        self._clear_terminal_plaintext_completion_state()
        self.stage_logger.log(
            "response_pipeline",
            "continue",
            reason="truncated_terminal_plaintext_answer",
            source="intent_completion_atomicity_guard",
            visible_text_chars=len(str(visible_text or "")),
            terminal_plaintext_reason=reason,
        )
        return ResponsePipelineOutcome.continue_with(
            self._terminal_completion_recovery_prompt(visible_text=visible_text, reason=reason),
            response_text=raw_response,
            reason="truncated_terminal_plaintext_answer",
            source="intent_completion_atomicity_guard",
        )

    def _classify_response_for_prevalidation(self, response: str, *, allow_think_autorepair: bool = True):
        normalized = self._normalize_response_stage(
            response,
            allow_autorepair=allow_think_autorepair,
            source="intent_prevalidation",
        )
        response = normalized.normalized_response
        segments = self.parser.parse(response)
        parsed_output = self._classify_intent_output(
            response,
            segments,
            allow_think_autorepair=allow_think_autorepair,
        )
        checkpoint_has_think = self.semantics.has_complete_think_before_action(response)
        checkpoint_has_marker = self.semantics.has_memory_update_done_before_action(response)
        checkpoint_has_tags = self.semantics.has_checkpoint_before_action(response)
        checkpoint_has_board_commit = False
        checkpoint_source_satisfied = bool(
            checkpoint_has_board_commit
            or checkpoint_has_marker
        )
        parsed_output.operational_checkpoint_has_think = checkpoint_has_think
        parsed_output.operational_checkpoint_has_marker = checkpoint_has_marker
        parsed_output.operational_checkpoint_has_board_commit = checkpoint_has_board_commit
        parsed_output.operational_checkpoint_has_tags = checkpoint_has_tags
        parsed_output.operational_checkpoint_satisfied = bool(
            checkpoint_has_think and checkpoint_source_satisfied
        )
        return segments, parsed_output

    async def _reject_invalid_intent_followup_before_transition(self, ctx, raw_response: str, step):
        if getattr(step, "intent_payload", None) is None:
            return None

        response = str(raw_response or "").strip()
        if not response:
            return None

        segments, parsed_output = self._classify_response_for_prevalidation(
            response,
            allow_think_autorepair=False,
        )
        parsed_output.model_stop_reason = str(getattr(step, "model_stop_reason", "") or "").strip()

        payload = getattr(step, "intent_payload", None)
        payload_mode = str((payload or {}).get("mode") or "").strip().lower() if isinstance(payload, dict) else ""
        intent_only_transition_required_now = bool(
            payload_mode in {"activate", "reuse", "replace"}
            and str(getattr(parsed_output, "invalid_kind", "") or "").strip() in {"missing_action_or_answer", "intent_only_without_next_step"}
            and not bool(getattr(parsed_output, "has_action_segment", False))
            and not str(getattr(parsed_output, "visible_text", "") or "").strip()
            and (
                bool(getattr(self.state, "intent_required_until_activated", False))
                or bool(getattr(self.state, "reuse_only_intent_required", False))
                or bool(getattr(self.state, "transition_only_intent_required", False))
            )
        )
        if intent_only_transition_required_now:
            return None
        if (
            payload_mode == "reuse"
            and str(getattr(parsed_output, "invalid_kind", "") or "").strip() in {"missing_action_or_answer", "intent_only_without_next_step"}
            and not bool(getattr(parsed_output, "has_action_segment", False))
            and not str(getattr(parsed_output, "visible_text", "") or "").strip()
        ):
            return None

        if not str(getattr(parsed_output, "invalid_kind", "") or "").strip():
            return None

        self.stage_logger.log(
            "response_pipeline",
            "continue",
            reason="intent_followup_prevalidation_failed",
            invalid_kind=parsed_output.invalid_kind,
            source="intent_atomicity_guard",
        )
        recovery_decision = await self.output_recovery.decide(
            parsed_output,
            malformed_action_retries=ctx.malformed_action_retries,
            audit_marker_retries=ctx.audit_marker_retries,
        )
        if recovery_decision.handled:
            return ResponsePipelineOutcome(
                handled=True,
                continue_loop=bool(recovery_decision.continue_loop),
                next_query=recovery_decision.next_query,
                stop_loop=bool(recovery_decision.stop_loop),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
                malformed_action_retries=recovery_decision.malformed_action_retries,
                audit_marker_retries=recovery_decision.audit_marker_retries,
                reason=recovery_decision.reason,
                source=recovery_decision.source,
            )

        return None

    def _terminal_plaintext_text_or_empty(self, response_text: str) -> str:
        visible_text, leak_detected = sanitize_visible_text_for_user(response_text)
        if leak_detected:
            return ""
        sanitized = str(visible_text or "").strip()
        forbidden_tokens = (
            "<think",
            "<memory_update_done",
            "<action",
            "<intent",
            "<subgoal",
            "<file_content",
        )
        assert all(token not in sanitized for token in forbidden_tokens)
        return sanitized
