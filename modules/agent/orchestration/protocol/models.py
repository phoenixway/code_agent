"""Core models for the protocol compiler pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    excerpt: str


@dataclass(frozen=True)
class EnumSpec:
    values: tuple[str, ...]


@dataclass(frozen=True)
class PayloadSpec:
    type: str


@dataclass(frozen=True)
class BlockSpec:
    name: str
    kind: Literal["closed", "self_closing"]
    attrs: dict[str, EnumSpec] = field(default_factory=dict)
    payload: PayloadSpec | None = None
    structural_only: bool = True
    allowed_contexts: tuple[str, ...] = ("root",)


@dataclass(frozen=True)
class ConstraintSpec:
    id: str
    phase: Literal["lex", "parse", "shape", "lowering", "semantic", "transaction"]
    applies_to: str
    error_code: str


@dataclass(frozen=True)
class ShapeSpec:
    name: str
    sequence: tuple[str, ...]
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    phase: Literal["lex", "parse", "shape", "lowering", "semantic", "transaction"]
    recovery_id: str
    default_message: str


@dataclass(frozen=True)
class ProtocolSpec:
    version: str
    blocks: dict[str, BlockSpec]
    shapes: dict[str, ShapeSpec]
    constraints: tuple[ConstraintSpec, ...]
    errors: dict[str, ErrorSpec]


class ResponseShape(str, Enum):
    PLAINTEXT_ONLY = "plaintext_only"
    MEMORY_TEXT = "memory_text"
    ACTION_ONLY = "action_only"
    READ_ONLY_BATCH_CANDIDATE = "read_only_batch_candidate"
    INTENT_ONLY = "intent_only"
    INTENT_ACTION_BUNDLE = "intent_action_bundle"
    INTENT_COMPLETE_WITH_TEXT = "intent_complete_with_text"
    INVALID = "invalid"


@dataclass(frozen=True)
class ErrorValue:
    code: str
    phase: Literal["lex", "parse", "shape", "lowering", "semantic", "transaction"]
    severity: Literal["recoverable", "fatal"]
    message: str
    span: Span | None = None
    offending_node_kind: str | None = None
    expected: tuple[str, ...] = ()
    actual: str | None = None
    invalid_part: str | None = None
    transaction_applied: bool = False
    action_dispatched: bool = False
    recovery_id: str | None = None
    repeat_fingerprint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProtocolToken:
    span: Span


@dataclass(frozen=True)
class StartTagToken(ProtocolToken):
    name: str
    attrs: dict[str, str]


@dataclass(frozen=True)
class EndTagToken(ProtocolToken):
    name: str


@dataclass(frozen=True)
class SelfClosingTagToken(ProtocolToken):
    name: str
    attrs: dict[str, str]


@dataclass(frozen=True)
class TextToken(ProtocolToken):
    text: str


@dataclass(frozen=True)
class InlineCodeToken(ProtocolToken):
    text: str


@dataclass(frozen=True)
class FencedCodeToken(ProtocolToken):
    text: str
    lang: str | None = None


@dataclass(frozen=True)
class Node:
    span: Span


@dataclass(frozen=True)
class ResponseAst:
    raw: str
    nodes: tuple[Node, ...]


@dataclass(frozen=True)
class ThinkNode(Node):
    content: str


@dataclass(frozen=True)
class MemoryNode(Node):
    tag: str
    attrs: dict[str, str]
    content: str | None


@dataclass(frozen=True)
class SubgoalNode(Node):
    attrs: dict[str, str]
    content: str | None


@dataclass(frozen=True)
class MarkerNode(Node):
    pass


@dataclass(frozen=True)
class IntentNode(Node):
    attrs: dict[str, str]
    raw_payload: str
    json_payload: dict[str, Any] | None
    json_error: str | None


@dataclass(frozen=True)
class ActionNode(Node):
    attrs: dict[str, str]
    raw_payload: str
    json_payload: Any | None
    json_error: str | None


@dataclass(frozen=True)
class FileContentNode(Node):
    content: str


@dataclass(frozen=True)
class VisibleTextNode(Node):
    text: str


@dataclass(frozen=True)
class LiteralProtocolTagNode(Node):
    text: str
    context: str


@dataclass(frozen=True)
class AnnotationIR:
    kind: str
    text: str


@dataclass(frozen=True)
class BoardOpIR:
    kind: str
    attrs: dict[str, str]
    content: str | None


@dataclass(frozen=True)
class IntentOpIR:
    mode: str
    payload: dict[str, Any]
    intent_id: str
    intent_type: str
    goal: str


@dataclass(frozen=True)
class ActionOpIR:
    action_type: str
    payload: dict[str, Any] | list[Any] | None
    file_content: str | None
    read_only: bool
    write_like: bool


@dataclass(frozen=True)
class EffectPreview:
    kind: str
    summary: str
    target: str | None = None


@dataclass(frozen=True)
class ResponseIR:
    shape: ResponseShape
    annotations: tuple[AnnotationIR, ...]
    board_ops: tuple[BoardOpIR, ...]
    intent_ops: tuple[IntentOpIR, ...]
    action_ops: tuple[ActionOpIR, ...]
    effects_preview: tuple[EffectPreview, ...]

    # Derived semantic fields
    has_think: bool = False
    think_text: str = ""
    has_visible_answer: bool = False
    visible_text: str = ""
    has_action: bool = False
    action_count: int = 0
    has_checkpoint: bool = False
    has_memory_checkpoint: bool = False
    has_plan_checkpoint: bool = False
    has_file_content: bool = False
    file_content_count: int = 0
    file_content_text: str = ""

    @property
    def visible_answer(self) -> str:
        """Compatibility property for legacy visible_answer."""
        return self.visible_text

    @property
    def file_content(self) -> str:
        """Compatibility property for legacy file_content."""
        return self.file_content_text


@dataclass(frozen=True)
class CompilerAnalysis:
    tokens: tuple[ProtocolToken, ...]
    ast: ResponseAst | None
    shape: ResponseShape
    error: ErrorValue | None
    ir: ResponseIR | None = None
