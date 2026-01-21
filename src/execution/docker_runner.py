"""
Docker-based execution runner for SWE-bench tasks.

Uses Docker containers to:
1. Clone repository at specific commit
2. Apply patches
3. Run test suites
4. Collect pass/fail results
"""

import asyncio
import logging
import os
import tempfile
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ContainerConfig:
    """Configuration for Docker container execution."""
    image: str = "python:3.11-slim"
    timeout: int = 300  # 5 minutes
    memory_limit: str = "4g"
    cpu_limit: str = "2"
    network_mode: str = "none"  # Security: no network access


class DockerRunner:
    """
    Manages Docker containers for executing SWE-bench patches.
    
    Instead of measuring semantic similarity, this actually:
    1. Clones the repo at the correct commit
    2. Applies the generated patch
    3. Runs the test suite
    4. Returns PASS/FAIL based on actual execution
    """
    
    def __init__(self, config: Optional[ContainerConfig] = None):
        self.config = config or ContainerConfig()
        self._check_docker_available()
    
    def _check_docker_available(self):
        """Verify Docker is installed and running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError("Docker daemon not running")
        except FileNotFoundError:
            raise RuntimeError("Docker not installed")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Docker daemon not responding")
    
    async def execute_in_container(
        self,
        repo: str,
        base_commit: str,
        patch: str,
        test_cmd: str = "pytest",
        setup_commands: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Execute a patch in a Docker container and run tests.
        
        Args:
            repo: Repository in format "owner/name" (e.g., "django/django")
            base_commit: Git commit to checkout
            patch: The patch content to apply (unified diff format)
            test_cmd: Command to run tests (default: pytest)
            setup_commands: Optional setup commands (e.g., pip install)
            
        Returns:
            Dict with:
                - success: bool (tests passed)
                - exit_code: int
                - stdout: str
                - stderr: str
                - tests_passed: int
                - tests_failed: int
                - execution_time: float
        """
        import time
        start_time = time.time()
        
        # Create temporary directory for this execution
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Write patch to file
            patch_file = tmpdir / "fix.patch"
            patch_file.write_text(patch)
            
            # Create execution script
            script = self._create_execution_script(
                repo, base_commit, test_cmd, setup_commands
            )
            script_file = tmpdir / "run.sh"
            script_file.write_text(script)
            script_file.chmod(0o755)
            
            # Build Docker command
            docker_cmd = [
                "docker", "run",
                "--rm",
                "--memory", self.config.memory_limit,
                "--cpus", self.config.cpu_limit,
                "--network", self.config.network_mode,
                "-v", f"{tmpdir}:/workspace:rw",
                "-w", "/workspace",
                self.config.image,
                "/bin/bash", "/workspace/run.sh"
            ]
            
            logger.info(f"Executing patch for {repo}@{base_commit[:8]}")
            
            try:
                # Run with timeout
                proc = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=self.config.timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Execution timeout",
                        "tests_passed": 0,
                        "tests_failed": 0,
                        "execution_time": time.time() - start_time,
                        "error": "timeout"
                    }
                
                stdout_str = stdout.decode('utf-8', errors='replace')
                stderr_str = stderr.decode('utf-8', errors='replace')
                
                # Parse test results
                tests_passed, tests_failed = self._parse_pytest_output(stdout_str)
                
                execution_time = time.time() - start_time
                
                return {
                    "success": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "tests_passed": tests_passed,
                    "tests_failed": tests_failed,
                    "execution_time": execution_time,
                    "error": None if proc.returncode == 0 else "test_failure"
                }
                
            except Exception as e:
                logger.error(f"Docker execution failed: {e}")
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "tests_passed": 0,
                    "tests_failed": 0,
                    "execution_time": time.time() - start_time,
                    "error": str(e)
                }
    
    def _create_execution_script(
        self,
        repo: str,
        base_commit: str,
        test_cmd: str,
        setup_commands: Optional[list]
    ) -> str:
        """Create bash script for container execution."""
        
        # Default setup for Python projects
        default_setup = [
            "pip install -q pytest",
            "pip install -q -e . 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null || true"
        ]
        
        setup = setup_commands or default_setup
        setup_str = "\n".join(setup)
        
        script = f"""#!/bin/bash
set -e

echo "=== Setting up environment ==="
apt-get update -qq && apt-get install -qq -y git > /dev/null 2>&1

echo "=== Cloning {repo} ==="
git clone --quiet https://github.com/{repo}.git repo
cd repo

echo "=== Checking out {base_commit[:8]} ==="
git checkout -q {base_commit}

echo "=== Setting up dependencies ==="
{setup_str}

echo "=== Applying patch ==="
if [ -s /workspace/fix.patch ]; then
    git apply /workspace/fix.patch || {{
        echo "PATCH_APPLY_FAILED"
        exit 1
    }}
    echo "Patch applied successfully"
else
    echo "WARNING: Empty patch"
fi

echo "=== Running tests ==="
{test_cmd} || exit $?

echo "=== EXECUTION_SUCCESS ==="
"""
        return script
    
    def _parse_pytest_output(self, output: str) -> Tuple[int, int]:
        """Parse pytest output to extract pass/fail counts."""
        import re
        
        # Look for pytest summary line: "X passed, Y failed"
        # or "X passed" or "Y failed"
        passed = 0
        failed = 0
        
        # Pattern: "5 passed, 2 failed, 1 error"
        match = re.search(r'(\d+)\s+passed', output)
        if match:
            passed = int(match.group(1))
        
        match = re.search(r'(\d+)\s+failed', output)
        if match:
            failed = int(match.group(1))
        
        match = re.search(r'(\d+)\s+error', output)
        if match:
            failed += int(match.group(1))
        
        return passed, failed
    
    async def verify_patch_execution(
        self,
        instance: Dict[str, Any],
        generated_patch: str
    ) -> Dict[str, Any]:
        """
        High-level method to verify a patch for a SWE-bench instance.
        
        Args:
            instance: SWE-bench instance dict with repo, base_commit, test_patch, etc.
            generated_patch: The patch generated by the agent
            
        Returns:
            Execution result with pass/fail status
        """
        repo = instance.get("repo", "")
        base_commit = instance.get("base_commit", "")
        
        # Get test command from instance or use default
        test_cmd = instance.get("test_cmd", "pytest -x")
        
        # Get setup commands
        setup_cmds = instance.get("setup_commands")
        
        result = await self.execute_in_container(
            repo=repo,
            base_commit=base_commit,
            patch=generated_patch,
            test_cmd=test_cmd,
            setup_commands=setup_cmds
        )
        
        result["instance_id"] = instance.get("instance_id", "unknown")
        result["repo"] = repo
        result["base_commit"] = base_commit
        
        return result


