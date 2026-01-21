#!/usr/bin/env python3
"""
Test script for Phase 2: Enforced Reproduction Gate.

This tests that:
1. Agents cannot submit patches without reproduction
2. Score = 0 if reproduction is skipped
3. Proper workflow: reproduce -> patch -> execute
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.execution.enforced_workflow import (
    EnforcedWorkflow, 
    EnforcedWorkflowResult,
    WorkflowPhase,
    generate_reproduction_script
)


# Sample instances
SAMPLE_INSTANCES = [
    {
        "instance_id": "django__django-11099",
        "repo": "django/django",
        "problem_statement": "UsernameValidator should allow trailing newlines",
        "base_commit": "abc123"
    },
    {
        "instance_id": "requests__requests-1234",
        "repo": "psf/requests",
        "problem_statement": "Session cookies not persisted correctly",
        "base_commit": "def456"
    },
    {
        "instance_id": "sympy__sympy-5678",
        "repo": "sympy/sympy",
        "problem_statement": "Matrix multiply fails for empty matrices",
        "base_commit": "ghi789"
    }
]

SAMPLE_PATCH = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,1 +1,2 @@
 # Original
+# Fixed
"""


async def test_no_reproduction_gets_zero():
    """Test 1: Without reproduction script, score should be 0."""
    print("\n" + "="*60)
    print("TEST 1: No Reproduction = Score 0")
    print("="*60)
    
    workflow = EnforcedWorkflow(strict_mode=True, allow_mock=True)
    
    instance = SAMPLE_INSTANCES[0]
    
    # Submit patch WITHOUT reproduction script
    result = await workflow.evaluate_agent_submission(
        instance=instance,
        reproduction_script=None,  # No reproduction!
        patch=SAMPLE_PATCH
    )
    
    print(f"Instance: {result.instance_id}")
    print(f"Reproduction attempted: {result.reproduction_attempted}")
    print(f"Reproduction verified: {result.reproduction_verified}")
    print(f"Final score: {result.final_score}")
    print(f"Phase reached: {result.workflow_phase_reached.value}")
    print(f"Error: {result.reproduction_error}")
    
    # KEY ASSERTION: Score must be 0 without reproduction
    assert result.final_score == 0.0, f"Score should be 0 without reproduction, got {result.final_score}"
    assert result.reproduction_verified == False, "Reproduction should not be verified"
    assert result.workflow_phase_reached == WorkflowPhase.REPRODUCTION, "Should stop at reproduction phase"
    
    print("\n✅ Test passed: No reproduction = Score 0")
    return True


async def test_bad_reproduction_gets_zero():
    """Test 2: Bad reproduction script (doesn't actually fail) gets score 0."""
    print("\n" + "="*60)
    print("TEST 2: Bad Reproduction (passes when should fail) = Score 0")
    print("="*60)
    
    workflow = EnforcedWorkflow(strict_mode=True, allow_mock=True)
    
    instance = SAMPLE_INSTANCES[1]
    
    # Submit a reproduction script that PASSES (bad - should fail)
    # No "assert" or "raise" - mock verification will return reproduced=False
    bad_script = """
# This script passes when it should fail
print("Hello world")
# No checks here
"""
    
    result = await workflow.evaluate_agent_submission(
        instance=instance,
        reproduction_script=bad_script,
        patch=SAMPLE_PATCH
    )
    
    print(f"Instance: {result.instance_id}")
    print(f"Reproduction attempted: {result.reproduction_attempted}")
    print(f"Reproduction verified: {result.reproduction_verified}")
    print(f"Final score: {result.final_score}")
    print(f"Error: {result.reproduction_error}")
    
    # KEY ASSERTION: Score must be 0 with bad reproduction
    assert result.final_score == 0.0, f"Score should be 0 with bad reproduction, got {result.final_score}"
    assert result.reproduction_attempted == True, "Reproduction should be attempted"
    assert result.reproduction_verified == False, "Reproduction should NOT be verified"
    
    print("\n✅ Test passed: Bad reproduction = Score 0")
    return True


async def test_good_reproduction_allows_patch():
    """Test 3: Good reproduction allows patch evaluation."""
    print("\n" + "="*60)
    print("TEST 3: Good Reproduction Allows Patch Evaluation")
    print("="*60)
    
    workflow = EnforcedWorkflow(strict_mode=True, allow_mock=True)
    
    instance = SAMPLE_INSTANCES[2]
    
    # Submit a reproduction script that FAILS (good - proves bug exists)
    # Has "assert" - mock verification will return reproduced=True
    good_script = """
# This script fails because the bug exists
assert False, "Bug: Matrix multiply fails for empty matrices"
"""
    
    result = await workflow.evaluate_agent_submission(
        instance=instance,
        reproduction_script=good_script,
        patch=SAMPLE_PATCH
    )
    
    print(f"Instance: {result.instance_id}")
    print(f"Reproduction attempted: {result.reproduction_attempted}")
    print(f"Reproduction verified: {result.reproduction_verified}")
    print(f"Patch accepted: {result.patch_accepted}")
    print(f"Execution pass: {result.execution_pass}")
    print(f"Final score: {result.final_score}")
    print(f"Phase reached: {result.workflow_phase_reached.value}")
    print(f"Score breakdown: {result.score_breakdown}")
    
    # KEY ASSERTIONS
    assert result.reproduction_verified == True, "Reproduction should be verified"
    assert result.patch_accepted == True, "Patch should be accepted after reproduction"
    assert result.workflow_phase_reached == WorkflowPhase.COMPLETE, "Should reach complete phase"
    assert result.final_score > 0, "Score should be > 0 with verified reproduction"
    
    # Score should be at least reproduction weight (0.3) even if execution fails
    assert result.final_score >= 0.3, f"Score should be at least 0.3 (repro weight), got {result.final_score}"
    
    print("\n✅ Test passed: Good reproduction allows patch evaluation")
    return True


