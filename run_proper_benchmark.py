#!/usr/bin/env python3
"""
PROPER SWE-bench A2A Benchmark - Addresses All Feedback Issues

This script fixes the following issues from the architectural review:

1. SEMANTIC MATCH CRITICAL FAILURE
   - Uses PatchExecutor for EXECUTION-based pass/fail
   - NOT semantic F1 similarity
   
2. GHOST ARCHITECTURE (Unenforced Protocols)
   - Uses EnforcedWorkflow to REQUIRE reproduction gate
   - Agents MUST demonstrate bug reproduction before patching
   
3. HEURISTIC ADVERSARIAL TESTING
   - Uses DynamicAdversarialTester with Docker execution
   - Real fuzz testing via hypothesis
   - Real mutation testing via mutmut
   
4. SIGNAL-TO-NOISE IN CONTAMINATION
   - Uses MultiRunExecutor for statistical significance
   - Reports mean ± std dev, not single runs
   
5. INTEGRATION RISKS
   - No heuristic fallback - LLM only
   - Strict validation of patch format

Usage:
    python run_proper_benchmark.py --model gpt-4o --tasks 100 --runs 3
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import random
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from openai import AsyncOpenAI

# Import the PROPER infrastructure
from src.execution.patch_executor import PatchExecutor, ExecutionConfig
from src.execution.enforced_workflow import EnforcedWorkflow, WorkflowConfig
from src.adversarial.dynamic_tester import DynamicAdversarialTester
from src.evaluation.multi_run import MultiRunExecutor
from src.evaluation.statistical_analysis import StatisticalAnalyzer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkConfig:
    """Configuration for proper benchmark."""
    model: str = "gpt-4o"
    num_tasks: int = 100
    num_runs: int = 3  # Multiple runs for statistical significance
    enforce_reproduction: bool = True  # MUST be True for valid results
    use_execution_metrics: bool = True  # MUST be True for valid results
    run_adversarial: bool = True
    use_docker: bool = True
    random_seed: int = 42  # For reproducible task selection
    allow_heuristics: bool = False  # MUST be False for valid results


class ProperPurpleAgent:
    """
    Purple agent that follows proper protocols.
    
    Key differences from the old implementation:
    1. Generates reproduction script FIRST
    2. Generates patch SECOND
    3. NO heuristic fallback
    """
    
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        logger.info(f"Initialized ProperPurpleAgent with model: {self.model}")
    
    async def generate_reproduction_script(
        self,
        problem_statement: str,
        repo: str,
        test_patch: str
    ) -> Dict[str, Any]:
        """
        Generate a script that reproduces the bug.
        This MUST succeed before patch generation.
        """
        prompt = f"""You are debugging a bug in {repo}.

PROBLEM STATEMENT:
{problem_statement}

TEST PATCH (what the tests expect):
{test_patch[:2000] if test_patch else 'No test patch available'}

Write a MINIMAL Python script that:
1. Imports the relevant module
2. Demonstrates the bug (should fail/error without fix)
3. Prints "BUG REPRODUCED" if the bug is present
4. Prints "BUG NOT FOUND" if the bug is already fixed

The script should be self-contained and runnable.

