from types import SimpleNamespace

from modules.agent.orchestration.prompts.intent_prompt_builder import IntentPromptBuilderMixin


class Harness(IntentPromptBuilderMixin):
    def __init__(self):
        self.state = SimpleNamespace()
        self.config = SimpleNamespace()

    def sanitize_intent_goal(self, goal, *, fallback):
        return goal or fallback

    def _current_intent_goal(self):
        return "Modify code."

    def _intent_universe(self):
        return SimpleNamespace(has_active_contract=False)

    def _current_active_intent(self):
        return None


def test_formal_multi_step_modify_prompt_allows_replace_symbol_when_edit_file_is_allowed():
    prompt = Harness().build_formal_intent_required_for_multi_step_state_change_prompt(
        goal="Modify checklist screen."
    )

    assert '"edit_file"' in prompt
    assert '"extract_symbol"' in prompt
    assert '"replace_symbol"' in prompt


def test_build_fix_modify_prompt_allows_replace_symbol_when_edit_file_is_allowed():
    prompt = Harness().build_build_fix_intent_required_prompt(goal="Fix current Android compile errors.")

    assert '"edit_file"' in prompt
    assert '"extract_symbol"' in prompt
    assert '"replace_symbol"' in prompt
