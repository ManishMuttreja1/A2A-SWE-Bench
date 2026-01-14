#!/usr/bin/env python3
"""
Enhanced SWE-bench test runner with A2A verification.
Runs multiple test instances and verifies solutions through the A2A system.
"""

import json
import time
import httpx
import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess
import sys

# Configuration
A2A_GREEN_URL = "http://localhost:8002"
A2A_PURPLE_URL = "http://localhost:8001"
SWEBENCH_DATA_FILE = "data/swebench_cache/swebench_verified.json"
RESULTS_DIR = Path("test_results")
RESULTS_DIR.mkdir(exist_ok=True)

class SWEBenchRunner:
    def __init__(self):
        self.instances = []
        self.results = []
        self.load_instances()
        
    def load_instances(self):
        """Load SWE-bench instances from the JSON file."""
        with open(SWEBENCH_DATA_FILE, 'r') as f:
            self.instances = json.load(f)
        print(f"Loaded {len(self.instances)} SWE-bench instances")
    
    def select_test_batch(self, count: int = 10, criteria: Optional[Dict] = None) -> List[Dict]:
        """Select a batch of test instances based on criteria."""
        available = self.instances.copy()
        
        if criteria:
            # Filter by repo if specified
            if 'repo' in criteria:
                available = [i for i in available if criteria['repo'] in i['repo']]
            
            # Filter by difficulty (based on patch size)
            if 'difficulty' in criteria:
                if criteria['difficulty'] == 'easy':
                    available = [i for i in available if len(i.get('patch', '')) < 500]
                elif criteria['difficulty'] == 'medium':
                    available = [i for i in available if 500 <= len(i.get('patch', '')) < 2000]
                elif criteria['difficulty'] == 'hard':
                    available = [i for i in available if len(i.get('patch', '')) >= 2000]
        
        # Random selection from available instances
        selected = random.sample(available, min(count, len(available)))
        return selected
    
    async def run_a2a_verification(self, instance: Dict) -> Dict[str, Any]:
        """Run a single instance through A2A verification."""
        instance_id = instance['instance_id']
        print(f"\n{'='*60}")
        print(f"Testing: {instance_id}")
        print(f"Repo: {instance['repo']}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        # Prepare the task payload
        payload = {
            "title": f"swebench-{instance_id}",
            "description": instance['problem_statement'][:500],  # Truncate if too long
            "resources": {
                "scenario_id": instance_id,
                "repo": instance['repo'],
                "base_commit": instance['base_commit'],
                "test_patch": instance.get('test_patch', ''),
                "hints": instance.get('hints_text', '')
            },
            "constraints": {
                "time_limit": 600,
                "max_attempts": 3
            }
        }
        
        try:
            # Submit task to Green Agent
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{A2A_GREEN_URL}/a2a/task", json=payload)
                
                if response.status_code != 200:
                    return {
                        "instance_id": instance_id,
                        "status": "error",
                        "error": f"Failed to create task: {response.text}"
                    }
                
                task_data = response.json()
                task_id = task_data.get("task_id")
                print(f"Task ID: {task_id}")
                
                # Poll for completion
                max_wait = 600  # 10 minutes
                poll_interval = 5
                elapsed = 0
                
                while elapsed < max_wait:
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                    
                    status_response = await client.get(f"{A2A_GREEN_URL}/a2a/task/{task_id}")
                    if status_response.status_code != 200:
                        continue
                    
                    status_data = status_response.json()
                    status = status_data.get("status")
                    
                    print(f"  [{elapsed}s] Status: {status}")
                    
                    if status in ("completed", "failed"):
                        # Extract verification results
                        verification_result = self.extract_verification_result(status_data)
                        
                        return {
                            "instance_id": instance_id,
                            "status": status,
                            "task_id": task_id,
                            "elapsed_time": elapsed,
                            "verification": verification_result,
                            "raw_response": status_data
                        }
                
                return {
                    "instance_id": instance_id,
                    "status": "timeout",
                    "elapsed_time": max_wait,
                    "error": "Task exceeded time limit"
                }
                
        except Exception as e:
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": str(e),
                "elapsed_time": time.time() - start_time
            }
    
    def extract_verification_result(self, status_data: Dict) -> Dict:
        """Extract structured verification results from the response."""
        result = {
            "passed": False,
            "patch_applied": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "error_message": None
        }
        
        # Look for verification data in artifacts
        artifacts = status_data.get("artifacts", [])
        for artifact in artifacts:
            for part in artifact.get("parts", []):
                content = part.get("content", "")
                
                # Parse verification results
                if "verification_result" in content or "tests_passed" in content:
                    if "'passed': True" in content or '"passed": true' in content:
                        result["passed"] = True
                    if "'patch_applied': True" in content or '"patch_applied": true' in content:
                        result["patch_applied"] = True
                    
                    # Extract test counts
                    import re
                    tests_passed = re.search(r"['\"]tests_passed['\"]: (\d+)", content)
                    tests_failed = re.search(r"['\"]tests_failed['\"]: (\d+)", content)
                    
                    if tests_passed:
                        result["tests_passed"] = int(tests_passed.group(1))
                    if tests_failed:
                        result["tests_failed"] = int(tests_failed.group(1))
        
        return result
    
    async def run_batch(self, instances: List[Dict]) -> List[Dict]:
        """Run a batch of instances concurrently."""
        tasks = [self.run_a2a_verification(instance) for instance in instances]
        results = await asyncio.gather(*tasks)
        return results
    
    def generate_report(self, results: List[Dict]) -> Dict:
        """Generate a comprehensive report of test results."""
        total = len(results)
        passed = sum(1 for r in results if r.get("verification", {}).get("passed"))
        failed = sum(1 for r in results if r.get("status") == "failed")
        errors = sum(1 for r in results if r.get("status") == "error")
        timeouts = sum(1 for r in results if r.get("status") == "timeout")
        
        avg_time = sum(r.get("elapsed_time", 0) for r in results) / max(total, 1)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_instances": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "timeouts": timeouts,
                "pass_rate": (passed / total * 100) if total > 0 else 0,
                "average_time": avg_time
            },
            "detailed_results": results,
            "by_repo": self.group_by_repo(results)
        }
        
        return report
    
    def group_by_repo(self, results: List[Dict]) -> Dict:
        """Group results by repository."""
        by_repo = {}
        for r in results:
            # Find the original instance to get repo info
            instance_id = r.get("instance_id")
            instance = next((i for i in self.instances if i["instance_id"] == instance_id), None)
            if instance:
                repo = instance["repo"]
                if repo not in by_repo:
                    by_repo[repo] = {"passed": 0, "failed": 0, "total": 0}
                
                by_repo[repo]["total"] += 1
                if r.get("verification", {}).get("passed"):
                    by_repo[repo]["passed"] += 1
                else:
                    by_repo[repo]["failed"] += 1
        
        return by_repo
    
    def print_report(self, report: Dict):
        """Print a formatted report to console."""
        print("\n" + "="*80)
        print("A2A SWE-BENCH TEST REPORT")
        print("="*80)
        
        summary = report["summary"]
        print(f"Timestamp: {report['timestamp']}")
        print(f"Total Instances: {summary['total_instances']}")
        print(f"\nResults:")
        print(f"  ✅ Passed: {summary['passed']} ({summary['pass_rate']:.1f}%)")
        print(f"  ❌ Failed: {summary['failed']}")
        print(f"  ⚠️  Errors: {summary['errors']}")
        print(f"  ⏱️  Timeouts: {summary['timeouts']}")
        print(f"\nAverage Time: {summary['average_time']:.1f}s")
        
        print("\nResults by Repository:")
        for repo, stats in report["by_repo"].items():
            pass_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {repo}: {stats['passed']}/{stats['total']} ({pass_rate:.1f}%)")
        
        print("\nDetailed Results:")
        print("-"*80)
        for r in report["detailed_results"]:
            v = r.get("verification", {})
            status_icon = "✅" if v.get("passed") else "❌"
            print(f"{status_icon} {r['instance_id']}")
            print(f"   Status: {r.get('status')}")
            print(f"   Patch Applied: {'Yes' if v.get('patch_applied') else 'No'}")
            print(f"   Tests: {v.get('tests_passed', 0)} passed, {v.get('tests_failed', 0)} failed")
            print(f"   Time: {r.get('elapsed_time', 0):.1f}s")
            if r.get("error"):
                print(f"   Error: {r['error'][:100]}")
        
        print("="*80)

