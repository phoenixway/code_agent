from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.protocol.models import ResponseShape


def _analyze(response: str):
    return ProtocolCompiler().analyze(response)


def test_memory_update_done_remains_recognized_checkpoint_control():
    analysis = _analyze("<memory_update_done />")

    assert analysis.error is None
    assert analysis.shape == ResponseShape.CHECKPOINT_ONLY
    assert analysis.ir is not None
    assert analysis.ir.has_checkpoint is True
    assert analysis.ir.has_memory_checkpoint is True
    assert analysis.ir.has_plan_checkpoint is False
    assert analysis.ir.has_subgoal_tags is False
    assert [op.kind for op in analysis.ir.board_ops] == ["memory_update_done"]


def test_plan_review_done_is_not_yet_a_checkpoint_marker():
    analysis = _analyze("<plan_review_done />")

    assert analysis.error is None
    assert analysis.shape == ResponseShape.PURE_PLAINTEXT
    assert analysis.ir is not None
    assert analysis.ir.has_checkpoint is False
    assert analysis.ir.has_memory_checkpoint is False
    assert analysis.ir.has_plan_checkpoint is False
    assert analysis.ir.has_subgoal_tags is False
    assert analysis.ir.board_ops == ()


def test_plan_review_done_before_action_is_currently_not_structural_checkpoint():
    analysis = _analyze('<plan_review_done />\n<action>{"type":"read_file","path":"x.py"}</action>')

    assert analysis.error is None
    assert analysis.shape == ResponseShape.PRE_ACTION_TEXT_AND_ACTION
    assert analysis.ir is not None
    assert analysis.ir.has_action is True
    assert analysis.ir.action_count == 1
    assert analysis.ir.has_checkpoint is False
    assert analysis.ir.board_ops == ()
    assert "plan_review_done" in analysis.ir.pre_action_text
