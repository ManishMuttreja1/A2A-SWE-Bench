"""Purple Agent - The Solver/Participant"""

from .wrapper import PurpleAgentWrapper
from .controller import AgentController
from .multi_agent import MultiAgentTeam

__all__ = [
    "PurpleAgentWrapper",
    "AgentController",
    "MultiAgentTeam",
]