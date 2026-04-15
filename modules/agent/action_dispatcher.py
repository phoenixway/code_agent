import ast
import hashlib
import json
import re
import shlex
from pathlib import Path
from types import SimpleNamespace


class ActionDispatcher:
    def __init__(self, agent):
        self.agent = agent
        self.ui = agent.ui
        self.processor = agent.processor
        self.config = agent.config

        # Мапінг команд до методів відображення/обробки
        self._handlers = {
            "run_shell": self._handle_shell,
            "read_file": self._handle_read_file,
            "read_chunk": self._handle_read_chunk,
            "edit_file": self._handle_edit_file,
            "create_file": self._handle_create_file,
        }

        # Евристики для preflight-оцінки working material
        self._SEARCH_RESULT_LINE_ESTIMATE = 140
        self._SEARCH_RESULT_HEADER_ESTIMATE = 400
        self._SKELETON_FRACTION = 0.18
        self._SKELETON_MIN_CHARS = 1200
        self._SKELETON_MAX_CHARS = 16000
        self._RUN_SHELL_DEFAULT_ESTIMATE = 12000
        self._RUN_SHELL_RG_FD_ESTIMATE = 8000
        self._READ_BATCH_SOFT_MIN_ACTIONS = 2

    async def dispatch_segments(self, segments, state):
        """Обробляє список сегментів, виконує дії та повертає результати."""
        processed_segments = []
        system_results = []
        should_stop = False

        action_segments = [seg for seg in segments if seg.type == "action"]
        action_commands = [seg.content for seg in action_segments]

        execute_indices, batch_notes = self._plan_action_batch(action_commands)
        execute_set = set(execute_indices)
        total_exec = len(execute_indices)

        state.last_batch_actions_executed = 0
        state.last_batch_actions_total = len(action_segments)
        action_ordinal = 0

        if batch_notes:
            system_results.extend(batch_notes)

        sm = getattr(state, "state_machine", None)
        if sm is not None and hasattr(sm, "note_planned_batch"):
            try:
                sm.note_planned_batch([action_commands[i] for i in execute_indices])
            except Exception:
                pass

        preflight_stop = self._preflight_turn_working_material_budget(
            action_commands, execute_indices, state
        )
        preflight_triggered = False

        for segment in segments:
            if segment.type == "thought":
                await self.ui.print_thought(segment.content)
                processed_segments.append(segment)

            elif segment.type == "text":
                await self.ui.print_message(segment.content, role="assistant")
                processed_segments.append(segment)

            elif segment.type == "action":
                current_idx = action_ordinal
                action_ordinal += 1
                cmd_type = (
                    segment.content.get("type")
                    or segment.content.get("action")
                    or "unknown"
                    if isinstance(segment.content, dict)
                    else "unknown"
                )

                if preflight_stop and not preflight_triggered and current_idx in execute_set:
                    preflight_triggered = True
                    should_stop = True
                    state.pending_loop_stop_info = preflight_stop

                    stop_reason = str(preflight_stop.get("reason") or "").strip()
                    blocked = False
                    if stop_reason in {"planned_turn_working_material_too_large", "planned_full_read_too_large"}:
                        blocked = self._block_current_intent_action_if_supported(
                            state,
                            segment.content if isinstance(segment.content, dict) else {},
                            stop_reason,
                        )

                    result_text = (
                        f"SYSTEM RESULT for `{cmd_type}`: {preflight_stop['message']}"
                    )
                    if blocked:
                        result_text += "\n[SYSTEM: This exact action shape is now blocked for the current intent. Choose a materially different action.]"
                    system_results.append(result_text)

                    if self.agent.log:
                        self.agent.log.debug(
                            "Action.finish type=%s should_stop=True reason=%s",
                            cmd_type,
                            preflight_stop.get("reason"),
                        )
                    break

                if current_idx not in execute_set:
                    system_results.append(
                        f"SYSTEM RESULT for `{cmd_type}`: Skipped by batch policy."
                    )
                    continue

                cmd_copy, result_text, stop_flag = await self._execute_action(
                    segment.content, state
                )
                state.last_batch_actions_executed += 1

                if total_exec > 1:
                    batch_pos = execute_indices.index(current_idx) + 1
                    result_text = f"[BATCH {batch_pos}/{total_exec}] {result_text}"

                processed_segments.append(
                    SimpleNamespace(
                        type="text",
                        content=self._build_history_audit_line(cmd_copy),
                    )
                )

                system_results.append(result_text)

                if stop_flag:
                    should_stop = True
                    if total_exec > 1 and batch_pos < total_exec:
                        system_results.append(
                            f"SYSTEM RESULT for `{cmd_type}`: Batch aborted after action {batch_pos}/{total_exec} due to stop condition."
                        )

                        all_exec_cmds = [action_commands[i] for i in execute_indices]
                        only_search_batch = all(
                            isinstance(cmd, dict)
                            and (cmd.get("type") or cmd.get("action")) == "search_content"
                            for cmd in all_exec_cmds
                        )
                        if only_search_batch and cmd_type == "search_content":
                            existing = getattr(state, "pending_loop_stop_info", None) or {}
                            state.pending_loop_stop_info = {
                                "reason": "search_batch_aborted_after_first_action",
                                "recoverable": True,
                                "error_code": "SEARCH_BATCH_ABORTED_AFTER_FIRST_ACTION",
                                "next_actions": ["search_content"],
                                "message": (
                                    "Your read-only search batch was aborted after the first action. "
                                    "Return exactly one narrower search_content action next. "
                                    "Do not send another broad batch."
                                ),
                                "previous_reason": existing.get("reason"),
                                "command": cmd_copy.copy(),
                            }
                    break

        return processed_segments, system_results, should_stop

    def _plan_action_batch(self, action_commands: list[dict]) -> tuple[list[int], list[str]]:
        if not action_commands:
            return [], []
        if len(action_commands) == 1:
            return [0], []

        notes: list[str] = []
        readonly_indices = [
            idx for idx, cmd in enumerate(action_commands)
            if self._is_read_only_action(cmd)
        ]

        if len(readonly_indices) == len(action_commands):
            max_batch = max(
                1, int(getattr(self.config, "MAX_READONLY_BATCH_ACTIONS", 6))
            )
            if len(action_commands) > max_batch:
                notes.append(
                    f"SYSTEM RESULT for `batch_policy`: Read-only batch limited to {max_batch} actions."
                )
                return list(range(max_batch)), notes
            return list(range(len(action_commands))), notes

        first_state_changing = next(
            idx for idx, cmd in enumerate(action_commands)
            if not self._is_read_only_action(cmd)
        )
        execute = list(range(first_state_changing + 1))
        notes.append(
            "SYSTEM RESULT for `batch_policy`: Mixed batch detected; executing leading read-only prefix plus the first state-changing action."
        )
        return execute, notes

    def _is_read_only_action(self, command: dict) -> bool:
        if not isinstance(command, dict):
            return False
        cmd_type = command.get("type") or command.get("action") or "unknown"
        read_only_tools = {
            "read_file",
            "read_chunk",
            "read_file_skeleton",
            "search_content",
            "search_files",
            "list_directory",
            "find_files",
            "git_diff",
        }
        if cmd_type == "run_shell":
            return self._is_read_only_shell_command(command.get("command"))
        return cmd_type in read_only_tools

    def _build_history_audit_line(self, command: dict) -> str:
        cmd_type = command.get("type") or command.get("action", "unknown")
        path = (
            command.get("path")
            if isinstance(command.get("path"), str) and command.get("path")
            else None
        )

        payload = {"type": cmd_type}
        if path:
            payload["path"] = path

        if cmd_type == "read_chunk":
            if "start_byte" in command:
                payload["start_byte"] = command.get("start_byte")
            if "end_byte" in command:
                payload["end_byte"] = command.get("end_byte")
            if "start_line" in command:
                payload["start_line"] = command.get("start_line")
            if "end_line" in command:
                payload["end_line"] = command.get("end_line")

        if command.get("content_redacted") is True:
            size = command.get("content_size")
            blob = command.get("content_blob_hash")
            blob_short = (str(blob)[:12] + "...") if blob else "unknown"
            payload["content"] = f"REDACTED(size={size}, blob={blob_short})"
        else:
            payload["content"] = "none"

        return "TOOL_HISTORY " + json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _has_explicit_reread_reason(self, command: dict) -> bool:
        reason_fields = (
            command.get("reason"),
            command.get("because"),
            command.get("before_execution"),
            command.get("note"),
        )
        blob = " ".join(str(x) for x in reason_fields if x).lower()
        return any(
            token in blob
            for token in (
                "exact",
                "verify",
                "patch",
                "edit",
                "implementation",
                "точн",
                "перевір",
                "патч",
                "редаг",
            )
        )

    def _error_code_from_reason(
        self, reason: str | None, default: str = "STATE_MACHINE_POLICY_DENY"
    ) -> str:
        if not isinstance(reason, str) or not reason.strip():
            return default
        code = re.sub(r"[^A-Z0-9]+", "_", reason.upper()).strip("_")
        return code or default

    def _intent_runtime(self, state):
        return getattr(state, "intent_runtime", None)

    def _block_current_intent_action_if_supported(self, state, command: dict, reason: str) -> bool:
        runtime = self._intent_runtime(state)
        if runtime is None or not isinstance(command, dict):
            return False
        blocker = getattr(runtime, "block_action_for_current_intent", None)
        if not callable(blocker):
            return False
        try:
            return bool(blocker(command, reason))
        except Exception:
            return False

    def _safe_turn_working_material_char_budget(self) -> int:
        history = getattr(self.agent, "history", None)
        max_tokens = int(getattr(history, "max_tokens", 4000) if history else 4000)
        ratio = float(
            getattr(history, "TURN_WORKING_MATERIAL_SAFE_RATIO", 0.72) if history else 0.72
        )
        return max(1024, int(max_tokens * ratio * 4))

    def _current_turn_working_material_chars(self, state) -> int:
        history = getattr(self.agent, "history", None)
        if history is None:
            return 0
        counter = getattr(history, "current_turn_working_material_token_count", None)
        turn_id = getattr(state, "current_turn_id", 0)
        if callable(counter):
            try:
                return int(counter(turn_id) * 4)
            except Exception:
                return 0
        return 0

    def _estimate_file_chars(self, path: str) -> int | None:
        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return None
            return int(p.stat().st_size)
        except Exception:
            return None

    def _estimate_action_working_material_chars(self, command: dict) -> int:
        if not isinstance(command, dict):
            return 0

        cmd_type = command.get("type") or command.get("action") or "unknown"

        if cmd_type == "read_file":
            path = command.get("path") if isinstance(command.get("path"), str) else ""
            size = self._estimate_file_chars(path)
            if size is None:
                return 12000
            return size

        if cmd_type == "read_chunk":
            path = command.get("path") if isinstance(command.get("path"), str) else ""
            size = self._estimate_file_chars(path)
            if size is None:
                return 4000
            try:
                sb = max(0, int(command.get("start_byte", 0)))
                eb = int(command.get("end_byte", sb))
                eb = max(sb, min(eb, size))
                return max(0, eb - sb)
            except Exception:
                return 4000

        if cmd_type == "read_file_skeleton":
            path = command.get("path") if isinstance(command.get("path"), str) else ""
            size = self._estimate_file_chars(path)
            if size is None:
                return 4000
            estimate = int(size * self._SKELETON_FRACTION)
            return max(self._SKELETON_MIN_CHARS, min(estimate, self._SKELETON_MAX_CHARS))

        if cmd_type in {"search_content", "search_files"}:
            limit = command.get("limit", 50)
            try:
                limit = max(1, min(int(limit), 200))
            except Exception:
                limit = 50
            return self._SEARCH_RESULT_HEADER_ESTIMATE + (
                limit * self._SEARCH_RESULT_LINE_ESTIMATE
            )

        if cmd_type == "run_shell":
            raw = command.get("command")
            if not isinstance(raw, str):
                return self._RUN_SHELL_DEFAULT_ESTIMATE
            lowered = raw.lower()
            if " rg " in f" {lowered} " or lowered.startswith("rg "):
                return self._RUN_SHELL_RG_FD_ESTIMATE
            if " fd " in f" {lowered} " or lowered.startswith("fd "):
                return self._RUN_SHELL_RG_FD_ESTIMATE
            return self._RUN_SHELL_DEFAULT_ESTIMATE

        if cmd_type in {"list_directory", "find_files", "git_diff"}:
            return 6000

        return 4000

    def _preflight_turn_working_material_budget(
        self, action_commands: list[dict], execute_indices: list[int], state
    ) -> dict | None:
        if not execute_indices:
            return None

        planned = []
        for idx in execute_indices:
            if idx < 0 or idx >= len(action_commands):
                continue
            cmd = action_commands[idx]
            if not isinstance(cmd, dict):
                continue
            if not self._is_read_only_action(cmd):
                continue
            planned.append(cmd)

        if not planned:
            return None

        current_chars = self._current_turn_working_material_chars(state)
        estimated_by_action = [
            self._estimate_action_working_material_chars(cmd) for cmd in planned
        ]
        estimated_new_chars = sum(estimated_by_action)
        safe_budget_chars = self._safe_turn_working_material_char_budget()

        if current_chars + estimated_new_chars <= safe_budget_chars:
            return None

        full_reads = [
            cmd for cmd in planned
            if isinstance(cmd, dict)
            and (cmd.get("type") or cmd.get("action")) == "read_file"
            and cmd.get("start_byte") is None
            and cmd.get("end_byte") is None
        ]

        # Case 1: single oversized full read. This must become a stricter recovery
        # class than generic batch overflow, otherwise the model loops on the same read_file.
        if len(planned) == 1 and len(full_reads) == 1:
            cmd = full_reads[0]
            path = cmd.get("path") if isinstance(cmd.get("path"), str) else ""
            if path:
                return {
                    "reason": "planned_full_read_too_large",
                    "recoverable": True,
                    "error_code": "PLANNED_FULL_READ_TOO_LARGE",
                    "next_actions": [
                        "read_chunk",
                        "read_file_skeleton",
                        "search_content",
                        "search_files",
                        "run_shell",
                    ],
                    "message": (
                        "The planned full read_file action is too large for this path. "
                        "Do not repeat the same full read_file action for this path right now. "
                        "Stay on the current goal, but switch to a smaller read strategy: "
                        "read_chunk, read_file_skeleton, search_content, search_files, "
                        "or run_shell with rg/fd. "
                        "If you later need a new intent, request it formally with a legitimate switch reason. "
                        "Return EXACTLY ONE materially different read-only action."
                    ),
                    "command": cmd.copy(),
                    "estimated_new_chars": estimated_new_chars,
                    "current_turn_chars": current_chars,
                    "safe_budget_chars": safe_budget_chars,
                    "intent_constraint_updates": {
                        "max_full_reads_per_step": 0,
                        "require_chunk_for_paths": [path],
                        "forbid_same_full_read_path": path,
                    },
                }

        # Case 2: generic batch / multi-output overflow. Allow smaller continuation.
        first_command = planned[0] if planned else {}
        return {
            "reason": "planned_turn_working_material_too_large",
            "recoverable": True,
            "error_code": "PLANNED_TURN_WORKING_MATERIAL_TOO_LARGE",
            "next_actions": [
                "read_file",
                "read_chunk",
                "read_file_skeleton",
                "search_content",
                "search_files",
                "run_shell",
            ],
            "message": (
                "The planned read/search output for this turn is too large to preserve safely in context. "
                "Continue under the current goal with a materially smaller step: read fewer files at once, "
                "read exactly one strongest candidate file, use read_chunk, use read_file_skeleton, "
                "or narrow the investigation through search first (search_content, search_files, rg, fd). "
                "If you truly need to change intent, do it only through a formal intent request with a legitimate switch reason. "
                "Return EXACTLY ONE revised action or a smaller read-only batch."
            ),
            "command": first_command.copy() if isinstance(first_command, dict) else {},
            "estimated_new_chars": estimated_new_chars,
            "current_turn_chars": current_chars,
            "safe_budget_chars": safe_budget_chars,
            "intent_constraint_updates": {
                "max_full_reads_per_step": 1,
            },
        }

    async def _execute_action(self, command, state):
        """Виконує одну дію, керує UI та повертає результат."""
        cmd_type = command.get("type") or command.get("action", "unknown")

        if cmd_type == "read_file":
            command = self._normalize_read_file_command(command)
            if not command.get("path"):
                output_text = (
                    "SYSTEM: Invalid read_file payload. Provide `path` as a top-level field.\n"
                    "Example:\n"
                    '<action type="read_file">{"path":"relative/or/absolute/path"}</action>'
                )
                state.pending_loop_stop_info = {
                    "reason": "malformed_read_file_payload",
                    "recoverable": True,
                    "error_code": "MALFORMED_READ_FILE_PAYLOAD",
                    "next_actions": ["read_file"],
                    "message": (
                        "read_file requires a top-level `path` field. "
                        "Return exactly one read_file action with only the corrected payload."
                    ),
                    "command": command.copy(),
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=read_file should_stop=True reason=malformed_read_file_payload"
                    )
                return self._sanitize_command_for_history(command), full_result_text, True

        if cmd_type == "read_chunk":
            normalized_command = self._normalize_read_chunk_command(command)
            line_mode = (
                bool(normalized_command.get("path"))
                and normalized_command.get("start_line") is not None
                and normalized_command.get("end_line") is not None
            )
            byte_mode = (
                bool(normalized_command.get("path"))
                and normalized_command.get("start_byte") is not None
                and normalized_command.get("end_byte") is not None
            )
            mixed_mode = (
                normalized_command.get("start_line") is not None
                and normalized_command.get("start_byte") is not None
            )
            command = normalized_command

            if mixed_mode:
                snapshot = self._read_chunk_validation_snapshot(
                    command,
                    normalized_command,
                    reason="read_chunk_mixed_line_and_byte_mode",
                    accepted=False,
                )
                self._log_read_chunk_validation(snapshot)
                output_text = (
                    "SYSTEM: Invalid read_chunk payload. Use either line ranges or byte ranges, not both.\n"
                    "Preferred format:\n"
                    '<action type="read_chunk">{"path":"relative/or/absolute/path","start_line":1304,"end_line":1500}</action>'
                )
                state.pending_loop_stop_info = {
                    "reason": "malformed_read_chunk_payload",
                    "recoverable": True,
                    "error_code": "MALFORMED_READ_CHUNK_PAYLOAD",
                    "next_actions": ["read_chunk"],
                    "message_key": "malformed_read_chunk_payload",
                    "message": (
                        "read_chunk accepts either line ranges or byte ranges, not both at once. "
                        "Preferred format uses top-level `path`, `start_line`, and `end_line`."
                    ),
                    "command": command.copy(),
                    "validation_snapshot": snapshot,
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=read_chunk should_stop=True reason=malformed_read_chunk_payload"
                    )
                return self._sanitize_command_for_history(command), full_result_text, True

            if not line_mode and not byte_mode:
                snapshot = self._read_chunk_validation_snapshot(
                    command,
                    normalized_command,
                    reason="read_chunk_missing_required_range",
                    accepted=False,
                )
                self._log_read_chunk_validation(snapshot)
                output_text = (
                    "SYSTEM: Invalid read_chunk payload.\n"
                    "Preferred format:\n"
                    '<action type="read_chunk">{"path":"relative/or/absolute/path","start_line":1304,"end_line":1500}</action>\n'
                    "Use top-level `path`, `start_line`, and `end_line` fields.\n"
                    "Byte offsets are optional only when explicitly needed."
                )
                state.pending_loop_stop_info = {
                    "reason": "malformed_read_chunk_payload",
                    "recoverable": True,
                    "error_code": "MALFORMED_READ_CHUNK_PAYLOAD",
                    "next_actions": ["read_chunk"],
                    "message_key": "malformed_read_chunk_payload",
                    "message": (
                        "read_chunk requires a valid top-level payload. "
                        "Preferred format uses line ranges: `path`, `start_line`, `end_line`. "
                        "Return exactly one corrected read_chunk action."
                    ),
                    "command": command.copy(),
                    "validation_snapshot": snapshot,
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=read_chunk should_stop=True reason=malformed_read_chunk_payload"
                    )
                return self._sanitize_command_for_history(command), full_result_text, True

            snapshot = self._read_chunk_validation_snapshot(
                command,
                normalized_command,
                reason="accepted_line_mode" if line_mode else "accepted_byte_mode",
                accepted=True,
            )
            self._log_read_chunk_validation(snapshot)

        if cmd_type == "read_file_skeleton":
            command = self._normalize_read_file_skeleton_command(command)
            if not command.get("path"):
                output_text = (
                    "SYSTEM: Invalid read_file_skeleton payload. Provide `path` as a top-level field.\n"
                    "Example:\n"
                    '<action type="read_file_skeleton">{"path":"relative/or/absolute/path"}</action>'
                )
                state.pending_loop_stop_info = {
                    "reason": "malformed_read_file_skeleton_payload",
                    "recoverable": True,
                    "error_code": "MALFORMED_READ_FILE_SKELETON_PAYLOAD",
                    "next_actions": ["read_file_skeleton"],
                    "message": (
                        "read_file_skeleton requires a top-level `path` field. "
                        "Return exactly one read_file_skeleton action with only the corrected payload."
                    ),
                    "command": command.copy(),
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=read_file_skeleton should_stop=True reason=malformed_read_file_skeleton_payload"
                    )
                return self._sanitize_command_for_history(command), full_result_text, True

            history = getattr(self.agent, "history", None)
            path = command.get("path") if isinstance(command.get("path"), str) else None
            if history is not None and path and getattr(
                history, "has_current_file_version", lambda _p: False
            )(path):
                if not self._has_explicit_reread_reason(command):
                    recently_summarized = bool(
                        getattr(history, "was_recently_summarized", lambda _w=90: False)(
                            getattr(self.config, "RECENT_SUMMARY_REREAD_WINDOW_SEC", 90)
                        )
                    )
                    reason = (
                        "reread_after_summary"
                        if recently_summarized
                        else "reread_already_in_history"
                    )
                    output_text = (
                        "SYSTEM: This file is already available in history at the current version. "
                        "Re-reading it without a specific reason is blocked. Use existing context, "
                        "narrow with search_content, or proceed to edit_file/write_file."
                    )
                    state.pending_loop_stop_info = {
                        "reason": reason,
                        "recoverable": True,
                        "error_code": "FILE_ALREADY_AVAILABLE_USE_EXISTING_CONTEXT",
                        "next_actions": ["search_content", "edit_file", "write_file"],
                        "command": command.copy(),
                    }
                    full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                    return self._sanitize_command_for_history(command), full_result_text, True

        if cmd_type == "list_directory" and not command.get("path"):
            output_text = (
                "SYSTEM: Invalid list_directory payload: explicit `path` is required. "
                "Do not omit path in read-only batches. Root listing without intent is blocked."
            )
            state.pending_loop_stop_info = {
                "reason": "list_directory_missing_path",
                "recoverable": True,
                "error_code": "LIST_DIRECTORY_MISSING_PATH",
                "next_actions": ["list_directory", "search_files", "search_content"],
                "command": command.copy(),
            }
            full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
            return self._sanitize_command_for_history(command), full_result_text, True

        command_for_history = self._sanitize_command_for_history(command)
        sm = getattr(state, "state_machine", None)

        intent_precheck = getattr(state, "check_intent_pre_action", None)
        if callable(intent_precheck):
            intent_stop = intent_precheck(command)
            if intent_stop:
                output_text = (
                    "SYSTEM: This action is outside the current intent contract. "
                    "Keep the current intent active unless you formally complete it or submit a formal intent switch with a legitimate reason. "
                    "Right now, choose one of the current intent's allowed actions, or complete the current intent if its goal is already satisfied."
                )
                state.pending_loop_stop_info = intent_stop
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=%s should_stop=True reason=%s",
                        cmd_type,
                        intent_stop.get("reason"),
                    )
                return command_for_history, full_result_text, True

        if sm is not None:
            pre_decision = sm.pre_action_policy(command)
            if not pre_decision.allow:
                output_text = (
                    pre_decision.recovery_prompt or "Action blocked by state machine policy."
                )
                state.pending_loop_stop_info = {
                    "reason": pre_decision.stop_reason or "policy_denied",
                    "recoverable": True,
                    "error_code": self._error_code_from_reason(
                        pre_decision.stop_reason
                    ),
                    "next_actions": pre_decision.required_next_action_types or [],
                    "message": output_text,
                    "command": command.copy(),
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=%s should_stop=True reason=%s",
                        cmd_type,
                        pre_decision.stop_reason,
                    )
                return command_for_history, full_result_text, True

        if state.consume_forbidden_action_if_matches(command):
            output_text = (
                "Action blocked: repeating the previous action immediately after malformed-action recovery "
                "is not allowed. Change tool or arguments. "
                "The current intent may continue, but this exact immediate retry is not accepted."
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "REPEATED_ACTION_AFTER_MALFORMED",
                "next_actions": ["search_content", "search_files", "edit_file", "write_file"],
                "command": command.copy(),
            }
            full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
            if self.agent.log:
                self.agent.log.debug(
                    "Action.finish type=%s should_stop=True", cmd_type
                )
            return command_for_history, full_result_text, True

        if self.agent.log:
            self.agent.log.debug("Action.start type=%s command=%s", cmd_type, command)

        handler = self._handlers.get(cmd_type, self._handle_default)
        result = await handler(command)

        self._capture_turn_working_material(command, result, state)

        output_text = result.get("output", "")
        status = result.get("status")
        error_code = result.get("error_code")
        recoverable = bool(result.get("recoverable", False))
        next_actions = result.get("next_actions") or []
        if not isinstance(next_actions, list):
            next_actions = []

        if self.agent.log:
            self.agent.log.debug(
                "Action.result type=%s status=%s error_code=%s recoverable=%s",
                cmd_type,
                status,
                error_code,
                recoverable,
            )

        state_metrics = state.record_action_result(command, result, self.config)
        if sm is not None:
            sm.note_action(command, result, self.config.STATE_CHANGING_OPS)

        if cmd_type in ["create_file", "edit_file"] and status == "success":
            path = command.get("path", "")
            if path.endswith(".py"):
                lint_error = self._check_python_syntax(path)
                if lint_error:
                    output_text += (
                        f"\n\n⚠️ SYSTEM WARNING: Syntax check failed for {path}:\n{lint_error}\n"
                        "Please fix this immediately."
                    )

        is_state_changing = cmd_type in self.config.STATE_CHANGING_OPS
        execution_failed = status in ["failed", "error"]
        action_denied = status == "denied"
        same_action_repeats = state_metrics.get("same_action_repeats", 0)

        read_only_repeat_threshold = max(
            2, int(getattr(self.config, "READ_ONLY_REPEAT_THRESHOLD", 3))
        )

        repeated_read_file_no_progress = (
            cmd_type in {"read_file", "read_chunk"}
            and status == "success"
            and same_action_repeats >= read_only_repeat_threshold
        )
        search_no_matches = "no matches found" in str(output_text).lower()
        repeated_search_no_match_no_progress = (
            cmd_type == "search_content"
            and status == "success"
            and search_no_matches
            and same_action_repeats >= read_only_repeat_threshold
        )
        repeated_readonly_shell_no_progress = (
            cmd_type == "run_shell"
            and status == "success"
            and same_action_repeats >= read_only_repeat_threshold
            and self._is_read_only_shell_command(command.get("command"))
        )

        should_stop = False
        state.pending_loop_stop_info = None

        if repeated_read_file_no_progress:
            should_stop = True
            self._block_current_intent_action_if_supported(state, command, "repeating_no_progress")
            output_text += (
                "\n[SYSTEM: Repeated read-file calls detected with no progress. "
                "Stop and switch to a different strategy.]"
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "READ_ONLY_LOOP",
                "next_actions": ["search_content", "read_file_skeleton", "read_chunk", "edit_file", "write_file"],
                "command": command.copy(),
            }

        elif repeated_search_no_match_no_progress:
            should_stop = True
            self._block_current_intent_action_if_supported(state, command, "repeating_no_progress")
            output_text += (
                "\n[SYSTEM: Repeated search_content calls returned no matches. "
                "Stop and switch to deterministic recovery.]"
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "SEARCH_NO_MATCH_LOOP",
                "next_actions": ["search_files", "read_chunk", "read_file_skeleton", "edit_file", "write_file"],
                "command": command.copy(),
            }

        elif repeated_readonly_shell_no_progress:
            should_stop = True
            self._block_current_intent_action_if_supported(state, command, "repeating_no_progress")
            output_text += (
                "\n[SYSTEM: Repeated read-only run_shell commands detected with no progress. "
                "Stop and switch to deterministic edit/write step.]"
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "READONLY_SHELL_LOOP",
                "next_actions": ["read_chunk", "read_file_skeleton", "edit_file", "write_file"],
                "command": command.copy(),
            }

        elif action_denied:
            output_text += "\n[SYSTEM: Action denied by user.]"
            should_stop = True

        elif execution_failed:
            output_text += (
                "\n[SYSTEM: Action failed. Analyze the error in <think> and retry.]"
            )
            same_error_repeats = state_metrics.get("same_error_repeats", 0)
            loop_threshold = max(
                2, int(getattr(self.config, "LOOP_ERROR_REPEAT_THRESHOLD", 2))
            )
            threshold_reached = same_error_repeats >= loop_threshold
            is_repeated_edit_search_mismatch = (
                cmd_type == "edit_file"
                and error_code == "VALIDATION_ERROR"
                and "Search block not found" in str(result.get("output", ""))
            )

            if threshold_reached:
                if is_repeated_edit_search_mismatch:
                    should_stop = True
                    output_text += (
                        "\n[SYSTEM: Repeated edit_file search mismatch detected. "
                        "Stop this loop and switch to deterministic recovery.]"
                    )
                    state.pending_loop_stop_info = {
                        "reason": "repeating_failure",
                        "recoverable": recoverable,
                        "error_code": error_code,
                        "next_actions": next_actions,
                        "command": command.copy(),
                    }
                elif state.consume_malformed_grace():
                    output_text += (
                        "\n[SYSTEM: Grace retry granted after malformed action recovery. "
                        "Try a different command/arguments now.]"
                    )
                else:
                    budget_ok = state.consume_retry_budget(recoverable)
                    if not budget_ok:
                        should_stop = True
                        output_text += (
                            "\n[SYSTEM: Repeated no-progress failure detected and retry budget exhausted.]"
                        )
                        state.pending_loop_stop_info = {
                            "reason": "repeating_failure",
                            "recoverable": recoverable,
                            "error_code": error_code,
                            "next_actions": next_actions,
                            "command": command.copy(),
                        }
                    else:
                        output_text += (
                            "\n[SYSTEM: Repeated failure detected. Retry budget remains, "
                            "but you must change strategy/arguments.]"
                        )

            feedback_lines = [
                "[SYSTEM_FEEDBACK]",
                f"last_tool_error_code={error_code or 'UNSPECIFIED'}",
                f"last_tool_error_message={str(result.get('output', ''))[:300]}",
            ]
            if next_actions:
                feedback_lines.append(
                    "suggested_recovery_actions=" + ",".join(str(x) for x in next_actions[:6])
                )
            feedback_lines.append(
                "instruction=Do not repeat the same tool call with the same arguments."
            )
            output_text += "\n" + "\n".join(feedback_lines)

            if cmd_type == "edit_file" and "Search block not found" in str(output_text):
                output_text += (
                    "\n[SYSTEM: edit_file search block mismatch. "
                    "Next step must be deterministic: read the file, copy the exact block, "
                    "then retry edit_file with exact whitespace or use write_file with full updated content.]"
                )

        elif is_state_changing:
            state.reset_retry_budgets(
                self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                self.config.CRITICAL_ERROR_RETRY_BUDGET,
            )
            should_stop = False
        else:
            state.reset_retry_budgets(
                self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                self.config.CRITICAL_ERROR_RETRY_BUDGET,
            )

        defect_info = state_metrics.get("defect_info")
        if defect_info and not should_stop:
            should_stop = True
            state.pending_loop_stop_info = defect_info
            if defect_info.get("reason") in {
                "too_broad_search",
                "low_value_broad_search_repeat",
                "history_self_reference_hit",
            }:
                output_text += (
                    "\n[SYSTEM: Search strategy issue detected. "
                    "Do not send another broad search batch. Return one narrower search_content action next.]"
                )
            else:
                output_text += (
                    "\n[SYSTEM: Defect detector flagged repeated intent execution or action-cycle behavior. "
                    "Pause and choose whether to continue, require a new intent, or stop.]"
                )

        full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"

        if self.agent.log:
            self.agent.log.debug(
                "Action.finish type=%s should_stop=%s", cmd_type, should_stop
            )
        return command_for_history, full_result_text, should_stop

    def _is_read_only_shell_command(self, raw_command: object) -> bool:
        if not isinstance(raw_command, str):
            return False
        cmd = raw_command.strip()
        if not cmd:
            return False

        lowered = cmd.lower()
        if any(
            tok in lowered
            for tok in (
                ">",
                "| tee",
                ">>",
                "sed -i",
                "perl -i",
                "mkdir ",
                "rm ",
                "mv ",
                "cp ",
                "touch ",
            )
        ):
            return False

        segments = re.split(r"\s*(?:&&|\|\||;|\n)\s*", lowered)
        if not segments:
            return False

        allowed_bins = {
            "cd",
            "cat",
            "head",
            "tail",
            "grep",
            "rg",
            "fd",
            "wc",
            "find",
            "stat",
            "file",
            "pwd",
            "ls",
            "sed",
            "awk",
        }
        saw_reader = False

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                tokens = shlex.split(segment)
            except Exception:
                return False
            if not tokens:
                continue
            bin_name = tokens[0]
            if bin_name not in allowed_bins:
                return False
            if bin_name == "sed" and "-n" not in tokens:
                return False
            if bin_name != "cd":
                saw_reader = True
        return saw_reader

    def _normalize_read_file_command(self, command: dict) -> dict:
        if not isinstance(command, dict):
            return {"type": "read_file"}
        if command.get("path"):
            return command

        raw = command.get("command")
        if not isinstance(raw, str):
            return command
        text = raw.strip()
        if not text.startswith("{"):
            return command
        try:
            nested = json.loads(text)
        except Exception:
            return command
        if not isinstance(nested, dict):
            return command

        merged = command.copy()
        for key in ("path", "before_execution", "during_execution", "after_execution"):
            if merged.get(key) in (None, "") and nested.get(key):
                merged[key] = nested.get(key)
        if not merged.get("path"):
            inferred = self._infer_read_file_path(merged)
            if inferred:
                merged["path"] = inferred
        return merged


    def _read_chunk_validation_snapshot(self, command: dict, normalized: dict | None = None, *, reason: str = "", accepted: bool = False) -> dict:
        raw = command if isinstance(command, dict) else {}
        merged = normalized if isinstance(normalized, dict) else raw

        payload = {
            "stage": "read_chunk_validate",
            "accepted": bool(accepted),
            "reason": str(reason or ""),
            "raw_payload_type": type(command).__name__,
            "normalized_payload_type": type(merged).__name__,
            "raw_keys": sorted(list(raw.keys())) if isinstance(raw, dict) else [],
            "normalized_keys": sorted(list(merged.keys())) if isinstance(merged, dict) else [],
            "path": str(merged.get("path") or ""),
            "has_path": bool(merged.get("path")),
            "has_start_line": merged.get("start_line") is not None,
            "has_end_line": merged.get("end_line") is not None,
            "has_start_byte": merged.get("start_byte") is not None,
            "has_end_byte": merged.get("end_byte") is not None,
            "command_field_type": type(raw.get("command")).__name__ if isinstance(raw, dict) and "command" in raw else "",
        }

        using_lines = payload["has_start_line"]
        using_bytes = payload["has_start_byte"]
        payload["expects_line_mode"] = bool(using_lines and not using_bytes)
        payload["expects_byte_mode"] = bool(using_bytes and not using_lines)
        payload["mixed_modes"] = bool(using_lines and using_bytes)
        return payload

    def _log_read_chunk_validation(self, payload: dict) -> None:
        if not self.agent.log:
            return
        level_method = self.agent.log.debug if payload.get("accepted") else self.agent.log.warning
        level_method(
            "ReadChunk.validate accepted=%s reason=%s path=%s line_mode=%s byte_mode=%s mixed_modes=%s normalized_keys=%s",
            payload.get("accepted"),
            payload.get("reason"),
            payload.get("path"),
            payload.get("expects_line_mode"),
            payload.get("expects_byte_mode"),
            payload.get("mixed_modes"),
            ",".join(payload.get("normalized_keys") or []),
        )

    def _normalize_read_chunk_command(self, command: dict) -> dict:
        if not isinstance(command, dict):
            return {"type": "read_chunk"}

        has_path = bool(command.get("path"))
        has_line_mode = command.get("start_line") is not None
        has_byte_mode = command.get("start_byte") is not None
        if has_path and ((has_line_mode and command.get("end_line") is not None) or (has_byte_mode and command.get("end_byte") is not None)):
            return command

        raw = command.get("command")
        if not isinstance(raw, str):
            return command
        text = raw.strip()
        if not text.startswith("{"):
            return command
        try:
            nested = json.loads(text)
        except Exception:
            return command
        if not isinstance(nested, dict):
            return command

        merged = command.copy()
        for key in (
            "path",
            "start_byte",
            "end_byte",
            "start_line",
            "end_line",
            "before_execution",
            "during_execution",
            "after_execution",
        ):
            if merged.get(key) in (None, "") and nested.get(key) is not None:
                merged[key] = nested.get(key)
        return merged

    def _normalize_read_file_skeleton_command(self, command: dict) -> dict:
        if not isinstance(command, dict):
            return {"type": "read_file_skeleton"}
        if command.get("path"):
            return command

        raw = command.get("command")
        if not isinstance(raw, str):
            return command
        text = raw.strip()
        if not text.startswith("{"):
            return command
        try:
            nested = json.loads(text)
        except Exception:
            return command
        if not isinstance(nested, dict):
            return command

        merged = command.copy()
        for key in ("path", "before_execution", "during_execution", "after_execution"):
            if merged.get(key) in (None, "") and nested.get(key):
                merged[key] = nested.get(key)
        if not merged.get("path"):
            inferred = self._infer_read_file_path(merged)
            if inferred:
                merged["path"] = inferred
        return merged

    def _infer_read_file_path(self, command: dict) -> str | None:
        if not isinstance(command, dict):
            return None

        direct_keys = ("path", "file", "file_path", "target", "target_path")
        for key in direct_keys:
            value = command.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        text_parts = []
        for key in (
            "before_execution",
            "during_execution",
            "after_execution",
            "reason",
            "note",
            "command",
        ):
            value = command.get(key)
            if isinstance(value, str) and value.strip():
                text_parts.append(value.strip())
        blob = "\n".join(text_parts)
        if not blob:
            return None

        path_match = re.search(
            r"([A-Za-z0-9._/\-]+/[A-Za-z0-9._/\-]+\.[A-Za-z0-9]+)", blob
        )
        if path_match:
            return path_match.group(1)

        filename_matches = re.findall(r"\b([A-Za-z0-9._-]+\.[A-Za-z0-9]+)\b", blob)
        unique_filenames = sorted(set(filename_matches))
        if len(unique_filenames) != 1:
            return None
        filename = unique_filenames[0]
        if re.match(r"^\d{2}_[A-Za-z0-9_-]+\.go$", filename):
            return f"go_examples/{filename}"
        if Path(filename).exists():
            return filename
        return None

    async def _handle_shell(self, command):
        widget = await self.ui.print_shell_start(command)
        await self.ui.start_action(command.get("during_execution", "Executing shell..."))
        result = await self.processor.process_single_action(command)
        await self.ui.update_shell_result(widget, result)
        return result

    async def _handle_read_file(self, command):
        widget = await self.ui.print_read_file_start(command)
        await self.ui.start_action(f"Reading {command.get('path', 'file')}...")
        result = await self.processor.process_single_action(command)
        await self.ui.update_read_file_result(widget, result)
        return result

    async def _handle_read_chunk(self, command):
        widget = await self.ui.print_read_file_start(command)
        if command.get("start_line") is not None and command.get("end_line") is not None:
            await self.ui.start_action(
                f"Reading lines {command.get('start_line')}:{command.get('end_line')} from {command.get('path', 'file')}..."
            )
        else:
            start_byte = command.get("start_byte")
            end_byte = command.get("end_byte")
            await self.ui.start_action(
                f"Reading chunk {start_byte}:{end_byte} from {command.get('path', 'file')}..."
            )
        result = await self.processor.process_single_action(command)
        await self.ui.update_read_file_result(widget, result)
        return result

    async def _handle_edit_file(self, command):
        widget = await self.ui.print_edit_file_start(command)
        await self.ui.start_action(f"Editing {command.get('path', 'file')}...")
        result = await self.processor.process_single_action(command)
        await self.ui.update_edit_file_result(widget, result)
        return result

    async def _handle_create_file(self, command):
        await self.ui.print_tool_call(self._sanitize_create_file_payload(command))
        await self.ui.start_action(f"Creating {command.get('path')}...")
        result = await self.processor.process_single_action(command)

        if result.get("status") == "success":
            await self.ui.print_confirmation(f"File {command.get('path')} created.")
        else:
            await self.ui.print_command_result(result.get("output"))
        return result

    def _sanitize_create_file_payload(self, command: dict) -> dict:
        safe = command.copy()
        content = safe.get("content")
        if not isinstance(content, str):
            return safe
        if len(content) <= 200:
            return safe

        blob_hash = None
        history = getattr(self.agent, "history", None)
        save_blob = getattr(history, "_save_blob", None)
        if callable(save_blob):
            try:
                blob_hash = save_blob(content)
            except Exception:
                blob_hash = None
        if not blob_hash:
            blob_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        safe.pop("content", None)
        safe["content_redacted"] = True
        safe["content_size"] = len(content)
        safe["content_blob_hash"] = blob_hash
        return safe

    def _sanitize_command_for_history(self, command: dict) -> dict:
        cmd_type = command.get("type") or command.get("action", "unknown")
        if cmd_type in {"create_file", "write_file", "edit_file", "replace"}:
            return self._sanitize_create_file_payload(command)
        return command.copy()

    async def _handle_default(self, command):
        await self.ui.print_tool_call(command)
        if command.get("before_execution"):
            await self.ui.print_plan(command["before_execution"])

        await self.ui.start_action(command.get("during_execution", "Working..."))
        result = await self.processor.process_single_action(command)

        if result.get("status") == "success" and command.get("after_execution"):
            await self.ui.print_confirmation(command["after_execution"])

        await self.ui.print_command_result(result.get("output", ""))
        return result

    def _capture_turn_working_material(self, command: dict, result: dict, state) -> None:
        history = getattr(self.agent, "history", None)
        if history is None:
            return

        add_material = getattr(history, "add_turn_working_material", None)
        if not callable(add_material):
            return

        turn_id = getattr(state, "current_turn_id", 0)
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path") if isinstance(command.get("path"), str) else ""
        status = str(result.get("status") or "")
        if status not in {"success", "failed", "error"}:
            return

        if cmd_type in {"read_file", "read_chunk"}:
            content = (
                result.get("file_content")
                or result.get("raw_output")
                or result.get("output")
            )
            if isinstance(content, str) and content:
                version = None
                add_file_version = getattr(history, "add_file_version", None)
                if callable(add_file_version) and path:
                    try:
                        meta = add_file_version(path, content, return_metadata=True)
                        version = meta.get("version") if isinstance(meta, dict) else None
                    except Exception:
                        version = None

                payload = {
                    "tool": cmd_type,
                    "path": path,
                    "filename": path,
                    "version": version,
                    "file_version": version,
                    "file_content": content,
                    "output": content,
                    "status": status,
                }

                start_byte = result.get("start_byte", command.get("start_byte"))
                end_byte = result.get("end_byte", command.get("end_byte"))
                if start_byte is not None:
                    payload["start_byte"] = start_byte
                if end_byte is not None:
                    payload["end_byte"] = end_byte

                add_material(
                    payload,
                    msg_type="turn_working_material",
                    turn_id=turn_id,
                )
                return

        if cmd_type == "read_file_skeleton":
            skeleton = result.get("skeleton_content") or result.get("output")
            if isinstance(skeleton, str) and skeleton:
                payload = {
                    "tool": "read_file_skeleton",
                    "path": path,
                    "output": skeleton,
                    "status": status,
                }
                add_material(
                    payload,
                    msg_type="turn_working_material",
                    turn_id=turn_id,
                )
                return

        payload = {
            "tool": cmd_type,
            "path": path,
            "status": status,
            # Preview fields kept for UI / compact history paths
            "output": result.get("output"),
        }
        for key in (
            "stdout",
            "stderr",
            # Full raw fields for short-lived working material / exact reasoning
            "raw_output",
            "stdout_full",
            "stderr_full",
            "raw_output_truncated",
            "raw_output_chars",
            "raw_output_total_chars",
            "result_count",
            "exit_code",
            "view",
            "history_self_reference_only",
            "real_usage_evidence",
            "truncated",
            "history_compact",
        ):
            if key in result:
                payload[key] = result.get(key)

        add_material(
            payload,
            msg_type="turn_working_material",
            turn_id=turn_id,
        )

    def _check_python_syntax(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source)
            return None
        except SyntaxError as e:
            return f"Line {e.lineno}: {e.msg}\n{e.text}"
        except Exception as e:
            return str(e)