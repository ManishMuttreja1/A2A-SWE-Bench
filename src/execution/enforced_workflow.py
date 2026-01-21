"""
Enforced Workflow - Requires reproduction gate before patch execution.

This addresses Gap 2: The reproduction gate was defined but not enforced.
Now: No patch can be evaluated without first proving bug reproduction.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum

from ..green_agent.reproduction_gate import ReproductionGate, ReproductionStatus
from ..a2a.protocol import Task
from .patch_executor import PatchExecutor
from .result_collector import ResultCollector, ExecutionResult

logger = logging.getLogger(__name__)


class WorkflowPhase(str, Enum):
    """Phases in the enforced workflow."""
    REPRODUCTION = "reproduction"
    PATCH = "patch"
    VERIFICATION = "verification"
    COMPLETE = "complete"


@dataclass
class EnforcedWorkflowResult:
    """Result from enforced workflow execution."""
    instance_id: str
    
    # Reproduction phase
    reproduction_attempted: bool = False
    reproduction_verified: bool = False
    reproduction_script: str = ""
    reproduction_error: Optional[str] = None
    
    # Patch phase (only if reproduction verified)
    patch_accepted: bool = False
    patch_content: str = ""
    
    # Execution phase (only if patch accepted)
    execution_pass: bool = False
    tests_passed: int = 0
    tests_failed: int = 0
    
    # Final score
    # KEY: Score is 0 if reproduction not verified, regardless of patch quality
    final_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    
    # Workflow metadata
    workflow_phase_reached: WorkflowPhase = WorkflowPhase.REPRODUCTION
    total_time: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "reproduction_attempted": self.reproduction_attempted,
            "reproduction_verified": self.reproduction_verified,
            "reproduction_script": self.reproduction_script[:500] if self.reproduction_script else "",
            "reproduction_error": self.reproduction_error,
            "patch_accepted": self.patch_accepted,
            "execution_pass": self.execution_pass,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "final_score": self.final_score,
            "score_breakdown": self.score_breakdown,
            "workflow_phase_reached": self.workflow_phase_reached.value,
            "total_time": self.total_time,
            "error": self.error
        }


class EnforcedWorkflow:
    """
    Enforced evaluation workflow that requires reproduction before patching.
    
    Workflow:
    1. Agent submits reproduction script
    2. System verifies reproduction (script must FAIL on buggy code)
    3. Only then can agent submit patch
    4. System runs patch through execution pipeline
    5. Score: 0 if reproduction skipped, otherwise based on execution
    
    This addresses the critique that reproduction gate was "defined but not enforced".
    """
    
    def __init__(
        self,
        strict_mode: bool = True,
        allow_mock: bool = True,  # For testing without Docker
        reproduction_weight: float = 0.3,  # 30% of score from reproduction
        execution_weight: float = 0.7      # 70% from execution
    ):
        self.strict_mode = strict_mode
        self.allow_mock = allow_mock
        self.reproduction_weight = reproduction_weight
        self.execution_weight = execution_weight
        
        # Initialize components
        self.reproduction_gate = ReproductionGate(
            strict_mode=strict_mode,
            allow_mock_verification=allow_mock
        )
        # Configure patch executor based on allow_mock setting
        from .patch_executor import ExecutionConfig
        exec_config = ExecutionConfig(use_docker=not allow_mock)
        self.patch_executor = PatchExecutor(exec_config)
        
        # Track workflow state per task
        self.task_state: Dict[str, Dict[str, Any]] = {}
    
    async def evaluate_agent_submission(
        self,
        instance: Dict[str, Any],
        reproduction_script: Optional[str],
        patch: str,
        expected_error: Optional[str] = None
    ) -> EnforcedWorkflowResult:
        """
        Evaluate a complete agent submission with enforced reproduction gate.
        
        Args:
            instance: SWE-bench instance
            reproduction_script: Script that reproduces the bug (required if strict_mode)
            patch: The patch to apply
            expected_error: Expected error from reproduction
            
        Returns:
            EnforcedWorkflowResult with score=0 if reproduction not verified
        """
        import time
        start_time = time.time()
        
        instance_id = instance.get("instance_id", "unknown")
        result = EnforcedWorkflowResult(instance_id=instance_id)
        
        # Create Task object for reproduction gate
        task = Task(
            id=instance_id,
            title=instance_id,  # Required field
            description=instance.get("problem_statement", ""),
            resources={"instance": instance}
        )
        
        # PHASE 1: REPRODUCTION (required in strict mode)
        if self.strict_mode:
            if not reproduction_script:
                result.reproduction_attempted = False
                result.reproduction_verified = False
                result.reproduction_error = "No reproduction script provided. SCORE=0."
                result.final_score = 0.0
                result.score_breakdown = {
                    "reproduction": 0.0,
                    "execution": 0.0,
                    "reason": "Reproduction gate not passed - no script provided"
                }
                result.workflow_phase_reached = WorkflowPhase.REPRODUCTION
                result.total_time = time.time() - start_time
                
                logger.warning(f"Task {instance_id}: No reproduction script - score 0")
                return result
            
            # Verify reproduction
            result.reproduction_attempted = True
            result.reproduction_script = reproduction_script
            
            repro_result = await self.reproduction_gate.submit_reproduction(
                task, reproduction_script, expected_error
            )
            
            logger.debug(f"Reproduction result: {repro_result}")
            
            # Check if bug was actually reproduced (script must FAIL on buggy code)
            reproduced_bug = repro_result.get("reproduced_bug", False)
            if not reproduced_bug:
                result.reproduction_verified = False
                result.reproduction_error = repro_result.get("message", "Reproduction failed")
                result.final_score = 0.0
                result.score_breakdown = {
                    "reproduction": 0.0,
                    "execution": 0.0,
                    "reason": f"Reproduction gate not passed - {result.reproduction_error}"
                }
                result.workflow_phase_reached = WorkflowPhase.REPRODUCTION
                result.total_time = time.time() - start_time
                
                logger.warning(f"Task {instance_id}: Reproduction failed - score 0")
                return result
            
            result.reproduction_verified = True
            logger.info(f"Task {instance_id}: Reproduction verified ✓")
        
        result.workflow_phase_reached = WorkflowPhase.PATCH
        
        # PHASE 2: PATCH ACCEPTANCE
        # Check if patch is allowed (reproduction must be verified)
        if self.strict_mode:
            patch_check = await self.reproduction_gate.check_patch_allowed(task)
            if not patch_check["allowed"]:
                result.patch_accepted = False
                result.error = patch_check["reason"]
                result.final_score = 0.0
                result.score_breakdown = {
                    "reproduction": self.reproduction_weight if result.reproduction_verified else 0.0,
                    "execution": 0.0,
                    "reason": patch_check["reason"]
                }
                result.total_time = time.time() - start_time
                return result
        
        result.patch_accepted = True
        result.patch_content = patch
        result.workflow_phase_reached = WorkflowPhase.VERIFICATION
        
        # PHASE 3: EXECUTION
        exec_result = await self.patch_executor.execute_patch(instance, patch)
        
        result.execution_pass = exec_result.get("execution_pass", False)
        result.tests_passed = exec_result.get("tests_passed", 0)
        result.tests_failed = exec_result.get("tests_failed", 0)
        result.workflow_phase_reached = WorkflowPhase.COMPLETE
        
        # PHASE 4: COMPUTE FINAL SCORE
        reproduction_score = 1.0 if result.reproduction_verified else 0.0
        execution_score = 1.0 if result.execution_pass else 0.0
        
        result.final_score = (
            reproduction_score * self.reproduction_weight +
            execution_score * self.execution_weight
        )
        
        result.score_breakdown = {
            "reproduction": reproduction_score * self.reproduction_weight,
            "execution": execution_score * self.execution_weight,
            "total": result.final_score
        }
        
        result.total_time = time.time() - start_time
        
        logger.info(
            f"Task {instance_id}: Final score = {result.final_score:.2f} "
            f"(repro={reproduction_score:.0f}, exec={execution_score:.0f})"
        )
        
        return result
    
    async def evaluate_batch(
        self,
        submissions: List[Dict[str, Any]]
    ) -> Tuple[List[EnforcedWorkflowResult], Dict[str, Any]]:
        """
        Evaluate multiple submissions with enforced workflow.
        
        Args:
            submissions: List of {instance, reproduction_script, patch}
            
        Returns:
            (results, summary_metrics)
        """
        results = []
        
        for i, sub in enumerate(submissions):
            logger.info(f"[{i+1}/{len(submissions)}] Evaluating {sub['instance'].get('instance_id')}")
            
            result = await self.evaluate_agent_submission(
                instance=sub["instance"],
                reproduction_script=sub.get("reproduction_script"),
                patch=sub["patch"],
                expected_error=sub.get("expected_error")
            )
            results.append(result)
        
        # Compute summary
        summary = self._compute_summary(results)
        
        return results, summary
    
    def _compute_summary(self, results: List[EnforcedWorkflowResult]) -> Dict[str, Any]:
        """Compute summary metrics from results."""
        if not results:
            return {"error": "No results"}
        
        n = len(results)
        
        reproductions_attempted = sum(1 for r in results if r.reproduction_attempted)
        reproductions_verified = sum(1 for r in results if r.reproduction_verified)
        patches_accepted = sum(1 for r in results if r.patch_accepted)
        executions_passed = sum(1 for r in results if r.execution_pass)
        
        avg_score = sum(r.final_score for r in results) / n
        
        # Count how many got score=0 due to reproduction gate
        blocked_by_gate = sum(
            1 for r in results 
            if not r.reproduction_verified and self.strict_mode
        )
        
        return {
            "total_tasks": n,
            "reproductions_attempted": reproductions_attempted,
            "reproductions_verified": reproductions_verified,
            "reproduction_rate": reproductions_verified / n,
            "patches_accepted": patches_accepted,
            "executions_passed": executions_passed,
            "execution_pass_rate": executions_passed / n,
            "avg_final_score": avg_score,
            "blocked_by_reproduction_gate": blocked_by_gate,
            "gate_block_rate": blocked_by_gate / n,
            "metric_type": "enforced_workflow"
        }
    
    def get_reproduction_statistics(self) -> Dict[str, Any]:
        """Get statistics from reproduction gate."""
        return self.reproduction_gate.get_statistics()


# Helper function to generate simple reproduction scripts
def generate_reproduction_script(instance: Dict[str, Any]) -> str:
    """
    Generate a simple reproduction script template.
    In a real scenario, the agent would generate this.
    """
    problem = instance.get("problem_statement", "")
    repo = instance.get("repo", "unknown")
    
    # Simple template
    script = f'''"""
Reproduction script for {instance.get("instance_id", "unknown")}
Repo: {repo}
"""

# This script should FAIL on the buggy code (exit code != 0)
# and PASS after the patch is applied

# Import from the repository
# from {repo.replace("/", ".").split(".")[-1]} import something

# Set up the buggy scenario
# ...

# Assert the expected vs actual behavior
# The assertion should FAIL on buggy code
assert False, "Bug reproduction: {problem[:100]}..."
'''
    return script
