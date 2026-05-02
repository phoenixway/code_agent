"""Supported public API for the agent package.

Keep this initializer lightweight by using lazy attribute loading.
Implementation code should prefer explicit submodule imports.
"""

from __future__ import annotations

from importlib import import_module

PUBLIC_API = (
    "AngelicaAgent",
    "TechnicalInterruption",
)

__all__ = list(PUBLIC_API)


def __getattr__(name: str):
    if name == "AngelicaAgent":
        return import_module(".core", __name__).AngelicaAgent
    if name == "TechnicalInterruption":
        return import_module(".technical_interruptions", __name__).TechnicalInterruption
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
