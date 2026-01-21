"""
Patch Executor - Orchestrates the execution-based verification pipeline.

This replaces semantic F1 scoring with actual execution results.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime

from .docker_runner import DockerRunner, ContainerConfig

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for patch execution."""
    use_docker: bool = True
    timeout: int = 300
    parallel_executions: int = 1  # Run one at a time for reliability
    retry_on_failure: bool = False
    save_outputs: bool = True


class PatchExecutor:
    """
    Orchestrates execution-based patch verification.
    
    Key difference from semantic comparison:
    - Semantic: Compare text tokens, return F1 score (0.0-1.0)
    - Execution: Actually run the code, return PASS/FAIL
    """
    
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        self.docker_runner = None
        
        if self.config.use_docker:
            try:
                self.docker_runner = DockerRunner(ContainerConfig(
                    timeout=self.config.timeout
                ))
                logger.info("Docker runner initialized")
            except RuntimeError as e:
                logger.warning(f"Docker not available: {e}. Will use mock execution.")
                self.config.use_docker = False
    
    async def execute_patch(
        self,
        instance: Dict[str, Any],
        generated_patch: str
    ) -> Dict[str, Any]:
        """
        Execute a generated patch and verify it passes tests.
        
        Args:
            instance: SWE-bench instance with repo, commit, etc.
            generated_patch: The patch to apply and test
            
        Returns:
            ExecutionResult with pass/fail and details
        """
        instance_id = instance.get("instance_id", "unknown")
        
        logger.info(f"Executing patch for {instance_id}")
        
        if not generated_patch or generated_patch.strip() == "":
            return {
                "instance_id": instance_id,
                "success": False,
                "execution_pass": False,
                "error": "empty_patch",
                "tests_passed": 0,
                "tests_failed": 0,
                "execution_time": 0,
                "stdout": "",
                "stderr": "Empty patch provided"
            }
        
        if self.config.use_docker and self.docker_runner:
            result = await self.docker_runner.verify_patch_execution(
                instance, generated_patch
            )
        else:
            # Mock execution for testing without Docker
            result = await self._mock_execution(instance, generated_patch)
        
        # Add execution-specific fields
        result["execution_pass"] = result.get("success", False)
        result["semantic_match"] = None  # We don't compute this anymore
        result["metric_type"] = "execution"  # Flag that this is execution-based
        
        return result
    
    async def _mock_execution(
        self,
        instance: Dict[str, Any],
        patch: str
    ) -> Dict[str, Any]:
        """
        Mock execution for testing without Docker.
        Returns a simulated result based on patch characteristics.
        """
        instance_id = instance.get("instance_id", "unknown")
        
        # Simple heuristics for mock (NOT for production use)
        has_diff = patch.startswith("diff ") or patch.startswith("---")
        has_content = len(patch.strip()) > 50
        
        # Simulate ~30% pass rate for realistic testing
        import random
        mock_pass = random.random() < 0.3 if has_diff and has_content else False
        
        return {
            "instance_id": instance_id,
            "success": mock_pass,
            "exit_code": 0 if mock_pass else 1,
            "stdout": "MOCK: Tests passed" if mock_pass else "MOCK: Tests failed",
            "stderr": "",
            "tests_passed": 5 if mock_pass else 2,
            "tests_failed": 0 if mock_pass else 3,
            "execution_time": 1.5,
            "error": None if mock_pass else "mock_test_failure",
            "mock": True
        }
    
    async def execute_batch(
        self,
        tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple patches.
        
        Args:
            tasks: List of (instance, patch) tuples
            
        Returns:
            List of execution results
        """
        results = []
        
        for i, task in enumerate(tasks):
            instance = task["instance"]
            patch = task["patch"]
            
            logger.info(f"[{i+1}/{len(tasks)}] Executing {instance.get('instance_id')}")
            
            result = await self.execute_patch(instance, patch)
            results.append(result)
            
            # Small delay between executions
            await asyncio.sleep(0.5)
        
        return results
    
    def compute_execution_metrics(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compute aggregate metrics from execution results.
        
        Returns execution-based metrics (NOT semantic F1):
        - pass_rate: % of patches that passed tests
        - total_tests_passed: Sum of tests passed
        - total_tests_failed: Sum of tests failed
        """
        if not results:
            return {
                "pass_rate": 0.0,
                "total_passed": 0,
                "total_failed": 0,
                "total_tests_passed": 0,
                "total_tests_failed": 0,
                "avg_execution_time": 0.0
            }
        
        passed = sum(1 for r in results if r.get("execution_pass", False))
        total = len(results)
        
        total_tests_passed = sum(r.get("tests_passed", 0) for r in results)
        total_tests_failed = sum(r.get("tests_failed", 0) for r in results)
        avg_time = sum(r.get("execution_time", 0) for r in results) / total
        
        return {
            "pass_rate": passed / total,
            "total_passed": passed,
            "total_failed": total - passed,
            "total_tests_passed": total_tests_passed,
            "total_tests_failed": total_tests_failed,
            "avg_execution_time": avg_time,
            "metric_type": "execution"  # Explicitly mark as execution-based
        }
