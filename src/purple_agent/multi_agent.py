"""Multi-Agent Team Coordination for Purple Agents"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from ..a2a import A2AClient, A2AProtocol, Task, Artifact, Part, PartType

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"


class MultiAgentTeam:
    """
    Coordinates a team of Purple Agents using the Triad pattern:
    - Architect (Manager): Decomposes tasks and coordinates
    - Developer (Coder): Implements solutions
    - Reviewer (QA): Validates and reviews code
    """
    
    def __init__(
        self,
        team_name: str = "Purple Team",
        architect_url: Optional[str] = None,
        developer_url: Optional[str] = None,
        reviewer_url: Optional[str] = None
    ):
        self.team_name = team_name
        
        # Agent endpoints (can be local or remote)
        self.agent_urls = {
            AgentRole.ARCHITECT: architect_url or "http://localhost:8001",
            AgentRole.DEVELOPER: developer_url or "http://localhost:8002",
            AgentRole.REVIEWER: reviewer_url or "http://localhost:8003"
        }
        
        # A2A client for inter-agent communication
        self.client = A2AClient(agent_id=f"{team_name}_coordinator")
        
        # Discovered agent cards
        self.agent_cards: Dict[AgentRole, Any] = {}
        
        # Task coordination state
        self.current_task: Optional[Task] = None
        self.subtasks: Dict[str, Dict[str, Any]] = {}
    
    async def discover_agents(self):
        """Discover all team agents via their Agent Cards"""
        for role, url in self.agent_urls.items():
            try:
                agent_card = await self.client.discover_agent(url)
                if agent_card:
                    self.agent_cards[role] = agent_card
                    logger.info(f"Discovered {role.value} agent: {agent_card.name}")
                else:
                    logger.warning(f"Failed to discover {role.value} agent at {url}")
            except Exception as e:
                logger.error(f"Error discovering {role.value} agent: {e}")
    
    async def solve_task(self, task: Task) -> Dict[str, Any]:
        """
        Solve a task using the multi-agent team.
        
        This implements the full Triad workflow.
        """
        self.current_task = task
        logger.info(f"Team {self.team_name} solving task: {task.title}")
        
        try:
            # 1. Architect decomposes the task
            decomposition = await self._architect_decompose(task)
            
            if not decomposition["success"]:
                return {
                    "success": False,
                    "error": "Failed to decompose task",
                    "artifacts": []
                }
            
            # 2. Developer implements each subtask
            implementations = []
            for subtask in decomposition["subtasks"]:
                impl = await self._developer_implement(subtask)
                implementations.append(impl)
            
            # 3. Combine implementations into a patch
            combined_patch = await self._combine_implementations(implementations)
            
            # 4. Reviewer validates the solution
            review_result = await self._reviewer_validate(
                task.description,
                combined_patch
            )
            
            # 5. If review fails, iterate (simplified - just one retry)
            if not review_result["approved"]:
                logger.info("Review failed, attempting fixes...")
                
                # Developer fixes issues
                fixed_patch = await self._developer_fix_issues(
                    combined_patch,
                    review_result["issues"]
                )
                
                # Review again
                final_review = await self._reviewer_validate(
                    task.description,
                    fixed_patch
                )
                
                if final_review["approved"]:
                    combined_patch = fixed_patch
                else:
                    logger.warning("Still has issues after fix attempt")
            
            # 6. Create final artifact
            final_artifact = A2AProtocol.create_artifact(
                parts=[
                    Part(
                        type=PartType.FILE_DIFF.value,
                        content=combined_patch,
                        metadata={"type": "final_patch"}
                    )
                ],
                metadata={
                    "team": self.team_name,
                    "review_status": review_result["approved"],
                    "iterations": 2 if not review_result["approved"] else 1
                }
            )
            
            return {
                "success": True,
                "artifacts": [final_artifact],
                "metrics": {
                    "subtasks": len(decomposition["subtasks"]),
                    "review_passed": review_result["approved"]
                }
            }
            
        except Exception as e:
            logger.error(f"Team error: {e}")
            return {
                "success": False,
                "error": str(e),
                "artifacts": []
            }
    
    async def _architect_decompose(self, task: Task) -> Dict[str, Any]:
        """Architect decomposes the main task into subtasks"""
        try:
            # Send task to Architect
            architect_url = self.agent_urls[AgentRole.ARCHITECT]
            
            task_id = await self.client.create_task(
                server_url=architect_url,
                title="Decompose SWE-bench task",
                description=task.description,
                resources=task.resources,
                metadata={"action": "decompose"}
            )
            
            if not task_id:
                return {"success": False, "subtasks": []}
            
            # Wait for decomposition result
            result = await self.client.wait_for_task_completion(
                architect_url, task_id, timeout=60
            )
            
            if result and result["status"] == "completed":
                # Extract subtasks from artifacts
                # In a real implementation, parse the architect's response
                subtasks = [
                    {
                        "id": "subtask_1",
                        "type": "locate_bug",
                        "description": "Find the bug location"
                    },
                    {
                        "id": "subtask_2",
                        "type": "implement_fix",
                        "description": "Implement the fix"
                    },
                    {
                        "id": "subtask_3",
                        "type": "add_tests",
                        "description": "Add test cases"
                    }
                ]
                
                return {"success": True, "subtasks": subtasks}
            
            return {"success": False, "subtasks": []}
            
        except Exception as e:
            logger.error(f"Architect error: {e}")
            return {"success": False, "subtasks": []}
    
    async def _developer_implement(self, subtask: Dict[str, Any]) -> Dict[str, Any]:
        """Developer implements a subtask"""
        try:
            developer_url = self.agent_urls[AgentRole.DEVELOPER]
            
            task_id = await self.client.create_task(
                server_url=developer_url,
                title=f"Implement: {subtask['type']}",
                description=subtask["description"],
                resources=self.current_task.resources if self.current_task else None,
                metadata={"subtask_id": subtask["id"]}
            )
            
            if not task_id:
                return {"success": False, "implementation": None}
            
            # Wait for implementation
            result = await self.client.wait_for_task_completion(
                developer_url, task_id, timeout=120
            )
            
            if result and result["status"] == "completed":
                # Extract implementation from artifacts
                # Simplified - return dummy implementation
                return {
                    "success": True,
                    "implementation": f"# Implementation for {subtask['id']}\n# Code here...\n"
                }
            
            return {"success": False, "implementation": None}
            
        except Exception as e:
            logger.error(f"Developer error: {e}")
            return {"success": False, "implementation": None}
    
    async def _combine_implementations(self, implementations: List[Dict[str, Any]]) -> str:
        """Combine multiple implementations into a single patch"""
        patch_parts = []
        
        for impl in implementations:
            if impl["success"] and impl["implementation"]:
                patch_parts.append(impl["implementation"])
        
        # In a real implementation, this would properly merge patches
        combined = "\n".join(patch_parts)
        
        # Convert to diff format
        diff = f"""diff --git a/solution.py b/solution.py
