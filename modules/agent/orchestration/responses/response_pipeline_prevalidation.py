"""Normalization and prevalidation helpers for response pipeline."""

from __future__ import annotations

from ..shared.decision_models import AtomicBundlePlan, NormalizedModelResponse, ResponsePipelineOutcome
from ..runtime.action_policy_models import AtomicBundlePolicyResultKind
from ..parsers.visible_text import sanitize_visible_text_for_user, terminal_plaintext_completion_status
from .bundle_semantic_validator import BundleResultKind, BundleSemanticValidator
from .protocol_decision_bridge import COMPILER_INVALID_KIND_BY_CODE
from .runtime_protocol_semantics import compact_runtime_protocol_semantics, runtime_semantics_from_compiler_analysis
from .terminal_answer_classifier import TerminalAnswerClassifier
from .terminal_answer_models import TerminalAnswerClassifierInput, TerminalAnswerKind


class ResponsePipelinePrevalidationMixin:
    COMPILER_DRIVEN_INVALID_KINDS = {
        "malformed_incomplete_think",
        "action_inside_think",
        "intent_inside_think",
        "file_content_inside_think",
        "malformed_incomplete_file_content",
        "mixed_visible_text_and_control_protocol",
        "mixed_intent_transition_and_visible_answer",
        "action_payload_array",
        "action_payload_xml_fields",
        "action_payload_tool_code",
        "action_payload_not_object",
        "protocol_tag_in_json_string",
        "multiple_actions",
        "file_content_must_follow_action",
        "conflicting_intent_transitions",
        "intent_complete_with_action_not_allowed",
    }

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

    def _merge_normalization_metadata(self, parsed_output, normalized: NormalizedModelResponse) -> None:
        if parsed_output is None or normalized is None:
            return
        if bool(getattr(normalized, "think_repair_applied", False)):
            parsed_output.auto_closed_think = True
            parsed_output.auto_closed_think_reason = str(getattr(normalized, "think_repair_reason", "") or "")
            parsed_output.auto_closed_think_tag = str(getattr(normalized, "think_repair_tag", "") or "")

    def _compiler_invalid_kind(self, compiler_analysis) -> str:
        error = getattr(compiler_analysis, "error", None)
        if error is None:
            return ""
        code = str(getattr(error, "code", "") or "").strip()
        if code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION":
            actual = str(getattr(error, "actual", "") or "").strip().lower()
            if actual == "array":
                return "action_payload_array"
            return "multiple_actions"
        return COMPILER_INVALID_KIND_BY_CODE.get(code, "")

    def _apply_compiler_diagnosis(self, parsed_output, response: str):
        compiler_analysis = self.protocol_compiler.analyze(response)
        parsed_output.compiler_shape = compiler_analysis.shape.name
        parsed_output.compiler_error_code = str(getattr(compiler_analysis.error, "code", "") or "")
        parsed_output.compiler_recovery_id = str(getattr(compiler_analysis.error, "recovery_id", "") or "")
        parsed_output.compiler_ir = getattr(compiler_analysis, "ir", None)
        compiler_invalid_kind = self._compiler_invalid_kind(compiler_analysis)
        parsed_output.runtime_protocol_semantics = runtime_semantics_from_compiler_analysis(
            compiler_analysis,
            invalid_kind=compiler_invalid_kind,
        )
        stage_logger = getattr(self, "stage_logger", None)
        if stage_logger and parsed_output.runtime_protocol_semantics:
            stage_logger.log(
                "runtime_protocol_semantics",
                "snapshot",
                **compact_runtime_protocol_semantics(parsed_output.runtime_protocol_semantics),
            )
        self._run_terminal_answer_classifier_shadow(parsed_output, response)
        if compiler_invalid_kind:
            legacy_invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
            has_plain_think_prefix = False
            checker = getattr(self.intent_response_parser, "has_plain_think_prefix", None)
            if callable(checker):
                try:
                    has_plain_think_prefix = bool(checker(response))
                except Exception:
                    has_plain_think_prefix = False
            if not has_plain_think_prefix:
                try:
                    has_plain_think_prefix = bool(self.semantics.has_plain_think_prefix(response))
                except Exception:
                    has_plain_think_prefix = False
            if (
                compiler_invalid_kind == "mixed_visible_text_and_control_protocol"
                and has_plain_think_prefix
                and not legacy_invalid_kind
            ):
                return compiler_analysis
            if not legacy_invalid_kind or legacy_invalid_kind in self.COMPILER_DRIVEN_INVALID_KINDS:
                parsed_output.invalid_kind = compiler_invalid_kind
        return compiler_analysis

    def _run_terminal_answer_classifier_shadow(self, parsed_output, response: str):
        """
        Runs the TerminalAnswerClassifier in shadow mode for diagnostics.

        This method is behavior-preserving:
        - It is called after the main compiler diagnosis is complete.
        - Its result is logged for analysis but NOT used for any production
          decision (e.g., invalid_kind, dispatch, policy).
        - All exceptions from the classifier or logging are caught and logged
          as a secondary error, ensuring the shadow path cannot break the
          production pipeline.
        - The `legacy_kind` and `is_match` fields are populated to enable
          parity analysis.
        """
        if not hasattr(self, "stage_logger") or not self.stage_logger:
            return

        runtime_semantics = getattr(parsed_output, "runtime_protocol_semantics", None)
        if not runtime_semantics:
            return

        try:
            # Lazy-init the classifier to avoid overhead if not used.
            if not hasattr(self, "_shadow_terminal_answer_classifier"):
                self._shadow_terminal_answer_classifier = TerminalAnswerClassifier()

            is_internal_summary = False
            checker = getattr(self, "_is_internal_summary_instead_of_final_answer", None)
            if callable(checker):
                try:
                    is_internal_summary = bool(checker(parsed_output))
                except Exception:
                    is_internal_summary = False

            classifier_input = TerminalAnswerClassifierInput(
                runtime_semantics=runtime_semantics,
                raw_response_text=response,
                is_internal_summary=is_internal_summary,
            )
            result = self._shadow_terminal_answer_classifier.classify(classifier_input)
            parsed_output.terminal_answer_semantic_result = result

            legacy_kind, _ = self._get_legacy_terminal_answer_kind(response, parsed_output)
            is_match = None
            if legacy_kind is not None:
                is_match = result.kind.value == legacy_kind

            self.stage_logger.log(
                "terminal_answer_classifier_shadow",
                "snapshot",
                classifier_kind=result.kind.value,
                classifier_source=result.source,
                classifier_reason_code=result.reason_code,
                classifier_evidence=list(result.evidence),
                classifier_visible_text_present=bool(result.visible_text),
                legacy_kind=legacy_kind,
                is_match=is_match,
            )
        except Exception as e:
            try:
                self.stage_logger.log(
                    "terminal_answer_classifier_shadow",
                    "error",
                    error_class=type(e).__name__,
                    error_message=str(e),
                )
            except Exception:
                # If the error logger itself fails, swallow the exception
                # to ensure the shadow path never affects production.
                pass

    def _get_legacy_terminal_answer_kind(self, response: str, parsed_output) -> tuple[str | None, str | None]:
        """
        Computes a legacy classification for diagnostic comparison.

        This is a diagnostic-only helper for the shadow classifier path. It may
        be inefficient as it re-parses the response to safely call legacy
        helpers without changing their production signatures.
        """
        # This is a diagnostic-only helper. It may be inefficient.

        # Priority 1: Leaked system result
        if hasattr(self.semantics, "looks_like_leaked_system_result"):
            if self.semantics.looks_like_leaked_system_result(response):
                return TerminalAnswerKind.LEAKED_SYSTEM_RESULT.value, "looks_like_leaked_system_result"

        # Priority 2: Truncated/invalid completion
        valid, reason, _ = terminal_plaintext_completion_status(response)
        if not valid:
            return (
                TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT.value,
                f"terminal_plaintext_completion_status:{reason}",
            )

        # Priority 3: Internal summary (best effort)
        checker = getattr(self, "_is_internal_summary_instead_of_final_answer", None)
        if callable(checker):
            try:
                if checker(parsed_output):
                    return TerminalAnswerKind.INTERNAL_SUMMARY_LIKE_TEXT.value, "legacy_internal_summary_helper"
            except Exception:
                pass

        # Priority 4: Plaintext answer path
        if hasattr(self.semantics, "is_plaintext_answer_path"):
            try:
                # Re-parsing is inefficient but safe for a shadow path.
                segments = self.parser.parse(response)
                parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
                if self.semantics.is_plaintext_answer_path(response, parsed_output, parsed_action_count):
                    return TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER.value, "is_plaintext_answer_path"
            except Exception:
                pass

        return None, None

    def _has_any_action_proposal(self, parsed_output, *, parsed_action_count: int = 0) -> bool:
        try:
            return bool(self.semantics.has_any_action_proposal(parsed_output, parsed_action_count))
        except Exception:
            return bool(getattr(parsed_output, "has_action_segment", False)) or int(parsed_action_count or 0) > 0

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

    def _reject_truncated_terminal_completion_before_transition(self, raw_response: str, step, *, parsed_output=None):
        payload = getattr(step, "intent_payload", None)
        if not isinstance(payload, dict):
            return None
        payload_mode = str(payload.get("mode") or "").strip().lower()
        if payload_mode != "complete":
            return None

        typed_result = getattr(parsed_output, "terminal_answer_semantic_result", None)
        is_typed_invalid_or_truncated = (
            typed_result is not None
            and getattr(typed_result, "kind", None) == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
        )
        # Step 4M.2 keeps the typed result as a primary hint only. The actual
        # rejection decision remains gated by the legacy helper on raw_response
        # because classifier and legacy semantics are not exact equivalents yet.
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
        self._merge_normalization_metadata(parsed_output, normalized)
        self._apply_compiler_diagnosis(parsed_output, response)
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

    async def _reject_invalid_intent_followup_before_transition(self, ctx, raw_response: str, step, *, preclassified=None):
        if getattr(step, "intent_payload", None) is None:
            return None

        response = str(raw_response or "").strip()
        if not response:
            return None

        if preclassified is None:
            segments, parsed_output = self._classify_response_for_prevalidation(
                response,
                allow_think_autorepair=False,
            )
        else:
            segments, parsed_output = preclassified
        parsed_output.model_stop_reason = str(getattr(step, "model_stop_reason", "") or "").strip()

        payload = getattr(step, "intent_payload", None)
        parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        has_any_action = self._has_any_action_proposal(parsed_output, parsed_action_count=parsed_action_count)
        payload_mode = str((payload or {}).get("mode") or "").strip().lower() if isinstance(payload, dict) else ""
        if (
            payload_mode in {"activate", "reuse", "replace"}
            and str(getattr(parsed_output, "visible_text", "") or "").strip()
            and not has_any_action
            and not str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        ):
            parsed_output.invalid_kind = "mixed_intent_transition_and_visible_answer"
        intent_only_transition_required_now = bool(
            payload_mode in {"activate", "reuse", "replace"}
            and str(getattr(parsed_output, "invalid_kind", "") or "").strip() in {"missing_action_or_answer", "intent_only_without_next_step"}
            and not has_any_action
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
            and not has_any_action
            and not str(getattr(parsed_output, "visible_text", "") or "").strip()
        ):
            return None

        compiler_bundle_rejection = self._reject_compiler_invalid_atomic_bundle_before_transition(
            ctx,
            payload,
            parsed_output,
            response=response,
        )
        if compiler_bundle_rejection is not None:
            return compiler_bundle_rejection

        if not str(getattr(parsed_output, "invalid_kind", "") or "").strip():
            bundle_rejection = self._reject_invalid_atomic_bundle_before_transition(
                ctx,
                payload,
                parsed_output,
                segments,
                response=response,
            )
            if bundle_rejection is not None:
                return bundle_rejection
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
                parsed_action_count=parsed_action_count,
                malformed_action_retries=recovery_decision.malformed_action_retries,
                audit_marker_retries=recovery_decision.audit_marker_retries,
                reason=recovery_decision.reason,
                source=recovery_decision.source,
            )

        return None

    def _reject_compiler_invalid_atomic_bundle_before_transition(self, ctx, payload: dict, parsed_output, *, response: str):
        payload_mode = str((payload or {}).get("mode") or "").strip().lower()
        if payload_mode not in {"activate", "reuse", "replace"}:
            return None

        compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
        if compiler_code not in {"E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION", "E_FILE_CONTENT_REQUIRES_ACTION"}:
            return None

        validator = BundleSemanticValidator()
        validation_result = validator.validate(parsed_output)

        if validation_result.kind not in {
            BundleResultKind.INVALID_ACTION_ARRAY,
            BundleResultKind.INVALID_MULTIPLE_ACTIONS,
            BundleResultKind.INVALID_FILE_CONTENT_PAIRING,
        }:
            return None

        if validation_result.kind == BundleResultKind.INVALID_FILE_CONTENT_PAIRING and compiler_code != "E_FILE_CONTENT_REQUIRES_ACTION":
            return None

        previewer = getattr(self.intent_transitions, "preview_payload_decision", None)
        if not callable(previewer):
            return None

        preview = previewer(payload)
        plan = self._atomic_bundle_plan_from_preview(payload, preview)
        if not bool(getattr(preview, "applied", False)):
            underlying_reason = str(getattr(preview, "message", "") or "invalid_intent_transition")
            plan.bundle_reason = underlying_reason
            plan.invalid_part = "intent"
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="atomic_bundle_intent_invalid",
                source="intent_atomic_bundle_guard",
                invalid_part=plan.invalid_part,
                bundle_reason=underlying_reason,
                compiler_code=compiler_code,
                bundle_validated=plan.bundle_validated,
                transition_applied=plan.transition_applied,
                action_dispatched=plan.action_dispatched,
                active_intent_unchanged=plan.active_intent_unchanged,
                before_active_intent_id=plan.before_active_intent_id,
                after_active_intent_id=plan.after_active_intent_id,
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_atomic_bundle_rejected_prompt(
                    invalid_part="intent",
                    reason=underlying_reason,
                    goal=str((payload or {}).get("goal") or ""),
                ),
                response_text=response,
                reason="atomic_bundle_intent_invalid",
                source="intent_atomic_bundle_guard",
                atomic_bundle_plan=plan,
            )

        invalid_part = "file_content" if compiler_code == "E_FILE_CONTENT_REQUIRES_ACTION" else "action"
        reason_text = self._compiler_atomic_bundle_reason_text(parsed_output, invalid_part=invalid_part)

        blocked_action = ""
        proposed_intent = getattr(preview, "active_intent", None)
        if proposed_intent is not None:
            blocked_action = str(getattr(proposed_intent, "intent_type", "") or "")

        plan.invalid_part = invalid_part
        legacy_invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        plan.bundle_reason = legacy_invalid_kind or compiler_code
        plan.blocked_action = blocked_action
        self.stage_logger.log(
            "response_pipeline",
            "continue",
            reason=f"atomic_bundle_{invalid_part}_invalid",
            source="intent_atomic_bundle_guard",
            invalid_part=plan.invalid_part,
            bundle_reason=plan.bundle_reason,
            compiler_code=compiler_code,
            bundle_validated=plan.bundle_validated,
            transition_applied=plan.transition_applied,
            action_dispatched=plan.action_dispatched,
            active_intent_unchanged=plan.active_intent_unchanged,
            before_active_intent_id=plan.before_active_intent_id,
            after_active_intent_id=plan.after_active_intent_id,
        )
        return ResponsePipelineOutcome.continue_with(
            self.prompt_builder.build_atomic_bundle_rejected_prompt(
                invalid_part=invalid_part,
                reason=reason_text,
                blocked_action=blocked_action,
                proposed_allowed_actions=list(getattr(proposed_intent, "allowed_actions", []) or []),
                goal=str((payload or {}).get("goal") or ""),
            ),
            response_text=response,
            reason=f"atomic_bundle_{invalid_part}_invalid",
            source="intent_atomic_bundle_guard",
            atomic_bundle_plan=plan,
        )

    def _compiler_atomic_bundle_reason_text(self, parsed_output, *, invalid_part: str) -> str:
        legacy_invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
        if invalid_part == "file_content":
            return "write_file_block requires a complete <file_content>...</file_content> block immediately after </action>."
        if legacy_invalid_kind == "action_payload_array":
            return "Atomic intent/action bundle requires exactly one <action> block with one JSON object. Do not return an action array."
        if legacy_invalid_kind == "multiple_actions":
            return "Atomic intent/action bundle requires exactly one <action> block. Do not return multiple <action> blocks."
        if compiler_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION":
            return "Atomic intent/action bundle requires exactly one <action> block."
        return "Atomic intent/action bundle is invalid."

    def _reject_invalid_atomic_bundle_before_transition(self, ctx, payload: dict, parsed_output, segments, *, response: str):
        payload_mode = str((payload or {}).get("mode") or "").strip().lower()
        if payload_mode not in {"activate", "reuse", "replace"}:
            return None
        parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        if not self._has_any_action_proposal(parsed_output, parsed_action_count=parsed_action_count):
            return None
        previewer = getattr(self.intent_transitions, "preview_payload_decision", None)
        validator = getattr(self.action_policy, "validate_atomic_bundle_action", None)
        if not callable(previewer) or not callable(validator):
            return None

        preview = previewer(payload)
        plan = self._atomic_bundle_plan_from_preview(payload, preview)
        if not bool(getattr(preview, "applied", False)):
            underlying_reason = str(getattr(preview, "message", "") or "invalid_intent_transition")
            plan.bundle_reason = underlying_reason
            plan.invalid_part = "intent"
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="atomic_bundle_intent_invalid",
                source="intent_atomic_bundle_guard",
                invalid_part=plan.invalid_part,
                bundle_reason=plan.bundle_reason,
                bundle_validated=plan.bundle_validated,
                transition_applied=plan.transition_applied,
                action_dispatched=plan.action_dispatched,
                active_intent_unchanged=plan.active_intent_unchanged,
                before_active_intent_id=plan.before_active_intent_id,
                after_active_intent_id=plan.after_active_intent_id,
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_atomic_bundle_rejected_prompt(
                    invalid_part="intent",
                    reason=underlying_reason,
                    goal=str((payload or {}).get("goal") or ""),
                ),
                response_text=response,
                reason="atomic_bundle_intent_invalid",
                source="intent_atomic_bundle_guard",
                atomic_bundle_plan=plan,
            )

        action_validation = validator(
            ctx,
            segments,
            proposed_active_intent=getattr(preview, "active_intent", None),
        )
        if bool(getattr(action_validation, "ok", False)):
            success_plan = self._atomic_bundle_success_plan(payload, preview, action_validation)
            self.stage_logger.log(
                "response_pipeline",
                "pass",
                reason="atomic_bundle_validated",
                source="intent_atomic_bundle_guard",
                bundle_validated=success_plan.bundle_validated,
                invalid_part=success_plan.invalid_part or "",
                bundle_reason=success_plan.bundle_reason,
                transition_applied=success_plan.transition_applied,
                action_dispatched=success_plan.action_dispatched,
                active_intent_unchanged=success_plan.active_intent_unchanged,
                before_active_intent_id=success_plan.before_active_intent_id,
                after_active_intent_id=success_plan.after_active_intent_id,
            )
            return None

        underlying_reason = str(getattr(action_validation, "reason", "") or "invalid_action")
        details = dict(getattr(action_validation, "details", {}) or {})
        invalid_part = (
            "file_content"
            if (
                getattr(action_validation, "kind", None) == AtomicBundlePolicyResultKind.REJECTED_MISSING_FILE_CONTENT
                or underlying_reason == "missing_file_content_block"
            )
            else "action"
        )
        plan.invalid_part = invalid_part
        plan.bundle_reason = underlying_reason
        plan.blocked_action = str(details.get("blocked_action") or "")
        self.stage_logger.log(
            "response_pipeline",
            "continue",
            reason=f"atomic_bundle_{invalid_part}_invalid",
            source="intent_atomic_bundle_guard",
            invalid_part=plan.invalid_part,
            bundle_reason=plan.bundle_reason,
            blocked_action=plan.blocked_action,
            bundle_validated=plan.bundle_validated,
            transition_applied=plan.transition_applied,
            action_dispatched=plan.action_dispatched,
            active_intent_unchanged=plan.active_intent_unchanged,
            before_active_intent_id=plan.before_active_intent_id,
            after_active_intent_id=plan.after_active_intent_id,
        )
        return ResponsePipelineOutcome.continue_with(
            self.prompt_builder.build_atomic_bundle_rejected_prompt(
                invalid_part=invalid_part,
                reason=str(details.get("message") or underlying_reason),
                blocked_action=str(details.get("blocked_action") or ""),
                proposed_allowed_actions=list(details.get("allowed_actions") or []),
                goal=str((payload or {}).get("goal") or ""),
            ),
            response_text=response,
            reason=f"atomic_bundle_{invalid_part}_invalid",
            source="intent_atomic_bundle_guard",
            atomic_bundle_plan=plan,
        )

    def _atomic_bundle_plan_from_preview(self, payload: dict, preview) -> AtomicBundlePlan:
        current_active = getattr(self.state, "active_intent", None)
        current_intent_id = str(getattr(current_active, "intent_id", "") or "").strip()
        transition_info = dict(getattr(preview, "transition_info", {}) or {})
        proposed_active = getattr(preview, "active_intent", None)
        after_intent_id = str(
            transition_info.get("after_active_intent_id")
            or getattr(proposed_active, "intent_id", "")
            or current_intent_id
        ).strip()
        before_intent_id = str(
            transition_info.get("before_active_intent_id")
            or current_intent_id
        ).strip()
        return AtomicBundlePlan(
            bundle_validated=False,
            invalid_part=None,
            bundle_reason="",
            transition_applied=False,
            active_intent_unchanged=(after_intent_id == before_intent_id),
            action_dispatched=False,
            before_active_intent_id=before_intent_id,
            after_active_intent_id=before_intent_id,
            proposed_intent_id=str((payload or {}).get("intent_id") or after_intent_id).strip(),
            blocked_action="",
        )

    def _atomic_bundle_success_plan(self, payload: dict, preview, action_validation) -> AtomicBundlePlan:
        _ = action_validation
        current_active = getattr(self.state, "active_intent", None)
        current_intent_id = str(getattr(current_active, "intent_id", "") or "").strip()
        transition_info = dict(getattr(preview, "transition_info", {}) or {})
        proposed_active = getattr(preview, "active_intent", None)
        after_intent_id = str(
            transition_info.get("after_active_intent_id")
            or getattr(proposed_active, "intent_id", "")
            or current_intent_id
        ).strip()
        before_intent_id = str(
            transition_info.get("before_active_intent_id")
            or current_intent_id
        ).strip()
        return AtomicBundlePlan(
            bundle_validated=True,
            invalid_part=None,
            bundle_reason="validated",
            transition_applied=True,
            active_intent_unchanged=(after_intent_id == before_intent_id),
            action_dispatched=True,
            before_active_intent_id=before_intent_id,
            after_active_intent_id=after_intent_id,
            proposed_intent_id=str((payload or {}).get("intent_id") or after_intent_id).strip(),
            blocked_action="",
        )

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
