"""
Execution-based verification module.

Replaces semantic F1 scoring with actual Docker-based patch execution.
"""

from .docker_runner import DockerRunner
from .patch_executor import PatchExecutor
from .result_collector import ExecutionResult, ResultCollector
from .enforced_workflow import EnforcedWorkflow, EnforcedWorkflowResult, WorkflowPhase

__all__ = [
    'DockerRunner', 
    'PatchExecutor', 
    'ExecutionResult', 
    'ResultCollector',
    'EnforcedWorkflow',
    'EnforcedWorkflowResult',
    'WorkflowPhase'
]