index abc123..def456 100644
--- a/solution.py
+++ b/solution.py
@@ -1,1 +1,{len(patch_parts)} @@
{combined}
"""
        return diff
    
    async def _reviewer_validate(self, issue: str, patch: str) -> Dict[str, Any]:
        """Reviewer validates the patch"""
        try:
            reviewer_url = self.agent_urls[AgentRole.REVIEWER]
            
            task_id = await self.client.create_task(
                server_url=reviewer_url,
                title="Review patch",
                description=f"Review this patch for issue: {issue[:200]}...",
                resources={"patch": patch},
                metadata={"action": "review"}
            )
            
            if not task_id:
                return {"approved": False, "issues": ["Failed to create review task"]}
            
            # Wait for review
            result = await self.client.wait_for_task_completion(
                reviewer_url, task_id, timeout=60
            )
            
            if result and result["status"] == "completed":
                # Parse review result
                # Simplified - randomly approve or reject
                import random
                approved = random.random() > 0.3  # 70% approval rate
                
                issues = [] if approved else [
                    "Missing error handling",
                    "Potential regression in edge case"
                ]
                
                return {"approved": approved, "issues": issues}
            
            return {"approved": False, "issues": ["Review failed"]}
            
        except Exception as e:
            logger.error(f"Reviewer error: {e}")
            return {"approved": False, "issues": [str(e)]}
    
    async def _developer_fix_issues(
        self,
        original_patch: str,
        issues: List[str]
    ) -> str:
        """Developer fixes issues identified by reviewer"""
        # In a real implementation, this would:
        # 1. Parse the issues
        # 2. Modify the patch to address them
        # 3. Return the updated patch
        
        # Simplified - just append a comment
        fixed_patch = original_patch + "\n# Fixed issues: " + ", ".join(issues)
        return fixed_patch
    
    async def get_team_status(self) -> Dict[str, Any]:
        """Get status of all team members"""
        status = {
            "team": self.team_name,
            "agents": {}
        }
        
        for role, url in self.agent_urls.items():
            try:
                # Check if agent is responsive
                agent_card = await self.client.discover_agent(url)
                status["agents"][role.value] = {
                    "available": agent_card is not None,
                    "url": url,
                    "name": agent_card.name if agent_card else "Unknown"
                }
            except Exception:
                status["agents"][role.value] = {
                    "available": False,
                    "url": url,
                    "name": "Unreachable"
                }
        
        return status