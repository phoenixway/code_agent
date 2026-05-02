"""Intent transition apply/finalization helpers."""

from __future__ import annotations

from .decision_models import IntentDecision
from .visible_text import sanitize_visible_text_for_user


class IntentTransitionApplyMixin:
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
