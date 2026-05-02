import json
from pathlib import Path
from types import SimpleNamespace

from modules.agent.action_dispatcher import ActionDispatcher
from modules.history import HistoryManager


class DummyUI:
    async def print_tool_call(self, command):
        return object()

    async def start_action(self, message):
        return None

    async def update_tool_call(self, widget, command, result):
        return None


def _history(tmp_path):
    return HistoryManager(
        chat_provider=None,
        storage_dir=str(tmp_path / ".angelica"),
        max_tokens=20000,
    )


def _working_payloads_for_path(history, path):
    out = []
    for msg in history.messages:
        if not msg.get("turn_working_material"):
            continue
        payload = msg.get("content")
        if isinstance(payload, dict) and (payload.get("path") == path or payload.get("filename") == path):
            out.append(payload)
    return out


def _all_payloads_for_path(history, path):
    out = []
    for msg in history.messages:
        payload = msg.get("content")
        if isinstance(payload, dict) and (payload.get("path") == path or payload.get("filename") == path):
            out.append(payload)
    return out


def test_update_file_state_after_edit_invalidates_old_read_and_chunk_working_material(tmp_path):
    history = _history(tmp_path)
    history.current_turn_id = 1

    target = str(tmp_path / "sample.py")
    Path(target).write_text("value = 'old'\n", encoding="utf-8")

    initial = history.update_file_state(
        target,
        "value = 'old'\n",
        source_tool="read_file",
        invalidate_stale=False,
    )
    old_version = initial["version"]

    history.add_transient_file_content(target, old_version, "value = 'old'\n")
    history.add_turn_working_material(
        {
            "tool": "read_chunk",
            "path": target,
            "filename": target,
            "version": old_version,
            "file_version": old_version,
            "file_content": "value = 'old'",
            "output": "value = 'old'",
            "status": "success",
            "start_line": 1,
            "end_line": 1,
        },
        turn_id=history.current_turn_id,
    )

    assert len(_working_payloads_for_path(history, target)) == 2

    Path(target).write_text("value = 'new'\n", encoding="utf-8")
    refreshed = history.update_file_state_from_disk(
        target,
        source_tool="edit_file",
        invalidate_stale=True,
    )

    assert refreshed["version"] == old_version + 1
    assert refreshed["stale_working_material_invalidated"] == 2

    current = history.get_current_file_state(target)
    assert current is not None
    assert current["version"] == old_version + 1
    assert current["file_content"] == "value = 'new'\n"

    # Old exact read/chunk outputs are preserved only as ordinary history, not
    # as protected working material that the model should treat as current.
    assert _working_payloads_for_path(history, target) == []
    stale_payloads = _all_payloads_for_path(history, target)
    assert stale_payloads
    assert all(payload.get("stale") is True for payload in stale_payloads)
    assert all(payload.get("superseded_by_file_version") == old_version + 1 for payload in stale_payloads)


def test_current_file_state_block_uses_latest_content_after_mutation(tmp_path):
    history = _history(tmp_path)
    target = str(tmp_path / "sample.py")

    history.update_file_state(target, "before = True\n", source_tool="read_file", invalidate_stale=False)
    history.update_file_state(target, "after = True\n", source_tool="edit_file", invalidate_stale=True)

    api_history = history.get_history_for_api()
    current_state_blocks = [
        msg["content"]
        for msg in api_history
        if msg.get("role") == "system" and str(msg.get("content") or "").startswith("## CURRENT FILE STATE")
    ]

    assert current_state_blocks
    current_state = "\n".join(current_state_blocks)
    assert "after = True" in current_state
    assert "before = True" not in current_state


