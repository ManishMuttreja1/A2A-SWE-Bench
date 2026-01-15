"""Adversarial Testing Script for SWE-bench A2A

Tests patches against adversarial inputs, fuzz tests, and mutations
to verify robustness beyond standard test suites.
"""

import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from openai import AsyncOpenAI

from src.adversarial import AdversarialEvaluator, FuzzTester, AdversarialGenerator, PatchMutationTester


def load_swebench_instances(cache_path: str = "data/swebench_cache/swebench_verified.json", limit: int = 100) -> List[Dict]:
    """Load SWE-bench instances from cache"""
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            instances = json.load(f)
            return instances[:limit]
    
    # Try alternative path
    alt_path = "swebench_verified.json"
    if os.path.exists(alt_path):
        with open(alt_path, 'r') as f:
            instances = json.load(f)
            return instances[:limit]
    
    print(f"Warning: Could not find SWE-bench cache at {cache_path}")
    return []


class GPTSolver:
    """Simple GPT-based patch generator for testing"""
    
    def __init__(self, model: str = "gpt-5.2"):
        self.client = AsyncOpenAI()
        self.model = model
        self.stats = {"solved": 0, "failed": 0, "total_cost": 0.0}
    
    async def generate_patch(self, instance: Dict) -> str:
        """Generate a patch for an instance"""
        problem = instance.get("problem_statement", "")
        repo = instance.get("repo", "")
        
        prompt = f"""You are an expert software engineer. Generate a minimal patch to fix this bug.

Repository: {repo}
Problem: {problem[:2000]}

Generate ONLY the patch in unified diff format. No explanation.
Start with: --- a/
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You generate minimal bug-fix patches."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
            )
            
            patch = response.choices[0].message.content
            self.stats["solved"] += 1
            
            # Estimate cost
            tokens = response.usage.total_tokens if response.usage else 0
            self.stats["total_cost"] += tokens * 0.00001
            
            return patch
            
        except Exception as e:
            print(f"Error generating patch: {e}")
            self.stats["failed"] += 1
            return ""


async def run_adversarial_tests(
    num_tasks: int = 10,
    model: str = "gpt-5.2",
    seed: int = 42
):
    """Run adversarial tests on generated patches"""
    print(f"\n{'='*70}")
    print(f"ADVERSARIAL TESTING")
    print(f"{'='*70}")
    print(f"Model: {model}")
    print(f"Instances: {num_tasks}")
    print(f"Seed: {seed}")
    print()
    
    random.seed(seed)
    
    # Load instances
    instances = load_swebench_instances(limit=num_tasks * 2)
    if not instances:
        print("No instances found. Creating synthetic test.")
        instances = create_synthetic_instances(num_tasks)
    
    random.shuffle(instances)
    instances = instances[:num_tasks]
    print(f"Loaded {len(instances)} instances\n")
    
    # Initialize components
    solver = GPTSolver(model=model)
    evaluator = AdversarialEvaluator(
        llm_client=solver.client,
        seed=seed
    )
    
    results = []
    
    for i, instance in enumerate(instances):
        instance_id = instance.get("instance_id", f"instance_{i}")
        print(f"\n[{i+1}/{num_tasks}] {instance_id}")
        print("-" * 50)
        
        # Generate patch
        print("  Generating patch...")
        patch = await solver.generate_patch(instance)
        
        if not patch:
            print("  ✗ Failed to generate patch")
            results.append({
                "instance_id": instance_id,
                "error": "patch_generation_failed",
                "passed": False
            })
            continue
        
        print(f"  Patch generated ({len(patch)} chars)")
        
        # Get expected patch if available
        expected_patch = instance.get("patch", None)
        
        # Run adversarial evaluation
        print("  Running adversarial evaluation...")
        score = await evaluator.evaluate(
            instance=instance,
            generated_patch=patch,
            expected_patch=expected_patch,
            run_fuzz=True,
            run_adversarial=True,
            run_mutation=expected_patch is not None
        )
        
        # Print results
        print(f"  Fuzz Score:        {score.fuzz_score:.1%}")
        print(f"  Adversarial Score: {score.adversarial_score:.1%}")
        print(f"  Mutation Score:    {score.mutation_score:.1%}")
        print(f"  Overall Score:     {score.overall_score:.1%}")
        print(f"  Passed:            {'✓' if score.passed else '✗'}")
        
        if score.high_risk_issues:
            print(f"  ⚠ High Risk Issues:")
            for issue in score.high_risk_issues:
                print(f"    - {issue}")
        
        results.append({
            "instance_id": instance_id,
            "patch_length": len(patch),
            **score.to_dict()
        })
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    total = len(results)
    passed = sum(1 for r in results if r.get("passed", False))
    failed = total - passed
    
    avg_fuzz = sum(r.get("fuzz_score", 0) for r in results) / total if total > 0 else 0
    avg_adv = sum(r.get("adversarial_score", 0) for r in results) / total if total > 0 else 0
    avg_mut = sum(r.get("mutation_score", 0) for r in results) / total if total > 0 else 0
    avg_overall = sum(r.get("overall_score", 0) for r in results) / total if total > 0 else 0
    
    print(f"Total instances:     {total}")
    print(f"Passed:              {passed} ({passed/total*100:.1f}%)")
    print(f"Failed:              {failed} ({failed/total*100:.1f}%)")
    print()
    print(f"Avg Fuzz Score:      {avg_fuzz:.1%}")
    print(f"Avg Adversarial:     {avg_adv:.1%}")
    print(f"Avg Mutation:        {avg_mut:.1%}")
    print(f"Avg Overall:         {avg_overall:.1%}")
    print()
    print(f"Solver stats:        {solver.stats}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"adversarial_results_{model}_{timestamp}.json"
    
    output = {
        "model": model,
        "num_tasks": num_tasks,
        "seed": seed,
        "timestamp": timestamp,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "avg_fuzz_score": avg_fuzz,
            "avg_adversarial_score": avg_adv,
            "avg_mutation_score": avg_mut,
            "avg_overall_score": avg_overall,
        },
        "solver_stats": solver.stats,
        "evaluator_stats": evaluator.get_statistics(),
        "results": results
    }
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    
    return output


def create_synthetic_instances(num: int) -> List[Dict]:
    """Create synthetic test instances if real ones not available"""
    instances = []
    
    bugs = [
        {
            "id": "null_check",
            "problem": "Function crashes when input is None",
            "patch": "--- a/lib.py\n+++ b/lib.py\n@@ -1,2 +1,4 @@\n def process(data):\n+    if data is None:\n+        return []\n     return data.split(',')"
        },
        {
            "id": "empty_list",
            "problem": "Index error when list is empty",
            "patch": "--- a/utils.py\n+++ b/utils.py\n@@ -1,2 +1,4 @@\n def get_first(items):\n+    if not items:\n+        return None\n     return items[0]"
        },
        {
            "id": "divide_zero",
            "problem": "Division by zero error",
            "patch": "--- a/math.py\n+++ b/math.py\n@@ -1,2 +1,4 @@\n def safe_divide(a, b):\n+    if b == 0:\n+        return 0\n     return a / b"
        },
    ]
    
    for i in range(num):
        bug = bugs[i % len(bugs)]
        instances.append({
            "instance_id": f"synthetic_{bug['id']}_{i}",
            "repo": "test/repo",
            "problem_statement": bug["problem"],
            "patch": bug["patch"],
        })
    
    return instances


async def run_quick_fuzz_test():
    """Quick standalone fuzz test demo"""
    print("\n" + "="*50)
    print("QUICK FUZZ TEST DEMO")
    print("="*50)
    
    fuzz = FuzzTester(seed=42)
    
    # Test patch
    patch = """
