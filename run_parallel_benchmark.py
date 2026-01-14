#!/usr/bin/env python3
"""
Enhanced Parallel SWE-bench Test Runner with Checkpoint/Resume
"""

import asyncio
import json
import time
import httpx
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import logging
import sys
import os
from concurrent.futures import ThreadPoolExecutor
import pickle
from tqdm.asyncio import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
A2A_GREEN_URL = os.getenv("GREEN_AGENT_URL", "http://localhost:8002")
A2A_PURPLE_URL = os.getenv("PURPLE_AGENT_URL", "http://localhost:8001")
SWEBENCH_DATA_FILE = "data/swebench_cache/swebench_verified.json"
RESULTS_DIR = Path("test_results")
CHECKPOINT_DIR = Path("checkpoints")
RESULTS_DIR.mkdir(exist_ok=True)
CHECKPOINT_DIR.mkdir(exist_ok=True)

# Test categorization
DIFFICULTY_LEVELS = {
    "easy": lambda i: len(i.get("patch", "")) < 500,
    "medium": lambda i: 500 <= len(i.get("patch", "")) < 2000,
    "hard": lambda i: len(i.get("patch", "")) >= 2000
}

REPO_CATEGORIES = {
    "django": "django/django",
    "flask": "pallets/flask",
    "requests": "psf/requests",
    "scikit-learn": "scikit-learn/scikit-learn",
    "matplotlib": "matplotlib/matplotlib",
    "sympy": "sympy/sympy",
    "sphinx": "sphinx-doc/sphinx"
}


