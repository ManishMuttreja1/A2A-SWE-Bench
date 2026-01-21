"""
Evaluation module with multi-run statistical framework.
"""

from .multi_run import MultiRunExecutor, MultiRunResult, RunConfig
from .statistical_analysis import StatisticalAnalyzer, ModelComparison

__all__ = [
    'MultiRunExecutor',
    'MultiRunResult', 
    'RunConfig',
    'StatisticalAnalyzer',
    'ModelComparison'
]