async def test_batch_evaluation():
    """Test 4: Batch evaluation with mixed results."""
    print("\n" + "="*60)
    print("TEST 4: Batch Evaluation (Mixed Results)")
    print("="*60)
    
    workflow = EnforcedWorkflow(strict_mode=True, allow_mock=True)
    
    submissions = [
        # No reproduction
        {
            "instance": SAMPLE_INSTANCES[0],
            "reproduction_script": None,
            "patch": SAMPLE_PATCH
        },
        # Bad reproduction
        {
            "instance": SAMPLE_INSTANCES[1],
            "reproduction_script": "print('passes')",
            "patch": SAMPLE_PATCH
        },
        # Good reproduction
        {
            "instance": SAMPLE_INSTANCES[2],
            "reproduction_script": "assert False, 'Bug exists'",
            "patch": SAMPLE_PATCH
        }
    ]
    
    results, summary = await workflow.evaluate_batch(submissions)
    
    print(f"\nBatch Summary:")
    print(f"  Total tasks: {summary['total_tasks']}")
    print(f"  Reproductions attempted: {summary['reproductions_attempted']}")
    print(f"  Reproductions verified: {summary['reproductions_verified']}")
    print(f"  Blocked by gate: {summary['blocked_by_reproduction_gate']}")
    print(f"  Gate block rate: {summary['gate_block_rate']:.1%}")
    print(f"  Avg final score: {summary['avg_final_score']:.2f}")
    
    # ASSERTIONS
    assert summary['total_tasks'] == 3, "Should have 3 tasks"
    assert summary['reproductions_verified'] == 1, "Only 1 should pass reproduction"
    assert summary['blocked_by_reproduction_gate'] == 2, "2 should be blocked by gate"
    assert summary['gate_block_rate'] > 0.5, "Block rate should be > 50%"
    
    print("\n✅ Test passed: Batch evaluation with proper gate enforcement")
    return True


async def test_non_strict_mode():
    """Test 5: Non-strict mode allows skipping reproduction."""
    print("\n" + "="*60)
    print("TEST 5: Non-Strict Mode (Reproduction Optional)")
    print("="*60)
    
    workflow = EnforcedWorkflow(strict_mode=False, allow_mock=True)
    
    instance = SAMPLE_INSTANCES[0]
    
    # Submit patch WITHOUT reproduction - should be allowed in non-strict mode
    result = await workflow.evaluate_agent_submission(
        instance=instance,
        reproduction_script=None,
        patch=SAMPLE_PATCH
    )
    
    print(f"Instance: {result.instance_id}")
    print(f"Reproduction verified: {result.reproduction_verified}")
    print(f"Final score: {result.final_score}")
    print(f"Phase reached: {result.workflow_phase_reached.value}")
    
    # In non-strict mode, should still get some score
    # (patch goes straight to execution)
    assert result.workflow_phase_reached != WorkflowPhase.REPRODUCTION, \
        "Should progress past reproduction in non-strict mode"
    
    print("\n✅ Test passed: Non-strict mode allows skipping reproduction")
    return True


async def main():
    """Run all Phase 2 tests."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║     PHASE 2: ENFORCED REPRODUCTION GATE                       ║
║     Testing: No reproduction = Score 0                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    all_passed = True
    
    tests = [
        ("No Reproduction = Zero", test_no_reproduction_gets_zero),
        ("Bad Reproduction = Zero", test_bad_reproduction_gets_zero),
        ("Good Reproduction Allows Patch", test_good_reproduction_allows_patch),
        ("Batch Evaluation", test_batch_evaluation),
        ("Non-Strict Mode", test_non_strict_mode),
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
    print("PHASE 2 TEST SUMMARY")
    print("="*60)
    
    if all_passed:
        print("""
✅ ALL TESTS PASSED

Phase 2 Implementation Status:
  ✅ Reproduction gate enforced in strict mode
  ✅ Score = 0 if reproduction not provided
  ✅ Score = 0 if reproduction doesn't actually fail
  ✅ Patch only accepted after verified reproduction
  ✅ Batch evaluation with proper gate statistics

Key difference from before:
  BEFORE: Agents could skip reproduction and submit patches directly
  NOW:    No reproduction = Score 0, regardless of patch quality
        """)
    else:
        print("\n❌ Some tests failed. Check output above.")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
