"""Passive action-vector semantic surface characterization.

Phase 60 Step 2.

These tests intentionally do not migrate any runtime consumer. They document
how action-vector facts can disagree across compiler/RPS, compiler IR,
legacy parser evidence, and compatibility accessors.

Important invariant:
RuntimeProtocolSemantics.has_action/action_count and compiler_ir.action_ops are
not dispatch-authoritative. has_any_action_proposal_compat is recovery/guardrail
evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from modules.agent.orchestration.responses.runtime_protocol_semantics import RuntimeProtocolSemantics
from modules.agent.orchestration.responses.semantic_accessors import has_any_action_proposal_compat
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


@dataclass(frozen=True)
class _ActionOp:
    kind: str = "action"
    payload: dict | None = None


@dataclass(frozen=True)
class _CompilerIR:
    action_ops: tuple[_ActionOp, ...] = ()


def _rps(
    *,
    shape: str,
    is_valid: bool,
    has_action: bool,
    action_count: int,
    action_ops: tuple[_ActionOp, ...] = (),
    error_code: str = "",
    recovery_id: str = "",
    invalid_kind: str = "",
) -> RuntimeProtocolSemantics:
    return RuntimeProtocolSemantics(
        source="test",
        shape=shape,
        is_valid=is_valid,
        error_code=error_code,
        recovery_id=recovery_id,
        invalid_kind=invalid_kind,
        action_count=action_count,
        has_action=has_action,
        action_ops=action_ops,
        intent_ops=(),
        visible_text="",
        has_visible_answer=False,
        pre_action_text="",
        has_pre_action_text=False,
        visible_text_source="",
        has_memory_tags=False,
        has_subgoal_tags=False,
        has_memory_checkpoint=False,
        memory_ops=(),
        subgoal_ops=(),
        has_file_content=False,
        file_content="",
        effects_preview=(),
    )


def _parsed(
    *,
    response: str,
    compiler_shape: str,
    rps: RuntimeProtocolSemantics,
    compiler_ir: _CompilerIR | None = None,
    has_action_segment: bool = False,
    invalid_kind: str = "",
) -> ParsedModelOutput:
    return ParsedModelOutput(
        response=response,
        compiler_shape=compiler_shape,
        runtime_protocol_semantics=rps,
        compiler_ir=compiler_ir,
        has_action_segment=has_action_segment,
        invalid_kind=invalid_kind,
    )


def _surface(parsed: ParsedModelOutput, *, parsed_action_count: int) -> dict:
    rps = parsed.runtime_protocol_semantics
    compiler_ir = parsed.compiler_ir

    return {
        "compiler_shape": parsed.compiler_shape,
        "rps_shape": rps.shape,
        "rps_is_valid": rps.is_valid,
        "rps_has_action": rps.has_action,
        "rps_action_count": rps.action_count,
        "rps_action_ops_count": len(tuple(rps.action_ops or ())),
        "compiler_ir_action_ops_count": len(tuple(getattr(compiler_ir, "action_ops", ()) or ())),
        "parsed_action_count": parsed_action_count,
        "has_action_segment": parsed.has_action_segment,
        "has_any_action_proposal_compat": has_any_action_proposal_compat(
            parsed,
            parsed_action_count=parsed_action_count,
        ),
        # Test-only explicit invariant. There is no production field named this;
        # the matrix documents that compatibility evidence is not dispatch authority.
        "dispatch_permission_implied": False,
    }


def test_valid_action_only_surface_all_action_evidence_agrees():
    op = _ActionOp(payload={"type": "read_file", "path": "README.md"})
    parsed = _parsed(
        response='<action>{"type":"read_file","path":"README.md"}</action>',
        compiler_shape="ACTION_ONLY",
        rps=_rps(
            shape="ACTION_ONLY",
            is_valid=True,
            has_action=True,
            action_count=1,
            action_ops=(op,),
        ),
        compiler_ir=_CompilerIR(action_ops=(op,)),
        has_action_segment=True,
    )

    surface = _surface(parsed, parsed_action_count=1)

    assert surface == {
        "compiler_shape": "ACTION_ONLY",
        "rps_shape": "ACTION_ONLY",
        "rps_is_valid": True,
        "rps_has_action": True,
        "rps_action_count": 1,
        "rps_action_ops_count": 1,
        "compiler_ir_action_ops_count": 1,
        "parsed_action_count": 1,
        "has_action_segment": True,
        "has_any_action_proposal_compat": True,
        "dispatch_permission_implied": False,
    }


def test_readonly_batch_candidate_surface_is_action_proposal_not_dispatch_permission():
    ops = (
        _ActionOp(payload={"type": "read_file", "path": "a.py"}),
        _ActionOp(payload={"type": "read_chunk", "path": "b.py", "start": 1, "end": 40}),
        _ActionOp(payload={"type": "search_content", "path": ".", "pattern": "needle"}),
    )
    parsed = _parsed(
        response=(
            "<action>["
            '{"type":"read_file","path":"a.py"},'
            '{"type":"read_chunk","path":"b.py","start":1,"end":40},'
            '{"type":"search_content","path":".","pattern":"needle"}'
            "]</action>"
        ),
        compiler_shape="READ_ONLY_BATCH_CANDIDATE",
        rps=_rps(
            shape="READ_ONLY_BATCH_CANDIDATE",
            is_valid=True,
            has_action=True,
            action_count=3,
            action_ops=ops,
        ),
        compiler_ir=_CompilerIR(action_ops=ops),
        has_action_segment=True,
    )

    surface = _surface(parsed, parsed_action_count=3)

    assert surface["compiler_shape"] == "READ_ONLY_BATCH_CANDIDATE"
    assert surface["rps_has_action"] is True
    assert surface["rps_action_count"] == 3
    assert surface["rps_action_ops_count"] == 3
    assert surface["compiler_ir_action_ops_count"] == 3
    assert surface["parsed_action_count"] == 3
    assert surface["has_action_segment"] is True
    assert surface["has_any_action_proposal_compat"] is True

    # Characterization invariant: action proposal evidence is not permission to
    # dispatch. Dispatch remains owned by the runtime dispatch/action-policy path.
    assert surface["dispatch_permission_implied"] is False


def test_compiler_invalid_with_legacy_action_segment_keeps_compat_proposal_true():
    parsed = _parsed(
        response='<action>{"type":"read_file","path":"README.md"</action>',
        compiler_shape="INVALID",
        rps=_rps(
            shape="INVALID",
            is_valid=False,
            error_code="E_MALFORMED_ACTION_JSON",
            recovery_id="malformed_action",
            invalid_kind="malformed_action",
            has_action=False,
            action_count=0,
            action_ops=(),
        ),
        compiler_ir=_CompilerIR(action_ops=()),
        has_action_segment=True,
        invalid_kind="malformed_action",
    )

    surface = _surface(parsed, parsed_action_count=1)

    assert surface["compiler_shape"] == "INVALID"
    assert surface["rps_is_valid"] is False
    assert surface["rps_has_action"] is False
    assert surface["rps_action_count"] == 0
    assert surface["rps_action_ops_count"] == 0
    assert surface["compiler_ir_action_ops_count"] == 0

    # Expected disagreement:
    # compiler/RPS says no valid action vector, but legacy/parser evidence still
    # sees action-like material. The compatibility shim must preserve that signal
    # for recovery/guardrail evidence only.
    assert surface["parsed_action_count"] == 1
    assert surface["has_action_segment"] is True
    assert surface["has_any_action_proposal_compat"] is True
    assert surface["dispatch_permission_implied"] is False


def test_pure_plaintext_surface_has_no_action_evidence():
    parsed = _parsed(
        response="Done. No tool needed.",
        compiler_shape="PURE_PLAINTEXT",
        rps=_rps(
            shape="PURE_PLAINTEXT",
            is_valid=True,
            has_action=False,
            action_count=0,
            action_ops=(),
        ),
        compiler_ir=_CompilerIR(action_ops=()),
        has_action_segment=False,
    )

    surface = _surface(parsed, parsed_action_count=0)

    assert surface["compiler_shape"] == "PURE_PLAINTEXT"
    assert surface["rps_has_action"] is False
    assert surface["rps_action_count"] == 0
    assert surface["rps_action_ops_count"] == 0
    assert surface["compiler_ir_action_ops_count"] == 0
    assert surface["parsed_action_count"] == 0
    assert surface["has_action_segment"] is False
    assert surface["has_any_action_proposal_compat"] is False
    assert surface["dispatch_permission_implied"] is False


def test_fenced_protocol_like_text_is_invalid_without_executable_dispatch_authority():
    parsed = _parsed(
        response='```xml\n<action>{"type":"read_file","path":"README.md"}</action>\n```',
        compiler_shape="INVALID",
        rps=_rps(
            shape="INVALID",
            is_valid=False,
            error_code="E_FENCED_PROTOCOL_BLOCK",
            recovery_id="fenced_protocol_block",
            invalid_kind="fenced_protocol_block",
            has_action=False,
            action_count=0,
            action_ops=(),
        ),
        compiler_ir=_CompilerIR(action_ops=()),
        has_action_segment=False,
        invalid_kind="fenced_protocol_block",
    )

    surface = _surface(parsed, parsed_action_count=0)

    assert "<action>" in parsed.response
    assert surface["compiler_shape"] == "INVALID"
    assert surface["rps_is_valid"] is False
    assert surface["rps_has_action"] is False
    assert surface["rps_action_count"] == 0
    assert surface["compiler_ir_action_ops_count"] == 0

    # Current characterization: protocol-looking text inside a markdown fence is
    # not executable action evidence for dispatch. It should be recovered as
    # invalid protocol, not treated as an action permission.
    assert surface["parsed_action_count"] == 0
    assert surface["has_action_segment"] is False
    assert surface["has_any_action_proposal_compat"] is False
    assert surface["dispatch_permission_implied"] is False


def test_xml_tool_shorthand_like_text_is_invalid_without_executable_dispatch_authority():
    parsed = _parsed(
        response='<run_shell command="which gradle" timeout="10" />',
        compiler_shape="INVALID",
        rps=_rps(
            shape="INVALID",
            is_valid=False,
            error_code="E_XML_TOOL_SHORTHAND",
            recovery_id="xml_tool_shorthand",
            invalid_kind="xml_tool_shorthand",
            has_action=False,
            action_count=0,
            action_ops=(),
        ),
        compiler_ir=_CompilerIR(action_ops=()),
        has_action_segment=False,
        invalid_kind="xml_tool_shorthand",
    )

    surface = _surface(parsed, parsed_action_count=0)

    assert "<run_shell" in parsed.response
    assert surface["compiler_shape"] == "INVALID"
    assert surface["rps_is_valid"] is False
    assert surface["rps_has_action"] is False
    assert surface["rps_action_count"] == 0
    assert surface["compiler_ir_action_ops_count"] == 0

    # XML shorthand is action-like text, but not canonical executable protocol.
    assert surface["parsed_action_count"] == 0
    assert surface["has_action_segment"] is False
    assert surface["has_any_action_proposal_compat"] is False
    assert surface["dispatch_permission_implied"] is False
