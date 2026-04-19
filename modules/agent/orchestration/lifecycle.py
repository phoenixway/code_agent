"""Turn lifecycle bootstrap for orchestrator runs."""

from __future__ import annotations


class TurnLifecycle:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history

    def start_turn(self, user_input: str):
        self.history.add_message("user", user_input)
        sm = getattr(self.state, "state_machine", None)
        if sm is not None:
            sm.start_turn(user_input)
            sm.intent_runtime = getattr(self.state, "intent_runtime", None)
            if self.agent.log:
                self.agent.log.debug(
                    f"Task contract: kind={getattr(sm, 'task_kind', None)}"
                )
        if hasattr(self.state, "clear_intent_requirement"):
            self.state.clear_intent_requirement()
        if hasattr(self.state, "start_turn_runtime"):
            self.state.start_turn_runtime()
        if hasattr(self.history, "start_turn"):
            try:
                self.history.start_turn(getattr(self.state, "current_turn_id", 0))
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"History turn rollover failed: {exc}")
        return sm
