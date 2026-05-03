"""Typed decision models for the orchestration pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...allowed_actions_resolver import ResolvedAllowedActions


@dataclass
class ParsedModelOutput:
    response: str
    segments: list[Any] = field(default_factory=list)
    has_action_tag: bool = False
    has_action_segment: bool = False
    has_intent_segment: bool = False
    visible_text: str = ""
    invalid_kind: str = ""
    model_stop_reason: str = ""
    auto_closed_think: bool = False
    auto_closed_think_reason: str = ""
    auto_closed_think_tag: str = ""
    operational_checkpoint_satisfied: bool = False
    operational_checkpoint_has_think: bool = False
    operational_checkpoint_has_marker: bool = False
    operational_checkpoint_has_board_commit: bool = False
    operational_checkpoint_has_tags: bool = False
    compiler_shape: str = ""
    compiler_error_code: str = ""
    compiler_recovery_id: str = ""


@dataclass
class NormalizedModelResponse:
    raw_response: str
    normalized_response: str
    repairs_applied: tuple[str, ...] = ()
    repair_blocked_reason: str = ""
    think_repair_applied: bool = False
    think_repair_reason: str = ""
    think_repair_confidence: str = ""
    think_repair_tag: str = ""
    think_repair_insert_at: int = -1
    think_repair_blocked_by_atomicity: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelStepResult:
    response: str
    intent_payload: dict | None
    intent_error: str | None
    model_stop_reason: str = ""


@dataclass
class OrchestrationTraceEntry:
    sequence: int
    stage: str
    decision: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopControlDecision:
    handled: bool = True
    continue_loop: bool = False
    next_query: str | None = None
    stop_loop: bool = False
    clear_pending_stop: bool = False
    reason: str = ""
    source: str = ""

    @classmethod
    def continue_with(
        cls,
        next_query: str | None,
        *,
        reason: str = "",
        source: str = "",
        clear_pending_stop: bool = False,
    ):
        return cls(
            handled=True,
            continue_loop=True,
            next_query=next_query,
            stop_loop=False,
            clear_pending_stop=clear_pending_stop,
            reason=reason,
            source=source,
        )

    @classmethod
    def stop(
        cls,
        *,
        reason: str = "",
        source: str = "",
        clear_pending_stop: bool = False,
    ):
        return cls(
            handled=True,
            continue_loop=False,
            next_query=None,
            stop_loop=True,
            clear_pending_stop=clear_pending_stop,
            reason=reason,
            source=source,
        )

    @classmethod
    def pass_through(cls, *, reason: str = "", source: str = ""):
        return cls(
            handled=False,
            continue_loop=False,
            next_query=None,
            stop_loop=False,
            clear_pending_stop=False,
            reason=reason,
            source=source,
        )


@dataclass
class RecoveryDecision(LoopControlDecision):
    next_query: str | None = None


@dataclass
class PreDispatchDecision:
    handled: bool = True
    continue_loop: bool = False
    next_query: str | None = None
    reason: str = ""
    source: str = ""

    @classmethod
    def continue_with(
        cls,
        next_query: str | None,
        *,
        reason: str = "",
        source: str = "",
        **extra,
    ):
        return cls(
            handled=True,
            continue_loop=True,
            next_query=next_query,
            reason=reason,
            source=source,
            **extra,
        )

    @classmethod
    def pass_through(cls, *, reason: str = "", source: str = "", **extra):
        return cls(
            handled=False,
            continue_loop=False,
            next_query=None,
            reason=reason,
            source=source,
            **extra,
        )


@dataclass
class OutputRecoveryDecision(PreDispatchDecision):
    next_query: str | None = None
    continue_loop: bool = False
    stop_loop: bool = False
    malformed_action_retries: int | None = None
    audit_marker_retries: int | None = None


@dataclass
class ActionPolicyDecision(PreDispatchDecision):
    next_query: str | None = None
    continue_loop: bool = False
    parsed_action_count: int = 0


@dataclass
class LoopGateDecision:
    proceed: bool
    reason: str = ""
    source: str = ""


@dataclass
class MemoryBoardDecision(PreDispatchDecision):
    response_text: str = ""
    next_query: str | None = None
    continue_loop: bool = False
    memory_checkpoint_only: bool = False
    memory_checkpoint_and_text: bool = False
    memory_checkpoint_and_action: bool = False


@dataclass
class PlanBoardDecision(PreDispatchDecision):
    response_text: str = ""
    next_query: str | None = None
    continue_loop: bool = False
    plan_checkpoint_only: bool = False
    plan_checkpoint_and_text: bool = False
    plan_checkpoint_and_action: bool = False


@dataclass
class PipelineIterationDecision:
    continue_loop: bool
    proceed_to_dispatch: bool = False
    stop_loop: bool = False
    next_query: str | None = None
    segments: list[Any] = field(default_factory=list)
    parsed_output: ParsedModelOutput | None = None
    parsed_action_count: int = 0
    malformed_action_retries: int | None = None
    audit_marker_retries: int | None = None
    reason: str = ""
    source: str = ""

    @classmethod
    def continue_with(
        cls,
        next_query: str | None,
        *,
        malformed_action_retries: int | None = None,
        audit_marker_retries: int | None = None,
        reason: str = "",
        source: str = "",
    ):
        return cls(
            continue_loop=True,
            proceed_to_dispatch=False,
            stop_loop=False,
            next_query=next_query,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            reason=reason,
            source=source,
        )

    @classmethod
    def dispatch_ready(
        cls,
        *,
        segments: list[Any],
        parsed_output: ParsedModelOutput | None,
        parsed_action_count: int,
        malformed_action_retries: int | None = None,
        audit_marker_retries: int | None = None,
        reason: str = "",
        source: str = "",
    ):
        return cls(
            continue_loop=False,
            proceed_to_dispatch=True,
            stop_loop=False,
            segments=segments,
            parsed_output=parsed_output,
            parsed_action_count=parsed_action_count,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            reason=reason,
            source=source,
        )

    @classmethod
    def stop(
        cls,
        *,
        reason: str = "",
        source: str = "",
    ):
        return cls(
            continue_loop=False,
            proceed_to_dispatch=False,
            stop_loop=True,
            reason=reason,
            source=source,
        )


@dataclass
class ResponsePipelineOutcome(PreDispatchDecision):
    continue_loop: bool
    next_query: str | None = None
    stop_loop: bool = False
    response_text: str = ""
    segments: list[Any] = field(default_factory=list)
    parsed_output: ParsedModelOutput | None = None
    parsed_action_count: int = 0
    malformed_action_retries: int | None = None
    audit_marker_retries: int | None = None
    memory_checkpoint_only: bool = False
    memory_checkpoint_and_text: bool = False
    memory_checkpoint_and_action: bool = False

    @classmethod
    def stop(
        cls,
        *,
        response_text: str = "",
        reason: str = "",
        source: str = "",
        malformed_action_retries: int | None = None,
        audit_marker_retries: int | None = None,
        memory_checkpoint_only: bool = False,
        memory_checkpoint_and_text: bool = False,
        memory_checkpoint_and_action: bool = False,
    ):
        return cls(
            handled=True,
            continue_loop=False,
            next_query=None,
            stop_loop=True,
            response_text=response_text,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            memory_checkpoint_only=memory_checkpoint_only,
            memory_checkpoint_and_text=memory_checkpoint_and_text,
            memory_checkpoint_and_action=memory_checkpoint_and_action,
            reason=reason,
            source=source,
        )

    @classmethod
    def dispatch_ready(
        cls,
        *,
        response_text: str = "",
        segments: list[Any],
        parsed_output: ParsedModelOutput | None,
        parsed_action_count: int,
        malformed_action_retries: int | None = None,
        audit_marker_retries: int | None = None,
        reason: str = "",
        source: str = "",
        memory_checkpoint_and_text: bool = False,
        memory_checkpoint_and_action: bool = False,
    ):
        return cls(
            handled=True,
            continue_loop=False,
            next_query=None,
            stop_loop=False,
            response_text=response_text,
            segments=segments,
            parsed_output=parsed_output,
            parsed_action_count=parsed_action_count,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            memory_checkpoint_and_text=memory_checkpoint_and_text,
            memory_checkpoint_and_action=memory_checkpoint_and_action,
            reason=reason,
            source=source,
        )


@dataclass
class DispatchHandlingDecision(LoopControlDecision):
    pass


@dataclass
class IntentDecision:
    applied: bool
    message: str = ""
    warning: str = ""
    active_intent: Any = None
    transition_info: dict[str, Any] = field(default_factory=dict)
    rejection_stop_info: dict[str, Any] | None = None
    completion_requested: bool = False


@dataclass
class IntentHandlingDecision(LoopControlDecision):
    pass


@dataclass
class RecoveryContext:
    reason: str = ""
    recoverable: bool = False
    error_code: str = ""
    message_key: str = ""
    message: str = ""
    next_actions: list[str] = field(default_factory=list)
    next_actions_source: str = ""
    intent_allowed_actions: list[str] = field(default_factory=list)
    recommended_next_actions: list[str] = field(default_factory=list)
    policy_allowed_actions: list[str] = field(default_factory=list)
    policy_recommended_actions: list[str] = field(default_factory=list)
    policy_blocked_actions: list[str] = field(default_factory=list)
    policy_intent_actions: list[str] = field(default_factory=list)
    policy_authoritative_source: str = ""
    policy_keep_current_intent: bool = False
    policy_metadata: dict[str, Any] = field(default_factory=dict)
    error_details: dict[str, Any] = field(default_factory=dict)
    failed_tool: str = ""
    failed_error_code: str = ""
    failed_error_message_short: str = ""
    safe_recovery_action: str = ""
    full_rewrite_allowed: bool | None = None
    recovery_protocol: str = ""
    suspicion: dict[str, Any] = field(default_factory=dict)
    command: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_stop_info(cls, stop_info: dict[str, Any] | None) -> "RecoveryContext":
        data = stop_info or {}
        return cls(
            reason=str(data.get("reason") or ""),
            recoverable=bool(data.get("recoverable", False)),
            error_code=str(data.get("error_code") or ""),
            message_key=str(data.get("message_key") or ""),
            message=str(data.get("message") or ""),
            next_actions=list(data.get("next_actions") or []),
            next_actions_source=str(data.get("next_actions_source") or ""),
            intent_allowed_actions=list(data.get("intent_allowed_actions") or []),
            recommended_next_actions=list(data.get("recommended_next_actions") or []),
            policy_allowed_actions=list(data.get("policy_allowed_actions") or []),
            policy_recommended_actions=list(data.get("policy_recommended_actions") or []),
            policy_blocked_actions=list(data.get("policy_blocked_actions") or []),
            policy_intent_actions=list(data.get("policy_intent_actions") or []),
            policy_authoritative_source=str(data.get("policy_authoritative_source") or ""),
            policy_keep_current_intent=bool(data.get("policy_keep_current_intent", False)),
            policy_metadata=dict(data.get("policy_metadata") or {}),
            error_details=dict(data.get("error_details") or {}),
            failed_tool=str(data.get("failed_tool") or ""),
            failed_error_code=str(data.get("failed_error_code") or ""),
            failed_error_message_short=str(data.get("failed_error_message_short") or ""),
            safe_recovery_action=str(data.get("safe_recovery_action") or ""),
            full_rewrite_allowed=data.get("full_rewrite_allowed"),
            recovery_protocol=str(data.get("recovery_protocol") or ""),
            suspicion=dict(data.get("suspicion") or {}),
            command=dict(data.get("command") or {}),
            raw=dict(data),
        )

    def to_stop_info(self) -> dict[str, Any]:
        merged = dict(self.raw)
        merged.update(
            {
                "reason": self.reason,
                "recoverable": self.recoverable,
                "error_code": self.error_code,
                "message_key": self.message_key,
                "message": self.message,
                "next_actions": list(self.next_actions),
                "next_actions_source": self.next_actions_source,
                "intent_allowed_actions": list(self.intent_allowed_actions),
                "recommended_next_actions": list(self.recommended_next_actions),
                "policy_allowed_actions": list(self.policy_allowed_actions),
                "policy_recommended_actions": list(self.policy_recommended_actions),
                "policy_blocked_actions": list(self.policy_blocked_actions),
                "policy_intent_actions": list(self.policy_intent_actions),
                "policy_authoritative_source": self.policy_authoritative_source,
                "policy_keep_current_intent": self.policy_keep_current_intent,
                "policy_metadata": dict(self.policy_metadata),
                "error_details": dict(self.error_details),
                "failed_tool": self.failed_tool,
                "failed_error_code": self.failed_error_code,
                "failed_error_message_short": self.failed_error_message_short,
                "safe_recovery_action": self.safe_recovery_action,
                "full_rewrite_allowed": self.full_rewrite_allowed,
                "recovery_protocol": self.recovery_protocol,
                "suspicion": dict(self.suspicion),
                "command": dict(self.command),
            }
        )
        return merged

    def resolved_action_policy(self) -> ResolvedAllowedActions | None:
        if not (
            self.policy_allowed_actions
            or self.policy_recommended_actions
            or self.policy_blocked_actions
            or self.policy_intent_actions
            or self.policy_authoritative_source
            or self.policy_keep_current_intent
        ):
            return None
        return ResolvedAllowedActions(
            allowed_actions=list(self.policy_allowed_actions),
            recommended_actions=list(self.policy_recommended_actions),
            blocked_actions=list(self.policy_blocked_actions),
            authoritative_source=self.policy_authoritative_source,
            intent_actions=list(self.policy_intent_actions),
            recovery_actions=list(self.next_actions),
            keep_current_intent=self.policy_keep_current_intent,
        )
