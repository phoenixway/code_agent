"""Narrow collaborator bundles for transition-layer handlers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionLayerCollaborators:
    state: object
    config: object | None = None
    ui: object | None = None
    logger: object | None = None

    @classmethod
    def from_agent(cls, agent, *, needs_config: bool = False) -> "TransitionLayerCollaborators":
        return cls(
            state=getattr(agent, "state", None),
            config=getattr(agent, "config", None) if needs_config else None,
            ui=getattr(agent, "ui", None),
            logger=getattr(agent, "log", None),
        )
