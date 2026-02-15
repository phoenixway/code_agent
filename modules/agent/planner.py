"""Planner protocol for optional task-board driven orchestration."""

from __future__ import annotations

import json
import re
from copy import deepcopy


ALLOWED_STEP_STATUSES = {"todo", "in_progress", "done", "blocked"}


class TaskBoardPlanner:
    """Parses and validates task-board updates produced by the model."""

    _TAG_RE = re.compile(r"<taskboard>(.*?)</taskboard>", re.IGNORECASE | re.DOTALL)

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
        """Protocol block appended to system prompt when planner is enabled."""
        if self.mode == "always":
            mode_rules = (
                "Planner mode is ALWAYS.\n"
                "You MUST include exactly one <taskboard> JSON block in every response.\n"
                "If you return an <action>, return <taskboard> before it.\n"
            )
        else:
            mode_rules = (
                "Planner mode is AUTO.\n"
                "If the task is complex, you MAY include exactly one <taskboard> JSON block.\n"
                "For simple tasks, do not include <taskboard>.\n"
            )
        return (
            "## OPTIONAL TASKBOARD PROTOCOL\n"
            f"{mode_rules}"
            "Use strict JSON only.\n"
            "For simple requests, keep the taskboard minimal: 1 short step, empty notes, no extra detail.\n"
            "Do not bloat taskboard text for trivial read-only tasks.\n"
            "Schema:\n"
            "{\n"
            '  "version": 1,\n'
            '  "goal": "short goal",\n'
            '  "planner_enabled": true,\n'
            '  "active_step_id": "s1" or null,\n'
            '  "steps": [\n'
            '    {"id":"s1","title":"...","status":"todo|in_progress|done|blocked","notes":"optional short text"}\n'
            "  ]\n"
            "}\n"
            "Keep steps concise and bounded. Do not output markdown inside JSON."
        )

    def extract_update_and_strip(self, response_text: str) -> tuple[str, dict | None, str | None]:
        """
        Extracts the last <taskboard> block from response and removes all taskboard blocks.
        Returns: (clean_response_text, validated_update_or_none, error_or_none)
        """
        if not isinstance(response_text, str) or not response_text:
            return response_text, None, None

        matches = list(self._TAG_RE.finditer(response_text))
        if not matches:
            return response_text, None, None

        last_block = matches[-1].group(1).strip()
        clean_text = self._TAG_RE.sub("", response_text).strip()
        if not last_block:
            return clean_text, None, "empty_taskboard_block"

        try:
            payload = json.loads(last_block)
        except json.JSONDecodeError:
            return clean_text, None, "invalid_taskboard_json"

        valid, error = self._validate_payload(payload)
        if not valid:
            return clean_text, None, error
        return clean_text, payload, None

    def _validate_payload(self, payload: dict) -> tuple[bool, str | None]:
        if not isinstance(payload, dict):
            return False, "taskboard_payload_must_be_object"
        if payload.get("version") != 1:
            return False, "unsupported_taskboard_version"

        goal = payload.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            return False, "taskboard_goal_required"
        if len(goal) > int(getattr(self.config, "PLANNER_MAX_GOAL_CHARS", 240)):
            return False, "taskboard_goal_too_long"

        planner_enabled = payload.get("planner_enabled", True)
        if not isinstance(planner_enabled, bool):
            return False, "taskboard_planner_enabled_must_be_bool"

        steps = payload.get("steps")
        if not isinstance(steps, list):
            return False, "taskboard_steps_must_be_list"
        if not steps:
            return False, "taskboard_steps_empty"
        if len(steps) > int(getattr(self.config, "PLANNER_MAX_STEPS", 12)):
            return False, "taskboard_too_many_steps"

        ids = set()
        max_title = int(getattr(self.config, "PLANNER_MAX_STEP_TITLE_CHARS", 160))
        max_notes = int(getattr(self.config, "PLANNER_MAX_STEP_NOTES_CHARS", 240))
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                return False, f"taskboard_step_{idx}_must_be_object"
            sid = step.get("id")
            title = step.get("title")
            status = step.get("status")
            notes = step.get("notes", "")

            if not isinstance(sid, str) or not sid.strip():
                return False, f"taskboard_step_{idx}_id_required"
            if sid in ids:
                return False, f"taskboard_duplicate_step_id:{sid}"
            ids.add(sid)

            if not isinstance(title, str) or not title.strip():
                return False, f"taskboard_step_{sid}_title_required"
            if len(title) > max_title:
                return False, f"taskboard_step_{sid}_title_too_long"

            if status not in ALLOWED_STEP_STATUSES:
                return False, f"taskboard_step_{sid}_bad_status"

            if notes is not None and not isinstance(notes, str):
                return False, f"taskboard_step_{sid}_notes_must_be_string"
            if isinstance(notes, str) and len(notes) > max_notes:
                return False, f"taskboard_step_{sid}_notes_too_long"

        active_id = payload.get("active_step_id")
        if active_id is not None and active_id not in ids:
            return False, "taskboard_active_step_not_found"
        return True, None

    def should_activate_board(self, update_payload: dict) -> bool:
        if self.mode == "always":
            return True
        return bool(update_payload.get("planner_enabled", True))

    def apply_update(self, state, update_payload: dict) -> tuple[bool, str]:
        """Applies validated planner payload to runtime state."""
        previous = deepcopy(getattr(state, "task_board", None))
        if not self.should_activate_board(update_payload):
            state.task_board = None
            state.task_board_enabled = False
            return True, "Планувальник вимкнено для цього завдання."

        state.task_board = deepcopy(update_payload)
        state.task_board_enabled = True
        summary = self.render_human_summary(state.task_board)
        delta = self.render_update_delta(previous, state.task_board)
        return True, f"{summary}\n{delta}"

    def render_compact_summary(self, board: dict) -> str:
        steps = board.get("steps") or []
        total = len(steps)
        done = sum(1 for s in steps if s.get("status") == "done")
        blocked = sum(1 for s in steps if s.get("status") == "blocked")
        active = board.get("active_step_id")
        return f"goal='{board.get('goal', '')[:80]}', done={done}/{total}, blocked={blocked}, active={active or '-'}"

    def render_runtime_snapshot(self, board: dict) -> str:
        """Returns compact control text for the next model step."""
        if not isinstance(board, dict):
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

        # Show active first, then next non-done items.
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
        lines = [f"SYSTEM TASKBOARD SNAPSHOT: goal={goal[:180]}"]
        lines.append(f"SYSTEM TASKBOARD PROGRESS: done={done}/{len(steps)} active={active or '-'}")
        for step in ordered[:max_visible]:
            lines.append(_line(step))
        return "\n".join(lines)

    def render_board_for_chat(self, board: dict) -> str:
        """Human-friendly compact board for visible chat messages."""
        if not isinstance(board, dict):
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
        if not isinstance(previous, dict):
            return "План створено."
        prev_steps = {str(s.get("id")): s for s in (previous.get("steps") or []) if isinstance(s, dict)}
        curr_steps = {str(s.get("id")): s for s in (current.get("steps") or []) if isinstance(s, dict)}

        added = [sid for sid in curr_steps.keys() if sid not in prev_steps]
        changed = []
        for sid, step in curr_steps.items():
            prev = prev_steps.get(sid)
            if not prev:
                continue
            if prev.get("status") != step.get("status"):
                changed.append(f"{sid}:{prev.get('status')}->{step.get('status')}")

        active_prev = previous.get("active_step_id")
        active_curr = current.get("active_step_id")
        parts = []
        if added:
            parts.append(f"додано кроків: {len(added)}")
        if changed:
            parts.append("змінено статуси: " + ", ".join(changed[:4]))
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
