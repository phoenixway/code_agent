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


def test_plan_review_done_is_recognized_as_plan_review_checkpoint_marker():
    analysis = _analyze("<plan_review_done />")

    assert analysis.error is None
    assert analysis.shape == ResponseShape.CHECKPOINT_ONLY
    assert analysis.ir is not None
    assert analysis.ir.has_checkpoint is True
    assert analysis.ir.has_memory_checkpoint is False
    assert analysis.ir.has_plan_checkpoint is False
    assert analysis.ir.has_plan_review_checkpoint is True
    assert analysis.ir.has_subgoal_tags is False
    assert [op.kind for op in analysis.ir.board_ops] == ["plan_review_done"]


def test_plan_review_done_before_action_is_structural_checkpoint_not_pre_action_text():
    analysis = _analyze('<plan_review_done />\n<action>{"type":"read_file","path":"x.py"}</action>')

    assert analysis.error is None
    assert analysis.shape == ResponseShape.ACTION_ONLY
    assert analysis.ir is not None
    assert analysis.ir.has_action is True
    assert analysis.ir.action_count == 1
    assert analysis.ir.has_checkpoint is True
    assert analysis.ir.has_plan_review_checkpoint is True
    assert [op.kind for op in analysis.ir.board_ops] == ["plan_review_done"]
    assert analysis.ir.pre_action_text == ""
