"""Issue2Test Reproduction Gate - Enforces Test-Driven Development"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from ..a2a.protocol import Task, Artifact, Part, PartType

logger = logging.getLogger(__name__)


class ReproductionStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    PENDING = "pending"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    REJECTED = "rejected"


class ReproductionGate:
    """
    Enforces the Issue2Test protocol - agents must reproduce the bug
    before they can submit a patch.
    
    This ensures agents understand the problem before fixing it,
    following Test-Driven Development principles.
    """
    
    def __init__(self, strict_mode: bool = True, allow_mock_verification: bool = False):
        """
        Args:
            strict_mode: If True, completely blocks patches until reproduction verified
            allow_mock_verification: If True, fall back to heuristic mock when no environment is available
        """
        self.strict_mode = strict_mode
        self.allow_mock_verification = allow_mock_verification
        
        # Track reproduction status per task
        self.task_reproductions: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            "total_attempts": 0,
            "successful_reproductions": 0,
            "failed_reproductions": 0,
            "rejected_patches": 0,
            "hallucinated_reproductions": 0  # Scripts that pass when they should fail
        }
    
    async def check_reproduction_required(
        self,
        task: Task,
        skip_for_simple_tasks: bool = False
    ) -> bool:
        """
        Check if reproduction is required for a task
        
        Args:
            task: The task to check
            skip_for_simple_tasks: Skip reproduction for trivial tasks
            
        Returns:
            Whether reproduction is required
        """
        task_id = task.id
        
        # Check if already verified
        if task_id in self.task_reproductions:
            status = self.task_reproductions[task_id]["status"]
            if status == ReproductionStatus.VERIFIED:
                return False  # Already done
        
        # In strict mode, always require reproduction
        if self.strict_mode:
            return True
        
        # Check if task is simple enough to skip
        if skip_for_simple_tasks:
            difficulty = task.metadata.get("difficulty", "medium") if task.metadata else "medium"
            if difficulty == "easy":
                return False
        
        return True
    
    async def submit_reproduction(
        self,
        task: Task,
        reproduction_script: str,
        expected_error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit a reproduction script for verification
        
        Args:
            task: The task being reproduced
            reproduction_script: Python script that should reproduce the bug
            expected_error: Optional expected error message/type
            
        Returns:
            Verification result
        """
        task_id = task.id
        self.stats["total_attempts"] += 1
        
        # Initialize tracking if needed
        if task_id not in self.task_reproductions:
            self.task_reproductions[task_id] = {
                "status": ReproductionStatus.PENDING,
                "attempts": [],
                "verified_at": None,
                "verified_script": None
            }
        
        reproduction_data = self.task_reproductions[task_id]
        reproduction_data["status"] = ReproductionStatus.VERIFYING
        
        # Record attempt
        attempt = {
            "script": reproduction_script,
            "expected_error": expected_error,
            "submitted_at": datetime.utcnow().isoformat(),
            "result": None
        }
        reproduction_data["attempts"].append(attempt)
        
        # Verify the reproduction
        verification_result = await self._verify_reproduction(
            task,
            reproduction_script,
            expected_error
        )
        
        attempt["result"] = verification_result
        
        # Update status based on result
        if verification_result["success"]:
            if verification_result["reproduced_bug"]:
                reproduction_data["status"] = ReproductionStatus.VERIFIED
                reproduction_data["verified_at"] = datetime.utcnow().isoformat()
                reproduction_data["verified_script"] = reproduction_script
                self.stats["successful_reproductions"] += 1
                
                logger.info(f"Reproduction verified for task {task_id}")
            else:
                # Script passed when it should have failed
                reproduction_data["status"] = ReproductionStatus.REJECTED
                self.stats["hallucinated_reproductions"] += 1
                
                logger.warning(f"Reproduction script passed but should fail for task {task_id}")
        else:
            reproduction_data["status"] = ReproductionStatus.FAILED
            self.stats["failed_reproductions"] += 1
            
            logger.error(f"Reproduction verification failed for task {task_id}")
        
        return verification_result
    
    async def _verify_reproduction(
        self,
        task: Task,
        script: str,
        expected_error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify that a reproduction script actually reproduces the bug
        
        Args:
            task: The task
            script: Reproduction script
            expected_error: Expected error
            
        Returns:
            Verification result
        """
        # Get environment from task resources
        environment = task.resources.get("environment") if task.resources else None
        
        if not environment:
            if self.allow_mock_verification:
                # Mock verification for testing
                return await self._mock_verification(script, expected_error)
            raise ValueError("No environment available for reproduction verification")
        
        # Run script in unpatched environment
        from ..green_agent.environment_orchestrator import EnvironmentOrchestrator
        orchestrator = EnvironmentOrchestrator()
        
        # Save script to container
        script_file = "/tmp/reproduce_bug.py"
        save_cmd = f"cat > {script_file} << 'EOF'\n{script}\nEOF"
        
        result = await orchestrator.execute_in_environment(
            environment["container_id"],
            save_cmd
        )
        
        # Run the script
        run_cmd = f"cd /workspace/repo && python {script_file}"
        run_result = await orchestrator.execute_in_environment(
            environment["container_id"],
            run_cmd
        )
        
        # Check if script failed (which means bug is reproduced)
        exit_code = run_result.get("exit_code", 0)
        stdout = run_result.get("stdout", "")
        stderr = run_result.get("stderr", "")
        
        reproduced_bug = exit_code != 0
        
        # If expected error provided, check if it matches
        error_matched = True
        if expected_error and reproduced_bug:
            output = stdout + stderr
            error_matched = expected_error.lower() in output.lower()
        
        return {
            "success": True,
            "reproduced_bug": reproduced_bug,
            "error_matched": error_matched,
            "exit_code": exit_code,
            "output": stdout + stderr,
            "message": self._generate_feedback(reproduced_bug, error_matched)
        }
    
    async def _mock_verification(
        self,
        script: str,
        expected_error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Mock verification for testing"""
        # Simple heuristic: if script contains 'assert' or 'raise', it's trying to fail
        reproduced = "assert" in script or "raise" in script
        
        return {
            "success": True,
            "reproduced_bug": reproduced,
            "error_matched": True,
            "exit_code": 1 if reproduced else 0,
            "output": "Mock verification completed",
            "message": self._generate_feedback(reproduced, True)
        }
    
    def _generate_feedback(self, reproduced: bool, error_matched: bool) -> str:
        """Generate feedback message for reproduction attempt"""
        if reproduced and error_matched:
            return "✅ Bug successfully reproduced. You may now submit a patch."
        elif reproduced and not error_matched:
            return "⚠️ Script failed but error doesn't match expected. Please verify the reproduction."
        elif not reproduced:
            return "❌ Script passed but should fail. You have not reproduced the bug. Please review the issue description."
        else:
            return "❓ Unexpected verification result. Please try again."
    
    async def check_patch_allowed(
        self,
        task: Task,
        bypass_token: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Check if patch submission is allowed for a task
        
        Args:
            task: The task
            bypass_token: Optional bypass token for special cases
            
        Returns:
            Dict with 'allowed' boolean and 'reason' string
        """
        task_id = task.id
        
        # Check for bypass
        if bypass_token and self._validate_bypass_token(bypass_token):
            return {
                "allowed": True,
                "reason": "Bypass token accepted"
            }
        
        # Check reproduction status
        if task_id not in self.task_reproductions:
            if self.strict_mode:
                return {
                    "allowed": False,
                    "reason": "No reproduction attempt found. Please submit a reproduction script first."
                }
            else:
                return {
                    "allowed": True,
                    "reason": "Reproduction not required (non-strict mode)"
                }
        
        status = self.task_reproductions[task_id]["status"]
        
        if status == ReproductionStatus.VERIFIED:
            return {
                "allowed": True,
                "reason": "Reproduction verified"
            }
        elif status == ReproductionStatus.VERIFYING:
            return {
                "allowed": False,
                "reason": "Reproduction verification in progress. Please wait."
            }
        elif status == ReproductionStatus.REJECTED:
            return {
                "allowed": False,
                "reason": "Your reproduction script passed when it should fail. Please fix your reproduction."
            }
        elif status == ReproductionStatus.FAILED:
            return {
                "allowed": False,
                "reason": "Reproduction verification failed. Please submit a valid reproduction script."
            }
        else:
            return {
                "allowed": False,
                "reason": "Reproduction not yet verified. Please submit a reproduction script."
            }
    
    def _validate_bypass_token(self, token: str) -> bool:
        """Validate bypass token (for emergency/admin use)"""
        # In production, this would check against secure token store
        return token == "EMERGENCY_BYPASS_2024"
    
    async def reject_patch(self, task: Task, reason: str) -> Dict[str, Any]:
        """
        Reject a patch submission due to missing reproduction
        
        Args:
            task: The task
            reason: Rejection reason
            
        Returns:
            Rejection response
        """
        self.stats["rejected_patches"] += 1
        
        return {
            "success": False,
            "error": "Patch rejected",
            "reason": reason,
            "message": f"❌ {reason}",
            "next_step": "Please submit a reproduction script that demonstrates the bug before submitting a patch.",
            "help_url": "https://docs.swebench.com/issue2test"
        }
    
    def get_reproduction_status(self, task_id: str) -> Dict[str, Any]:
        """Get reproduction status for a task"""
        if task_id not in self.task_reproductions:
            return {
                "status": ReproductionStatus.NOT_ATTEMPTED,
                "attempts": 0,
                "verified": False
            }
        
        data = self.task_reproductions[task_id]
        return {
            "status": data["status"],
            "attempts": len(data["attempts"]),
            "verified": data["status"] == ReproductionStatus.VERIFIED,
            "verified_at": data.get("verified_at"),
            "last_attempt": data["attempts"][-1] if data["attempts"] else None
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get reproduction gate statistics"""
        verified_count = sum(
            1 for data in self.task_reproductions.values()
            if data["status"] == ReproductionStatus.VERIFIED
        )
        
        return {
            **self.stats,
            "tasks_with_reproductions": len(self.task_reproductions),
            "verified_reproductions": verified_count,
            "verification_rate": verified_count / max(self.stats["total_attempts"], 1),
            "hallucination_rate": self.stats["hallucinated_reproductions"] / max(self.stats["total_attempts"], 1)
        }
    
    async def generate_reproduction_hints(
        self,
        task: Task,
        previous_attempts: Optional[List[str]] = None
    ) -> List[str]:
        """
        Generate hints for creating a good reproduction script
        
        Args:
            task: The task
            previous_attempts: Previous failed attempts
            
        Returns:
            List of hints
        """
        hints = [
            "The reproduction script should fail (exit code != 0) on the buggy code",
            "Focus on the specific behavior described in the problem statement",
            "Use assertions to verify expected vs actual behavior",
            "Import only necessary modules from the repository",
            "Keep the reproduction minimal - only test the bug, not the entire feature"
        ]
        
        # Add task-specific hints
        if task.description:
            if "TypeError" in task.description or "type" in task.description.lower():
                hints.append("Include type checking in your reproduction")
            if "ValueError" in task.description or "value" in task.description.lower():
                hints.append("Test with the specific values mentioned in the issue")
            if "import" in task.description.lower():
                hints.append("Ensure you're importing from the correct module path")
        
        # Add hints based on previous attempts
        if previous_attempts:
            if len(previous_attempts) > 2:
                hints.append("Consider simplifying your reproduction - focus on the core issue")
            for attempt in previous_attempts[-2:]:
                if "assert" not in attempt:
                    hints.append("Use assert statements to verify the buggy behavior")
                if "try" in attempt and "except" in attempt:
                    hints.append("Let exceptions propagate - don't catch them in the reproduction")
        
        return hints