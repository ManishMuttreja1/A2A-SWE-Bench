"""Verification Engine for patch evaluation"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import tempfile
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class VerificationEngine:
    """
    Verifies patches submitted by Purple Agents.
    Runs tests and computes metrics.
    """
    
    def __init__(self):
        self.verification_history: List[Dict[str, Any]] = []
    
    async def verify_patch(
        self,
        environment: Dict[str, Any],
        patch: str,
        test_commands: List[str],
        oracle_tests: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Verify a patch in the given environment.
        
        Args:
            environment: Environment dict with container info
            patch: Diff/patch content to apply
            test_commands: Commands to run tests
            oracle_tests: Specific test cases that must pass
            
        Returns:
            Verification result dict
        """
        logger.info(f"Starting verification for environment {environment['id']}")
        
        result = {
            "passed": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "execution_time": 0,
            "patch_applied": False,
            "test_results": [],
            "error": None
        }
        
        try:
            # Apply the patch
            patch_result = await self._apply_patch(environment, patch)
            
            if not patch_result["success"]:
                result["error"] = f"Failed to apply patch: {patch_result.get('error')}"
                return result
            
            result["patch_applied"] = True
            
            # Run test commands
            for test_cmd in test_commands:
                test_result = await self._run_test(environment, test_cmd)
                result["test_results"].append(test_result)
                
                if test_result["success"]:
                    result["tests_passed"] += test_result.get("tests_passed", 1)
                else:
                    result["tests_failed"] += test_result.get("tests_failed", 1)
            
            # Run oracle tests if provided
            if oracle_tests:
                oracle_result = await self._run_oracle_tests(environment, oracle_tests)
                result["oracle_tests"] = oracle_result
                
                # All oracle tests must pass for success
                if oracle_result["all_passed"]:
                    result["passed"] = True
            else:
                # If no oracle tests, check if majority of tests passed
                result["passed"] = result["tests_passed"] > result["tests_failed"]
            
            # Calculate execution time
            result["execution_time"] = sum(
                tr.get("execution_time", 0) for tr in result["test_results"]
            )
            
            # Store in history
            self.verification_history.append(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error during verification: {e}")
            result["error"] = str(e)
            return result
    
    async def _apply_patch(self, environment: Dict[str, Any], patch: str) -> Dict[str, Any]:
        """Apply a patch to the environment"""
        try:
            # Save patch to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                f.write(patch)
                patch_file = f.name
            
            # Copy patch to container
            from ..orchestrator import EnvironmentOrchestrator
            orchestrator = EnvironmentOrchestrator()
            
            # Apply patch using git apply or patch command
            apply_result = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=f"git apply --3way {patch_file} || patch -p1 < {patch_file}",
                workdir="/workspace/repo"
            )
            
            return {
                "success": apply_result["exit_code"] == 0,
                "output": apply_result.get("stdout", ""),
                "error": apply_result.get("stderr", "")
            }
            
        except Exception as e:
            logger.error(f"Error applying patch: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # Clean up temp file
            if 'patch_file' in locals():
                Path(patch_file).unlink(missing_ok=True)
    
    async def _run_test(self, environment: Dict[str, Any], test_command: str) -> Dict[str, Any]:
        """Run a test command in the environment"""
        try:
            from ..orchestrator import EnvironmentOrchestrator
            orchestrator = EnvironmentOrchestrator()
            
            # Record start time
            import time
            start_time = time.time()
            
            # Execute test command
            result = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=test_command,
                workdir="/workspace/repo"
            )
            
            execution_time = time.time() - start_time
            
            # Parse test output to extract pass/fail counts
            output = result.get("stdout", "")
            tests_passed, tests_failed = self._parse_test_output(output)
            
            return {
                "command": test_command,
                "success": result["exit_code"] == 0,
                "exit_code": result["exit_code"],
                "output": output,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "execution_time": execution_time
            }
            
        except Exception as e:
            logger.error(f"Error running test: {e}")
            return {
                "command": test_command,
                "success": False,
                "error": str(e),
                "tests_passed": 0,
                "tests_failed": 1,
                "execution_time": 0
            }
    
    async def _run_oracle_tests(
        self,
        environment: Dict[str, Any],
        oracle_tests: List[str]
    ) -> Dict[str, Any]:
        """Run specific oracle tests that must pass"""
        results = {
            "all_passed": True,
            "tests": []
        }
        
        for test in oracle_tests:
            # Run each oracle test
            test_result = await self._run_test(environment, f"pytest {test}")
            
            results["tests"].append({
                "test": test,
                "passed": test_result["success"],
                "output": test_result.get("output", "")
            })
            
            if not test_result["success"]:
                results["all_passed"] = False
        
        return results
    
    def _parse_test_output(self, output: str) -> tuple:
        """
        Parse test output to extract pass/fail counts.
        
        Returns:
            Tuple of (tests_passed, tests_failed)
        """
        tests_passed = 0
        tests_failed = 0
        
        # Try to parse pytest output
        if "passed" in output or "PASSED" in output:
            # Look for pytest summary
            import re
            
            # Match patterns like "5 passed, 2 failed"
            match = re.search(r'(\d+)\s+passed', output, re.IGNORECASE)
            if match:
                tests_passed = int(match.group(1))
            
            match = re.search(r'(\d+)\s+failed', output, re.IGNORECASE)
            if match:
                tests_failed = int(match.group(1))
        
        # Try to parse unittest output
        elif "OK" in output or "FAIL" in output:
            # Look for patterns like "Ran 10 tests"
            match = re.search(r'Ran\s+(\d+)\s+test', output)
            if match:
                total_tests = int(match.group(1))
                
                if "FAILED" in output:
                    match = re.search(r'failures=(\d+)', output)
                    if match:
                        tests_failed = int(match.group(1))
                        tests_passed = total_tests - tests_failed
                elif "OK" in output:
                    tests_passed = total_tests
        
        # Default: if exit code was 0, assume 1 test passed
        elif "error" not in output.lower() and "fail" not in output.lower():
            tests_passed = 1
        else:
            tests_failed = 1
        
        return tests_passed, tests_failed
    
    async def compute_metrics(
        self,
        verification_result: Dict[str, Any],
        trajectory: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Compute additional metrics for the verification.
        
        Args:
            verification_result: Result from verify_patch
            trajectory: Optional trajectory of agent actions
            
        Returns:
            Metrics dict
        """
        metrics = {
            "success_rate": 0,
            "test_coverage": 0,
            "execution_efficiency": 0,
            "patch_size": 0
        }
        
        # Calculate success rate
        total_tests = verification_result["tests_passed"] + verification_result["tests_failed"]
        if total_tests > 0:
            metrics["success_rate"] = verification_result["tests_passed"] / total_tests
        
        # Estimate patch size (lines changed)
        if "patch" in verification_result:
            patch_lines = verification_result["patch"].split('\n')
            metrics["patch_size"] = len([l for l in patch_lines if l.startswith('+') or l.startswith('-')])
        
        # Calculate execution efficiency if trajectory provided
        if trajectory:
            # Count different action types
            action_counts = {}
            for action in trajectory:
                action_type = action.get("action", "unknown")
                action_counts[action_type] = action_counts.get(action_type, 0) + 1
            
            # Lower score is better (fewer actions)
            total_actions = sum(action_counts.values())
            if total_actions > 0:
                metrics["execution_efficiency"] = 1.0 / total_actions
            
            metrics["action_counts"] = action_counts
        
        return metrics