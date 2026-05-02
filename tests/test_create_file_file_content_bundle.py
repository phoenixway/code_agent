from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.parser import ResponseParser
from modules.processor import ResponseProcessor


class DummyUI:
    async def print_tool_call(self, command):
        return object()

    async def start_action(self, message):
        return None

    async def update_tool_call(self, widget, command, result):
        return None


class RecordingTools:
    def __init__(self):
        self.calls = []

    async def call(self, action_type, ui=None, **args):
        self.calls.append((action_type, args))
        if action_type == "create_file":
            path = Path(args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return {"status": "success", "output": f"Created {args['path']}"}
        if action_type == "write_file_block":
            path = Path(args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["file_content"], encoding="utf-8")
            return {"status": "success", "output": f"Wrote {args['path']}"}
        return {"status": "success", "output": "ok"}


class AllowAllPolicy:
    async def check(self, normalized_cmd):
        return True


def _processor(tmp_path):
    tools = RecordingTools()
    processor = ResponseProcessor(DummyUI(), tools, None, AllowAllPolicy(), history=None)
    return processor, tools


def test_create_file_accepts_following_file_content():
    response = (
        '<action>{"type":"create_file","path":"tmp/Example.kt"}</action>\n'
        "<file_content>\n"
        "package tmp\n\n"
        "fun main() {\n"
        '    println("hello")\n'
        "}\n"
        "</file_content>"
    )
    segments = ResponseParser().parse(response)
    action = next(seg.content for seg in segments if seg.type == "action")
    assert action["type"] == "create_file"
    assert action["file_content"] == 'package tmp\n\nfun main() {\n    println("hello")\n}\n'


@pytest.mark.asyncio
async def test_create_file_bundle_dispatches_content(tmp_path):
    processor, tools = _processor(tmp_path)
    response = (
        '<action>{"type":"create_file","path":"'
        + str(tmp_path / "tmp/Example.kt")
        + '"}</action>\n'
        "<file_content>\n"
        "package tmp\n\n"
        "fun main() {\n"
        '    println("hello")\n'
        "}\n"
        "</file_content>"
    )
    action = next(seg.content for seg in ResponseParser().parse(response) if seg.type == "action")
    result = await processor.process_single_action(action)

    assert result["status"] == "success"
    dispatched = tools.calls[-1][1]
    assert dispatched["content"] == 'package tmp\n\nfun main() {\n    println("hello")\n}\n'


@pytest.mark.asyncio
async def test_create_file_with_json_content_still_works(tmp_path):
    processor, tools = _processor(tmp_path)
    action = {"type": "create_file", "path": str(tmp_path / "tmp/Example.kt"), "content": "hello"}
    result = await processor.process_single_action(action)

    assert result["status"] == "success"
    assert tools.calls[-1][1]["content"] == "hello"


@pytest.mark.asyncio
async def test_create_file_without_content_and_without_file_content_still_fails(tmp_path):
    processor, _tools = _processor(tmp_path)
    action = {"type": "create_file", "path": str(tmp_path / "tmp/Example.kt")}
    result = await processor.process_single_action(action)

    assert result["status"] == "failed"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "requires file body" in result["output"]
    assert "following" in result["output"] or "<file_content>" in result["output"]


@pytest.mark.asyncio
async def test_write_file_block_behavior_unchanged(tmp_path):
    processor, tools = _processor(tmp_path)
    action = {"type": "write_file_block", "path": str(tmp_path / "tmp/Example.kt"), "file_content": "hello"}
    result = await processor.process_single_action(action)

    assert result["status"] == "success"
    assert tools.calls[-1][0] == "write_file_block"
    assert tools.calls[-1][1]["file_content"] == "hello"
