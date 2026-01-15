"""Green Agent Service - The Assessor and Orchestrator"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import uuid

from ..a2a import (
    A2AServer,
    AgentCard,
    Task,
    TaskStatus,
    Artifact,
    Part,
    PartType,
)
from ..a2a.client import A2AClient
from ..a2a.protocol import MessageType
from ..trajectory.capture import TrajectoryCapture
from ..scoring.advanced_metrics import AdvancedMetrics
from .scenario_manager import ScenarioManager
from .environment_orchestrator import EnvironmentOrchestrator
from .verification_engine import VerificationEngine
from .ambiguity_layer import AmbiguityLayer
from .reproduction_gate import ReproductionGate

# Anti-contamination imports
try:
    from ..anti_contamination import (
        AntiContaminationConfig,
        AntiContaminationPipeline,
        EvaluationSlice,
        RunMode,
    )
    ANTI_CONTAMINATION_AVAILABLE = True
except ImportError:
    ANTI_CONTAMINATION_AVAILABLE = False

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
        enable_mutation: bool = True,
        purple_agent_url: Optional[str] = None,
        allow_mock_reproduction: bool = False,
        purple_timeout_seconds: int = 3600,
        dataset_config: str = "verified",
        # Anti-contamination settings
        allow_heuristics: bool = False,
        evaluation_slice: Optional[str] = None,
        mutation_level: str = "medium",
        mutation_seed: Optional[int] = None,
    ):
        self.name = name
        self.version = version
        self.host = host
        self.port = port
        self.enable_ambiguity = enable_ambiguity
        self.enable_mutation = enable_mutation
        self.purple_agent_url = purple_agent_url
        self.purple_timeout_seconds = purple_timeout_seconds
        self.allow_heuristics = allow_heuristics
        self.default_evaluation_slice = evaluation_slice
        
        # Initialize components
        self.scenario_manager = ScenarioManager(dataset_config=dataset_config)
        self.environment_orchestrator = EnvironmentOrchestrator()
        self.verification_engine = VerificationEngine()
        self.ambiguity_layer = AmbiguityLayer() if enable_ambiguity else None
        self.reproduction_gate = ReproductionGate(
            strict_mode=True,
            allow_mock_verification=allow_mock_reproduction
        )
        self.a2a_client = A2AClient(agent_id=self.name)
        self.trajectory_capture = TrajectoryCapture(enable_streaming=False)
        self.metrics = AdvancedMetrics()
        
        # Initialize anti-contamination pipeline
        self.anti_contamination = None
        if ANTI_CONTAMINATION_AVAILABLE:
            ac_config = AntiContaminationConfig(
                enable_mutations=enable_mutation,
                mutation_level=mutation_level,
                mutation_seed=mutation_seed,
                allow_heuristics=allow_heuristics,
            )
            self.anti_contamination = AntiContaminationPipeline(config=ac_config)
            logger.info(f"Anti-contamination pipeline initialized: heuristics={allow_heuristics}")
        
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
        
        environment = None
        purple_task_id = None
        action_logger = self.trajectory_capture.create_logger(assessment_id)
        
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
            await action_logger.log_action(
                "scenario_select",
                action_target=scenario.get("instance_id"),
                action_output="selected"
            )
            
            # Apply ambiguity injection if enabled
            issue_description = scenario["problem_statement"]
            if self.enable_ambiguity and self.ambiguity_layer:
                issue_description = await self.ambiguity_layer.inject_ambiguity(
                    issue_description,
                    level=task.constraints.get("ambiguity_level", "medium") if task.constraints else "medium"
                )
                logger.info("Applied ambiguity injection to issue description")
                await action_logger.log_action(
                    "ambiguity_injection",
                    action_target=scenario.get("instance_id"),
                    action_output="applied"
                )
            
            # Provision environment
            repo_url = scenario.get("repo_url") or f"https://github.com/{scenario.get('repo')}.git"
            environment = await self.environment_orchestrator.provision_environment(
                repo_url=repo_url,
                commit_hash=scenario["base_commit"],
                instance_id=scenario["instance_id"]
            )
            
            if not environment:
                raise RuntimeError("Failed to provision environment")
            
            logger.info(f"Provisioned environment: {environment['container_id']}")
            await action_logger.log_action(
                "provision_environment",
                action_target=environment.get("container_id"),
                action_output="ready"
            )
            # Attach environment to task resources for downstream gates
            task.resources = task.resources or {}
            task.resources["environment"] = environment
            task.resources["scenario_id"] = scenario["instance_id"]
            
            # Apply anti-contamination pipeline if available
            ac_metadata = None
            if self.anti_contamination and ANTI_CONTAMINATION_AVAILABLE:
                from pathlib import Path
                repo_path = Path(environment.get("repo_path", "/tmp/repo"))
                prepared_scenario, ac_task_metadata = await self.anti_contamination.prepare_task(
                    instance=scenario,
                    repo_path=repo_path,
                    evaluation_slice=EvaluationSlice(self.default_evaluation_slice) if self.default_evaluation_slice else None,
                    force_heuristics=self.allow_heuristics,
                )
                scenario = prepared_scenario
                ac_metadata = ac_task_metadata.to_dict()
                
                await action_logger.log_action(
                    "anti_contamination",
                    action_target=scenario.get("instance_id"),
                    action_output="applied",
                    metadata=ac_metadata
                )
            elif self.enable_mutation:
                # Fallback to legacy mutation if pipeline not available
                await self._apply_code_mutation(environment, scenario)
                logger.info("Applied code mutation to environment (legacy)")
                await action_logger.log_action(
                    "mutation",
                    action_target=scenario.get("instance_id"),
                    action_output="applied"
                )
            
            purple_url = (
                task.metadata.get("purple_agent_url")
                if task.metadata
                else None
            ) or self.purple_agent_url
            if not purple_url:
                raise ValueError("No Purple agent URL provided for task dispatch")
            
            purple_task_id = await self._dispatch_task_to_purple(
                purple_url=purple_url,
                title=scenario["instance_id"],
                description=issue_description,
                task=task,
                assessment_id=assessment_id,
                scenario=scenario,
                task_metadata=ac_metadata,
            )
            if not purple_task_id:
                raise RuntimeError("Failed to create task on Purple agent")
            await action_logger.log_action(
                "dispatch_task",
                action_target=purple_task_id,
                action_output="sent",
                metadata={"purple_url": purple_url}
            )
            
            purple_artifact = await self._wait_for_purple_artifact(
                purple_url=purple_url,
                purple_task_id=purple_task_id,
                task=task,
            )
            await action_logger.log_action(
                "receive_artifact",
                action_target=purple_task_id,
                action_output="received",
                metadata={"artifact_type": (purple_artifact.metadata or {}).get("type")}
            )
            
            # Extract patch from artifact
            patch = self._extract_patch_from_artifact(purple_artifact)
            
            # Apply patch and run verification
            verification_result = await self.verification_engine.verify_patch(
                environment=environment,
                patch=patch,
                test_commands=scenario.get("test_commands", []),
                oracle_tests=scenario.get("oracle_tests", []),
                timeout_seconds=task.constraints.get("test_timeout_seconds", 600) if task.constraints else 600,
                flaky_retries=task.constraints.get("flaky_retries", 0) if task.constraints else 0,
                fuzz_commands=scenario.get("fuzz_commands", []),
                adversarial_commands=scenario.get("adversarial_commands", []),
            )
            
            logger.info(f"Verification result: {verification_result}")
            await action_logger.log_action(
                "verification",
                action_target=scenario.get("instance_id"),
                action_output="completed",
                success=verification_result.get("passed", False),
                metadata={
                    "tests_passed": verification_result.get("tests_passed", 0),
                    "tests_failed": verification_result.get("tests_failed", 0),
                }
            )

            # Collect trajectory
            trajectory = []
            try:
                trajectory = await self.trajectory_capture.get_task_trajectory(assessment_id)
            except Exception as e:
                logger.warning(f"Failed to fetch trajectory from store: {e}")
                trajectory = getattr(action_logger, "action_stack", [])

            # Compute advanced metrics
            score = None
            try:
                score = await self.metrics.calculate_comprehensive_score(
                    task_id=task.id,
                    task_result={
                        "passed": verification_result.get("passed", False),
                        "tests_passed": verification_result.get("tests_passed", 0),
                        "tests_failed": verification_result.get("tests_failed", 0),
                        "execution_time": verification_result.get("execution_time", 0),
                        "difficulty": scenario.get("difficulty", "medium"),
                    },
                    trajectory=trajectory or [],
                    dialogue_metrics=None,
                    reproduction_metrics=None,
                    review_metrics=None,
                )
            except Exception as e:
                logger.warning(f"Failed to compute advanced metrics: {e}")
            
            # Prepare result
            result = {
                "success": verification_result["passed"],
                "metrics": {
                    "tests_passed": verification_result.get("tests_passed", 0),
                    "tests_failed": verification_result.get("tests_failed", 0),
                    "execution_time": verification_result.get("execution_time", 0),
                    "token_usage": verification_result.get("token_usage", 0)
                },
                # Anti-contamination provenance
                "metadata": ac_metadata or {
                    "evaluation_slice": "verified",
                    "run_mode": "llm_only" if not self.allow_heuristics else "heuristic_assisted",
                    "heuristics_allowed": self.allow_heuristics,
                    "mutation_applied": False,
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
                                    "trajectory": trajectory,
                                    "score": score,
                                    "anti_contamination": ac_metadata,
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
        
        finally:
            if action_logger:
                try:
                    self.trajectory_capture.remove_logger(assessment_id)
                except Exception as log_cleanup_error:
                    logger.warning(f"Failed to remove action logger for {assessment_id}: {log_cleanup_error}")
            if environment:
                try:
                    await self.environment_orchestrator.cleanup_environment(environment["container_id"])
                except Exception as cleanup_error:
                    logger.warning(f"Cleanup failed for container {environment.get('container_id')}: {cleanup_error}")
    
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
    
    def _extract_reproduction_script(self, artifact: Artifact) -> Optional[str]:
        """Extract reproduction script content from artifact"""
        for part in artifact.parts:
            if part.type == PartType.CODE and part.metadata:
                if part.metadata.get("purpose") == "reproduction":
                    return part.content
        return None
    
    async def _dispatch_task_to_purple(
        self,
        purple_url: str,
        title: str,
        description: str,
        task: Task,
        assessment_id: str,
        scenario: Dict[str, Any],
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Send task to Purple agent via A2A and return task id"""
        resources = {
            "environment": task.resources.get("environment") if task.resources else None,
            "scenario_id": scenario["instance_id"],
            "repo_url": scenario.get("repo_url") or scenario.get("repo"),
            "base_commit": scenario.get("base_commit"),
            "test_commands": scenario.get("test_commands"),
            "oracle_tests": scenario.get("oracle_tests"),
        }
        constraints = task.constraints or {}
        metadata = (task.metadata or {}).copy() if task.metadata else {}
        metadata.update(
            {
                "assessment_id": assessment_id,
                "scenario_id": scenario["instance_id"],
                "green_agent": self.name,
                # Anti-contamination metadata
                "heuristics_allowed": self.allow_heuristics,
            }
        )
        # Add anti-contamination provenance if available
        if task_metadata:
            metadata["anti_contamination"] = task_metadata
        
        purple_task_id = await self.a2a_client.create_task(
            server_url=purple_url,
            title=title,
            description=description,
            resources=resources,
            constraints=constraints,
            metadata=metadata,
        )
        if purple_task_id:
            logger.info(f"Created Purple task {purple_task_id} at {purple_url}")
        return purple_task_id
    
    async def _wait_for_purple_artifact(
        self,
        purple_url: str,
        purple_task_id: str,
        task: Task,
    ) -> Artifact:
        """Poll Purple task for reproduction then patch artifact"""
        processed: set = set()
        start = time.time()
        while time.time() - start < self.purple_timeout_seconds:
            status = await self.a2a_client.get_task_status(purple_url, purple_task_id)
            if not status:
                raise RuntimeError("Failed to fetch Purple task status")
            artifacts_data = status.get("artifacts") or []
            for artifact_data in artifacts_data:
                artifact_id = artifact_data.get("id")
                if artifact_id in processed:
                    continue
                processed.add(artifact_id)
                artifact = Artifact(**artifact_data)
                artifact_type = (artifact.metadata or {}).get("type")
                
                if artifact_type == "reproduction_script":
                    script = self._extract_reproduction_script(artifact)
                    if not script:
                        raise ValueError("Reproduction artifact missing script content")
                    await self.reproduction_gate.submit_reproduction(task, script)
                    continue
                
                is_patch = artifact_type == "patch_submission" or any(
                    part.type == PartType.FILE_DIFF for part in artifact.parts
                )
                if is_patch:
                    allowed = await self.reproduction_gate.check_patch_allowed(task)
                    if not allowed["allowed"]:
                        raise ValueError(f"Patch rejected: {allowed['reason']}")
                    return artifact
            await asyncio.sleep(2)
        raise TimeoutError("Timed out waiting for Purple agent artifact")
    
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
    
    async def run(self):
        """Run the Green Agent Service"""
        logger.info(f"Starting {self.name} on {self.host}:{self.port}")
        await self.server.run_async()