```python
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at reproducing bugs. Generate minimal, self-contained reproduction scripts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            
            # Extract script
            script = self._extract_code_block(content, "python")
            
            return {
                "success": True,
                "reproduction_script": script,
                "raw_response": content
            }
            
        except Exception as e:
            logger.error(f"Reproduction script generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_patch(
        self,
        problem_statement: str,
        repo: str,
        reproduction_result: str
    ) -> Dict[str, Any]:
        """
        Generate a patch to fix the bug.
        Called ONLY after reproduction is verified.
        """
        prompt = f"""You are fixing a bug in {repo}.

PROBLEM STATEMENT:
{problem_statement}

REPRODUCTION RESULT:
{reproduction_result}

Generate a MINIMAL unified diff patch to fix this bug.
Start with proper diff headers (--- a/file and +++ b/file).
Only include essential changes.

```diff
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert bug fixer. Generate minimal, focused patches in unified diff format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            patch = self._extract_code_block(content, "diff")
            
            return {
                "success": True,
                "patch": patch,
                "raw_response": content
            }
            
        except Exception as e:
            logger.error(f"Patch generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_code_block(self, content: str, lang: str) -> str:
        """Extract code block from response."""
        import re
        pattern = rf'```{lang}\n(.*?)```'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Fallback: look for diff-like content
        if lang == "diff":
            lines = []
            in_diff = False
            for line in content.split('\n'):
                if line.startswith(('diff --git', '---', '+++')):
                    in_diff = True
                if in_diff:
                    if line.startswith(('diff', '---', '+++', '@@', '+', '-', ' ')) or line == '':
                        lines.append(line)
                    elif line and not line[0] in '@ +-':
                        break
            return '\n'.join(lines) if lines else content
        
        return content


async def run_proper_benchmark(config: BenchmarkConfig):
    """Run the benchmark with PROPER protocols."""
    
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PROPER SWE-bench A2A Benchmark                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ✓ Execution-based metrics (NOT semantic F1)                                 ║
║  ✓ Reproduction gate ENFORCED                                                ║
║  ✓ Dynamic adversarial testing (Docker execution)                            ║
║  ✓ Multi-run statistical analysis                                            ║
║  ✗ NO heuristic fallback                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    print(f"Configuration:")
    print(f"  Model: {config.model}")
    print(f"  Tasks: {config.num_tasks}")
    print(f"  Runs: {config.num_runs}")
    print(f"  Reproduction Gate: {'ENFORCED' if config.enforce_reproduction else 'DISABLED'}")
    print(f"  Metrics: {'EXECUTION' if config.use_execution_metrics else 'SEMANTIC'}")
    print(f"  Adversarial: {'ENABLED' if config.run_adversarial else 'DISABLED'}")
    print(f"  Docker: {'ENABLED' if config.use_docker else 'MOCK'}")
    print()
    
    # Validate config
    if not config.enforce_reproduction:
        print("⚠️  WARNING: Reproduction gate disabled - results may be invalid")
    if not config.use_execution_metrics:
        print("⚠️  WARNING: Using semantic metrics - results may be invalid")
    if config.allow_heuristics:
        print("⚠️  WARNING: Heuristics allowed - results may be invalid")
    
    # Load dataset with CONSISTENT random selection
    data_path = Path(__file__).parent / "data" / "swebench_cache" / "swebench_verified.json"
    with open(data_path) as f:
        all_instances = json.load(f)
    
    # Use RANDOM selection (not sorted by difficulty) for fair comparison
    random.seed(config.random_seed)
    random.shuffle(all_instances)
    instances = all_instances[:config.num_tasks]
    
    avg_patch_size = sum(len(i.get('patch', '')) for i in instances) / len(instances)
    print(f"Loaded {len(instances)} instances (avg patch: {avg_patch_size:.0f} chars)")
    print()
    
    # Initialize components
    agent = ProperPurpleAgent(model=config.model)
    
    # Initialize execution-based infrastructure
    executor = PatchExecutor(ExecutionConfig(
        use_docker=config.use_docker,
        timeout=300
    ))
    
    workflow = EnforcedWorkflow(WorkflowConfig(
        require_reproduction=config.enforce_reproduction,
        require_explanation=False,
        timeout=300
    ))
    
    adversarial_tester = DynamicAdversarialTester(
        use_docker=config.use_docker,
        timeout=120
    ) if config.run_adversarial else None
    
    # Run multiple times for statistical significance
    all_run_results = []
    
    for run_num in range(1, config.num_runs + 1):
        print(f"\n{'='*70}")
        print(f"RUN {run_num}/{config.num_runs}")
        print(f"{'='*70}\n")
        
        run_results = []
        
        for i, instance in enumerate(instances, 1):
            instance_id = instance['instance_id']
            repo = instance['repo']
            problem = instance.get('problem_statement', '')
            test_patch = instance.get('test_patch', '')
            expected_patch = instance.get('patch', '')
            
            print(f"[{i}/{len(instances)}] {instance_id}")
            
            result = {
                "instance_id": instance_id,
                "repo": repo,
                "run": run_num
            }
            
            try:
                # Step 1: Generate reproduction script
                if config.enforce_reproduction:
                    repro_result = await agent.generate_reproduction_script(
                        problem, repo, test_patch
                    )
                    
                    if not repro_result.get("success"):
                        result["success"] = False
                        result["error"] = "reproduction_failed"
                        result["execution_pass"] = False
                        print(f"  ❌ Reproduction failed")
                        run_results.append(result)
                        continue
                    
                    # Verify reproduction via workflow
                    workflow_result = await workflow.verify_reproduction(
                        instance, repro_result.get("reproduction_script", "")
                    )
                    
                    if not workflow_result.reproduction_verified:
                        result["success"] = False
                        result["error"] = "reproduction_not_verified"
                        result["execution_pass"] = False
                        print(f"  ❌ Reproduction not verified")
                        run_results.append(result)
                        continue
                    
                    print(f"  ✓ Reproduction verified")
                    repro_output = workflow_result.reproduction_output
                else:
                    repro_output = "Reproduction gate bypassed"
                
                # Step 2: Generate patch
                patch_result = await agent.generate_patch(problem, repo, repro_output)
                
                if not patch_result.get("success"):
                    result["success"] = False
                    result["error"] = "patch_generation_failed"
                    result["execution_pass"] = False
                    print(f"  ❌ Patch generation failed")
                    run_results.append(result)
                    continue
                
                generated_patch = patch_result.get("patch", "")
                
                # Step 3: Execute patch (NOT semantic comparison!)
                if config.use_execution_metrics:
                    exec_result = await executor.execute_patch(instance, generated_patch)
                    
                    result["success"] = True
                    result["execution_pass"] = exec_result.get("execution_pass", False)
                    result["tests_passed"] = exec_result.get("tests_passed", 0)
                    result["tests_failed"] = exec_result.get("tests_failed", 0)
                    result["execution_time"] = exec_result.get("execution_time", 0)
                    result["metric_type"] = "execution"
                    
                    status = "✅" if result["execution_pass"] else "❌"
                    print(f"  {status} Execution: {result['tests_passed']} passed, {result['tests_failed']} failed")
                else:
                    # Fallback to semantic (NOT RECOMMENDED)
                    from src.scoring.semantic_patch import compute_patch_metrics
                    comparison = compute_patch_metrics(generated_patch, expected_patch)
                    result["success"] = True
                    result["semantic_match"] = comparison.get("f1_score", 0)
                    result["metric_type"] = "semantic"
                    print(f"  ⚠️ Semantic: {result['semantic_match']*100:.0f}%")
                
                # Step 4: Adversarial testing (optional)
                if config.run_adversarial and adversarial_tester and result.get("execution_pass"):
                    adv_result = await adversarial_tester.run_adversarial_suite(
                        instance, generated_patch
                    )
                    result["adversarial"] = {
                        "fuzz_pass_rate": adv_result.fuzz_result.pass_rate if adv_result.fuzz_result else None,
                        "mutation_pass_rate": adv_result.mutation_result.pass_rate if adv_result.mutation_result else None,
                        "overall_robustness": adv_result.overall_robustness
                    }
                    print(f"  🔬 Adversarial robustness: {adv_result.overall_robustness*100:.0f}%")
                
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)
                result["execution_pass"] = False
                print(f"  ❌ Error: {e}")
            
            run_results.append(result)
            await asyncio.sleep(0.5)  # Rate limit
        
        all_run_results.append(run_results)
    
    # Statistical analysis across runs
    print(f"\n{'='*70}")
    print("STATISTICAL ANALYSIS")
    print(f"{'='*70}\n")
    
    analyzer = StatisticalAnalyzer()
    
    # Compute per-run metrics
    run_metrics = []
    for run_num, run_results in enumerate(all_run_results, 1):
        if config.use_execution_metrics:
            passed = sum(1 for r in run_results if r.get("execution_pass", False))
        else:
            passed = sum(1 for r in run_results if r.get("semantic_match", 0) >= 0.7)
        
        pass_rate = passed / len(run_results) if run_results else 0
        run_metrics.append(pass_rate)
        print(f"  Run {run_num}: {pass_rate*100:.1f}% pass rate")
    
    # Compute statistics
    if len(run_metrics) > 1:
        import statistics
        mean = statistics.mean(run_metrics)
        stdev = statistics.stdev(run_metrics)
        print(f"\n  Mean: {mean*100:.1f}% ± {stdev*100:.1f}% (std dev)")
        print(f"  Range: {min(run_metrics)*100:.1f}% - {max(run_metrics)*100:.1f}%")
    else:
        mean = run_metrics[0] if run_metrics else 0
        stdev = 0
        print(f"\n  Single run: {mean*100:.1f}%")
        print("  ⚠️ Multiple runs recommended for statistical significance")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "config": asdict(config),
        "statistics": {
            "mean_pass_rate": mean,
            "std_dev": stdev,
            "run_pass_rates": run_metrics,
            "num_runs": config.num_runs,
            "num_tasks": len(instances)
        },
        "methodology": {
            "metric_type": "execution" if config.use_execution_metrics else "semantic",
            "reproduction_enforced": config.enforce_reproduction,
            "adversarial_enabled": config.run_adversarial,
            "heuristics_allowed": config.allow_heuristics,
            "docker_enabled": config.use_docker,
            "task_selection": "random_seed_42",
            "avg_patch_size": avg_patch_size
        },
        "runs": all_run_results
    }
    
    output_file = Path(__file__).parent / f"proper_benchmark_{config.model}_{timestamp}.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"\nModel: {config.model}")
    print(f"Tasks: {config.num_tasks}")
    print(f"Runs: {config.num_runs}")
    print(f"\nMetric Type: {'EXECUTION (pass/fail)' if config.use_execution_metrics else 'SEMANTIC (F1)'}")
    print(f"Reproduction Gate: {'ENFORCED' if config.enforce_reproduction else 'DISABLED'}")
    print(f"Adversarial Testing: {'EXECUTION-BASED' if config.run_adversarial else 'DISABLED'}")
    print(f"\nResult: {mean*100:.1f}% ± {stdev*100:.1f}%")
    
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PROPER SWE-bench A2A Benchmark")
    parser.add_argument("--model", type=str, default="gpt-4o", help="Model to evaluate")
    parser.add_argument("--tasks", type=int, default=100, help="Number of tasks")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs for statistics")
    parser.add_argument("--no-reproduction", action="store_true", help="Disable reproduction gate (NOT RECOMMENDED)")
    parser.add_argument("--semantic-only", action="store_true", help="Use semantic F1 instead of execution (NOT RECOMMENDED)")
    parser.add_argument("--no-adversarial", action="store_true", help="Disable adversarial testing")
    parser.add_argument("--no-docker", action="store_true", help="Use mock execution instead of Docker")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for task selection")
    
    args = parser.parse_args()
    
    config = BenchmarkConfig(
        model=args.model,
        num_tasks=args.tasks,
        num_runs=args.runs,
        enforce_reproduction=not args.no_reproduction,
        use_execution_metrics=not args.semantic_only,
        run_adversarial=not args.no_adversarial,
        use_docker=not args.no_docker,
        random_seed=args.seed,
        allow_heuristics=False  # Never allow heuristics
    )
    
    asyncio.run(run_proper_benchmark(config))
