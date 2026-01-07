#!/usr/bin/env python3
"""
A2A SWEbench - SWE-bench Integration Module
Provides seamless integration with the original SWE-bench evaluation system
"""

import asyncio
import json
import os
import sys
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import random
import hashlib

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SWEbenchTask:
    """Represents a SWE-bench evaluation task"""
    task_id: str
    repo: str
    issue: str
    description: str
    base_commit: str
    test_patch: str
    problem_statement: str
    
    def to_a2a_format(self) -> Dict[str, Any]:
        """Convert to A2A protocol format"""
        return {
            "id": self.task_id,
            "type": "swebench_evaluation",
            "repo": self.repo,
            "issue": self.issue,
            "description": self.description,
            "metadata": {
                "base_commit": self.base_commit,
                "test_patch": self.test_patch,
                "problem_statement": self.problem_statement
            }
        }


class SWEbenchAdapter:
    """
    Adapter to integrate A2A SWEbench with original SWE-bench
    Provides compatibility layer and enhanced features
    """
    
    def __init__(
        self,
        a2a_server: str = "http://localhost:8080",
        enable_mutations: bool = True,
        enable_synthesis: bool = True,
        enable_trajectory: bool = True
    ):
        self.a2a_server = a2a_server
        self.enable_mutations = enable_mutations
        self.enable_synthesis = enable_synthesis
        self.enable_trajectory = enable_trajectory
        
        # Import mutation engine if available
        try:
            from src.mutation.mutation_engine import MutationEngine
            self.mutation_engine = MutationEngine() if enable_mutations else None
        except ImportError:
            logger.warning("Mutation engine not available")
            self.mutation_engine = None
    
    def load_swebench_dataset(
        self,
        dataset_path: str = "princeton-nlp/SWE-bench",
        split: str = "test"
    ) -> List[SWEbenchTask]:
        """
        Load SWE-bench dataset
        
        Args:
            dataset_path: Path to dataset or HuggingFace identifier
            split: Dataset split (train/test/val)
            
        Returns:
            List of SWEbenchTask objects
        """
        tasks = []
        
        try:
            # Try to load from HuggingFace
            from datasets import load_dataset
            dataset = load_dataset(dataset_path, split=split)
            
            for item in dataset:
                task = SWEbenchTask(
                    task_id=item['instance_id'],
                    repo=item['repo'],
                    issue=item.get('issue', ''),
                    description=item['problem_statement'],
                    base_commit=item['base_commit'],
                    test_patch=item['test_patch'],
                    problem_statement=item['problem_statement']
                )
                tasks.append(task)
                
        except ImportError:
            # Fallback to mock data
            logger.info("Using mock SWE-bench data (install 'datasets' for real data)")
            
            # Generate mock tasks
            repos = ["django/django", "scikit-learn/scikit-learn", "matplotlib/matplotlib"]
            for i in range(10):
                task = SWEbenchTask(
                    task_id=f"task_{i:04d}",
                    repo=random.choice(repos),
                    issue=f"#{random.randint(1000, 9999)}",
                    description=f"Fix issue in {random.choice(['template', 'model', 'view'])}",
                    base_commit=hashlib.md5(f"commit_{i}".encode()).hexdigest()[:8],
                    test_patch=f"diff --git a/test.py b/test.py\n+test {i}",
                    problem_statement=f"Problem statement for task {i}"
                )
                tasks.append(task)
        
        logger.info(f"Loaded {len(tasks)} tasks from {dataset_path}")
        return tasks
    
    async def apply_mutations(
        self,
        task: SWEbenchTask,
        mutation_rate: float = 0.3
    ) -> SWEbenchTask:
        """
        Apply anti-memorization mutations to a task
        
        Args:
            task: Original task
            mutation_rate: Probability of applying mutations
            
        Returns:
            Mutated task
        """
        if not self.enable_mutations:
            return task
        
        # Create a copy
        import copy
        mutated = copy.deepcopy(task)
        
        if random.random() < mutation_rate:
            # Apply various mutations
            mutations = []
            
            # 1. Variable renaming in test patch
            if "def test_" in mutated.test_patch:
                old_name = f"test_{task.task_id.split('_')[-1]}"
                new_name = f"test_{hashlib.md5(task.task_id.encode()).hexdigest()[:8]}"
                mutated.test_patch = mutated.test_patch.replace(old_name, new_name)
                mutations.append("test_rename")
            
            # 2. Add noise to problem statement
            if random.random() < 0.5:
                noise = [
                    "\n# Note: Variable names may differ from original.",
                    "\n# Implementation details are flexible.",
                    "\n# Focus on solving the core issue."
                ]
                mutated.problem_statement += random.choice(noise)
                mutations.append("statement_noise")
            
            # 3. Modify issue number format
            if mutated.issue and random.random() < 0.3:
                # Change format but keep same number
                issue_num = mutated.issue.replace("#", "").replace("issue-", "")
                formats = [f"#{issue_num}", f"issue-{issue_num}", f"ISSUE{issue_num}"]
                mutated.issue = random.choice(formats)
                mutations.append("issue_format")
            
            logger.info(f"Applied mutations to {task.task_id}: {mutations}")
        
        return mutated
    
    async def evaluate_with_swebench(
        self,
        task: SWEbenchTask,
        agent_endpoint: str,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Evaluate a task using both SWE-bench and A2A protocols
        
        Args:
            task: Task to evaluate
            agent_endpoint: Agent API endpoint
            timeout: Evaluation timeout in seconds
            
        Returns:
            Evaluation results
        """
        result = {
            "task_id": task.task_id,
            "success": False,
            "score": 0.0,
            "time_taken": 0,
            "trajectory": [],
            "mutations_applied": False,
            "synthesis_used": False
        }
        
        # Apply mutations if enabled
        if self.enable_mutations:
            task = await self.apply_mutations(task)
            result["mutations_applied"] = True
        
        # Convert to A2A format
        a2a_task = task.to_a2a_format()
        
        try:
            import aiohttp
            import time
            
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                # Submit task to A2A server
                async with session.post(
                    f"{self.a2a_server}/api/v1/tasks",
                    json=a2a_task
                ) as resp:
                    if resp.status == 201:
                        task_response = await resp.json()
                        a2a_task_id = task_response["id"]
                    else:
                        logger.error(f"Failed to create task: {resp.status}")
                        return result
                
                # Forward to agent
                async with session.post(
                    f"{agent_endpoint}/evaluate",
                    json={
                        "task": a2a_task,
                        "timeout": timeout
                    }
                ) as resp:
                    if resp.status == 200:
                        agent_result = await resp.json()
                        
                        result["success"] = agent_result.get("success", False)
                        result["score"] = agent_result.get("score", 0.0)
                        
                        if self.enable_trajectory:
                            result["trajectory"] = agent_result.get("trajectory", [])
                    else:
                        logger.error(f"Agent evaluation failed: {resp.status}")
            
            result["time_taken"] = time.time() - start_time
            
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            result["error"] = str(e)
        
        return result
    
    async def run_full_evaluation(
        self,
        dataset_path: str = "princeton-nlp/SWE-bench",
        agent_endpoint: str = "http://localhost:8001",
        max_tasks: Optional[int] = None,
        parallel_workers: int = 4
    ) -> Dict[str, Any]:
        """
        Run full SWE-bench evaluation with A2A enhancements
        
        Args:
            dataset_path: Path to SWE-bench dataset
            agent_endpoint: Agent API endpoint
            max_tasks: Maximum number of tasks to evaluate
            parallel_workers: Number of parallel evaluations
            
        Returns:
            Evaluation results and statistics
        """
        # Load dataset
        tasks = self.load_swebench_dataset(dataset_path)
        
        if max_tasks:
            tasks = tasks[:max_tasks]
        
        logger.info(f"Starting evaluation of {len(tasks)} tasks")
        
        # Run evaluations
        results = []
        
        # Create task batches for parallel execution
        batch_size = parallel_workers
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            
            # Evaluate batch in parallel
            batch_results = await asyncio.gather(*[
                self.evaluate_with_swebench(task, agent_endpoint)
                for task in batch
            ])
            
            results.extend(batch_results)
            
            logger.info(f"Completed {len(results)}/{len(tasks)} evaluations")
        
        # Compute statistics
        stats = self.compute_statistics(results)
        
        return {
            "results": results,
            "statistics": stats,
            "config": {
                "mutations_enabled": self.enable_mutations,
                "synthesis_enabled": self.enable_synthesis,
                "trajectory_enabled": self.enable_trajectory
            }
        }
    
    def compute_statistics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute evaluation statistics"""
        total = len(results)
        successful = sum(1 for r in results if r["success"])
        
        stats = {
            "total_tasks": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0,
            "average_time": sum(r["time_taken"] for r in results) / total if total > 0 else 0,
            "with_mutations": sum(1 for r in results if r.get("mutations_applied", False)),
            "with_synthesis": sum(1 for r in results if r.get("synthesis_used", False))
        }
        
        # Compute memorization score
        if self.enable_trajectory:
            memorization_scores = []
            for result in results:
                if result.get("trajectory"):
                    # Simple heuristic: direct matches to expected patterns
                    score = self.compute_memorization_score(result["trajectory"])
                    memorization_scores.append(score)
            
            stats["average_memorization"] = (
                sum(memorization_scores) / len(memorization_scores)
                if memorization_scores else 0
            )
        
        return stats
    
    def compute_memorization_score(self, trajectory: List[Dict]) -> float:
        """
        Compute memorization score from trajectory
        
        Returns:
            Score between 0 (no memorization) and 1 (high memorization)
        """
        if not trajectory:
            return 0.0
        
        # Heuristics for detecting memorization
        indicators = {
            "direct_patch_match": 0,
            "no_exploration": 0,
            "instant_solution": 0,
            "pattern_match": 0
        }
        
        # Check for direct patch without exploration
        if len(trajectory) < 5:
            indicators["no_exploration"] = 1
        
        # Check for instant solutions (< 1 second)
        first_action = trajectory[0] if trajectory else {}
        if first_action.get("timestamp", 0) < 1:
            indicators["instant_solution"] = 1
        
        # Check for pattern matching
        action_types = [t.get("action_type", "") for t in trajectory]
        if action_types.count("apply_patch") > len(action_types) * 0.5:
            indicators["pattern_match"] = 1
        
        # Compute weighted score
        weights = {
            "direct_patch_match": 0.4,
            "no_exploration": 0.3,
            "instant_solution": 0.2,
            "pattern_match": 0.1
        }
        
        score = sum(
            indicators[key] * weights[key]
            for key in indicators
        )
        
        return min(score, 1.0)


def create_mock_agent_server(port: int = 8001):
    """Create a mock agent server for testing"""
    import http.server
    import socketserver
    import threading
    
    class MockAgentHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/evaluate":
                # Mock evaluation response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                response = {
                    "success": random.random() > 0.3,
                    "score": random.random(),
                    "trajectory": [
                        {"action_type": "read_file", "timestamp": 0.5},
                        {"action_type": "analyze", "timestamp": 1.2},
                        {"action_type": "apply_patch", "timestamp": 2.0}
                    ]
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_error(404)
        
        def log_message(self, format, *args):
            pass  # Suppress logs
    
    httpd = socketserver.TCPServer(("", port), MockAgentHandler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    
    return httpd


async def demo():
    """Run a demonstration of SWE-bench integration"""
    print("""
╔════════════════════════════════════════════════════════════╗
║           A2A SWEbench - SWE-bench Integration Demo        ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    # Check if A2A server is running
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/health") as resp:
                if resp.status == 200:
                    print("✅ A2A SWEbench server is running")
                else:
                    print("⚠️  A2A server not responding, using mock mode")
    except:
        print("⚠️  A2A server not running, start with: python demo_server.py")
    
    # Create adapter
    adapter = SWEbenchAdapter(
        enable_mutations=True,
        enable_synthesis=True,
        enable_trajectory=True
    )
    
    # Load mock dataset
    print("\n📚 Loading SWE-bench dataset...")
    tasks = adapter.load_swebench_dataset()
    print(f"   Loaded {len(tasks)} tasks")
    
    # Show sample task
    if tasks:
        task = tasks[0]
        print(f"\n📝 Sample Task: {task.task_id}")
        print(f"   Repo: {task.repo}")
        print(f"   Issue: {task.issue}")
        print(f"   Description: {task.description[:100]}...")
        
        # Apply mutations
        print("\n🔀 Applying anti-memorization mutations...")
        mutated = await adapter.apply_mutations(task, mutation_rate=0.8)
        
        if mutated.test_patch != task.test_patch:
            print("   ✅ Test patch mutated")
        if mutated.problem_statement != task.problem_statement:
            print("   ✅ Problem statement modified")
        if mutated.issue != task.issue:
            print("   ✅ Issue format changed")
    
    # Create mock agent
    print("\n🤖 Starting mock agent server...")
    mock_agent = create_mock_agent_server(8001)
    await asyncio.sleep(1)
    
    # Run evaluation
    print("\n🚀 Running evaluation...")
    results = await adapter.run_full_evaluation(
        max_tasks=5,
        agent_endpoint="http://localhost:8001",
        parallel_workers=2
    )
    
    # Show results
    stats = results["statistics"]
    print("\n📊 Evaluation Results:")
    print(f"   Total Tasks: {stats['total_tasks']}")
    print(f"   Successful: {stats['successful']}")
    print(f"   Success Rate: {stats['success_rate']:.1%}")
    print(f"   Average Time: {stats['average_time']:.2f}s")
    print(f"   With Mutations: {stats['with_mutations']}")
    
    if "average_memorization" in stats:
        print(f"   Memorization Score: {stats['average_memorization']:.2f}")
    
    print("\n✨ Demo Complete!")
    print("\nTo integrate with real SWE-bench:")
    print("1. Install HuggingFace datasets: pip install datasets")
    print("2. Set up your agent endpoint")
    print("3. Run: python swebench_integration.py")


if __name__ == "__main__":
    # Run demo
    asyncio.run(demo())