import json
import re
from types import SimpleNamespace

import pytest

from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline


class Segment(SimpleNamespace):
    pass


class MiniParser:
    ACTION_RE = re.compile(r"<action(?:\s+[^>]*)?>(.*?)</action>", re.IGNORECASE | re.DOTALL)
    THINK_RE = re.compile(r"<think(?:\s+[^>]*)?>(.*?)</think>", re.IGNORECASE | re.DOTALL)

    def parse(self, response):
        segments = []
        for match in self.THINK_RE.finditer(response):
            segments.append(Segment(type="thought", content=match.group(1).strip()))

        for match in self.ACTION_RE.finditer(response):
            body = match.group(1).strip()
            try:
                payload = json.loads(body)
            except Exception:
                payload = body
            if isinstance(payload, dict):
                segments.append(Segment(type="action", content=payload))
            else:
                segments.append(Segment(type="text", content=body))

        # Add a text segment only for visible tail not needed by these tests.
        return segments


class DummyStage:
    async def apply(self, ctx, response_text):
        return SimpleNamespace(
            handled=False,
            next_query="",
            response_text=response_text,
            reason="",
            source="",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class DummyIntentTransitions:
    async def handle_model_step(self, *, intent_payload, intent_error, response_text, state_machine=None):
        return SimpleNamespace(handled=False, next_query="", reason="", source="")


class DummyOutputRecovery:
    async def decide(self, parsed_output, malformed_action_retries=0, audit_marker_retries=0):
        if parsed_output.invalid_kind:
            return SimpleNamespace(
                handled=True,
                continue_loop=True,
                stop_loop=False,
                next_query=f"RECOVER:{parsed_output.invalid_kind}",
                malformed_action_retries=malformed_action_retries,
                audit_marker_retries=audit_marker_retries,
                reason=parsed_output.invalid_kind,
                source="output_recovery",
            )
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            stop_loop=False,
            next_query="",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            reason="",
            source="",
        )


class DummyActionPolicy:
    async def decide(self, ctx, segments, *, intent_payload):
        action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            stop_loop=False,
            next_query="",
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=action_count,
        )


class DummyPromptBuilder:
    def build_multiple_actions_prompt(self):
        return (
            "SYSTEM: Your last response contained a forbidden multi-action batch.\n"
            "Multiple top-level <action> blocks are allowed only when every action is read-only.\n"
            "State-changing or mixed read/write batches are not atomic and are rejected."
        )

    def build_missing_action_or_answer_prompt(self):
        return "SYSTEM: Missing action or answer."

    def build_plain_text_completion_prompt(self, *args, **kwargs):
        return "SYSTEM: Return a final answer."

    def build_reflection_repair_accepted_prompt(self):
        return "SYSTEM: Repair accepted."

    def build_durable_state_repair_prompt(self, reason=None):
        return "SYSTEM: Repair durable state."

    def build_repeated_thinking_without_valid_output_prompt(self):
        return "SYSTEM: Stop thinking without output."


class DummyAgent:
    def __init__(self):
        self.state = SimpleNamespace(
            last_memory_update_done=False,
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
        )
        self.config = SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        )
        self.ui = SimpleNamespace(
            print_error=lambda *args, **kwargs: None,
        )
        self.log = None
        self.memory_board_engine = None


def _response_with_actions(actions):
    body = [
        "<think>! Need current file state. ? Need relevant files. → read them.</think>",
        "<memory_update_done />",
    ]
    for action in actions:
        body.append(f"<action>{json.dumps(action)}</action>")
    return "\n".join(body)


def test_parser_allows_multiple_top_level_read_only_actions():
    response = _response_with_actions(
        [
            {"type": "read_file", "path": "app/src/main/AndroidManifest.xml"},
            {"type": "read_file", "path": "app/src/main/java/MainActivity.kt"},
            {"type": "search_content", "path": ".", "pattern": "ShareReceiverActivity"},
        ]
    )

    parser = IntentResponseParser()
    segments = MiniParser().parse(response)
    parsed = parser.classify(response, segments)

    assert parsed.invalid_kind == ""
    assert sum(1 for segment in parsed.segments if segment.type == "action") == 3


def test_parser_rejects_mixed_read_and_state_changing_actions_as_multiple_actions():
    response = _response_with_actions(
        [
            {"type": "read_file", "path": "app/src/main/AndroidManifest.xml"},
            {
                "type": "edit_file",
                "path": "app/src/main/AndroidManifest.xml",
                "search_text": "old",
                "replace_text": "new",
            },
        ]
    )

    parser = IntentResponseParser()
    segments = MiniParser().parse(response)
    parsed = parser.classify(response, segments)

    assert parsed.invalid_kind == "multiple_actions"


@pytest.mark.asyncio
async def test_response_pipeline_dispatches_pure_read_only_batch():
    agent = DummyAgent()
    pipeline = ModelResponsePipeline(
        agent=agent,
        parser=MiniParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=DummyIntentTransitions(),
        output_recovery=DummyOutputRecovery(),
        action_policy=DummyActionPolicy(),
        plan_board_stage=DummyStage(),
        memory_board_stage=DummyStage(),
    )

    response = _response_with_actions(
        [
            {"type": "read_file", "path": "app/src/main/AndroidManifest.xml"},
            {"type": "read_file", "path": "app/src/main/java/MainActivity.kt"},
            {"type": "read_file", "path": "app/src/main/java/ShareReceiverActivity.kt"},
        ]
    )

    outcome = await pipeline.run_step(
        SimpleNamespace(
            state_machine=None,
            malformed_action_retries=0,
            audit_marker_retries=0,
            user_input="Verify current share flow files.",
        ),
        SimpleNamespace(
            response=response,
            intent_payload=None,
            intent_error=None,
            model_stop_reason="",
        ),
    )

    assert outcome.handled is True
    assert outcome.continue_loop is False
    assert outcome.stop_loop is False
    assert outcome.reason == "dispatch_ready"
    assert outcome.parsed_action_count == 3


@pytest.mark.asyncio
async def test_response_pipeline_rejects_mixed_multi_action_batch():
    agent = DummyAgent()
    pipeline = ModelResponsePipeline(
        agent=agent,
        parser=MiniParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=DummyIntentTransitions(),
        output_recovery=DummyOutputRecovery(),
        action_policy=DummyActionPolicy(),
        plan_board_stage=DummyStage(),
        memory_board_stage=DummyStage(),
    )

    response = _response_with_actions(
        [
            {"type": "read_file", "path": "app/src/main/AndroidManifest.xml"},
            {
                "type": "edit_file",
                "path": "app/src/main/AndroidManifest.xml",
                "search_text": "old",
                "replace_text": "new",
            },
        ]
    )

    outcome = await pipeline.run_step(
        SimpleNamespace(
            state_machine=None,
            malformed_action_retries=0,
            audit_marker_retries=0,
            user_input="Read then edit manifest.",
        ),
        SimpleNamespace(
            response=response,
            intent_payload=None,
            intent_error=None,
            model_stop_reason="",
        ),
    )

    assert outcome.handled is True
    assert outcome.continue_loop is True
    assert outcome.reason == "multiple_actions"
    assert outcome.source in {"transaction_guard", "output_recovery"}
    assert "read-only" in outcome.next_query.lower() or outcome.next_query == "RECOVER:multiple_actions"
