"""Green Agent Service - The Assessor and Orchestrator"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import uuid

from ..a2a import A2AServer, AgentCard, Task, TaskStatus, Artifact, Part, PartType
from .scenario_manager import ScenarioManager
from .environment_orchestrator import EnvironmentOrchestrator
from .verification_engine import VerificationEngine
from .ambiguity_layer import AmbiguityLayer

logger = logging.getLogger(__name__)


class GreenAgentService:
    """
    Green Agent Service that orchestrates SWE-bench evaluation.
    Acts as the assessor in the AAA framework.
    """
    
    def __init__(
        self,
        name: str = "SWE-bench Green Agent",
        version: str = "1.0.0",
        host: str = "0.0.0.0",
        port: int = 8000,
        enable_ambiguity: bool = True,
        enable_mutation: bool = True
    ):
        self.name = name
        self.version = version
        self.host = host
        self.port = port
        self.enable_ambiguity = enable_ambiguity
        self.enable_mutation = enable_mutation
        
        # Initialize components
        self.scenario_manager = ScenarioManager()
        self.environment_orchestrator = EnvironmentOrchestrator()
        self.verification_engine = VerificationEngine()
        self.ambiguity_layer = AmbiguityLayer() if enable_ambiguity else None
        
        # Track active assessments
        self.active_assessments: Dict[str, Dict[str, Any]] = {}
        
        # Create agent card
        self.agent_card = AgentCard(
            name=self.name,
            version=self.version,
            capabilities=[
                "swe-bench-evaluation",
                "code-generation",
                "diff-review",
                "python",
                "dynamic-environment",
                "ambiguity-injection"
            ],
            endpoints={
                "task": f"http://{host}:{port}/a2a/task",
                "streaming": f"http://{host}:{port}/a2a/task/{{task_id}}/stream",
                "health": f"http://{host}:{port}/health"
            },
            description="Green Agent Service for SWE-bench evaluation using A2A protocol"
        )
        
        # Initialize A2A server
        self.server = A2AServer(
            agent_card=self.agent_card,
            task_handler=self.handle_assessment_task,
            host=host,
            port=port
        )
    
    async def handle_assessment_task(self, task: Task) -> Dict[str, Any]:
        """
        Handle an assessment task from a Purple Agent.
        
        This is the main entry point for evaluation.
        """
        assessment_id = str(uuid.uuid4())
        logger.info(f"Starting assessment {assessment_id} for task {task.id}")
        
        try:
            # Store assessment context
            self.active_assessments[assessment_id] = {
                "task_id": task.id,
                "started_at": datetime.utcnow(),
                "purple_agent_id": task.metadata.get("agent_id") if task.metadata else None
            }
            
            # Parse task resources to get scenario selection
            scenario_id = None
            if task.resources:
                scenario_id = task.resources.get("scenario_id")
                
            # Select a scenario (specific or random)
            scenario = await self.scenario_manager.get_scenario(scenario_id)
            if not scenario:
                raise ValueError(f"Scenario {scenario_id} not found")
            
            logger.info(f"Selected scenario: {scenario['instance_id']}")
            
            # Apply ambiguity injection if enabled
            issue_description = scenario["problem_statement"]
            if self.enable_ambiguity and self.ambiguity_layer:
                issue_description = await self.ambiguity_layer.inject_ambiguity(
                    issue_description,
                    level=task.constraints.get("ambiguity_level", "medium") if task.constraints else "medium"
                )
                logger.info("Applied ambiguity injection to issue description")
            
            # Provision environment
            environment = await self.environment_orchestrator.provision_environment(
                repo_url=scenario["repo"],
                commit_hash=scenario["base_commit"],
                instance_id=scenario["instance_id"]
            )
            
            if not environment:
                raise RuntimeError("Failed to provision environment")
            
            logger.info(f"Provisioned environment: {environment['container_id']}")
            
            # Apply code mutation if enabled
            if self.enable_mutation:
                await self._apply_code_mutation(environment, scenario)
                logger.info("Applied code mutation to environment")
            
            # Create the actual task for the Purple Agent
            purple_task = {
                "issue_description": issue_description,
                "repo_url": scenario["repo"],
                "environment": {
                    "container_id": environment["container_id"],
                    "access_type": environment.get("access_type", "docker"),
                    "connection_info": environment.get("connection_info")
                },
                "allowed_tools": ["file_read", "file_write", "terminal", "search"],
                "time_limit": task.constraints.get("time_limit", 3600) if task.constraints else 3600,
                "metadata": {
                    "assessment_id": assessment_id,
                    "scenario_id": scenario["instance_id"]
                }
            }
            
            # Send task to Purple Agent and wait for response
            # This would normally involve A2A client communication
            # For now, we'll simulate the response
            
            # Wait for Purple Agent to submit artifact
            purple_artifact = await self._wait_for_purple_artifact(task.id)
            
            if not purple_artifact:
                raise TimeoutError("Purple Agent did not submit artifact in time")
            
            # Extract patch from artifact
            patch = self._extract_patch_from_artifact(purple_artifact)
            
            # Apply patch and run verification
            verification_result = await self.verification_engine.verify_patch(
                environment=environment,
                patch=patch,
                test_commands=scenario.get("test_commands", []),
                oracle_tests=scenario.get("oracle_tests", [])
            )
            
            logger.info(f"Verification result: {verification_result}")
            
            # Clean up environment
            await self.environment_orchestrator.cleanup_environment(environment["container_id"])
            
            # Prepare result
            result = {
                "success": verification_result["passed"],
                "metrics": {
                    "tests_passed": verification_result.get("tests_passed", 0),
                    "tests_failed": verification_result.get("tests_failed", 0),
                    "execution_time": verification_result.get("execution_time", 0),
                    "token_usage": verification_result.get("token_usage", 0)
                },
                "artifacts": [
                    Artifact(
                        parts=[
                            Part(
                                type=PartType.JSON,
                                content={
                                    "assessment_id": assessment_id,
                                    "scenario_id": scenario["instance_id"],
                                    "verification_result": verification_result,
                                    "trajectory": self._get_assessment_trajectory(assessment_id)
                                }
                            )
                        ],
                        metadata={"type": "assessment_result"}
                    )
                ],
                "error": verification_result.get("error")
            }
            
            # Update assessment record
            self.active_assessments[assessment_id]["completed_at"] = datetime.utcnow()
            self.active_assessments[assessment_id]["result"] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in assessment {assessment_id}: {e}")
            
            # Clean up on error
            if assessment_id in self.active_assessments:
                self.active_assessments[assessment_id]["error"] = str(e)
                self.active_assessments[assessment_id]["completed_at"] = datetime.utcnow()
            
            return {
                "success": False,
                "error": str(e),
                "artifacts": []
            }
    
    async def _apply_code_mutation(self, environment: Dict[str, Any], scenario: Dict[str, Any]):
        """Apply code mutation to prevent memorization"""
        # This would implement variable renaming, file moving, etc.
        # For now, this is a placeholder
        mutations = []
        
        # Example: Rename common variables
        if scenario.get("mutation_targets"):
            for target in scenario["mutation_targets"]:
                mutations.append({
                    "type": "rename_variable",
                    "file": target["file"],
                    "old_name": target["old_name"],
                    "new_name": f"{target['old_name']}_mut_{uuid.uuid4().hex[:8]}"
                })
        
        # Apply mutations to environment
        for mutation in mutations:
            await self.environment_orchestrator.apply_mutation(
                environment["container_id"],
                mutation
            )
    
    async def _wait_for_purple_artifact(self, task_id: str, timeout: int = 3600) -> Optional[Artifact]:
        """Wait for Purple Agent to submit an artifact"""
        # In a real implementation, this would monitor the task's artifact submissions
        # For now, we'll simulate waiting
        await asyncio.sleep(1)  # Simulate processing time
        
        # Return a simulated artifact
        return Artifact(
            parts=[
                Part(
                    type=PartType.FILE_DIFF,
                    content="diff --git a/test.py b/test.py\n...",
                    metadata={"file_path": "test.py"}
                )
            ]
        )
    
    def _extract_patch_from_artifact(self, artifact: Artifact) -> str:
        """Extract patch content from artifact"""
        patch_parts = [
            part for part in artifact.parts
            if part.type == PartType.FILE_DIFF
        ]
        
        if not patch_parts:
            raise ValueError("No patch found in artifact")
        
        # Combine all diff parts
        return "\n".join(part.content for part in patch_parts)
    
    def _get_assessment_trajectory(self, assessment_id: str) -> List[Dict[str, Any]]:
        """Get the trajectory of an assessment for analysis"""
        # This would return the logged trajectory of the Purple Agent's actions
        # For now, return a placeholder
        return [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "action": "search",
                "target": "views.py",
                "result": "found"
            },
            {
                "timestamp": datetime.utcnow().isoformat(),
                "action": "edit",
                "target": "views.py",
                "changes": "Applied fix"
            }
        ]
    
    def run(self):
        """Run the Green Agent Service"""
        logger.info(f"Starting {self.name} on {self.host}:{self.port}")
        self.server.run()