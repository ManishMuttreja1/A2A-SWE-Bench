"""Purple Agent Wrapper for A2A Protocol"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
import json

from ..a2a import (
    A2AServer, A2AClient, AgentCard, Task, TaskStatus,
    Artifact, Part, PartType, A2AProtocol
)

logger = logging.getLogger(__name__)


class PurpleAgentWrapper:
    """
    Wraps an existing solver agent to make it A2A-compliant.
    This is the participant in the AAA framework.
    """
    
    def __init__(
        self,
        agent_name: str,
        agent_version: str,
        solver_function: Callable,
        capabilities: Optional[list] = None,
        host: str = "0.0.0.0",
        port: int = 8001
    ):
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.solver_function = solver_function
        self.host = host
        self.port = port
        
        # Default capabilities
        if capabilities is None:
            capabilities = ["code-generation", "bug-fixing", "python"]
        
        # Create agent card
        self.agent_card = AgentCard(
            name=agent_name,
            version=agent_version,
            capabilities=capabilities,
            endpoints={
                "task": f"http://{host}:{port}/a2a/task",
                "streaming": f"http://{host}:{port}/a2a/task/{{task_id}}/stream",
                "health": f"http://{host}:{port}/health"
            },
            description=f"Purple Agent wrapper for {agent_name}"
        )
        
        # Initialize A2A server
        self.server = A2AServer(
            agent_card=self.agent_card,
            task_handler=self.handle_task,
            host=host,
            port=port
        )
        
        # Track active tasks
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        
        # MCP client for tool access (optional)
        self.mcp_client = None
    
    async def handle_task(self, task: Task) -> Dict[str, Any]:
        """
        Handle a task from the Green Agent.
        
        This wraps the solver function and converts its output to A2A format.
        """
        logger.info(f"Handling task {task.id}: {task.title}")
        
        try:
            # Store task context
            self.active_tasks[task.id] = {
                "task": task,
                "started_at": asyncio.get_event_loop().time()
            }
            
            # Extract task details
            task_input = {
                "issue_description": task.description,
                "resources": task.resources,
                "constraints": task.constraints
            }
            
            # Send progress update
            await self._send_progress(task.id, "Starting analysis", 0.1)
            
            # Call the wrapped solver function
            solver_result = await self._call_solver(task_input)
            
            # Send progress update
            await self._send_progress(task.id, "Generating patch", 0.7)
            
            # Convert solver result to ordered A2A artifacts (repro then patch)
            artifacts = self._create_artifacts_from_result(solver_result)
            
            # Send final progress
            await self._send_progress(task.id, "Completed", 1.0)
            
            # Return result
            result = {
                "success": solver_result.get("success", False),
                "artifacts": artifacts,
                "metrics": {
                    "execution_time": asyncio.get_event_loop().time() - self.active_tasks[task.id]["started_at"],
                    "tokens_used": solver_result.get("tokens_used", 0)
                }
            }
            
            # Clean up task context
            del self.active_tasks[task.id]
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling task {task.id}: {e}")
            
            # Clean up on error
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            
            return {
                "success": False,
                "error": str(e),
                "artifacts": []
            }
    
    async def _call_solver(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call the wrapped solver function.
        
        This handles both sync and async solver functions.
        """
        try:
            # Check if solver is async
            if asyncio.iscoroutinefunction(self.solver_function):
                result = await self.solver_function(task_input)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self.solver_function, task_input)
            
            return result
            
        except Exception as e:
            logger.error(f"Solver function error: {e}")
            return {
                "success": False,
                "error": str(e),
                "patch": None
            }
    
    def _create_artifacts_from_result(self, solver_result: Dict[str, Any]) -> list:
        """
        Convert solver result to ordered A2A artifacts (reproduction then patch).
        """
        artifacts = []
        
        reproduction_script = solver_result.get("reproduction_script")
        if reproduction_script:
            repro_artifact = Artifact(
                parts=[
                    Part(
                        type=PartType.CODE,
                        content=reproduction_script,
                        metadata={
                            "purpose": "reproduction",
                            "language": "python",
                            "expected_failure": True,
                        },
                    )
                ],
                metadata={
                    "type": "reproduction_script",
                    "solver": self.agent_name,
                    "version": self.agent_version,
                },
            )
            artifacts.append(repro_artifact)
        
        parts = []
        
        # Add patch if present
        if solver_result.get("patch"):
            parts.append(
                Part(
                    type=PartType.FILE_DIFF,
                    content=solver_result["patch"],
                    metadata={"type": "unified_diff"}
                )
            )
        
        # Add individual file changes if present
        if solver_result.get("file_changes"):
            for change in solver_result["file_changes"]:
                parts.append(
                    Part(
                        type=PartType.FILE_DIFF,
                        content=change["diff"],
                        metadata={
                            "file_path": change["file"],
                            "change_type": change.get("type", "modification")
                        }
                    )
                )
        
        # Add analysis if present
        if solver_result.get("analysis"):
            parts.append(
                Part(
                    type=PartType.TEXT,
                    content=solver_result["analysis"],
                    metadata={"type": "analysis"}
                )
            )
        
        # Add code if present (for new file creation)
        if solver_result.get("new_files"):
            for new_file in solver_result["new_files"]:
                parts.append(
                    Part(
                        type=PartType.CODE,
                        content=new_file["content"],
                        metadata={
                            "file_path": new_file["path"],
                            "language": new_file.get("language", "python")
                        }
                    )
                )
        
        if parts:
            patch_artifact = Artifact(
                parts=parts,
                metadata={
                    "type": "patch_submission",
                    "solver": self.agent_name,
                    "version": self.agent_version,
                    "success": solver_result.get("success", False),
                    "confidence": solver_result.get("confidence", 0.5)
                }
            )
            artifacts.append(patch_artifact)
        
        return artifacts
    
    async def _send_progress(self, task_id: str, message: str, progress: float):
        """Send progress update for a task"""
        try:
            if task_id in self.active_tasks:
                # In a real implementation, this would send to the Green Agent
                logger.info(f"Task {task_id} progress: {message} ({progress*100:.0f}%)")
        except Exception as e:
            logger.error(f"Error sending progress: {e}")
    
    def set_mcp_client(self, mcp_client):
        """Set MCP client for tool access"""
        self.mcp_client = mcp_client
    
    def run(self):
        """Run the Purple Agent server"""
        logger.info(f"Starting {self.agent_name} on {self.host}:{self.port}")
        self.server.run()


