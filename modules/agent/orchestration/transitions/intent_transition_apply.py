"""Intent transition apply/finalization helpers."""

from __future__ import annotations

from copy import deepcopy

from ..shared.decision_models import IntentDecision
from ..parsers.visible_text import sanitize_visible_text_for_user


class IntentTransitionApplyMixin:
    def _preview_payload_decision_via_compat_apply(self, payload: dict) -> IntentDecision:
        if not hasattr(self.state, "apply_intent_contract"):
            return IntentDecision(
                applied=False,
                message="intent_runtime_unavailable",
                warning="",
                active_intent=getattr(self.state, "active_intent", None),
                transition_info={"transition": "rejected", "transition_applied": False, "reason": "intent_runtime_unavailable"},
                rejection_stop_info={"reason": "intent_runtime_unavailable", "recoverable": True, "next_actions": []},
                completion_requested=False,
            )

        snapshot = {
            "active_intent": deepcopy(getattr(self.state, "active_intent", None)),
            "intent_required_until_activated": deepcopy(getattr(self.state, "intent_required_until_activated", False)),
            "intent_required_reason": deepcopy(getattr(self.state, "intent_required_reason", "")),
            "intent_runtime": deepcopy(getattr(self.state, "intent_runtime", None)),
            "last_defect_info": deepcopy(getattr(self.state, "last_defect_info", None)),
            "apply_called": deepcopy(getattr(self.state, "apply_called", None)),
        }
        ok = False
        message = "intent_runtime_unavailable"
        transition_info = {"transition": "rejected", "transition_applied": False, "reason": message}
        active_after = snapshot["active_intent"]
        try:
            ok, message = self.state.apply_intent_contract(payload, self.config)
            active_after = deepcopy(getattr(self.state, "active_intent", None))
            runtime = getattr(self.state, "intent_runtime", None)
            transition_info = deepcopy(getattr(runtime, "last_transition_info", {}) or transition_info)
        finally:
            try:
                self.state.active_intent = snapshot["active_intent"]
            except Exception:
                pass
            for field in ("intent_required_until_activated", "intent_required_reason", "intent_runtime", "last_defect_info"):
                try:
                    setattr(self.state, field, snapshot[field])
                except Exception:
                    pass
            if snapshot["apply_called"] is not None:
                try:
                    setattr(self.state, "apply_called", snapshot["apply_called"])
                except Exception:
                    pass

        if ok:
            return IntentDecision(
                applied=True,
                message=str(message or ""),
                warning="",
                active_intent=active_after,
                transition_info=transition_info if isinstance(transition_info, dict) else {},
                rejection_stop_info=None,
                completion_requested=(str(message or "") == "intent_completed"),
            )
        return IntentDecision(
            applied=False,
            message=str(message or "invalid_intent_transition"),
            warning="",
            active_intent=snapshot["active_intent"],
            transition_info=transition_info if isinstance(transition_info, dict) else {},
            rejection_stop_info={"reason": str(message or "invalid_intent_transition"), "recoverable": True, "next_actions": []},
            completion_requested=False,
        )

    def _inherit_memory_to_successor(self, intent_decision: IntentDecision) -> None:
        transition_info = dict(intent_decision.transition_info or {})
        if transition_info.get("transition") != "intent_replaced":
            return
        if not bool(transition_info.get("same_lineage")):
            return
        from_intent_id = str(transition_info.get("before_active_intent_id") or "").strip()
        to_intent_id = str(transition_info.get("after_active_intent_id") or "").strip()
        lineage_id = str(transition_info.get("lineage_id") or "").strip()
        if not from_intent_id or not to_intent_id or from_intent_id == to_intent_id:
            return
        memory_board_store = getattr(self.agent, "memory_board_store", None)
        inheritor = getattr(memory_board_store, "inherit_intent_scope", None)
        if not callable(inheritor):
            return
        try:
            copied = int(inheritor(
                from_intent_id=from_intent_id,
                to_intent_id=to_intent_id,
                lineage_id=lineage_id,
                source="intent_transition",
            ) or 0)
            transition_info["inherited_memory_entries"] = copied
            intent_decision.transition_info = transition_info
        except Exception:
            pass

    def _finalize_completed_intent(self) -> None:
        runtime = getattr(self.state, "intent_runtime", None)
        finalized = False

        for method_name in ("finalize_current_intent_completion", "close_current_intent", "clear_current_intent"):
            method = getattr(runtime, method_name, None) if runtime is not None else None
            if callable(method):
                try:
                    method()
                    finalized = True
                    break
                except Exception:
                    pass

        if not finalized:
            for method_name in ("complete_current_intent", "clear_active_intent"):
                method = getattr(self.state, method_name, None)
                if callable(method):
                    try:
                        method()
                        finalized = True
                        break
                    except Exception:
                        pass

        if not finalized:
            try:
                self.state.active_intent = None
            except Exception:
                pass

        if hasattr(self.state, "pending_loop_stop_info"):
            self.state.pending_loop_stop_info = None

    def _mark_terminal_plaintext_completion(self, response_text: str) -> None:
        text, leak_detected = sanitize_visible_text_for_user(response_text)
        text = "" if leak_detected else str(text or "").strip()
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", bool(text))
            setattr(self.state, "terminal_plaintext_completion_text", text)
            if hasattr(self.state, "readonly_steps_this_turn"):
                self.state.readonly_steps_this_turn = 0
        except Exception:
            pass

    def apply_payload_decision(self, payload: dict) -> IntentDecision:
        active_before = getattr(self.state, "active_intent", None)
        ok, intent_msg = self.state.apply_intent_contract(payload, self.config)
        runtime = getattr(self.state, "intent_runtime", None)
        warning = getattr(runtime, "last_apply_warning", "") if runtime is not None else ""
        transition_info = getattr(runtime, "last_transition_info", {}) if runtime is not None else {}
        active_intent = getattr(self.state, "active_intent", None)
        if isinstance(transition_info, dict):
            transition_applied = bool(ok)
            after_intent = active_intent if transition_applied else active_before
            transition_info = {
                **transition_info,
                "transition": (
                    str(transition_info.get("transition") or "").strip()
                    if transition_applied
                    else "rejected"
                ),
                "transition_applied": transition_applied,
                "before_active_intent_id": getattr(active_before, "intent_id", ""),
                "before_active_intent_type": getattr(active_before, "intent_type", ""),
                "after_active_intent_id": getattr(after_intent, "intent_id", ""),
                "after_active_intent_type": getattr(after_intent, "intent_type", ""),
            }
            if transition_info.get("transition") == "intent_completed":
                self.state.last_completed_intent_type = str(
                    transition_info.get("before_active_intent_type", "") or ""
                ).strip().upper()
            if transition_info.get("transition") == "intent_reused_with_step_refresh" and hasattr(self.state, "pending_loop_stop_info"):
                self.state.pending_loop_stop_info = None

        rejection_stop_info = None
        if not ok:
            rejection_stop_info = getattr(self.state, "last_defect_info", None) or {
                "reason": intent_msg,
                "recoverable": True,
                "next_actions": getattr(active_intent, "allowed_actions", None) or [],
            }
            if isinstance(transition_info, dict) and transition_info.get("transition") == "policy_rejected":
                rejection_stop_info = {
                    **rejection_stop_info,
                    "reason": transition_info.get("reason", intent_msg),
                    "recoverable": True,
                    "error_code": transition_info.get("error_code", ""),
                    "message_key": transition_info.get("message_key", ""),
                    "policy_metadata": transition_info.get("metadata", {}) or {},
                }

        return IntentDecision(
            applied=ok,
            message=intent_msg,
            warning=warning,
            active_intent=active_intent,
            transition_info=transition_info if isinstance(transition_info, dict) else {},
            rejection_stop_info=rejection_stop_info,
            completion_requested=(intent_msg == "intent_completed"),
        )

    def _preview_active_intent_after_transition(self, contract, info: dict | None):
        if contract is None:
            return None
        info = dict(info or {})
        active = getattr(self.state, "active_intent", None)
        same_lineage = bool(info.get("same_lineage"))

        if contract.mode == "complete":
            return None

        if contract.mode == "reuse":
            grant = max(1, int(contract.user_step_extension or getattr(self.config, "INTENT_REUSE_EXTENSION_STEPS", 4)))
            if active is None:
                preview = deepcopy(contract)
                preview.user_step_extension = grant
                preview.hard_limit_hit_count = 0
                preview.force_plaintext_completion = False
                return preview
            preview = deepcopy(active)
            preview.user_step_extension += grant
            preview.hard_limit_hit_count = 0
            preview.force_plaintext_completion = False
            preview.intent_type = contract.intent_type or preview.intent_type
            preview.switch_reason = contract.switch_reason
            preview.switch_explanation = contract.switch_explanation
            preview.user_visible_note = contract.user_visible_note or preview.user_visible_note
            preview.allowed_actions = contract.allowed_actions[:] or preview.allowed_actions[:]
            preview.original_allowed_actions = (
                contract.original_allowed_actions[:]
                if contract.original_allowed_actions
                else (preview.original_allowed_actions[:] if preview.original_allowed_actions else preview.allowed_actions[:])
            )
            return preview

        preview = deepcopy(contract)
        if active is not None and same_lineage:
            preview.lineage_id = active.lineage_id or active.intent_id
            preview.retry_count = min(active.retry_count, preview.retry_limit)
            preview.hard_limit_hit_count = active.hard_limit_hit_count
            preview.canonical_goal = active.canonical_goal or active.goal
            preview.goal_frozen = True
            preview.goal = active.goal
            preview.user_step_extension = active.user_step_extension
            preview.user_one_shot_steps_remaining = active.user_one_shot_steps_remaining
            preview.user_unlimited_override = active.user_unlimited_override
            preview.force_plaintext_completion = active.force_plaintext_completion
            preview.action_constraints = self.state.intent_runtime._merge_constraints(  # noqa: SLF001
                active.action_constraints,
                preview.action_constraints,
            )
            preview.blocked_action_signatures = set(active.blocked_action_signatures or set())
            preview.blocked_action_reasons = dict(active.blocked_action_reasons or {})
            if bool(getattr(self.config, "INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH", True)):
                preview.step_count = min(active.step_count, preview.safe_steps_limit + max(0, preview.user_step_extension))
            preview.original_allowed_actions = (
                active.original_allowed_actions[:] if active.original_allowed_actions else preview.original_allowed_actions[:]
            )
        return preview

    def preview_payload_decision(self, payload: dict) -> IntentDecision:
        attach = getattr(self.state, "attach_config", None)
        if callable(attach):
            attach(self.config)
        runtime = getattr(self.state, "intent_runtime", None)
        if runtime is None:
            return IntentDecision(
                applied=False,
                message="intent_runtime_unavailable",
                warning="",
                active_intent=getattr(self.state, "active_intent", None),
                transition_info={"transition": "rejected", "transition_applied": False, "reason": "intent_runtime_unavailable"},
                rejection_stop_info={"reason": "intent_runtime_unavailable", "recoverable": True, "next_actions": []},
                completion_requested=False,
            )

        try:
            runtime.last_apply_warning = ""
            runtime.last_transition_info = {}
        except Exception:
            pass

        if not hasattr(runtime, "inspect_transition"):
            return self._preview_payload_decision_via_compat_apply(payload)

        contract, info, error = runtime.inspect_transition(payload)
        if error:
            return IntentDecision(
                applied=False,
                message=error,
                warning="",
                active_intent=getattr(self.state, "active_intent", None),
                transition_info={"transition": "rejected", "transition_applied": False, "reason": error},
                rejection_stop_info={"reason": error, "recoverable": True, "next_actions": []},
                completion_requested=False,
            )

        policy_ctx = runtime._build_policy_context(contract, info)  # noqa: SLF001
        decision = runtime.policy_engine.evaluate_transition(policy_ctx)
        if not decision.allowed:
            return IntentDecision(
                applied=False,
                message=decision.reason,
                warning="",
                active_intent=getattr(self.state, "active_intent", None),
                transition_info={
                    "transition": "policy_rejected",
                    "transition_applied": False,
                    "reason": decision.reason,
                    "error_code": decision.error_code,
                    "message_key": decision.message_key,
                    "metadata": dict(decision.metadata or {}),
                    "same_lineage": bool((info or {}).get("same_lineage")),
                },
                rejection_stop_info={
                    "reason": decision.reason,
                    "recoverable": True,
                    "error_code": decision.error_code,
                    "message_key": decision.message_key,
                    "policy_metadata": dict(decision.metadata or {}),
                    "next_actions": [],
                },
                completion_requested=False,
            )

        active = getattr(self.state, "active_intent", None)
        same_lineage = bool((info or {}).get("same_lineage"))
        if contract.mode == "reuse":
            if active is None and not runtime._can_reuse_recently_completed_intent():  # noqa: SLF001
                error = "intent_reuse_without_active_intent"
            elif active is not None and contract.intent_id != active.intent_id:
                error = "intent_reuse_wrong_active_id"
            else:
                error = ""
        elif contract.mode == "complete":
            if active is None:
                error = "intent_complete_without_active_intent"
            elif contract.intent_id != active.intent_id:
                error = "intent_complete_wrong_active_id"
            else:
                error = ""
        else:
            error = ""
            if (
                active is not None
                and active.action_constraints.get("forbid_new_intent")
                and same_lineage
                and contract.mode in {"activate", "replace"}
                and contract.intent_id != active.intent_id
                and not runtime._is_legitimate_switch_reason(contract.switch_reason)  # noqa: SLF001
            ):
                error = "intent_new_block_forbidden_for_current_lineage"
            elif active is not None and not runtime._reason_allows_transition(contract, active, same_lineage):  # noqa: SLF001
                error = "intent_transition_trigger_required"

        if error:
            return IntentDecision(
                applied=False,
                message=error,
                warning="",
                active_intent=getattr(self.state, "active_intent", None),
                transition_info={"transition": "rejected", "transition_applied": False, "reason": error},
                rejection_stop_info={"reason": error, "recoverable": True, "next_actions": []},
                completion_requested=False,
            )

        preview_intent = self._preview_active_intent_after_transition(contract, info)
        transition_name = "intent_completed" if contract.mode == "complete" else (
            "intent_reused_with_step_refresh" if contract.mode == "reuse" else (
                "intent_replaced" if active is not None and (contract.mode == "replace" or contract.intent_id != getattr(active, "intent_id", "")) and same_lineage else (
                    "intent_activated" if active is None or contract.intent_id != getattr(active, "intent_id", "") else "intent_refreshed"
                )
            )
        )
        return IntentDecision(
            applied=True,
            message=transition_name,
            warning="",
            active_intent=preview_intent,
            transition_info={
                "transition": transition_name,
                "transition_applied": True,
                "same_lineage": same_lineage,
                "before_active_intent_id": getattr(active, "intent_id", ""),
                "after_active_intent_id": getattr(preview_intent, "intent_id", ""),
            },
            rejection_stop_info=None,
            completion_requested=(contract.mode == "complete"),
        )
