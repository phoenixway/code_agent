from types import SimpleNamespace

from modules.agent.orchestration.protocol.models import ActionNode, ResponseAst, Span
from modules.agent.orchestration.transitions import TransitionFollowupSemantics


def _analysis(*, shape_name: str, nodes: list[object], error_code: str = ""):
    error = None
    if error_code:
        error = SimpleNamespace(code=error_code)
    return SimpleNamespace(
        ast=ResponseAst(nodes=list(nodes), raw=""),
        shape=SimpleNamespace(name=shape_name),
        error=error,
    )


def _action_node():
    return ActionNode(
        span=Span(start=0, end=8, excerpt="<action>"),
        attrs={},
        raw_payload='{"type":"read_file","path":"a.py"}',
        json_payload={"type": "read_file", "path": "a.py"},
        json_error=None,
    )


def test_rejected_transition_semantics_escalates_terminal_repeats():
    semantics = TransitionFollowupSemantics()
    summary = semantics.summarize(None)

    decision = semantics.evaluate_rejected_transition(
        rejection_reason="intent_reuse_without_active_intent",
        defect_count=3,
        has_active_intent=False,
        summary=summary,
    )

    assert decision.kind == "terminal_repeated_intent_transition_defect"


def test_unified_transition_semantics_reports_accepted_followup_conflict():
    semantics = TransitionFollowupSemantics()
    summary = semantics.summarize(
        _analysis(
            shape_name="READ_ONLY_BATCH_CANDIDATE",
            nodes=[_action_node(), _action_node()],
            error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        )
    )

    decision = semantics.evaluate_transition(
        phase="accepted",
        payload_mode="activate",
        completion_requested=False,
        transition_only_required=False,
        reuse_only_required=False,
        summary=summary,
    )

    assert decision.phase == "accepted"
    assert decision.kind == "followup_conflict"
    assert decision.conflict_reason == "multiple_actions"
    assert decision.has_any_action is True


def test_rejected_transition_semantics_marks_second_reuse_as_strict():
    semantics = TransitionFollowupSemantics()
    summary = semantics.summarize(None)

    decision = semantics.evaluate_rejected_transition(
        rejection_reason="intent_reuse_without_active_intent",
        defect_count=2,
        has_active_intent=False,
        summary=summary,
    )

    assert decision.kind == "intent_reuse_without_active_intent"
    assert decision.strict is True


def test_rejected_transition_semantics_ignores_redundant_reactivation_with_single_action_followup():
    semantics = TransitionFollowupSemantics()
    summary = semantics.summarize(_analysis(shape_name="ACTION_ONLY", nodes=[_action_node()]))

    decision = semantics.evaluate_rejected_transition(
        rejection_reason="unnecessary_intent_reactivation_or_replace",
        defect_count=1,
        has_active_intent=True,
        summary=summary,
    )

    assert decision.kind == "ignored_redundant_intent_reactivation_with_followup_action"


def test_unified_transition_semantics_reports_rejected_reuse_without_active_as_strict():
    semantics = TransitionFollowupSemantics()
    summary = semantics.summarize(None)

    decision = semantics.evaluate_transition(
        phase="rejected",
        rejection_reason="intent_reuse_without_active_intent",
        defect_count=2,
        has_active_intent=False,
        summary=summary,
    )

    assert decision.phase == "rejected"
    assert decision.kind == "intent_reuse_without_active_intent"
    assert decision.strict is True
