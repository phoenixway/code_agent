"""AST -> IR lowering for protocol compiler analysis."""

from __future__ import annotations

from .models import (
    ActionNode,
    ActionOpIR,
    AnnotationIR,
    BoardOpIR,
    EffectPreview,
    ErrorValue,
    FileContentNode,
    IntentNode,
    IntentOpIR,
    LiteralProtocolTagNode,
    MarkerNode,
    MemoryNode,
    ResponseAst,
    ResponseIR,
    ResponseShape,
    SubgoalNode,
    ThinkNode,
    VisibleTextNode,
)
from .spec import PROTOCOL_SPEC


READ_ONLY_ACTION_TYPES = {
    "read_file",
    "read_chunk",
    "read_file_skeleton",
    "extract_kotlin_function",
    "extract_symbol",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
}

WRITE_LIKE_ACTION_TYPES = {
    "edit_file",
    "create_file",
    "write_file",
    "write_file_block",
    "append_file_block",
}


class ProtocolLowerer:
    def __init__(self, spec=PROTOCOL_SPEC):
        self.spec = spec

    def lower(self, ast: ResponseAst, shape: ResponseShape) -> tuple[ResponseIR | None, ErrorValue | None]:
        if shape == ResponseShape.INVALID:
            return None, None

        think_nodes = [node for node in ast.nodes if isinstance(node, ThinkNode)]
        memory_nodes = [node for node in ast.nodes if isinstance(node, MemoryNode)]
        subgoal_nodes = [node for node in ast.nodes if isinstance(node, SubgoalNode)]
        marker_nodes = [node for node in ast.nodes if isinstance(node, MarkerNode)]
        intent_nodes = [node for node in ast.nodes if isinstance(node, IntentNode)]
        action_nodes = [node for node in ast.nodes if isinstance(node, ActionNode)]
        file_nodes = [node for node in ast.nodes if isinstance(node, FileContentNode)]

        # Compute raw semantic values
        think_text = "\n".join(node.content for node in think_nodes if node.content)
        visible_text = self._merge_visible_text(ast) or ""
        file_content_text = file_nodes[0].content if file_nodes else ""

        # Lower to primary IR ops
        annotations = tuple(AnnotationIR(kind="think", text=node.content) for node in think_nodes)
        board_ops = tuple(self._lower_board_nodes(memory_nodes, subgoal_nodes, marker_nodes))
        intent_ops = tuple(self._lower_intent_node(node) for node in intent_nodes if isinstance(node.json_payload, dict))
        action_ops = tuple(self._lower_action_node(node, file_content_text or None) for node in action_nodes)
        effects_preview = tuple(self._preview_effects(intent_ops, action_ops, visible_text or None, file_content_text or None))

        # Compute derived semantic flags
        has_think = bool(think_text.strip())
        has_visible_answer = bool(visible_text.strip())
        has_action = len(action_ops) > 0
        action_count = len(action_ops)
        has_memory_checkpoint = len(memory_nodes) > 0 or len(marker_nodes) > 0
        has_plan_checkpoint = len(subgoal_nodes) > 0
        has_checkpoint = has_memory_checkpoint or has_plan_checkpoint
        has_file_content = len(file_nodes) > 0
        file_content_count = len(file_nodes)

        return ResponseIR(
            shape=shape,
            annotations=annotations,
            board_ops=board_ops,
            intent_ops=intent_ops,
            action_ops=action_ops,
            effects_preview=effects_preview,
            has_think=has_think,
            think_text=think_text,
            has_visible_answer=has_visible_answer,
            visible_text=visible_text,
            has_action=has_action,
            action_count=action_count,
            has_checkpoint=has_checkpoint,
            has_memory_checkpoint=has_memory_checkpoint,
            has_plan_checkpoint=has_plan_checkpoint,
            has_file_content=has_file_content,
            file_content_count=file_content_count,
            file_content_text=file_content_text,
        ), None

    def _lower_board_nodes(self, memory_nodes, subgoal_nodes, marker_nodes):
        for node in memory_nodes:
            yield BoardOpIR(kind=node.tag, attrs=dict(node.attrs), content=node.content)
        for node in subgoal_nodes:
            yield BoardOpIR(kind="subgoal", attrs=dict(node.attrs), content=node.content)
        for _node in marker_nodes:
            yield BoardOpIR(kind="memory_update_done", attrs={}, content=None)

    def _lower_intent_node(self, node: IntentNode) -> IntentOpIR:
        payload = dict(node.json_payload or {})
        return IntentOpIR(
            mode=str(node.attrs.get("mode") or payload.get("mode") or "").strip().lower(),
            payload=payload,
            intent_id=str(payload.get("intent_id") or "").strip(),
            intent_type=str(payload.get("intent_type") or "").strip(),
            goal=str(payload.get("goal") or "").strip(),
        )

    def _lower_action_node(self, node: ActionNode, file_content: str | None) -> ActionOpIR:
        payload = node.json_payload if isinstance(node.json_payload, (dict, list)) else None
        action_type = ""
        if isinstance(payload, dict):
            action_type = str(payload.get("type") or payload.get("action") or "").strip().lower()
        return ActionOpIR(
            action_type=action_type,
            payload=payload,
            file_content=file_content,
            read_only=action_type in READ_ONLY_ACTION_TYPES,
            write_like=action_type in WRITE_LIKE_ACTION_TYPES,
        )

    def _merge_visible_text(self, ast: ResponseAst) -> str | None:
        spans: list[tuple[int, int]] = []
        for node in ast.nodes:
            if isinstance(node, (VisibleTextNode, LiteralProtocolTagNode)):
                spans.append((node.span.start, node.span.end))
        if not spans:
            return None
        parts = [ast.raw[start:end] for start, end in spans]
        merged = "".join(parts).strip()
        return merged or None

    def _preview_effects(
        self,
        intent_ops: tuple[IntentOpIR, ...],
        action_ops: tuple[ActionOpIR, ...],
        visible_answer: str | None,
        file_content: str | None,
    ):
        for op in intent_ops:
            yield EffectPreview(
                kind="intent_proposal",
                summary=f"{op.mode or 'intent'}:{op.intent_type or '?'}:{op.intent_id or '?'}",
                target=op.intent_id or None,
            )
        for op in action_ops:
            target = None
            if isinstance(op.payload, dict):
                target = str(op.payload.get("path") or op.payload.get("command") or "").strip() or None
            summary = op.action_type or "action"
            if op.write_like and file_content is not None:
                summary = f"{summary}:with_file_content"
            yield EffectPreview(kind="action_proposal", summary=summary, target=target)
        if visible_answer:
            yield EffectPreview(kind="final_answer", summary="visible_answer")
