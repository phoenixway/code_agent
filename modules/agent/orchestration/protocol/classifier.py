"""AST-only response shape classifier."""

from __future__ import annotations

import re

from .lowerer import ProtocolLowerer
from .models import (
    ActionNode,
    CompilerAnalysis,
    ErrorValue,
    FileContentNode,
    IntentNode,
    LiteralProtocolTagNode,
    MarkerNode,
    MemoryNode,
    ResponseAst,
    ResponseShape,
    ThinkNode,
    VisibleTextNode,
)
from .parser import ProtocolParser
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


class ProtocolCompiler:
    def __init__(self, spec=PROTOCOL_SPEC):
        self.spec = spec
        self.parser = ProtocolParser(spec)
        self.lowerer = ProtocolLowerer(spec)

    def _mask_code_in_think(self, content: str) -> str:
        # Mask fenced code blocks
        masked = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
        # Mask inline code
        masked = re.sub(r"`[^`]*`", "", masked)
        return masked

    def analyze(self, raw: str) -> CompilerAnalysis:
        ast, error, tokens = self.parser.parse(raw)
        if error is not None:
            return CompilerAnalysis(tokens=tokens, ast=None, shape=ResponseShape.INVALID, error=error)
        assert ast is not None
        shape, shape_error = self._classify(ast)
        if shape_error is not None:
            return CompilerAnalysis(tokens=tokens, ast=ast, shape=shape, error=shape_error)
        ir, lowering_error = self.lowerer.lower(ast, shape)
        return CompilerAnalysis(tokens=tokens, ast=ast, shape=shape, error=lowering_error, ir=ir)

    def _classify(self, ast: ResponseAst) -> tuple[ResponseShape, ErrorValue | None]:
        nodes = list(ast.nodes)
        for node in nodes:
            if isinstance(node, ThinkNode):
                masked_content = self._mask_code_in_think(node.content)
                if "<action" in masked_content:
                    return ResponseShape.INVALID, self._error("E_ACTION_INSIDE_THINK", node.span, invalid_part="action")
                if "<file_content" in masked_content:
                    return ResponseShape.INVALID, self._error("E_FILE_CONTENT_INSIDE_THINK", node.span, invalid_part="file_content")
                if "<intent" in masked_content:
                    return ResponseShape.INVALID, self._error("E_INTENT_INSIDE_THINK", node.span, invalid_part="intent")

        visible_nodes = [node for node in nodes if isinstance(node, VisibleTextNode) and node.text.strip()]
        action_nodes = [node for node in nodes if isinstance(node, ActionNode)]
        intent_nodes = [node for node in nodes if isinstance(node, IntentNode)]
        file_nodes = [node for node in nodes if isinstance(node, FileContentNode)]
        control_nodes = [
            node
            for node in nodes
            if isinstance(node, (ThinkNode, MemoryNode, MarkerNode, ActionNode, IntentNode, FileContentNode, LiteralProtocolTagNode))
        ]

        if file_nodes and not action_nodes:
            return ResponseShape.INVALID, self._error(
                "E_FILE_CONTENT_REQUIRES_ACTION",
                file_nodes[0].span,
                invalid_part="file_content",
            )

        if visible_nodes and len(intent_nodes) == 1 and not action_nodes:
            if self._intent_mode(intent_nodes[0]) == "complete":
                return ResponseShape.INTENT_COMPLETE_WITH_TEXT, None

        first_action_idx = next((i for i, n in enumerate(nodes) if isinstance(n, ActionNode)), -1)
        last_visible_idx = (
            nodes.index(visible_nodes[-1]) if visible_nodes else -1
        )

        if first_action_idx != -1 and last_visible_idx > first_action_idx:
            return ResponseShape.INVALID, self._error(
                "E_VISIBLE_TEXT_AFTER_ACTION",
                nodes[last_visible_idx].span,
                invalid_part="visible_text_after_action",
            )

        if visible_nodes and len(action_nodes) == 1 and not intent_nodes:
            return ResponseShape.PRE_ACTION_TEXT_AND_ACTION, None

        if visible_nodes and (intent_nodes or len(action_nodes) > 1):
            if len(intent_nodes) == 1 and self._intent_mode(intent_nodes[0]) == "complete" and not action_nodes:
                return ResponseShape.INTENT_COMPLETE_WITH_TEXT, None
            return ResponseShape.INVALID, self._error(
                "E_MIXED_VISIBLE_TEXT_AND_CONTROL",
                visible_nodes[0].span,
                invalid_part="mixed_visible",
            )

        if len(intent_nodes) == 1 and len(action_nodes) == 1 and not visible_nodes:
            if isinstance(action_nodes[0].json_payload, list):
                return ResponseShape.INVALID, self._error(
                    "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
                    action_nodes[0].span,
                    actual="array",
                    invalid_part="action",
                )
            if self._needs_file_content(action_nodes[0]) and not file_nodes:
                return ResponseShape.INVALID, self._error(
                    "E_FILE_CONTENT_REQUIRES_ACTION",
                    action_nodes[0].span,
                    invalid_part="file_content",
                )
            return ResponseShape.INTENT_ACTION_BUNDLE, None

        if len(intent_nodes) == 1 and len(action_nodes) > 1:
            return ResponseShape.INVALID, self._error(
                "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
                action_nodes[1].span,
                actual="multiple_blocks",
                invalid_part="action",
            )

        if len(intent_nodes) == 1 and not action_nodes and not visible_nodes:
            return ResponseShape.INTENT_ONLY, None

        if not intent_nodes and len(action_nodes) == 1 and not visible_nodes:
            if isinstance(action_nodes[0].json_payload, list):
                return ResponseShape.INVALID, self._error(
                    "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
                    action_nodes[0].span,
                    actual="array",
                    invalid_part="action",
                )
            return ResponseShape.ACTION_ONLY, None

        if not intent_nodes and len(action_nodes) > 1 and not visible_nodes:
            if all(self._is_read_only_action(node) for node in action_nodes):
                return ResponseShape.READ_ONLY_BATCH_CANDIDATE, None
            return ResponseShape.INVALID, self._error(
                "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
                action_nodes[1].span,
                actual="multiple_blocks",
                invalid_part="action",
            )

        if visible_nodes and not action_nodes and not intent_nodes:
            has_only_board = all(isinstance(node, (VisibleTextNode, ThinkNode, MemoryNode, MarkerNode, LiteralProtocolTagNode)) for node in nodes)
            if has_only_board and any(isinstance(node, (MemoryNode, MarkerNode)) for node in nodes):
                return ResponseShape.MEMORY_TEXT, None
            return ResponseShape.PLAINTEXT_ONLY, None

        if not action_nodes and not intent_nodes and not file_nodes:
            literal_only = all(isinstance(node, (LiteralProtocolTagNode, VisibleTextNode)) for node in nodes)
            if literal_only:
                return ResponseShape.PLAINTEXT_ONLY, None

        return ResponseShape.INVALID, self._error("E_AMBIGUOUS_PROTOCOL_SYNTAX", None)

    def _intent_mode(self, node: IntentNode) -> str:
        return str(node.attrs.get("mode") or (node.json_payload or {}).get("mode") or "").strip().lower()

    def _is_read_only_action(self, node: ActionNode) -> bool:
        if not isinstance(node.json_payload, dict):
            return False
        action_type = str(node.json_payload.get("type") or node.json_payload.get("action") or "").strip().lower()
        return action_type in READ_ONLY_ACTION_TYPES

    def _needs_file_content(self, node: ActionNode) -> bool:
        if not isinstance(node.json_payload, dict):
            return False
        action_type = str(node.json_payload.get("type") or node.json_payload.get("action") or "").strip().lower()
        return action_type in WRITE_LIKE_ACTION_TYPES

    def _error(
        self,
        code: str,
        span,
        *,
        actual: str | None = None,
        invalid_part: str | None = None,
    ) -> ErrorValue:
        spec = self.spec.errors[code]
        return ErrorValue(
            code=code,
            phase=spec.phase,
            severity="recoverable",
            message=spec.default_message,
            span=span,
            actual=actual,
            invalid_part=invalid_part,
            transaction_applied=False,
            action_dispatched=False,
            recovery_id=spec.recovery_id,
        )
