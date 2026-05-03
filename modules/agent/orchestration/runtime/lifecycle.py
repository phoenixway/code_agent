"""Turn lifecycle bootstrap for orchestrator runs."""

from __future__ import annotations

from .dependencies import RuntimeCollaborators


class TurnLifecycle:
    def __init__(self, agent):
        self.agent = agent
        self.runtime = RuntimeCollaborators.from_agent(agent, needs_history=True)
        self.state = self.runtime.state
        self.history = self.runtime.history

    def start_turn(self, user_input: str, *, add_user_history: bool = True, user_history_meta: dict | None = None):
        if add_user_history:
            self.history.add_message("user", user_input, **dict(user_history_meta or {}))
        sm = getattr(self.state, "state_machine", None)
        if sm is not None:
            sm.start_turn(user_input)
            sm.intent_runtime = getattr(self.state, "intent_runtime", None)
            if self.runtime.logger:
                self.runtime.logger.debug(
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
                if self.runtime.logger:
                    self.runtime.logger.warning(f"History turn rollover failed: {exc}")
        return sm
