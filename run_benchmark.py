#!/usr/bin/env python
"""
Run A2A SWE-bench benchmark against multiple instances.
Compares results and generates a summary report.
"""

import httpx
import time
import json
from datetime import datetime
from typing import Dict, List, Any
import sys


# Test instances to run
TEST_INSTANCES = [
    "django__django-11099",  # UsernameValidator trailing newline
    "django__django-11133",  # HttpResponse charset handling
    "django__django-11179",  # model_to_dict for unsaved model
]


def submit_task(instance_id: str, timeout: int = 600) -> Dict[str, Any]:
    """Submit a task to the Green agent and wait for completion."""
    payload = {
        "title": f"swebench-{instance_id}",
        "description": f"Resolve SWE-bench issue {instance_id}",
        "resources": {"scenario_id": instance_id},
        "constraints": {"time_limit": timeout}
    }
    
    print(f"\n{'='*60}")
    print(f"Submitting task: {instance_id}")
    print(f"{'='*60}")
    
    try:
        # Create task
        r = httpx.post("http://localhost:8002/a2a/task", json=payload, timeout=30)
        if r.status_code != 200:
            return {"instance_id": instance_id, "error": f"Failed to create task: {r.text}"}
        
        data = r.json()
        task_id = data.get("task_id")
        print(f"Task created: {task_id}")
        
        # Poll for completion
        start_time = time.time()
        while time.time() - start_time < timeout:
            resp = httpx.get(f"http://localhost:8002/a2a/task/{task_id}", timeout=300)
            if resp.status_code != 200:
                print(f"  Warning: Status check failed: {resp.status_code}")
                time.sleep(5)
                continue
            
            status_data = resp.json()
            status = status_data.get("status")
            elapsed = int(time.time() - start_time)
            print(f"  [{elapsed}s] Status: {status}")
            
            if status in ("completed", "failed"):
                return {
                    "instance_id": instance_id,
                    "task_id": task_id,
                    "status": status,
                    "elapsed_time": elapsed,
                    "data": status_data
                }
            
            time.sleep(5)
        
        return {
            "instance_id": instance_id,
            "task_id": task_id,
            "status": "timeout",
            "elapsed_time": timeout,
            "error": "Timeout waiting for completion"
        }
        
    except Exception as e:
        return {"instance_id": instance_id, "error": str(e)}


def extract_result_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key metrics from a task result."""
    summary = {
        "instance_id": result.get("instance_id"),
        "status": result.get("status", "error"),
        "elapsed_time": result.get("elapsed_time", 0),
    }
    
    if "error" in result:
        summary["error"] = result["error"]
        return summary
    
    # Extract verification result from artifacts
    data = result.get("data", {})
    artifacts = data.get("artifacts", [])
    
    for artifact in artifacts:
        parts = artifact.get("parts", [])
        for part in parts:
            if part.get("type") == "json":
                content = part.get("content", "")
                # Parse the Python dict string (it's not JSON but repr)
                try:
                    # Extract verification_result from the content string
                    if "verification_result" in content:
                        # Find passed status
                        if "'passed': True" in content:
                            summary["passed"] = True
                        elif "'passed': False" in content:
                            summary["passed"] = False
                        
                        # Find patch_applied status
                        if "'patch_applied': True" in content:
                            summary["patch_applied"] = True
                        elif "'patch_applied': False" in content:
                            summary["patch_applied"] = False
                        
                        # Find tests counts
                        import re
                        tests_passed = re.search(r"'tests_passed': (\d+)", content)
                        tests_failed = re.search(r"'tests_failed': (\d+)", content)
                        if tests_passed:
                            summary["tests_passed"] = int(tests_passed.group(1))
                        if tests_failed:
                            summary["tests_failed"] = int(tests_failed.group(1))
                except Exception as e:
                    summary["parse_error"] = str(e)
    
    return summary


def print_summary(results: List[Dict[str, Any]]):
    """Print a summary of all results."""
    print("\n" + "="*80)
    print("A2A SWE-BENCH BENCHMARK RESULTS")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Total instances: {len(results)}")
    
    passed = sum(1 for r in results if r.get("passed") == True)
    failed = sum(1 for r in results if r.get("status") == "failed" or r.get("passed") == False)
    errors = sum(1 for r in results if "error" in r)
    
    print(f"\nOverall Results:")
    print(f"  ✅ Passed: {passed}/{len(results)}")
    print(f"  ❌ Failed: {failed}/{len(results)}")
    print(f"  ⚠️  Errors: {errors}/{len(results)}")
    
    print(f"\nDetailed Results:")
    print("-"*80)
    for r in results:
        status_icon = "✅" if r.get("passed") else "❌" if r.get("status") == "failed" else "⚠️"
        patch_icon = "✓" if r.get("patch_applied") else "✗"
        
        print(f"\n{status_icon} {r['instance_id']}")
        print(f"   Status: {r.get('status', 'unknown')}")
        print(f"   Patch Applied: {patch_icon}")
        print(f"   Tests Passed: {r.get('tests_passed', 'N/A')}")
        print(f"   Tests Failed: {r.get('tests_failed', 'N/A')}")
        print(f"   Time: {r.get('elapsed_time', 'N/A')}s")
        if "error" in r:
            print(f"   Error: {r['error'][:100]}")
    
    print("\n" + "="*80)
    
    # Calculate pass rate
    total_valid = len(results) - errors
    if total_valid > 0:
        pass_rate = (passed / total_valid) * 100
        print(f"Pass Rate: {pass_rate:.1f}% ({passed}/{total_valid})")
    
    print("="*80)


def main():
    print("Starting A2A SWE-bench Benchmark")
    print(f"Testing {len(TEST_INSTANCES)} instances\n")
    
    # Check if agents are running
    try:
        purple_health = httpx.get("http://localhost:8001/health", timeout=5).json()
        green_health = httpx.get("http://localhost:8002/health", timeout=5).json()
        print(f"Purple Agent: {purple_health['agent']} ({purple_health['status']})")
        print(f"Green Agent: {green_health['agent']} ({green_health['status']})")
    except Exception as e:
        print(f"Error: Could not connect to agents: {e}")
        print("Make sure Purple (port 8001) and Green (port 8002) agents are running.")
        sys.exit(1)
    
    results = []
    for instance_id in TEST_INSTANCES:
        result = submit_task(instance_id, timeout=600)
        summary = extract_result_summary(result)
        results.append(summary)
        print(f"\nResult for {instance_id}: {'PASSED' if summary.get('passed') else 'FAILED'}")
    
    print_summary(results)
    
    # Save results to file
    output_file = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
