#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(".")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Pattern not found in {path}:\n{old[:400]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_after_once(path: Path, marker: str, insertion: str, sentinel: str) -> None:
    text = path.read_text(encoding="utf-8")
    if sentinel in text:
        return
    if marker not in text:
        raise SystemExit(f"Marker not found in {path}:\n{marker}")
    path.write_text(text.replace(marker, marker + insertion, 1), encoding="utf-8")


# parsing.py
parsing = ROOT / "modules/agent/orchestration/parsing.py"
insert_after_once(
    parsing,
    '''    LIST_FIELDS = {
        "allowed_actions",
    }
''',
    '''
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
''',
    "READ_ONLY_ACTION_TYPES",
)

replace_once(
    parsing,
    '''    def has_multiple_actions(self, segments) -> bool:
        action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        return action_count >= 2

    def has_file_content_before_action(self, segments) -> bool:
''',
    '''    def action_segment_is_read_only(self, segment) -> bool:
        """Return True when an action segment is safe to batch pre-dispatch.

        Protocol-level multi-action output is only allowed for pure read-only
        batches. State-changing actions still require a single-action turn so
        the runtime can keep edits atomic and recoverable.
        """
        if getattr(segment, "type", "") != "action":
            return False
        content = getattr(segment, "content", None)
        if not isinstance(content, dict):
            return False
        action_type = str(content.get("type") or content.get("action") or "").strip().lower()
        return action_type in self.READ_ONLY_ACTION_TYPES

    def multiple_actions_are_pure_read_only(self, segments) -> bool:
        action_segments = [
            seg for seg in list(segments or [])
            if getattr(seg, "type", "") == "action"
        ]
        if len(action_segments) < 2:
            return False
        return all(self.action_segment_is_read_only(seg) for seg in action_segments)

    def has_multiple_actions(self, segments) -> bool:
        action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        if action_count < 2:
            return False
        return not self.multiple_actions_are_pure_read_only(segments)

    def has_file_content_before_action(self, segments) -> bool:
''',
)

# response_pipeline.py
response_pipeline = ROOT / "modules/agent/orchestration/response_pipeline.py"
insert_after_once(
    response_pipeline,
    '''    @property
    def ui(self):
        return self.agent.ui
''',
    '''
    def _multiple_actions_are_pure_read_only(self, segments) -> bool:
        checker = getattr(self.intent_response_parser, "multiple_actions_are_pure_read_only", None)
        if callable(checker):
            try:
                return bool(checker(segments))
            except Exception:
                return False
        return False
''',
    "_multiple_actions_are_pure_read_only",
)

replace_once(
    response_pipeline,
    '''        parsed_action_count = action_policy_decision.parsed_action_count
        if parsed_action_count > 1:
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="multiple_actions",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_multiple_actions_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="multiple_actions",
                source="transaction_guard",
            )
        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
''',
    '''        parsed_action_count = action_policy_decision.parsed_action_count
        if parsed_action_count > 1 and not self._multiple_actions_are_pure_read_only(segments):
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="multiple_actions",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_multiple_actions_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="multiple_actions",
                source="transaction_guard",
            )
        if parsed_action_count > 1:
            self.stage_logger.log(
                "response_pipeline",
                "pass",
                reason="pure_readonly_batch_allowed",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
''',
)

# prompting.py
prompting = ROOT / "modules/agent/orchestration/prompting.py"
replace_once(
    prompting,
    '''    def build_multiple_actions_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained multiple top-level <action> blocks.\\n"
            "Return EXACTLY ONE valid <action>...</action> block now.\\n"
            "Only top-level protocol <action> blocks count here; raw text inside <file_content> does not.\\n"
            "Do not use an action array.\\n"
            "Do not batch state-changing actions."
        )
''',
    '''    def build_multiple_actions_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained multiple top-level <action> blocks that cannot be batched.\\n"
            "Multiple top-level <action> blocks are allowed only when every action is read-only.\\n"
            "State-changing or mixed read/write batches are not atomic and are rejected.\\n"
            "Return EXACTLY ONE valid <action>...</action> block now for the single next state-changing step, "
            "or return a pure read-only batch only if every action is read-only.\\n"
            "Only top-level protocol <action> blocks count here; raw text inside <file_content> does not.\\n"
            "Do not use an action array."
        )
''',
)

print("Applied pure read-only multi-action batch fix.")