def test_successful_edit_file_refreshes_history_current_file_state_from_disk(tmp_path):
    history = _history(tmp_path)
    target = tmp_path / "sample.py"
    target.write_text("old = 1\n", encoding="utf-8")

    old = history.update_file_state(
        str(target),
        "old = 1\n",
        source_tool="read_file",
        invalidate_stale=False,
    )
    history.add_transient_file_content(str(target), old["version"], "old = 1\n")

    agent = SimpleNamespace(
        ui=DummyUI(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(),
        history=history,
        log=None,
    )
    dispatcher = ActionDispatcher(agent)

    target.write_text("new = 2\n", encoding="utf-8")
    dispatcher._refresh_current_file_state_after_success(
        {"type": "edit_file", "path": str(target)},
        {"status": "success", "output": "Edited file"},
    )

    current = history.get_current_file_state(str(target))
    assert current is not None
    assert current["file_content"] == "new = 2\n"
    assert current["source_tool"] == "edit_file"

    assert _working_payloads_for_path(history, str(target)) == []


def test_failed_edit_file_does_not_refresh_current_file_state_or_invalidate_working_material(tmp_path):
    history = _history(tmp_path)
    target = tmp_path / "sample.py"
    target.write_text("old = 1\n", encoding="utf-8")

    old = history.update_file_state(
        str(target),
        "old = 1\n",
        source_tool="read_file",
        invalidate_stale=False,
    )
    history.add_transient_file_content(str(target), old["version"], "old = 1\n")

    agent = SimpleNamespace(
        ui=DummyUI(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(),
        history=history,
        log=None,
    )
    dispatcher = ActionDispatcher(agent)

    target.write_text("new = 2\n", encoding="utf-8")
    dispatcher._refresh_current_file_state_after_success(
        {"type": "edit_file", "path": str(target)},
        {"status": "failed", "output": "SEARCH_BLOCK_NOT_FOUND"},
    )

    current = history.get_current_file_state(str(target))
    assert current is not None
    assert current["file_content"] == "old = 1\n"
    assert len(_working_payloads_for_path(history, str(target))) == 1
    assert _working_payloads_for_path(history, str(target))[0].get("stale") is not True


def test_write_file_block_refreshes_current_file_state_from_disk(tmp_path):
    history = _history(tmp_path)
    target = tmp_path / "sample.py"

    agent = SimpleNamespace(
        ui=DummyUI(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(),
        history=history,
        log=None,
    )
    dispatcher = ActionDispatcher(agent)

    target.write_text("created = True\n", encoding="utf-8")
    dispatcher._refresh_current_file_state_after_success(
        {"type": "write_file_block", "path": str(target)},
        {"status": "success", "output": "Wrote file"},
    )

    current = history.get_current_file_state(str(target))
    assert current is not None
    assert current["file_content"] == "created = True\n"
    assert current["source_tool"] == "write_file_block"


def test_append_file_block_refreshes_current_file_state_from_disk(tmp_path):
    history = _history(tmp_path)
    target = tmp_path / "sample.py"
    target.write_text("head = 1\n", encoding="utf-8")

    history.update_file_state(
        str(target),
        "head = 1\n",
        source_tool="read_file",
        invalidate_stale=False,
    )

    agent = SimpleNamespace(
        ui=DummyUI(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(),
        history=history,
        log=None,
    )
    dispatcher = ActionDispatcher(agent)

    target.write_text("head = 1\ntail = 2\n", encoding="utf-8")
    dispatcher._refresh_current_file_state_after_success(
        {"type": "append_file_block", "path": str(target)},
        {"status": "success", "output": "Appended file"},
    )

    current = history.get_current_file_state(str(target))
    assert current is not None
    assert current["file_content"] == "head = 1\ntail = 2\n"
    assert "tail = 2" in current["file_content"]
    assert current["source_tool"] == "append_file_block"


def test_large_file_mutation_invalidates_old_snippets_without_blocking(tmp_path):
    history = _history(tmp_path)
    history.MAX_CANONICAL_FILE_CACHE_BYTES = 64
    history.current_turn_id = 1

    target = str(tmp_path / "large.py")
    Path(target).write_text("x = 1\n", encoding="utf-8")
    initial = history.update_file_state(target, "x = 1\n", source_tool="read_file", invalidate_stale=False)
    history.add_transient_file_content(target, initial["version"], "x = 1\n")

    large_body = "value = 1\n" + ("A" * 2048)
    Path(target).write_text(large_body, encoding="utf-8")
    refreshed = history.update_file_state_from_disk(
        target,
        source_tool="write_file_block",
        invalidate_stale=True,
    )

    assert refreshed["version"] == initial["version"] + 1
    assert refreshed["stale_working_material_invalidated"] == 1

    current = history.get_current_file_state(target)
    assert current is not None
    assert current["version"] == initial["version"] + 1
    assert current["file_content"] == ""
    assert current.get("content_elided") is True
    assert current.get("content_hash")

    stale_payloads = _all_payloads_for_path(history, target)
    assert stale_payloads
    assert any(payload.get("stale") is True for payload in stale_payloads)
