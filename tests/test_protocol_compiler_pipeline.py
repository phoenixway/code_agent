from __future__ import annotations

from pathlib import Path

import yaml

from modules.agent.orchestration.protocol import PROTOCOL_SPEC, ProtocolCompiler, ResponseShape


FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "model_outputs"


def _fixture_paths():
    return sorted(FIXTURES_ROOT.rglob("*.yaml"))


def test_protocol_spec_is_first_class_registry():
    assert PROTOCOL_SPEC.version
    assert "intent" in PROTOCOL_SPEC.blocks
    assert "INTENT_ACTION_BUNDLE" in PROTOCOL_SPEC.shapes
    assert any(c.id == "atomic_bundle_requires_exactly_one_action" for c in PROTOCOL_SPEC.constraints)
    assert "E_MIXED_VISIBLE_TEXT_AND_CONTROL" in PROTOCOL_SPEC.errors


def test_grammar_doc_exists():
    grammar = Path("docs/protocol/response_grammar.md")
    assert grammar.exists()
    text = grammar.read_text(encoding="utf-8")
    assert "Lexer Responsibilities" in text
    assert "READ_ONLY_BATCH_CANDIDATE" in text


def test_fixture_corpus_is_loadable():
    assert len(_fixture_paths()) >= 14


def test_fixture_corpus_compiles_consistently():
    compiler = ProtocolCompiler()
    for path in _fixture_paths():
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        analysis = compiler.analyze(payload["raw"])
        assert analysis.shape.name == payload["shape"], path.name
        if payload["valid"]:
            assert analysis.error is None, path.name
        else:
            assert analysis.error is not None, path.name
            assert analysis.error.code == payload["error_code"], path.name
            assert analysis.error.recovery_id == payload["recovery_id"], path.name
            assert analysis.error.invalid_part == payload.get("invalid_part"), path.name
            assert analysis.error.transaction_applied is False, path.name
            assert analysis.error.action_dispatched is False, path.name


def test_inline_and_fenced_literals_do_not_become_structural_blocks():
    compiler = ProtocolCompiler()

    inline = compiler.analyze("Use `<action>` only as an example.")
    fenced = compiler.analyze("```xml\n<action>{\"type\":\"read_file\"}</action>\n```")

    assert inline.shape == ResponseShape.PURE_PLAINTEXT
    assert inline.error is None
    assert fenced.shape == ResponseShape.PURE_PLAINTEXT
    assert fenced.error is None


def test_file_content_preserves_raw_body():
    compiler = ProtocolCompiler()
    analysis = compiler.analyze(
        '<action>{"type":"write_file_block","path":"x.xml"}</action>\n'
        "<file_content>\n"
        'if (a < b && c > d) println("<action>literal</action>")\n'
        "</file_content>"
    )

    assert analysis.error is None
    assert analysis.shape == ResponseShape.ACTION_ONLY
    assert analysis.ast is not None
    assert analysis.ir is not None
    file_nodes = [node for node in analysis.ast.nodes if node.__class__.__name__ == "FileContentNode"]
    assert len(file_nodes) == 1
    assert "<action>literal</action>" in file_nodes[0].content
    assert analysis.ir.action_ops[0].file_content is not None


def test_single_action_ir_exposes_plan_first_candidate_fields():
    compiler = ProtocolCompiler()
    analysis = compiler.analyze('<action>{"type":"read_file","path":"README.md"}</action>')

    assert analysis.error is None
    assert analysis.ir is not None
    assert analysis.shape == ResponseShape.ACTION_ONLY
    assert analysis.ir.action_count == 1
    assert analysis.ir.has_action is True
    assert analysis.ir.has_pre_action_text is False
    assert analysis.ir.visible_text_source == "NONE"
    assert analysis.ir.action_ops[0].action_type == "read_file"
    assert analysis.ir.action_ops[0].payload == {"type": "read_file", "path": "README.md"}


def test_pre_action_text_ir_exposes_plan_first_fields():
    compiler = ProtocolCompiler()
    analysis = compiler.analyze(
        'I will inspect the file first.<action>{"type":"read_file","path":"README.md"}</action>'
    )

    assert analysis.error is None
    assert analysis.ir is not None
    assert analysis.shape == ResponseShape.PRE_ACTION_TEXT_AND_ACTION
    assert analysis.ir.has_pre_action_text is True
    assert analysis.ir.pre_action_text == "I will inspect the file first."
    assert analysis.ir.visible_text_source == "PRE_ACTION_TEXT"
    assert analysis.ir.action_count == 1
    assert analysis.ir.action_ops[0].action_type == "read_file"
    assert analysis.ir.action_ops[0].payload == {"type": "read_file", "path": "README.md"}