class ParallelBenchmarkRunner:
    def __init__(
        self,
        max_workers: int = 5,
        checkpoint_interval: int = 10,
        timeout_per_task: int = 600
    ):
        self.max_workers = max_workers
        self.checkpoint_interval = checkpoint_interval
        self.timeout_per_task = timeout_per_task
        self.instances = []
        self.results = []
        self.completed_ids: Set[str] = set()
        self.failed_ids: Set[str] = set()
        self.checkpoint_file = CHECKPOINT_DIR / f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
        self.load_instances()
        
    def load_instances(self):
        """Load SWE-bench instances"""
        with open(SWEBENCH_DATA_FILE, 'r') as f:
            self.instances = json.load(f)
        logger.info(f"Loaded {len(self.instances)} SWE-bench instances")
    
    def categorize_instances(self) -> Dict[str, List[Dict]]:
        """Categorize instances by repo and difficulty"""
        categories = {
            "by_repo": {},
            "by_difficulty": {"easy": [], "medium": [], "hard": []},
            "by_combined": {}
        }
        
        for instance in self.instances:
            repo = instance.get("repo", "unknown")
            
            # By repository
            if repo not in categories["by_repo"]:
                categories["by_repo"][repo] = []
            categories["by_repo"][repo].append(instance)
            
            # By difficulty
            for level, check_func in DIFFICULTY_LEVELS.items():
                if check_func(instance):
                    categories["by_difficulty"][level].append(instance)
                    break
            
            # Combined categorization
            for level in ["easy", "medium", "hard"]:
                if DIFFICULTY_LEVELS[level](instance):
                    key = f"{repo}_{level}"
                    if key not in categories["by_combined"]:
                        categories["by_combined"][key] = []
                    categories["by_combined"][key].append(instance)
                    break
        
        return categories
    
    def select_test_batch(
        self,
        count: int = 50,
        strategy: str = "balanced",
        exclude_completed: bool = True
    ) -> List[Dict]:
        """
        Select test batch with different strategies.
        
        Strategies:
        - balanced: Mix of difficulties and repos
        - easy_first: Start with easy instances
        - by_repo: Focus on specific repos
        - random: Random selection
        """
        available = [
            i for i in self.instances 
            if not exclude_completed or i["instance_id"] not in self.completed_ids
        ]
        
        if strategy == "balanced":
            categories = self.categorize_instances()
            selected = []
            
            # Get balanced mix
            for level in ["easy", "medium", "hard"]:
                level_instances = [
                    i for i in categories["by_difficulty"][level]
                    if i["instance_id"] not in self.completed_ids
                ]
                level_count = count // 3
                selected.extend(random.sample(
                    level_instances,
                    min(level_count, len(level_instances))
                ))
            
            # Fill remaining with random
            remaining = count - len(selected)
            if remaining > 0:
                unused = [
                    i for i in available 
                    if i["instance_id"] not in {s["instance_id"] for s in selected}
                ]
                selected.extend(random.sample(
                    unused,
                    min(remaining, len(unused))
                ))
            
            return selected[:count]
            
        elif strategy == "easy_first":
            sorted_instances = sorted(
                available,
                key=lambda i: len(i.get("patch", ""))
            )
            return sorted_instances[:count]
            
        elif strategy == "by_repo":
            # Focus on Django first, then others
            django_instances = [
                i for i in available 
                if "django" in i.get("repo", "").lower()
            ]
            other_instances = [
                i for i in available 
                if "django" not in i.get("repo", "").lower()
            ]
            
            selected = django_instances[:count//2]
            selected.extend(other_instances[:count - len(selected)])
            return selected
            
        else:  # random
            return random.sample(available, min(count, len(available)))
    
    async def run_single_test(
        self,
        instance: Dict,
        semaphore: asyncio.Semaphore
    ) -> Dict[str, Any]:
        """Run a single test with semaphore control"""
        async with semaphore:
            instance_id = instance["instance_id"]
            
            # Skip if already completed
            if instance_id in self.completed_ids:
                return {
                    "instance_id": instance_id,
                    "status": "skipped",
                    "reason": "already_completed"
                }
            
            logger.info(f"Starting test: {instance_id}")
            
            # Prepare task payload
            payload = {
                "title": f"swebench-{instance_id}",
                "description": instance["problem_statement"][:1000],
                "resources": {
                    "scenario_id": instance_id,
                    "repo": instance["repo"],
                    "base_commit": instance["base_commit"],
                    "test_patch": instance.get("test_patch", ""),
                    "hints": instance.get("hints_text", "")
                },
                "constraints": {
                    "time_limit": self.timeout_per_task,
                    "max_attempts": 2
                }
            }
            
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Submit task
                    response = await client.post(
                        f"{A2A_GREEN_URL}/a2a/task",
                        json=payload
                    )
                    
                    if response.status_code != 200:
                        return {
                            "instance_id": instance_id,
                            "status": "error",
                            "error": f"Failed to create task: {response.status_code}"
                        }
                    
                    task_data = response.json()
                    task_id = task_data.get("task_id")
                    
                    # Poll for completion with timeout
                    start_time = time.time()
                    while time.time() - start_time < self.timeout_per_task:
                        await asyncio.sleep(5)
                        
                        status_response = await client.get(
                            f"{A2A_GREEN_URL}/a2a/task/{task_id}"
                        )
                        
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            status = status_data.get("status")
                            
                            if status in ("completed", "failed"):
                                elapsed = time.time() - start_time
                                
                                # Mark as completed
                                self.completed_ids.add(instance_id)
                                
                                return {
                                    "instance_id": instance_id,
                                    "status": status,
                                    "task_id": task_id,
                                    "elapsed_time": elapsed,
                                    "data": status_data
                                }
                    
                    # Timeout
                    self.failed_ids.add(instance_id)
                    return {
                        "instance_id": instance_id,
                        "status": "timeout",
                        "elapsed_time": self.timeout_per_task
                    }
                    
            except Exception as e:
                logger.error(f"Error testing {instance_id}: {e}")
                self.failed_ids.add(instance_id)
                return {
                    "instance_id": instance_id,
                    "status": "error",
                    "error": str(e)
                }
    
    async def run_batch_parallel(
        self,
        instances: List[Dict],
        max_concurrent: int = 5
    ) -> List[Dict]:
        """Run batch of tests in parallel"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # Create tasks
        tasks = [
            self.run_single_test(instance, semaphore)
            for instance in instances
        ]
        
        # Run with progress bar
        results = []
        with tqdm(total=len(tasks), desc="Running tests") as pbar:
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                pbar.update(1)
                
                # Checkpoint periodically
                if len(results) % self.checkpoint_interval == 0:
                    await self.save_checkpoint(results)
        
        return results
    
    async def save_checkpoint(self, partial_results: List[Dict]):
        """Save checkpoint for resume capability"""
        checkpoint_data = {
            "completed_ids": list(self.completed_ids),
            "failed_ids": list(self.failed_ids),
            "results": partial_results,
            "timestamp": datetime.now().isoformat()
        }
        
        with open(self.checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)
        
        logger.info(f"Checkpoint saved: {len(self.completed_ids)} completed")
    
    def load_checkpoint(self, checkpoint_file: Path) -> bool:
        """Load checkpoint if exists"""
        if not checkpoint_file.exists():
            return False
        
        try:
            with open(checkpoint_file, 'rb') as f:
                data = pickle.load(f)
            
            self.completed_ids = set(data["completed_ids"])
            self.failed_ids = set(data["failed_ids"])
            self.results = data["results"]
            
            logger.info(f"Checkpoint loaded: {len(self.completed_ids)} completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False
    
    def generate_report(self, results: List[Dict]) -> Dict:
        """Generate comprehensive benchmark report"""
        total = len(results)
        passed = sum(1 for r in results if self._is_passed(r))
        failed = sum(1 for r in results if r.get("status") == "failed")
        errors = sum(1 for r in results if r.get("status") == "error")
        timeouts = sum(1 for r in results if r.get("status") == "timeout")
        skipped = sum(1 for r in results if r.get("status") == "skipped")
        
        times = [r.get("elapsed_time", 0) for r in results if r.get("elapsed_time")]
        avg_time = sum(times) / len(times) if times else 0
        
        # Group by repository
        by_repo = {}
        for r in results:
            instance_id = r.get("instance_id")
            instance = next((i for i in self.instances if i["instance_id"] == instance_id), None)
            if instance:
                repo = instance["repo"]
                if repo not in by_repo:
                    by_repo[repo] = {"passed": 0, "failed": 0, "total": 0}
                
                by_repo[repo]["total"] += 1
                if self._is_passed(r):
                    by_repo[repo]["passed"] += 1
                else:
                    by_repo[repo]["failed"] += 1
        
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_instances": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "timeouts": timeouts,
                "skipped": skipped,
                "pass_rate": (passed / (total - skipped) * 100) if (total - skipped) > 0 else 0,
                "average_time": avg_time,
                "min_time": min(times) if times else 0,
                "max_time": max(times) if times else 0
            },
            "by_repository": by_repo,
            "detailed_results": results
        }
    
    def _is_passed(self, result: Dict) -> bool:
        """Check if test passed"""
        if result.get("status") != "completed":
            return False
        
        # Check verification results in data
        data = result.get("data", {})
        artifacts = data.get("artifacts", [])
        
        for artifact in artifacts:
            for part in artifact.get("parts", []):
                content = str(part.get("content", ""))
                if "passed': True" in content or '"passed": true' in content:
                    return True
        
        return False


async def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description="Run SWE-bench tests in parallel")
    parser.add_argument("--count", type=int, default=50, help="Number of tests to run")
    parser.add_argument("--workers", type=int, default=5, help="Max parallel workers")
    parser.add_argument("--strategy", default="balanced", help="Test selection strategy")
    parser.add_argument("--resume", help="Resume from checkpoint file")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per task")
    
    args = parser.parse_args()
    
    runner = ParallelBenchmarkRunner(
        max_workers=args.workers,
        timeout_per_task=args.timeout
    )
    
    # Load checkpoint if resuming
    if args.resume:
        checkpoint_file = Path(args.resume)
        if runner.load_checkpoint(checkpoint_file):
            print(f"Resumed from checkpoint: {len(runner.completed_ids)} already completed")
    
    # Check agents are running
    try:
        async with httpx.AsyncClient() as client:
            purple = await client.get(f"{A2A_PURPLE_URL}/health")
            green = await client.get(f"{A2A_GREEN_URL}/health")
            print(f"Purple Agent: {purple.json()['status']}")
            print(f"Green Agent: {green.json()['status']}")
    except Exception as e:
        print(f"Error: Agents not accessible - {e}")
        sys.exit(1)
    
    # Select test batch
    print(f"\nSelecting {args.count} tests with '{args.strategy}' strategy...")
    test_batch = runner.select_test_batch(
        count=args.count,
        strategy=args.strategy
    )
    
    print(f"Selected {len(test_batch)} instances")
    print(f"Already completed: {len(runner.completed_ids)}")
    print(f"To run: {len([i for i in test_batch if i['instance_id'] not in runner.completed_ids])}")
    
    # Run tests
    print(f"\nRunning tests with {args.workers} parallel workers...")
    results = await runner.run_batch_parallel(test_batch, args.workers)
    
    # Combine with previous results if resuming
    all_results = runner.results + results
    
    # Generate report
    report = runner.generate_report(all_results)
    
    # Print summary
    print("\n" + "="*80)
    print("PARALLEL BENCHMARK RESULTS")
    print("="*80)
    print(f"Total: {report['summary']['total_instances']}")
    print(f"Passed: {report['summary']['passed']} ({report['summary']['pass_rate']:.1f}%)")
    print(f"Failed: {report['summary']['failed']}")
    print(f"Errors: {report['summary']['errors']}")
    print(f"Timeouts: {report['summary']['timeouts']}")
    print(f"Average Time: {report['summary']['average_time']:.1f}s")
    
    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = RESULTS_DIR / f"parallel_report_{timestamp}.json"
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\nReport saved to: {report_file}")
    
    # Save final checkpoint
    await runner.save_checkpoint(all_results)
    print(f"Final checkpoint: {runner.checkpoint_file}")


if __name__ == "__main__":
    import argparse
    
    # Check for tqdm
    try:
        from tqdm.asyncio import tqdm
    except ImportError:
        print("Installing tqdm...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
        from tqdm.asyncio import tqdm
    
    asyncio.run(main())