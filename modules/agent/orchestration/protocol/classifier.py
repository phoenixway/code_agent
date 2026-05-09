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
    SubgoalNode,
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
            # For parse errors, we can't trust the AST. Don't lower.
            return CompilerAnalysis(tokens=tokens, ast=ast, shape=ResponseShape.INVALID, error=error, ir=None)

        assert ast is not None
        shape, shape_error = self._classify(ast)

        ir = None
        lowering_error = None
        # For valid shapes, or for safe invalid shapes, we can lower to get IR.
        # "Safe" invalid shapes are those without action/intent/file_content nodes,
        # which could have dispatch implications if IR were generated.
        if shape_error is None:
            ir, lowering_error = self.lowerer.lower(ast, shape)
        elif self._may_attach_structural_facts_ir(ast, shape_error):
            ir, lowering_error = self.lowerer.lower(ast, shape)

        final_error = shape_error or lowering_error
        return CompilerAnalysis(tokens=tokens, ast=ast, shape=shape, error=final_error, ir=ir)

    def _may_attach_structural_facts_ir(self, ast: ResponseAst, error: ErrorValue) -> bool:
        """
        Returns True if an AST contains only nodes that are safe for structural fact lowering,
        even if the shape is technically invalid.
        """
        # Never lower if the error itself is about a dangerous tag inside think.
        if error and error.code in (
            "E_ACTION_INSIDE_THINK",
            "E_INTENT_INSIDE_THINK",
            "E_FILE_CONTENT_INSIDE_THINK",
        ):
            return False

        if not ast or not ast.nodes:
            return True

        # Check for top-level dangerous nodes.
        return not any(isinstance(node, (ActionNode, IntentNode, FileContentNode)) for node in ast.nodes)

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

        if len(intent_nodes) > 1:
            return ResponseShape.INVALID, self._error(
                "E_MULTIPLE_INTENTS",
                intent_nodes[1].span,
                invalid_part="intent",
            )

        if len(intent_nodes) == 1 and self._intent_mode(intent_nodes[0]) == "complete" and action_nodes:
            return ResponseShape.INVALID, self._error(
                "E_INTENT_COMPLETE_WITH_ACTION",
                intent_nodes[0].span,
                invalid_part="intent",
            )

        if visible_nodes and len(intent_nodes) == 1 and not action_nodes:
            if self._intent_mode(intent_nodes[0]) == "complete":
                return ResponseShape.INTENT_COMPLETE_WITH_TEXT, None

        if visible_nodes and len(action_nodes) == 1 and not intent_nodes:
            first_action_idx = next((i for i, n in enumerate(nodes) if isinstance(n, ActionNode)), -1)
            last_visible_idx = nodes.index(visible_nodes[-1]) if visible_nodes else -1
            if first_action_idx > last_visible_idx:
                return ResponseShape.PRE_ACTION_TEXT_AND_ACTION, None

        if file_nodes:
            if not action_nodes:
                return ResponseShape.INVALID, self._error(
                    "E_FILE_CONTENT_REQUIRES_ACTION",
                    file_nodes[0].span,
                    invalid_part="file_content_missing_action",
                )

            first_file_idx = next((i for i, n in enumerate(nodes) if isinstance(n, FileContentNode)), -1)
            first_action_idx = next((i for i, n in enumerate(nodes) if isinstance(n, ActionNode)), -1)

            if first_file_idx < first_action_idx:
                return ResponseShape.INVALID, self._error(
                    "E_FILE_CONTENT_REQUIRES_ACTION",
                    file_nodes[0].span,
                    invalid_part="file_content_order",
                )

            if len(action_nodes) > 1:
                return ResponseShape.INVALID, self._error(
                    "E_FILE_CONTENT_ACTION_MISMATCH",
                    file_nodes[0].span,
                    invalid_part="file_content_multiple_actions",
                )

            if not self._needs_file_content(action_nodes[0]):
                return ResponseShape.INVALID, self._error(
                    "E_FILE_CONTENT_ACTION_MISMATCH",
                    action_nodes[0].span,
                    invalid_part="file_content_action_mismatch",
                )

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

        first_intent_idx = next((i for i, n in enumerate(nodes) if isinstance(n, IntentNode)), -1)
        if first_intent_idx != -1 and last_visible_idx > first_intent_idx:
            intent_node = nodes[first_intent_idx]
            if self._intent_mode(intent_node) != "complete":
                return ResponseShape.INVALID, self._error(
                    "E_VISIBLE_TEXT_AFTER_INTENT",
                    nodes[last_visible_idx].span,
                    invalid_part="visible_text_after_intent",
                )

        if visible_nodes and (intent_nodes or len(action_nodes) > 1):
            if len(intent_nodes) == 1 and self._intent_mode(intent_nodes[0]) == "complete" and not action_nodes:
                return ResponseShape.INTENT_COMPLETE_WITH_TEXT, None
            return ResponseShape.INVALID, self._error(
                "E_MIXED_VISIBLE_TEXT_AND_CONTROL",
                visible_nodes[0].span,
                invalid_part="mixed_visible",
            )

        if len(intent_nodes) == 1 and len(action_nodes) == 1 and not visible_nodes:
            first_intent_idx = nodes.index(intent_nodes[0])
            first_action_idx = nodes.index(action_nodes[0])
            if first_intent_idx > first_action_idx:
                return ResponseShape.INVALID, self._error(
                    "E_AMBIGUOUS_PROTOCOL_SYNTAX",
                    action_nodes[0].span,
                    invalid_part="action_before_intent_in_bundle",
                )
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
            has_only_board_and_text = all(
                isinstance(node, (VisibleTextNode, ThinkNode, MemoryNode, SubgoalNode, MarkerNode, LiteralProtocolTagNode)) for node in nodes
            )
            if has_only_board_and_text:
                if any(isinstance(node, SubgoalNode) for node in nodes):
                    return ResponseShape.SUBGOAL_WITH_TEXT, None
                if any(isinstance(node, (MemoryNode, MarkerNode)) for node in nodes):
                    return ResponseShape.MEMORY_TEXT, None
            return ResponseShape.PURE_PLAINTEXT, None

        if not action_nodes and not intent_nodes and not file_nodes and not visible_nodes:
            has_only_checkpoint_protocol = all(
                isinstance(node, (ThinkNode, MemoryNode, SubgoalNode, MarkerNode)) for node in nodes
            )
            has_checkpoint_protocol = any(isinstance(node, (MemoryNode, SubgoalNode, MarkerNode)) for node in nodes)
            if has_only_checkpoint_protocol and has_checkpoint_protocol:
                return ResponseShape.CHECKPOINT_ONLY, None

        if not action_nodes and not intent_nodes and not file_nodes:
            literal_only = all(isinstance(node, (LiteralProtocolTagNode, VisibleTextNode)) for node in nodes)
            if literal_only:
                return ResponseShape.PURE_PLAINTEXT, None

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
