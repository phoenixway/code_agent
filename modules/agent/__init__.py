"""Agent module - модульна архітектура головного агента."""

from .core import AngelicaAgent
from .orchestrator import Orchestrator
from .state_manager import AgentState
from .model_client import ModelClient
from .action_dispatcher import ActionDispatcher
from .config import AgentConfig

__all__ = [
    'AngelicaAgent',
    'Orchestrator',
    'AgentState',
    'ModelClient',
    'ActionDispatcher',
    'AgentConfig',
]
