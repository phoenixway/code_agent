from __future__ import annotations

from modules.agent.orchestration.protocol import ProtocolCompiler, ResponseShape


def test_intent_action_bundle_lowers_to_ir_proposal():
    compiler = ProtocolCompiler()

    analysis = compiler.analyze(
        '<intent mode="activate">{"intent_id":"save_doc","intent_type":"MODIFY","goal":"Save analysis","allowed_actions":["write_file_block"],"mode":"activate","switch_reason":"user_requested_save"}</intent>\n'
        '<action>{"type":"write_file_block","path":"docs/out.md","overwrite":true}</action>\n'
        "<file_content>\n# Saved\n</file_content>"
    )

    assert analysis.shape == ResponseShape.INTENT_ACTION_BUNDLE
    assert analysis.error is None
    assert analysis.ir is not None
    assert len(analysis.ir.intent_ops) == 1
    assert len(analysis.ir.action_ops) == 1
    assert analysis.ir.file_content == "\n# Saved\n"
    assert analysis.ir.intent_ops[0].intent_id == "save_doc"
    assert analysis.ir.action_ops[0].action_type == "write_file_block"
    assert analysis.ir.action_ops[0].write_like is True
    assert analysis.ir.annotations == ()
    assert [effect.summary for effect in analysis.ir.effects_preview] == [
        "activate:MODIFY:save_doc",
        "write_file_block:with_file_content",
    ]


def test_plaintext_only_lowers_to_final_answer_ir():
    compiler = ProtocolCompiler()

    analysis = compiler.analyze("Ось відповідь.\nТег `<action>` тут лише як приклад.")

    assert analysis.shape == ResponseShape.PURE_PLAINTEXT
    assert analysis.error is None
    assert analysis.ir is not None
    assert analysis.ir.visible_answer == "Ось відповідь.\nТег `<action>` тут лише як приклад."
    assert analysis.ir.intent_ops == ()
    assert analysis.ir.action_ops == ()
    assert [effect.kind for effect in analysis.ir.effects_preview] == ["final_answer"]


def test_memory_text_lowers_think_to_annotation_only():
    compiler = ProtocolCompiler()

    analysis = compiler.analyze(
        "<think>Need to checkpoint the discovered path.</think>\n"
        '<path scope="intent">modules/x.py</path>\n'
        "<memory_update_done />\n"
        "Next, inspect the file."
    )

    assert analysis.shape == ResponseShape.MEMORY_TEXT
    assert analysis.error is None
    assert analysis.ir is not None
    assert len(analysis.ir.annotations) == 1
    assert analysis.ir.annotations[0].kind == "think"
    assert len(analysis.ir.board_ops) == 2
    assert analysis.ir.board_ops[0].kind == "path"
    assert analysis.ir.board_ops[1].kind == "memory_update_done"
    assert analysis.ir.visible_answer == "Next, inspect the file."
