"""Purple Agent - The Solver/Participant"""

from .wrapper import PurpleAgentWrapper, SimpleSolver, LLMSolver
from .controller import AgentController
from .multi_agent import MultiAgentTeam

__all__ = [
    "PurpleAgentWrapper",
    "SimpleSolver",
    "LLMSolver",
    "AgentController",
    "MultiAgentTeam",
]