class SimpleSolver:
    """
    Example simple solver for testing.
    
    This would be replaced with actual solver logic (GPT-4, Claude, etc.)
    """
    
    def __init__(self, model_name: str = "simple-solver"):
        self.model_name = model_name
    
    async def solve(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Solve a task (simplified for testing).
        
        In reality, this would:
        1. Analyze the issue description
        2. Search the codebase
        3. Generate a fix
        4. Create a patch
        """
        issue = task_input.get("issue_description", "")
        
        # Simulate some processing
        await asyncio.sleep(0.5)
        
        # Generate a dummy patch
        patch = """diff --git a/example.py b/example.py
index abc123..def456 100644
--- a/example.py
+++ b/example.py
@@ -10,7 +10,7 @@ def buggy_function():
     # This is the buggy line
-    result = value / 0  # Bug: division by zero
+    result = value / 1  # Fixed: avoid division by zero
     return result
"""
        
        return {
            "success": True,
            "reproduction_script": """import pytest

def test_repro():
    # mock reproduction script that fails before fix
    assert False, "Reproduction: failing as expected"
""",
            "patch": patch,
            "analysis": f"Found and fixed the issue: {issue[:100]}...",
            "confidence": 0.85,
            "tokens_used": len(issue) * 2  # Rough estimate
        }