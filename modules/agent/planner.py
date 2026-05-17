"""Subgoal-board XML protocol for current active intent orchestration."""

from __future__ import annotations

import re
from copy import deepcopy


ALLOWED_STEP_STATUSES = {"todo", "in_progress", "done", "blocked"}
ALLOWED_SUBGOAL_ACTIONS = {
    "create",
    "modify",
    "mark_done",
    "mark_blocked",
    "mark_todo",
    "mark_in_progress",
    "remove",
    "reorder",
    "clear_all",
}


class TaskBoardPlanner:
    """Parses, validates, and applies flat XML subgoal mutations."""

    SUBGOAL_TAG_RE = re.compile(
        r"<subgoal\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</subgoal>|(?P<selfclose>/\s*>))",
        re.IGNORECASE | re.DOTALL,
    )
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

    def __init__(self, config, logger=None):
        self.config = config
        self.log = logger

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.config, "PLANNER_ENABLED", False))

    @property
    def mode(self) -> str:
        mode = str(getattr(self.config, "PLANNER_MODE", "auto") or "auto").strip().lower()
        if mode not in {"auto", "always"}:
            return "auto"
        return mode

    def build_protocol_instructions(self) -> str:
        return (
            "## SUBGOAL BOARD XML PROTOCOL\n"
            "The subgoal board belongs to the CURRENT ACTIVE INTENT. Do not repeat intent_id in subgoal tags.\n"
            "Emit flat top-level <subgoal ...> XML tags. Do not wrap them inside a container tag.\n"
            "Each subgoal tag is an independent mutation applied to the current active intent subgoal board.\n"
            "Subgoal tags are optional for trivial one-step work, but required when decomposition is useful.\n"
            "Canonical syntax:\n"
            "- <subgoal action=\"create\" id=\"sg_1\" status=\"todo|in_progress|done|blocked\">Meaningful subgoal</subgoal>\n"
            "- <subgoal action=\"modify\" id=\"sg_1\" status=\"todo|in_progress|done|blocked\">Updated title</subgoal>\n"
            "- <subgoal action=\"mark_done\" id=\"sg_1\" evidence=\"tool:read_file path.py lines 10-20\" />\n"
            "- <subgoal action=\"mark_todo\" id=\"sg_1\" />\n"
            "- <subgoal action=\"mark_in_progress\" id=\"sg_1\" />\n"
            "- <subgoal action=\"mark_blocked\" id=\"sg_1\" reason=\"Short blocking reason\" />\n"
            "- <subgoal action=\"remove\" id=\"sg_1\" reason=\"Why this is no longer needed\" />\n"
            "- <subgoal action=\"reorder\" id=\"sg_3\" after=\"sg_1\" />\n"
            "- <subgoal action=\"clear_all\" />\n"
            "Rules:\n"
            "- Each id must be stable.\n"
            "- Each subgoal must be a meaningful subproblem, not a trivial tool click.\n"
            "- Prefer a few strong subgoals over many micro-steps.\n"
            "- Use memory tags to explain WHY the subgoal board changed; use subgoal tags to change the board state.\n"
        )

    def _mask_think_blocks(self, response_text: str) -> str:
        def _mask(match: re.Match) -> str:
            return " " * (match.end() - match.start())

        return self.THINK_TAG_RE.sub(_mask, response_text)

    def _parse_attrs(self, attrs_raw: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        if not isinstance(attrs_raw, str) or not attrs_raw.strip():
            return attrs
        cleaned = attrs_raw.strip()
        if cleaned.endswith("/"):
            cleaned = cleaned[:-1].rstrip()
        for key, v1, v2 in self.ATTR_RE.findall(cleaned):
            attrs[str(key).strip().lower()] = str(v1 or v2 or "").strip()
        return attrs

    def _normalize_text(self, value: str) -> str:
        return " ".join(str(value or "").strip().split())

    def _normalize_status(self, value: str | None, *, default: str | None = None) -> str | None:
        raw = str(value or default or "").strip().lower()
        if not raw:
            return default
        return raw if raw in ALLOWED_STEP_STATUSES else None

    def extract_update_and_strip(self, response_text: str) -> tuple[str, list[dict] | None, str | None]:
        """Extract plan mutations from response and strip plan tags from text."""
        if not isinstance(response_text, str) or not response_text:
            return response_text, None, None

        masked = self._mask_think_blocks(response_text)
        matches = list(self.SUBGOAL_TAG_RE.finditer(masked))
        if not matches:
            return response_text, None, None

        ops: list[dict] = []
        spans: list[tuple[int, int]] = []
        for match in matches:
            original = response_text[match.start() : match.end()]
            op, error = self._parse_operation(original)
            if error:
                clean_text = self._strip_spans(response_text, spans + [match.span()])
                return clean_text, None, error
            if op is not None:
                ops.append(op)
                spans.append(match.span())

        clean_text = self._strip_spans(response_text, spans)
        return clean_text, ops, None

    def _strip_spans(self, text: str, spans: list[tuple[int, int]]) -> str:
        if not spans:
            return text
        out = []
        cursor = 0
        for start, end in spans:
            out.append(text[cursor:start])
            cursor = end
        out.append(text[cursor:])
        cleaned = "".join(out)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _parse_operation(self, tag_text: str) -> tuple[dict | None, str | None]:
        match = self.SUBGOAL_TAG_RE.fullmatch(tag_text.strip())
        if not match:
            return None, "invalid_subgoal_tag_syntax"

        attrs = self._parse_attrs(match.group("attrs") or "")
        body = self._normalize_text(match.group("body") or "")
        action = str(attrs.get("action") or "").strip().lower()
        step_id = str(attrs.get("id") or "").strip()

        if action not in ALLOWED_SUBGOAL_ACTIONS:
            return None, "subgoal_action_invalid"

        if action != "clear_all" and not step_id:
            return None, f"subgoal_{action}_id_required"

        if action == "create":
            status = self._normalize_status(attrs.get("status"), default="todo")
            if status is None:
                return None, "subgoal_create_bad_status"
            if not body:
                return None, "subgoal_create_title_required"
            return {
                "op": action,
                "step_id": step_id,
                "status": status,
                "title": body,
            }, None

        if action == "modify":
            status = self._normalize_status(attrs.get("status"))
            if attrs.get("status") is not None and status is None:
                return None, "subgoal_modify_bad_status"
            if not body and status is None:
                return None, "subgoal_modify_empty"
            op = {"op": action, "step_id": step_id}
            if body:
                op["title"] = body
            if status is not None:
                op["status"] = status
            return op, None

        if action == "mark_done":
            evidence = self._normalize_text(attrs.get("evidence") or "")
            if not evidence:
                return None, "subgoal_mark_done_evidence_required"
            return {
                "op": action,
                "step_id": step_id,
                "status": "done",
                "evidence": evidence,
            }, None

        if action == "mark_blocked":
            reason = self._normalize_text(attrs.get("reason") or body or "")
            if not reason:
                return None, "subgoal_mark_blocked_reason_required"
            return {
                "op": action,
                "step_id": step_id,
                "status": "blocked",
                "reason": reason,
            }, None

        if action in {"mark_todo", "mark_in_progress"}:
            status = action.replace("mark_", "")
            return {"op": action, "step_id": step_id, "status": status}, None

        if action == "remove":
            reason = self._normalize_text(attrs.get("reason") or "")
            if not reason:
                return None, "subgoal_remove_reason_required"
            return {"op": action, "step_id": step_id, "reason": reason}, None

        if action == "reorder":
            after_step_id = str(attrs.get("after") or "").strip()
            if not after_step_id:
                return None, "subgoal_reorder_after_required"
            return {"op": action, "step_id": step_id, "after_step_id": after_step_id}, None

        if action == "clear_all":
            return {"op": action}, None

        return None, "unsupported_subgoal_action"

    def _default_goal(self, state) -> str:
        active_intent = getattr(state, "active_intent", None)
        goal = str(getattr(active_intent, "goal", "") or "").strip()
        if goal:
            return goal[: int(getattr(self.config, "PLANNER_MAX_GOAL_CHARS", 240))]
        board = getattr(state, "task_board", None)
        if isinstance(board, dict):
            return str(board.get("goal", "") or "").strip()
        return ""

    def _active_board_owner(self, state) -> tuple[str, str]:
        active_intent = getattr(state, "active_intent", None)
        if active_intent is None:
            return "", ""
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        lineage_id = str(getattr(active_intent, "lineage_id", "") or intent_id or "").strip()
        return intent_id, lineage_id

    def bind_board_to_active_intent(self, state, board: dict | None) -> dict | None:
        if not isinstance(board, dict):
            return None
        intent_id, lineage_id = self._active_board_owner(state)
        board["intent_id"] = intent_id
        board["lineage_id"] = lineage_id
        return board

    def board_matches_active_intent(self, state, board: dict | None) -> bool:
        if not isinstance(board, dict):
            return False
        active_intent = getattr(state, "active_intent", None)
        if active_intent is None:
            return False
        active_intent_id, active_lineage_id = self._active_board_owner(state)
        board_intent_id = str(board.get("intent_id", "") or "").strip()
        board_lineage_id = str(board.get("lineage_id", "") or "").strip()
        if board_lineage_id and board_lineage_id == active_lineage_id:
            return True
        if board_intent_id and board_intent_id == active_intent_id:
            return True
        return False

    def normalize_board_for_active_intent(self, state, board: dict | None) -> dict | None:
        if not isinstance(board, dict):
            return None
        steps = board.get("steps")
        if not isinstance(steps, list) or not steps:
            return None
        if not self.board_matches_active_intent(state, board):
            return None
        return self.bind_board_to_active_intent(state, deepcopy(board))

    def _new_board(self, state) -> dict:
        board = {
            "version": 2,
            "goal": self._default_goal(state),
            "active_step_id": None,
            "steps": [],
        }
        return self.bind_board_to_active_intent(state, board) or board

    def _steps(self, board: dict) -> list[dict]:
        steps = board.get("steps")
        if not isinstance(steps, list):
            board["steps"] = []
        return board["steps"]

    def _index_of_step(self, steps: list[dict], step_id: str) -> int:
        for idx, step in enumerate(steps):
            if str(step.get("id") or "").strip() == step_id:
                return idx
        return -1

    def _normalize_step_title_for_dedupe(self, title: str) -> str:
        return self._normalize_text(title).casefold()

    def _index_of_duplicate_active_title(self, steps: list[dict], title: str, *, exclude_step_id: str = "") -> int:
        normalized_title = self._normalize_step_title_for_dedupe(title)
        if not normalized_title:
            return -1
        excluded = str(exclude_step_id or "").strip()
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            if excluded and str(step.get("id") or "").strip() == excluded:
                continue
            if step.get("status") not in {"todo", "in_progress", "blocked"}:
                continue
            if self._normalize_step_title_for_dedupe(str(step.get("title") or "")) == normalized_title:
                return idx
        return -1

    def _ensure_active_step(self, board: dict) -> None:
        steps = self._steps(board)
        valid_ids = {str(step.get("id") or "").strip() for step in steps}
        active_step_id = str(board.get("active_step_id") or "").strip()
        if active_step_id and active_step_id in valid_ids:
            return

        for preferred_status in ("in_progress", "todo", "blocked"):
            for step in steps:
                if step.get("status") == preferred_status:
                    board["active_step_id"] = step.get("id")
                    return
        board["active_step_id"] = None

    def _enforce_step_limit(self, board: dict) -> None:
        steps = self._steps(board)
        max_steps = max(1, int(getattr(self.config, "PLANNER_MAX_STEPS", 12) or 12))
        if len(steps) <= max_steps:
            return
        del steps[max_steps:]

    def apply_update(self, state, update_ops: list[dict]) -> tuple[bool, dict]:
        """Applies validated plan mutations to runtime state."""
        if not isinstance(update_ops, list) or not update_ops:
            return False, "No plan changes."

        previous = deepcopy(getattr(state, "task_board", None))
        normalized_previous = self.normalize_board_for_active_intent(state, previous)
        board = normalized_previous if isinstance(normalized_previous, dict) else self._new_board(state)
        board["version"] = 2
        board["goal"] = self._default_goal(state)
        steps = self._steps(board)

        for op in update_ops:
            name = str(op.get("op") or "").strip().lower()
            step_id = str(op.get("step_id") or "").strip()

            if name == "clear_all":
                board["steps"] = []
                board["active_step_id"] = None
                steps = board["steps"]
                continue

            if name == "create":
                title = str(op.get("title") or "").strip()[: int(getattr(self.config, "PLANNER_MAX_STEP_TITLE_CHARS", 160))]
                status = op.get("status") or "todo"
                idx = self._index_of_step(steps, step_id)
                if idx < 0:
                    idx = self._index_of_duplicate_active_title(steps, title, exclude_step_id=step_id)
                step = {
                    "id": step_id,
                    "title": title,
                    "status": status,
                }
                if idx >= 0:
                    existing_id = str(steps[idx].get("id") or "").strip()
                    if existing_id and existing_id != step_id:
                        step["id"] = existing_id
                    steps[idx].update(step)
                else:
                    steps.append(step)
                if step["status"] == "in_progress":
                    board["active_step_id"] = step["id"]
                continue

            if name == "modify":
                idx = self._index_of_step(steps, step_id)
                if idx < 0:
                    continue
                if "title" in op:
                    steps[idx]["title"] = str(op.get("title") or "").strip()[: int(getattr(self.config, "PLANNER_MAX_STEP_TITLE_CHARS", 160))]
                if "status" in op:
                    steps[idx]["status"] = op["status"]
                    if op["status"] == "in_progress":
                        board["active_step_id"] = step_id
                continue

            if name in {"mark_done", "mark_todo", "mark_in_progress", "mark_blocked"}:
                idx = self._index_of_step(steps, step_id)
                if idx < 0:
                    continue
                steps[idx]["status"] = op["status"]
                if name == "mark_done" and op.get("evidence"):
                    steps[idx]["notes"] = str(op.get("evidence") or "").strip()[: int(getattr(self.config, "PLANNER_MAX_STEP_NOTES_CHARS", 240))]
                if name == "mark_blocked" and op.get("reason"):
                    steps[idx]["notes"] = str(op.get("reason") or "").strip()[: int(getattr(self.config, "PLANNER_MAX_STEP_NOTES_CHARS", 240))]
                if op["status"] == "in_progress":
                    board["active_step_id"] = step_id
                elif str(board.get("active_step_id") or "").strip() == step_id and op["status"] != "in_progress":
                    board["active_step_id"] = None
                continue

            if name == "remove":
                idx = self._index_of_step(steps, step_id)
                if idx < 0:
                    continue
                steps.pop(idx)
                if str(board.get("active_step_id") or "").strip() == step_id:
                    board["active_step_id"] = None
                continue

            if name == "reorder":
                idx = self._index_of_step(steps, step_id)
                after_idx = self._index_of_step(steps, str(op.get("after_step_id") or "").strip())
                if idx < 0 or after_idx < 0 or idx == after_idx:
                    continue
                step = steps.pop(idx)
                if idx < after_idx:
                    after_idx -= 1
                steps.insert(after_idx + 1, step)

        self._enforce_step_limit(board)
        self._ensure_active_step(board)
        self.bind_board_to_active_intent(state, board)
        state.task_board = board
        state.task_board_enabled = bool(board.get("steps"))
        return True, self.render_chat_update_payload(previous, board)

    def render_compact_summary(self, board: dict) -> str:
        steps = board.get("steps") or []
        total = len(steps)
        done = sum(1 for s in steps if s.get("status") == "done")
        blocked = sum(1 for s in steps if s.get("status") == "blocked")
        active = board.get("active_step_id")
        return f"goal='{board.get('goal', '')[:80]}', done={done}/{total}, blocked={blocked}, active={active or '-'}"

    def render_runtime_snapshot(self, board: dict) -> str:
        """Returns compact canonical board projection for the next model step."""
        if not isinstance(board, dict) or not board.get("steps"):
            return ""
        goal = str(board.get("goal", "")).strip()
        steps = board.get("steps") or []
        active = board.get("active_step_id")
        max_visible = int(getattr(self.config, "PLANNER_MAX_VISIBLE_STEPS", 4))

        def _line(step: dict) -> str:
            sid = step.get("id", "?")
            title = str(step.get("title", "")).strip()
            status = step.get("status", "todo")
            return f"- {sid} [{status}] {title[:140]}"

        ordered = []
        if active:
            active_step = next((s for s in steps if s.get("id") == active), None)
            if active_step:
                ordered.append(active_step)
        for step in steps:
            if step in ordered:
                continue
            if step.get("status") in {"todo", "in_progress", "blocked"}:
                ordered.append(step)
            if len(ordered) >= max_visible:
                break

        done = sum(1 for s in steps if s.get("status") == "done")
        lines = ["## CURRENT PLAN BOARD"]
        lines.append("This board is canonical runtime state for decomposition of the current active intent.")
        lines.append(f"goal: {goal[:180] or '<none>'}")
        lines.append(f"progress: done={done}/{len(steps)} active={active or '-'}")
        for step in ordered[:max_visible]:
            lines.append(_line(step))
        return "\n".join(lines)

    def render_board_for_chat(self, board: dict) -> str:
        """Human-friendly compact board for visible chat messages."""
        if not isinstance(board, dict) or not board.get("steps"):
            return "План зараз порожній."
        goal = str(board.get("goal", "")).strip()
        active = board.get("active_step_id")
        steps = board.get("steps") or []
        max_visible = int(getattr(self.config, "PLANNER_MAX_VISIBLE_STEPS", 4))
        lines = ["План задач"]
        if goal:
            lines.append(f"Ціль: {goal[:120]}")

        active_step = None
        if active:
            active_step = next((s for s in steps if s.get("id") == active), None)
        if active_step:
            lines.append(f"Зараз у роботі: {str(active_step.get('title', '')).strip()[:120]}")

        upcoming = []
        for step in steps:
            if step is active_step:
                continue
            if step.get("status") in {"todo", "in_progress", "blocked"}:
                upcoming.append(step)
            if len(upcoming) >= max_visible:
                break

        if upcoming:
            lines.append("Наступні кроки:")
            for step in upcoming:
                status = step.get("status")
                prefix = "•"
                if status == "blocked":
                    prefix = "⚠"
                elif status == "in_progress":
                    prefix = "→"
                lines.append(f"{prefix} {str(step.get('title', '')).strip()[:110]}")

        done = sum(1 for s in steps if s.get("status") == "done")
        blocked = sum(1 for s in steps if s.get("status") == "blocked")
        lines.append(f"Прогрес: виконано {done} з {len(steps)}" + (f", заблоковано {blocked}" if blocked else ""))
        return "\n".join(lines)

    def render_update_delta(self, previous: dict | None, current: dict) -> str:
        """Short update summary for chat/history."""
        if not isinstance(previous, dict) or not previous.get("steps"):
            return "План створено."
        prev_steps = {str(s.get("id")): s for s in (previous.get("steps") or []) if isinstance(s, dict)}
        curr_steps = {str(s.get("id")): s for s in (current.get("steps") or []) if isinstance(s, dict)}

        added = [sid for sid in curr_steps.keys() if sid not in prev_steps]
        removed = [sid for sid in prev_steps.keys() if sid not in curr_steps]
        changed = []
        for sid, step in curr_steps.items():
            prev = prev_steps.get(sid)
            if not prev:
                continue
            prev_status = prev.get("status")
            curr_status = step.get("status")
            prev_title = str(prev.get("title", "")).strip()
            curr_title = str(step.get("title", "")).strip()
            if prev_status != curr_status:
                changed.append(f"{sid}:{prev_status}->{curr_status}")
            elif prev_title != curr_title:
                changed.append(f"{sid}:title")

        active_prev = previous.get("active_step_id")
        active_curr = current.get("active_step_id")
        parts = []
        if added:
            parts.append(f"додано кроків: {len(added)}")
        if removed:
            parts.append(f"прибрано кроків: {len(removed)}")
        if changed:
            parts.append("змінено: " + ", ".join(changed[:4]))
        if active_prev != active_curr:
            curr = curr_steps.get(str(active_curr), {})
            parts.append(f"поточний крок: {str(curr.get('title', '')).strip()[:90] or '-'}")
        if not parts:
            parts.append("План уточнено.")
        return " ".join(parts)

    def render_human_summary(self, board: dict) -> str:
        steps = board.get("steps") or []
        done = sum(1 for s in steps if s.get("status") == "done")
        active = board.get("active_step_id")
        active_title = ""
        if active:
            active_step = next((s for s in steps if s.get("id") == active), None)
            if active_step:
                active_title = str(active_step.get("title", "")).strip()[:100]
        if active_title:
            return f"План оновлено. Зараз: {active_title}. Прогрес {done}/{len(steps)}."
        return f"План оновлено. Прогрес {done}/{len(steps)}."

    def render_chat_update_payload(self, previous: dict | None, current: dict) -> dict:
        steps = [s for s in (current.get("steps") or []) if isinstance(s, dict)]
        total = len(steps)
        completed = sum(1 for s in steps if s.get("status") == "done")

        active_step_id = str(current.get("active_step_id") or "").strip()
        current_step = None
        if active_step_id:
            current_step = next((s for s in steps if str(s.get("id") or "").strip() == active_step_id), None)
        if current_step is None:
            current_step = next((s for s in steps if s.get("status") == "in_progress"), None)
        if current_step is None:
            current_step = next((s for s in steps if s.get("status") in {"todo", "blocked"}), None)

        current_title = ""
        if current_step is not None:
            current_title = str(current_step.get("title", "")).strip()
        if not current_title:
            current_title = str(current.get("goal", "")).strip()

        prev_steps = {}
        if isinstance(previous, dict):
            prev_steps = {
                str(s.get("id")): s
                for s in (previous.get("steps") or [])
                if isinstance(s, dict) and str(s.get("id") or "").strip()
            }

        changed_steps: list[dict] = []
        for step in steps:
            step_id = str(step.get("id") or "").strip()
            if not step_id:
                continue
            status = str(step.get("status") or "").strip()
            prev = prev_steps.get(step_id)
            prev_status = str(prev.get("status") or "").strip() if isinstance(prev, dict) else ""
            if prev is None or prev_status != status:
                changed_steps.append({"id": step_id, "status": status})

        return {
            "kind": "plan_update",
            "completed": completed,
            "total": total,
            "current_title": current_title,
            "changed_steps": changed_steps,
        }