async def main():
    """Main execution function."""
    runner = SWEBenchRunner()
    
    print("A2A SWE-Bench Test Runner")
    print("="*40)
    
    # Check if agents are running
    try:
        async with httpx.AsyncClient() as client:
            purple = await client.get(f"{A2A_PURPLE_URL}/health")
            green = await client.get(f"{A2A_GREEN_URL}/health")
            print(f"Purple Agent: {purple.json()['status']}")
            print(f"Green Agent: {green.json()['status']}")
    except Exception as e:
        print(f"Error: Agents not accessible - {e}")
        print("Please start the Purple and Green agents first.")
        sys.exit(1)
    
    # Select test batch
    print("\nSelecting test instances...")
    
    # Start with easy Django instances
    test_batch = runner.select_test_batch(
        count=10,
        criteria={"repo": "django", "difficulty": "easy"}
    )
    
    print(f"Selected {len(test_batch)} instances for testing")
    
    # Run tests
    print("\nStarting test execution...")
    results = await runner.run_batch(test_batch)
    
    # Generate and save report
    report = runner.generate_report(results)
    runner.print_report(report)
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = RESULTS_DIR / f"swebench_report_{timestamp}.json"
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\nDetailed report saved to: {report_file}")
    
    # Check if we should scale up
    if report["summary"]["pass_rate"] > 50:
        print("\n✅ Initial batch successful! Ready to scale up to more instances.")
    else:
        print("\n⚠️  Pass rate below 50%. Review and fix issues before scaling up.")

if __name__ == "__main__":
    asyncio.run(main())