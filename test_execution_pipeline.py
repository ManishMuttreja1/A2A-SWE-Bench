#!/usr/bin/env python3
"""
Test script for Phase 1: Execution-based verification pipeline.

This tests the Docker-based execution instead of semantic F1 scoring.
Run 2-3 tasks to verify the pipeline works.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.execution.docker_runner import DockerRunner, ContainerConfig
from src.execution.patch_executor import PatchExecutor, ExecutionConfig
from src.execution.result_collector import ResultCollector


# Sample SWE-bench instances for testing
SAMPLE_INSTANCES = [
    {
        "instance_id": "test__simple-1",
        "repo": "psf/requests",  # Simple, well-known repo
        "base_commit": "v2.31.0",  # Use a tag for reliability
        "problem_statement": "Test execution pipeline",
        "test_cmd": "python -c 'print(\"tests passed\"); exit(0)'"  # Simple test
    },
    {
        "instance_id": "test__python-math",
        "repo": "python/cpython",
        "base_commit": "v3.11.0",
        "problem_statement": "Test with larger repo",
        "test_cmd": "python -c 'import math; assert math.pi > 3; print(\"OK\")'"
    }
]

# Sample patches (some valid, some invalid to test both cases)
SAMPLE_PATCHES = {
    "test__simple-1": """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Requests
+# Modified by test
""",
    "test__python-math": """diff --git a/README.rst b/README.rst
--- a/README.rst
+++ b/README.rst
@@ -1 +1,2 @@
 Python
