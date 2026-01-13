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
        oracle_tests: Optional[List[str]] = None,
        timeout_seconds: int = 600,
        flaky_retries: int = 0,
        fail_closed_on_missing_oracle: bool = True,
        fuzz_commands: Optional[List[str]] = None,
        adversarial_commands: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Verify a patch in the given environment.
        
        Args:
            environment: Environment dict with container info
            patch: Diff/patch content to apply
            test_commands: Commands to run tests
            oracle_tests: Specific test cases that must pass
            timeout_seconds: Max seconds per test command
            flaky_retries: Number of extra retries for failing tests (for flakiness)
            fail_closed_on_missing_oracle: If True, fail when oracle_tests is provided but empty
            fuzz_commands: Optional extra test commands for fuzz/property/mutation checks
            adversarial_commands: Optional red-team style commands to try to break the patch
            
        Returns:
            Verification result dict
        """
        logger.info(f"Starting verification for environment {environment['id']}")
        
        def _normalize_pytest_command(cmd: str) -> str:
            """
            Convert strings like
            'pytest test_name (package.module.ClassName)'
            into a concrete pytest node id:
            'pytest package/module.py::ClassName::test_name'
            """
            if not cmd.startswith("pytest") or "(" not in cmd or ")" not in cmd:
                return cmd
            try:
                prefix, rest = cmd.split("pytest", 1)[1].strip(), ""
                # prefix now like: 'test_ascii_validator (auth_tests.test_validators.UsernameValidatorsTests)'
                test_part, module_part = prefix.split("(", 1)
                test_name = test_part.strip()
                module_class = module_part.strip().rstrip(")")
                pieces = module_class.split(".")
                if len(pieces) < 2:
                    return cmd  # fallback
                class_name = pieces[-1]
                module_path = "/".join(pieces[:-1]) + ".py"
                # Many SWE-bench cases keep tests under a top-level `tests/` directory.
                if not module_path.startswith("tests/"):
                    module_path = f"tests/{module_path}"
                return f"pytest {module_path}::{class_name}::{test_name}"
            except Exception:
                return cmd
        
        result = {
            "passed": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "execution_time": 0,
            "patch_applied": False,
            "test_results": [],
            "fuzz_results": [],
            "adversarial_results": [],
            "error": None
        }
        
        try:
            # Apply the patch (but continue even if it fails, to surface baseline test behavior)
            patch_result = await self._apply_patch(environment, patch)
            result["patch_applied"] = patch_result.get("success", False)
            if not patch_result.get("success", False):
                result["error"] = f"Failed to apply patch: {patch_result.get('error', '')}"
                logger.warning(result["error"])
                # If patch is already applied, allow tests to proceed.
                if patch_result.get("error", "").strip() != "already_applied":
                    result["passed"] = False
                    self.verification_history.append(result)
                return result
            
            # Run test commands
            for test_cmd in test_commands:
                test_cmd = _normalize_pytest_command(test_cmd)
                test_result = await self._run_test(
                    environment,
                    test_cmd,
                    timeout_seconds=timeout_seconds,
                    flaky_retries=flaky_retries,
                )
                result["test_results"].append(test_result)
                
                if test_result["success"]:
                    result["tests_passed"] += test_result.get("tests_passed", 1)
                else:
                    result["tests_failed"] += test_result.get("tests_failed", 1)
            
            # Run oracle tests if provided
            if oracle_tests:
                normalized_oracles = [_normalize_pytest_command(f"pytest {cmd}") for cmd in oracle_tests]
                oracle_result = await self._run_oracle_tests(
                    environment,
                    normalized_oracles,
                    timeout_seconds=timeout_seconds,
                    flaky_retries=flaky_retries,
                )
                result["oracle_tests"] = oracle_result
                
                # All oracle tests must pass for success
                if oracle_result["all_passed"]:
                    result["passed"] = True
                else:
                    result["passed"] = False
            elif fail_closed_on_missing_oracle:
                result["passed"] = False
                result["error"] = result.get("error") or "Oracle tests missing; fail-closed"
            else:
                # If no oracle tests, check if majority of tests passed
                result["passed"] = result["tests_passed"] > result["tests_failed"]

            # Run fuzz/dynamic tests if provided
            if fuzz_commands:
                fuzz_pass = True
                for fuzz_cmd in fuzz_commands:
                    fuzz_res = await self._run_test(
                        environment,
                        fuzz_cmd,
                        timeout_seconds=timeout_seconds,
                        flaky_retries=flaky_retries,
                    )
                    result["fuzz_results"].append(fuzz_res)
                    if not fuzz_res.get("success"):
                        fuzz_pass = False
                result["passed"] = result["passed"] and fuzz_pass

            # Run adversarial/red-team commands if provided
            if adversarial_commands:
                adversary_pass = True
                for adv_cmd in adversarial_commands:
                    adv_res = await self._run_test(
                        environment,
                        adv_cmd,
                        timeout_seconds=timeout_seconds,
                        flaky_retries=flaky_retries,
                    )
                    result["adversarial_results"].append(adv_res)
                    if not adv_res.get("success"):
                        adversary_pass = False
                result["passed"] = result["passed"] and adversary_pass
            
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
            import base64
            from .environment_orchestrator import EnvironmentOrchestrator
            orchestrator = EnvironmentOrchestrator()
            
            # Encode patch as base64 and decode inside container, write to file
            patch_b64 = base64.b64encode(patch.encode("utf-8")).decode("utf-8")
            
            # Write patch to file first
            write_cmd = f"echo '{patch_b64}' | base64 -d > /tmp/fix.patch"
            write_result = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=write_cmd,
                workdir="/workspace/repo"
            )
            
            if write_result.get("exit_code") != 0:
                logger.error(f"Failed to write patch file: {write_result.get('stderr', '')}")
            
            # Debug: check patch file contents
            check_cmd = "cat /tmp/fix.patch | head -20"
            check_result = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=check_cmd,
                workdir="/workspace/repo"
            )
            logger.info(f"Patch file contents:\n{check_result.get('stdout', '')}")
            
            # Debug: check the file we're trying to patch
            file_cmd = "head -25 django/contrib/auth/validators.py"
            file_result = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=file_cmd,
                workdir="/workspace/repo"
            )
            logger.info(f"Target file contents:\n{file_result.get('stdout', '')}")
            
            # Try git apply first, fall back to patch
            apply_cmd = "git apply --verbose /tmp/fix.patch 2>&1 || patch -p1 --verbose < /tmp/fix.patch 2>&1"
            apply_result = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=apply_cmd,
                workdir="/workspace/repo"
            )
            logger.info(f"Apply result exit={apply_result['exit_code']}: {apply_result.get('stdout', '')}")
            
            if apply_result["exit_code"] == 0:
                return {
                    "success": True,
                    "output": apply_result.get("stdout", ""),
                    "error": apply_result.get("stderr", "")
                }

            # If apply failed, check whether the patch is already present.
            reverse_cmd = "git apply --reverse --check /tmp/fix.patch"
            reverse_check = await orchestrator.execute_in_environment(
                container_id=environment["container_id"],
                command=reverse_cmd,
                workdir="/workspace/repo"
            )
            if reverse_check.get("exit_code") == 0:
                return {"success": True, "output": "already applied", "error": "already_applied"}
            
            return {
                "success": False,
                "output": apply_result.get("stdout", ""),
                "error": apply_result.get("stderr", "")
            }
            
        except Exception as e:
            logger.error(f"Error applying patch: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _run_test(
        self,
        environment: Dict[str, Any],
        test_command: str,
        timeout_seconds: int = 600,
        flaky_retries: int = 0,
    ) -> Dict[str, Any]:
        """Run a test command in the environment with optional retries and timeout"""
        import time
        from .environment_orchestrator import EnvironmentOrchestrator
        orchestrator = EnvironmentOrchestrator()
        
        attempts = []
        for attempt in range(flaky_retries + 1):
            try:
                start_time = time.time()
                # Ensure repo is on PYTHONPATH; add framework-specific settings when needed.
                repo_url = environment.get("repo_url", "")
                exports = ["export PYTHONPATH=/workspace/repo"]
                if "django/django" in repo_url:
                    exports.append("export DJANGO_SETTINGS_MODULE=tests.test_sqlite")
                    exports.append("export DJANGO_ALLOW_ASYNC_UNSAFE=true")
                env_prefix = "; ".join(exports) + "; "

                # For Django core repo, route tests through Django's runtests harness for proper settings/apps.
                if "django/django" in repo_url and test_command.strip().startswith("pytest "):
                    raw_target = test_command.split("pytest", 1)[1].strip()
                    dotted = (
                        raw_target.replace("::", ".")
                        .replace("/", ".")
                        .replace(".py", "")
                    )
                    django_cmd = f"python tests/runtests.py --settings=test_sqlite --verbosity=1 {dotted}"
                    base_cmd = django_cmd
                else:
                    base_cmd = test_command

                command_with_env = base_cmd if base_cmd.strip().startswith("export") else f"{env_prefix}{base_cmd}"
                exec_future = orchestrator.execute_in_environment(
                    container_id=environment["container_id"],
                    command=command_with_env,
                    workdir="/workspace/repo"
                )
                result = await asyncio.wait_for(exec_future, timeout=timeout_seconds)
                execution_time = time.time() - start_time
                
                output = result.get("stdout", "")
                tests_passed, tests_failed = self._parse_test_output(output)
                
                attempt_result = {
                    "command": test_command,
                    "success": result["exit_code"] == 0,
                    "exit_code": result["exit_code"],
                    "output": output,
                    "tests_passed": tests_passed,
                    "tests_failed": tests_failed,
                    "execution_time": execution_time,
                    "attempt": attempt + 1,
                }
                attempts.append(attempt_result)
                
                if attempt_result["success"]:
                    return attempt_result
            except asyncio.TimeoutError:
                logger.warning(f"Test command timed out after {timeout_seconds}s: {test_command}")
                attempts.append({
                    "command": test_command,
                    "success": False,
                    "error": f"timeout_after_{timeout_seconds}s",
                    "tests_passed": 0,
                    "tests_failed": 1,
                    "execution_time": timeout_seconds,
                    "attempt": attempt + 1,
                })
            except Exception as e:
                logger.error(f"Error running test (attempt {attempt+1}): {e}")
                attempts.append({
                    "command": test_command,
                    "success": False,
                    "error": str(e),
                    "tests_passed": 0,
                    "tests_failed": 1,
                    "execution_time": 0,
                    "attempt": attempt + 1,
                })
        
        # Return last attempt if all failed
        return attempts[-1] if attempts else {
            "command": test_command,
            "success": False,
            "error": "no_attempts",
            "tests_passed": 0,
            "tests_failed": 1,
            "execution_time": 0,
        }
    
    async def _run_oracle_tests(
        self,
        environment: Dict[str, Any],
        oracle_tests: List[str],
        timeout_seconds: int = 600,
        flaky_retries: int = 0,
    ) -> Dict[str, Any]:
        """Run specific oracle tests that must pass"""
        results = {
            "all_passed": True,
            "tests": []
        }
        
        for test in oracle_tests:
            # Run each oracle test
            test_result = await self._run_test(
                environment,
                f"pytest {test}",
                timeout_seconds=timeout_seconds,
                flaky_retries=flaky_retries,
            )
            
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
        import re
        tests_passed = 0
        tests_failed = 0
        
        # Try to parse pytest output
        if "passed" in output or "PASSED" in output:
            # Look for pytest summary
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