+def process_data(items: list, threshold: int = 0):
+    if items is None:
+        return []
+    if not items:
+        return []
+    result = []
+    for item in items:
+        if item > threshold:
+            result.append(item)
+    return result
"""
    
    problem = "Process data crashes on empty or None input"
    
    result = fuzz.run_fuzz_tests(patch, problem, num_random_tests=20)
    
    print(f"Total tests:  {result.total_tests}")
    print(f"Passed:       {result.passed}")
    print(f"Failed:       {result.failed}")
    print(f"Crashes:      {result.crashes}")
    print(f"Score:        {result.score:.1%}")
    
    print("\nSample test cases:")
    for tc in result.test_cases[:5]:
        status = "✓" if tc.passed else "✗"
        print(f"  {status} {tc.name}: {tc.actual_result}")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Adversarial testing for SWE-bench A2A")
    parser.add_argument("--tasks", type=int, default=10, help="Number of tasks")
    parser.add_argument("--model", type=str, default="gpt-5.2", help="Model to use")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--quick", action="store_true", help="Run quick fuzz demo only")
    
    args = parser.parse_args()
    
    if args.quick:
        await run_quick_fuzz_test()
    else:
        await run_adversarial_tests(
            num_tasks=args.tasks,
            model=args.model,
            seed=args.seed
        )


if __name__ == "__main__":
    asyncio.run(main())
