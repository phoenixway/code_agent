"""Narrow runtime collaborator bundles for orchestration coordinators."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeCollaborators:
    state: object
    history: object | None = None
    config: object | None = None
    ui: object | None = None
    logger: object | None = None
    dispatcher: object | None = None

    @classmethod
    def from_agent(
        cls,
        agent,
        *,
        needs_history: bool = False,
        needs_config: bool = False,
        needs_dispatcher: bool = False,
    ) -> "RuntimeCollaborators":
        return cls(
            state=getattr(agent, "state", None),
            history=getattr(agent, "history", None) if needs_history else None,
            config=getattr(agent, "config", None) if needs_config else None,
            ui=getattr(agent, "ui", None),
            logger=getattr(agent, "log", None),
            dispatcher=getattr(agent, "action_dispatcher", None) if needs_dispatcher else None,
        )