# Lightweight execution for environments without Docker
class LocalExecutor:
    """
    Fallback executor for environments without Docker.
    Uses local git and pytest - less isolated but functional for testing.
    """
    
    async def execute_patch(
        self,
        repo_path: str,
        patch: str,
        test_cmd: str = "pytest -x"
    ) -> Dict[str, Any]:
        """Execute patch locally (for testing purposes)."""
        import time
        start_time = time.time()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy repo to temp
            shutil.copytree(repo_path, f"{tmpdir}/repo")
            
            # Write and apply patch
            patch_file = Path(tmpdir) / "fix.patch"
            patch_file.write_text(patch)
            
            try:
                # Apply patch
                apply_result = subprocess.run(
                    ["git", "apply", str(patch_file)],
                    cwd=f"{tmpdir}/repo",
                    capture_output=True,
                    timeout=30
                )
                
                if apply_result.returncode != 0:
                    return {
                        "success": False,
                        "exit_code": apply_result.returncode,
                        "stdout": "",
                        "stderr": f"Patch apply failed: {apply_result.stderr.decode()}",
                        "tests_passed": 0,
                        "tests_failed": 0,
                        "execution_time": time.time() - start_time,
                        "error": "patch_apply_failed"
                    }
                
                # Run tests
                test_result = subprocess.run(
                    test_cmd.split(),
                    cwd=f"{tmpdir}/repo",
                    capture_output=True,
                    timeout=300
                )
                
                return {
                    "success": test_result.returncode == 0,
                    "exit_code": test_result.returncode,
                    "stdout": test_result.stdout.decode('utf-8', errors='replace'),
                    "stderr": test_result.stderr.decode('utf-8', errors='replace'),
                    "tests_passed": 0,  # Would need parsing
                    "tests_failed": 0,
                    "execution_time": time.time() - start_time,
                    "error": None if test_result.returncode == 0 else "test_failure"
                }
                
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Timeout",
                    "tests_passed": 0,
                    "tests_failed": 0,
                    "execution_time": time.time() - start_time,
                    "error": "timeout"
                }
            except Exception as e:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "tests_passed": 0,
                    "tests_failed": 0,
                    "execution_time": time.time() - start_time,
                    "error": str(e)
                }