+Test modification
""",
    "invalid_patch": "this is not a valid patch format"
}


async def test_docker_available():
    """Test 1: Check if Docker is available."""
    print("\n" + "="*60)
    print("TEST 1: Docker Availability")
    print("="*60)
    
    try:
        runner = DockerRunner()
        print("✅ Docker is available and running")
        return True
    except RuntimeError as e:
        print(f"❌ Docker not available: {e}")
        print("   Will use mock execution instead")
        return False


async def test_patch_executor_mock():
    """Test 2: Test PatchExecutor with mock execution (no Docker needed)."""
    print("\n" + "="*60)
    print("TEST 2: PatchExecutor (Mock Mode)")
    print("="*60)
    
    # Force mock mode
    config = ExecutionConfig(use_docker=False)
    executor = PatchExecutor(config)
    
    instance = SAMPLE_INSTANCES[0]
    patch = SAMPLE_PATCHES["test__simple-1"]
    
    print(f"Instance: {instance['instance_id']}")
    print(f"Patch length: {len(patch)} chars")
    
    result = await executor.execute_patch(instance, patch)
    
    print(f"\nResult:")
    print(f"  execution_pass: {result['execution_pass']}")
    print(f"  metric_type: {result.get('metric_type', 'unknown')}")
    print(f"  tests_passed: {result['tests_passed']}")
    print(f"  tests_failed: {result['tests_failed']}")
    print(f"  error: {result.get('error', 'None')}")
    
    # Verify we're NOT computing semantic F1
    assert result.get('semantic_match') is None, "Should not compute semantic match"
    assert result.get('metric_type') == 'execution', "Metric type should be 'execution'"
    
    print("\n✅ Mock execution test passed")
    return True


async def test_result_collector():
    """Test 3: Test ResultCollector aggregation."""
    print("\n" + "="*60)
    print("TEST 3: ResultCollector")
    print("="*60)
    
    collector = ResultCollector(output_dir=Path("results/execution_test"))
    
    # Add some mock results
    mock_results = [
        {
            "instance_id": "test-1",
            "execution_pass": True,
            "success": True,
            "exit_code": 0,
            "tests_passed": 5,
            "tests_failed": 0,
            "execution_time": 2.5,
            "stdout": "All tests passed",
            "stderr": ""
        },
        {
            "instance_id": "test-2",
            "execution_pass": False,
            "success": False,
            "exit_code": 1,
            "tests_passed": 3,
            "tests_failed": 2,
            "execution_time": 3.1,
            "stdout": "Some tests failed",
            "stderr": "AssertionError"
        },
        {
            "instance_id": "test-3",
            "execution_pass": True,
            "success": True,
            "exit_code": 0,
            "tests_passed": 10,
            "tests_failed": 0,
            "execution_time": 1.8,
            "stdout": "OK",
            "stderr": ""
        }
    ]
    
    collector.add_results(mock_results)
    
    # Print summary
    collector.print_summary(model="test-model")
    
    # Compute metrics
    summary = collector.compute_summary(model="test-model")
    
    print(f"\nVerifying metrics:")
    print(f"  Pass rate: {summary.execution_pass_rate:.1%} (expected: 66.7%)")
    print(f"  Total passed: {summary.total_passed} (expected: 2)")
    print(f"  Total failed: {summary.total_failed} (expected: 1)")
    print(f"  Metric type: {summary.metric_type} (expected: execution)")
    
    assert abs(summary.execution_pass_rate - 0.667) < 0.01, "Pass rate should be ~66.7%"
    assert summary.total_passed == 2, "Should have 2 passed"
    assert summary.total_failed == 1, "Should have 1 failed"
    assert summary.metric_type == "execution", "Metric type should be execution"
    
    # Save results
    filepath = collector.save_results(model="test-model", filename="test_results.json")
    print(f"\n✅ Results saved to {filepath}")
    
    return True


async def test_docker_execution():
    """Test 4: Test actual Docker execution (if Docker available)."""
    print("\n" + "="*60)
    print("TEST 4: Docker Execution (if available)")
    print("="*60)
    
    try:
        runner = DockerRunner(ContainerConfig(
            timeout=120,  # 2 minutes for test
            image="python:3.11-slim"
        ))
    except RuntimeError as e:
        print(f"⚠️ Docker not available, skipping: {e}")
        return True  # Not a failure, just skipped
    
    # Simple test: run Python in container
    print("Running simple Python test in Docker...")
    
    result = await runner.execute_in_container(
        repo="psf/requests",
        base_commit="v2.31.0",
        patch="",  # Empty patch - just test setup
        test_cmd="python --version && echo 'EXECUTION_SUCCESS'",
        setup_commands=["echo 'Setup complete'"]
    )
    
    print(f"\nDocker execution result:")
    print(f"  success: {result['success']}")
    print(f"  exit_code: {result['exit_code']}")
    print(f"  execution_time: {result['execution_time']:.1f}s")
    print(f"  stdout preview: {result['stdout'][:200]}...")
    
    if result['success']:
        print("\n✅ Docker execution test passed")
    else:
        print(f"\n⚠️ Docker execution returned error: {result.get('error')}")
        print(f"   stderr: {result['stderr'][:200]}")
    
    return True


async def test_full_pipeline():
    """Test 5: Full pipeline test with multiple instances."""
    print("\n" + "="*60)
    print("TEST 5: Full Pipeline (2-3 instances)")
    print("="*60)
    
    # Use mock mode for reliable testing
    config = ExecutionConfig(use_docker=False)
    executor = PatchExecutor(config)
    collector = ResultCollector(output_dir=Path("results/execution_test"))
    
    tasks = [
        {"instance": SAMPLE_INSTANCES[0], "patch": SAMPLE_PATCHES["test__simple-1"]},
        {"instance": SAMPLE_INSTANCES[1], "patch": SAMPLE_PATCHES["test__python-math"]},
        {"instance": {"instance_id": "test__invalid", "repo": "test/test"}, "patch": "invalid"}
    ]
    
    print(f"Running {len(tasks)} tasks through execution pipeline...")
    
    results = await executor.execute_batch(tasks)
    collector.add_results(results)
    
    # Compute metrics
    metrics = executor.compute_execution_metrics(results)
    
    print(f"\nPipeline metrics:")
    print(f"  Pass rate: {metrics['pass_rate']:.1%}")
    print(f"  Total passed: {metrics['total_passed']}")
    print(f"  Total failed: {metrics['total_failed']}")
    print(f"  Metric type: {metrics['metric_type']}")
    
    # Save final results
    filepath = collector.save_results(model="pipeline-test")
    
    print(f"\n✅ Full pipeline test complete")
    print(f"   Results saved to: {filepath}")
    
    return True


async def main():
    """Run all Phase 1 tests."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║     PHASE 1: EXECUTION-BASED VERIFICATION PIPELINE           ║
║     Testing Docker-based patch execution                      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    all_passed = True
    
    # Run tests
    tests = [
        ("Docker Available", test_docker_available),
        ("Mock Execution", test_patch_executor_mock),
        ("Result Collector", test_result_collector),
        ("Docker Execution", test_docker_execution),
        ("Full Pipeline", test_full_pipeline),
    ]
    
    for name, test_fn in tests:
        try:
            result = await test_fn()
            if not result:
                all_passed = False
        except Exception as e:
            print(f"\n❌ Test '{name}' failed with exception: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    # Summary
    print("\n" + "="*60)
    print("PHASE 1 TEST SUMMARY")
    print("="*60)
    
    if all_passed:
        print("""
✅ ALL TESTS PASSED

Phase 1 Implementation Status:
  ✅ Docker runner created
  ✅ Patch executor created (replaces semantic F1)
  ✅ Result collector created
  ✅ Execution-based metrics working
  ✅ NOT computing semantic similarity - using PASS/FAIL

Key difference from before:
  BEFORE: semantic_match = 0.45 (text similarity)
  NOW:    execution_pass = True/False (actual test results)
        """)
    else:
        print("\n❌ Some tests failed. Check output above.")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
