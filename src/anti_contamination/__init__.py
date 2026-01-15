"""Anti-Contamination Framework for SWE-bench A2A

Implements:
- Evaluation slices (verified, mutated, fresh, adversarial)
- Mode tracking (LLM_ONLY, HEURISTIC_ASSISTED)
- Retro-holdout mutations
- Fresh issue harvesting
"""

from .config import AntiContaminationConfig, EvaluationSlice, RunMode
from .pipeline import AntiContaminationPipeline

__all__ = [
    "AntiContaminationConfig",
    "EvaluationSlice", 
    "RunMode",
    "AntiContaminationPipeline",
]
