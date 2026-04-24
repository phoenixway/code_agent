
from __future__ import annotations

import hashlib
import json
from typing import Any


class HistoryMaterialTools:
    def __init__(
        self,
        *,
        code_parser,
        max_structured_text_chars: int = 2500,
        max_structured_stdout_chars: int = 1200,
        max_structured_stderr_chars: int = 800,
        max_structured_output_lines: int = 40,
        large_result_count_hint: int = 80,
    ):
        self.code_parser = code_parser
        self.max_structured_text_chars = max_structured_text_chars
        self.max_structured_stdout_chars = max_structured_stdout_chars
        self.max_structured_stderr_chars = max_structured_stderr_chars
        self.max_structured_output_lines = max_structured_output_lines
        self.large_result_count_hint = large_result_count_hint

    def working_material_identity(self, content: Any) -> str:
        try:
            if isinstance(content, dict):
                tool = str(content.get("tool") or "")
                path = str(content.get("path") or content.get("file_path") or content.get("filename") or "")
                version = str(content.get("version") or content.get("file_version") or "")
                start = str(content.get("start_byte") or "")
                end = str(content.get("end_byte") or "")
                start_line = str(content.get("start_line") or "")
                end_line = str(content.get("end_line") or "")
                chunk_id = str(content.get("chunk_id") or "")
                status = str(content.get("status") or "")
                command = str(content.get("command") or "") if tool == "run_shell" else ""
                core = self.preferred_text(content)
                blob = hashlib.sha256(str(core).encode("utf-8")).hexdigest()[:16] if core else ""
                return f"{tool}|{path}|{version}|{start_line}|{end_line}|{start}|{end}|{chunk_id}|{status}|{command}|{blob}"
            raw = str(content)
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        except Exception:
            return ""

    def material_kind(self, content: Any) -> str:
        if not isinstance(content, dict):
            return "generic"
        tool = str(content.get("tool") or "")
        if tool == "read_file":
            return "full_file"
        if tool == "read_chunk":
            return "chunk"
        if tool == "read_file_skeleton":
            return "skeleton"
        if tool in {"extract_symbol", "extract_kotlin_function"}:
            return "exact_symbol"
        if tool in {"search_content", "search_files", "list_directory", "find_files", "git_diff"}:
            return "search"
        if tool == "run_shell":
            return "shell"
        return "generic"

    def material_priority(self, kind: str) -> int:
        # Lower number = degrade earlier.
        kind = str(kind or "generic")
        if kind in {"search", "shell", "generic"}:
            return 0
        if kind == "skeleton":
            return 1
        if kind == "full_file":
            return 2
        if kind in {"chunk", "exact_symbol"}:
            return 3
        return 1

    def truncate_multiline_text(self, text: str, *, max_chars: int, max_lines: int) -> str:
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return text
        lines = text.splitlines()
        out = "\n".join(lines[:max_lines])
        if len(out) > max_chars:
            out = out[:max_chars].rstrip() + "\n...[truncated]"
        elif len(lines) > max_lines:
            out += "\n...[truncated]"
        return out

    def preferred_text(self, payload: dict) -> str:
        if not isinstance(payload, dict):
            return str(payload or "")
        for key in (
            "raw_output",
            "stdout_full",
            "stderr_full",
            "file_content",
            "content",
            "output",
            "stdout",
            "stderr",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    def compact_structured_message_content(self, content: Any):
        try:
            if isinstance(content, list):
                return [self.compact_structured_message_content(item) for item in content]
            if not isinstance(content, dict):
                return content
            compact = dict(content)
            history_compact = bool(compact.get("history_compact", False))
            truncated = bool(compact.get("truncated", False))
            result_count = int(compact.get("result_count", 0) or 0)
            if isinstance(compact.get("output"), str):
                compact["output"] = self.truncate_multiline_text(
                    compact["output"],
                    max_chars=self.max_structured_text_chars,
                    max_lines=self.max_structured_output_lines,
                )
            if isinstance(compact.get("stdout"), str):
                if history_compact or truncated or result_count >= self.large_result_count_hint:
                    compact["stdout"] = self.truncate_multiline_text(
                        compact["stdout"],
                        max_chars=self.max_structured_stdout_chars,
                        max_lines=20,
                    )
                else:
                    compact["stdout"] = self.truncate_multiline_text(
                        compact["stdout"],
                        max_chars=self.max_structured_text_chars,
                        max_lines=self.max_structured_output_lines,
                    )
            if isinstance(compact.get("stderr"), str):
                compact["stderr"] = self.truncate_multiline_text(
                    compact["stderr"],
                    max_chars=self.max_structured_stderr_chars,
                    max_lines=12,
                )
            return compact
        except Exception:
            return content

    def degrade_material(self, payload: Any, *, kind: str | None = None, stage: int = 1, preserve_type: str = "history"):
        if stage <= 0:
            return payload
        if not isinstance(payload, dict):
            if stage <= 1:
                return self.truncate_multiline_text(str(payload or ""), max_chars=800, max_lines=20)
            return "Degraded history marker. Rerun or reread the original source if exact content is needed."

        kind = kind or self.material_kind(payload)
        tool = str(payload.get("tool") or kind or "tool")
        path = str(payload.get("path") or payload.get("filename") or "")
        version = payload.get("version") or payload.get("file_version")

        if kind == "full_file":
            full = payload.get("file_content") or payload.get("content") or payload.get("output") or ""
            if stage <= 1:
                skeleton = None
                if isinstance(full, str) and full and path:
                    try:
                        skeleton = self.code_parser.get_skeleton(path, full)
                    except Exception:
                        skeleton = None
                if skeleton and skeleton.strip() and str(full).strip() != skeleton.strip():
                    return (
                        f"{preserve_type.capitalize()} degraded: file `{path}` version `{version}` was read.\n"
                        f"Skeleton:\n{skeleton}\n\n"
                        "If exact content is needed again, reread via read_file."
                    )
                preview = self.truncate_multiline_text(str(full or ""), max_chars=1200, max_lines=40)
                return (
                    f"{preserve_type.capitalize()} degraded: file `{path}` version `{version}` was read.\n"
                    f"Preview:\n{preview}\n\n"
                    "If exact content is needed again, reread via read_file."
                )
            return (
                f"{preserve_type.capitalize()} marker: file `{path}` version `{version}` was read earlier. "
                "If exact content is needed again, reread via read_file."
            )

        if kind == "chunk":
            full = payload.get("file_content") or payload.get("content") or payload.get("output") or ""
            start_line = payload.get("start_line")
            end_line = payload.get("end_line")
            start_byte = payload.get("start_byte")
            end_byte = payload.get("end_byte")
            range_label = (
                f"lines [{start_line}, {end_line}]"
                if start_line is not None or end_line is not None
                else f"bytes [{start_byte}, {end_byte})"
            )
            if stage <= 1:
                preview = self.truncate_multiline_text(str(full or ""), max_chars=1000, max_lines=30)
                return (
                    f"{preserve_type.capitalize()} degraded: file chunk from `{path}` version `{version}` {range_label} was read.\n"
                    f"Preview:\n{preview}\n\n"
                    "If exact chunk content is needed again, reread via read_chunk."
                )
            return (
                f"{preserve_type.capitalize()} marker: file chunk from `{path}` version `{version}` {range_label} was read earlier. "
                "If exact chunk content is needed again, reread via read_chunk."
            )

        if kind == "skeleton":
            preview = self.truncate_multiline_text(str(payload.get("output") or self.preferred_text(payload) or ""), max_chars=1200, max_lines=40)
            if stage <= 1:
                return (
                    f"{preserve_type.capitalize()} degraded: skeleton for `{path}` was read.\n"
                    f"{preview}\n\n"
                    "If exact content is needed again, reread via read_file_skeleton or read_file."
                )
            return (
                f"{preserve_type.capitalize()} marker: skeleton for `{path}` was read earlier. "
                "If exact content is needed again, reread via read_file_skeleton or read_file."
            )

        if kind == "exact_symbol":
            symbol_name = str(payload.get("symbol_name") or "")
            symbol_kind = str(payload.get("symbol_kind") or payload.get("kind") or "")
            signature = str(payload.get("signature") or "")
            if stage <= 1:
                parts = [
                    f"{preserve_type.capitalize()} degraded: symbol `{symbol_name}`"
                    + (f" ({symbol_kind})" if symbol_kind else "")
                    + f" from `{path}` was extracted.",
                ]
                if signature:
                    parts.append(f"Signature:\n{self.truncate_multiline_text(signature, max_chars=800, max_lines=12)}")
                body = self.preferred_text(payload)
                if body and body != signature:
                    parts.append(
                        "Preview:\n"
                        + self.truncate_multiline_text(body, max_chars=1000, max_lines=30)
                    )
                parts.append("If exact content is needed again, reread via extract_symbol.")
                return "\n\n".join(parts)
            return (
                f"{preserve_type.capitalize()} marker: symbol `{symbol_name}`"
                + (f" ({symbol_kind})" if symbol_kind else "")
                + f" from `{path}` was extracted earlier. "
                "If exact content is needed again, reread via extract_symbol."
            )

        if kind == "search":
            pattern = str(payload.get("pattern") or "")
            result_count = int(payload.get("result_count", 0) or 0)
            preferred = self.preferred_text(payload)
            preview = self.truncate_multiline_text(preferred, max_chars=900, max_lines=24)
            if stage <= 1:
                return {
                    "tool": tool,
                    "path": path,
                    "pattern": pattern,
                    "result_count": result_count,
                    "history_compact": True,
                    "note": "Search result degraded under context pressure.",
                    "output_preview": preview,
                    "rerun_hint": "If insufficient, rerun a narrower search or lower the limit.",
                }
            return {
                "tool": tool,
                "path": path,
                "pattern": pattern,
                "result_count": result_count,
                "history_compact": True,
                "note": "Search result degraded to marker under context pressure. Rerun a narrower search if exact output is needed.",
            }

        if kind == "shell":
            command = str(payload.get("command") or "")
            status = str(payload.get("status") or "")
            stdout_preview = self.truncate_multiline_text(str(payload.get("stdout") or payload.get("output") or ""), max_chars=900, max_lines=20)
            stderr_preview = self.truncate_multiline_text(str(payload.get("stderr") or ""), max_chars=500, max_lines=8)
            if stage <= 1:
                compact = {
                    "tool": tool,
                    "command": command,
                    "status": status,
                    "history_compact": True,
                    "note": "Shell result degraded under context pressure.",
                }
                if stdout_preview:
                    compact["stdout_preview"] = stdout_preview
                if stderr_preview:
                    compact["stderr_preview"] = stderr_preview
                return compact
            return {
                "tool": tool,
                "command": command,
                "status": status,
                "history_compact": True,
                "note": "Shell result degraded to marker under context pressure. Rerun a narrower command if exact output is needed.",
            }

        preview = self.preferred_text(payload)
        if isinstance(preview, str):
            preview = self.truncate_multiline_text(preview, max_chars=800, max_lines=20)
        if stage <= 1:
            return {
                "tool": tool,
                "path": path,
                "history_compact": True,
                "note": f"{preserve_type.capitalize()} degraded to compact preview.",
                "output_preview": preview,
            }
        return {
            "tool": tool,
            "path": path,
            "history_compact": True,
            "note": f"{preserve_type.capitalize()} degraded to marker. Rerun the tool if exact content is needed.",
        }