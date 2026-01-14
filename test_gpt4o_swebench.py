#!/usr/bin/env python3
"""
Simple GPT-4o Test for SWE-bench Tasks

Tests GPT-4o's ability to solve SWE-bench tasks with the A2A framework.
This is a direct test without Docker - evaluates patch generation quality.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

# Check for OpenAI
try:
    from openai import AsyncOpenAI
except ImportError:
    print("❌ OpenAI not installed. Run: pip install openai")
    sys.exit(1)


class GPT4oSWEBenchSolver:
    """GPT-4o solver for SWE-bench tasks"""
    
    def __init__(self, model: str = "gpt-4o"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
        
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.total_tokens = 0
        self.total_cost = 0.0
        
    async def solve_task(
        self,
        instance: Dict[str, Any],
        include_hints: bool = True
    ) -> Dict[str, Any]:
        """Solve a SWE-bench task"""
        
        # Build prompt
        prompt = self._build_prompt(instance, include_hints)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert software engineer specializing in fixing bugs in open-source Python projects. You analyze bug reports and generate minimal, focused patches in unified diff format."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4096
            )
            
            solution = response.choices[0].message.content
            
            # Track tokens
            if response.usage:
                self.total_tokens += response.usage.total_tokens
                # GPT-4o pricing estimate
                input_cost = response.usage.prompt_tokens * 0.005 / 1000
                output_cost = response.usage.completion_tokens * 0.015 / 1000
                self.total_cost += input_cost + output_cost
            
            # Extract patch
            patch = self._extract_patch(solution)
            
            return {
                "success": True,
                "solution": solution,
                "patch": patch,
                "model": self.model,
                "tokens_used": response.usage.total_tokens if response.usage else 0
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_prompt(self, instance: Dict[str, Any], include_hints: bool) -> str:
        """Build prompt for the LLM"""
        
        problem = instance.get("problem_statement", "")
        repo = instance.get("repo", "")
        base_commit = instance.get("base_commit", "")
        test_patch = instance.get("test_patch", "")
        hints = instance.get("hints_text", "") if include_hints else ""
        
        prompt = f"""You are fixing a bug in the {repo} repository.

## Problem Statement:
{problem}

## Repository Information:
- Repository: {repo}
- Base Commit: {base_commit}
"""
        
        if hints:
            prompt += f"""
## Hints from maintainers:
{hints[:2000]}
"""
        
        if test_patch:
            prompt += f"""
## Test Patch (tests that verify the fix):
```diff
{test_patch[:3000]}
```
"""
        
        prompt += """
## Your Task:
1. Analyze the problem statement and understand what needs to be fixed
2. Generate a patch that fixes the issue
3. Ensure your patch is minimal and focused on the problem
4. Return the patch in unified diff format

## Response Format:
First provide a brief ANALYSIS (2-3 sentences), then provide the PATCH:

ANALYSIS:
[Your brief analysis]

PATCH:
```diff
[Your patch in unified diff format]
```

Important:
- Make minimal changes necessary to fix the issue
- Follow the repository's coding style
- The patch should make the failing tests pass
"""
        
        return prompt
    
    def _extract_patch(self, solution: str) -> str:
        """Extract patch from the solution"""
        import re
        
        # Look for diff code blocks
        diff_pattern = r'```diff\n(.*?)```'
        matches = re.findall(diff_pattern, solution, re.DOTALL)
        
        if matches:
            return matches[-1].strip()
        
        # Try after PATCH: marker
        patch_pattern = r'PATCH:\s*\n```.*?\n(.*?)```'
        matches = re.findall(patch_pattern, solution, re.DOTALL)
        
        if matches:
            return matches[-1].strip()
        
        # Fallback: extract diff-like content
        lines = solution.split('\n')
        patch_lines = []
        in_patch = False
        
        for line in lines:
            if line.startswith(('---', '+++', '@@', 'diff --git')):
                in_patch = True
                patch_lines.append(line)
            elif in_patch and (line.startswith((' ', '-', '+', '@')) or line == ''):
                patch_lines.append(line)
            elif in_patch and line and not line[0] in (' ', '-', '+', '@'):
                break
        
        if patch_lines:
            return '\n'.join(patch_lines)
        
        return ""
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get usage metrics"""
        return {
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.total_cost, 4),
            "model": self.model
        }


def compare_patches(generated: str, expected: str) -> Dict[str, Any]:
    """Simple comparison of generated vs expected patches"""
    
    # Basic metrics
    gen_lines = set(line.strip() for line in generated.split('\n') if line.strip())
    exp_lines = set(line.strip() for line in expected.split('\n') if line.strip())
    
    # Find modifications (lines starting with + or -)
    gen_mods = set(line for line in gen_lines if line.startswith(('+', '-')) and not line.startswith(('+++', '---')))
    exp_mods = set(line for line in exp_lines if line.startswith(('+', '-')) and not line.startswith(('+++', '---')))
    
    overlap = gen_mods & exp_mods
    
    if exp_mods:
        recall = len(overlap) / len(exp_mods)
    else:
        recall = 0.0
    
    if gen_mods:
        precision = len(overlap) / len(gen_mods)
    else:
        precision = 0.0
    
    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0
    
    # Check if same files modified
    gen_files = set(line.split()[1] if len(line.split()) > 1 else '' for line in gen_lines if line.startswith('---') or line.startswith('+++'))
    exp_files = set(line.split()[1] if len(line.split()) > 1 else '' for line in exp_lines if line.startswith('---') or line.startswith('+++'))
    files_match = len(gen_files & exp_files) > 0
    
    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "files_match": files_match,
        "generated_modifications": len(gen_mods),
        "expected_modifications": len(exp_mods),
        "overlapping_modifications": len(overlap)
    }


async def run_benchmark(num_tasks: int = 5, easy_first: bool = True):
    """Run GPT-4o benchmark on SWE-bench tasks"""
    
    print("""
╔══════════════════════════════════════════════════════════════════╗
║         GPT-4o SWE-bench Benchmark with A2A Framework            ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Load dataset
    data_file = Path(__file__).parent / "data" / "swebench_cache" / "swebench_verified.json"
    if not data_file.exists():
        data_file = Path(__file__).parent / "data" / "cache" / "swebench_verified.json"
    
    if not data_file.exists():
        print(f"❌ Dataset not found at {data_file}")
        return
    
    with open(data_file, 'r') as f:
        instances = json.load(f)
    
    print(f"📚 Loaded {len(instances)} SWE-bench instances")
    
    # Select instances (prefer smaller patches for easier tasks)
    if easy_first:
        instances = sorted(instances, key=lambda x: len(x.get('patch', '')))
    
    # Take first N
    selected = instances[:num_tasks]
    
    print(f"🎯 Selected {len(selected)} tasks for testing")
    print(f"🤖 Model: gpt-4o\n")
    
    # Initialize solver
    solver = GPT4oSWEBenchSolver(model="gpt-4o")
    
    results = []
    
    for i, instance in enumerate(selected, 1):
        instance_id = instance.get('instance_id', 'unknown')
        repo = instance.get('repo', 'unknown')
        
        print(f"\n{'='*60}")
        print(f"Task {i}/{len(selected)}: {instance_id}")
        print(f"Repository: {repo}")
        print(f"Patch size: {len(instance.get('patch', ''))} chars")
        print('='*60)
        
        # Solve task
        print("🧠 Generating solution with GPT-4o...")
        start_time = datetime.now()
        
        result = await solver.solve_task(instance)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if result['success']:
            print(f"✅ Solution generated in {elapsed:.1f}s")
            print(f"   Tokens used: {result.get('tokens_used', 0)}")
            
            # Compare with expected patch
            expected_patch = instance.get('patch', '')
            generated_patch = result.get('patch', '')
            
            comparison = compare_patches(generated_patch, expected_patch)
            
            print(f"\n📊 Patch Comparison:")
            print(f"   F1 Score: {comparison['f1_score']:.2%}")
            print(f"   Precision: {comparison['precision']:.2%}")
            print(f"   Recall: {comparison['recall']:.2%}")
            print(f"   Files Match: {'✅' if comparison['files_match'] else '❌'}")
            
            # Show a snippet of the generated patch
            if generated_patch:
                print(f"\n📝 Generated Patch (first 500 chars):")
                print(f"   {generated_patch[:500].replace(chr(10), chr(10) + '   ')}")
            
            result['comparison'] = comparison
            result['elapsed_time'] = elapsed
            result['instance_id'] = instance_id
            result['repo'] = repo
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")
            result['instance_id'] = instance_id
            result['repo'] = repo
        
        results.append(result)
        
        # Small delay to avoid rate limits
        await asyncio.sleep(1)
    
    # Summary
    print("\n" + "="*70)
    print("BENCHMARK SUMMARY")
    print("="*70)
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    print(f"\nTotal Tasks: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        avg_f1 = sum(r['comparison']['f1_score'] for r in successful) / len(successful)
        avg_precision = sum(r['comparison']['precision'] for r in successful) / len(successful)
        avg_recall = sum(r['comparison']['recall'] for r in successful) / len(successful)
        files_matched = sum(1 for r in successful if r['comparison']['files_match'])
        
        print(f"\n📈 Average Metrics (across successful tasks):")
        print(f"   Average F1 Score: {avg_f1:.2%}")
        print(f"   Average Precision: {avg_precision:.2%}")
        print(f"   Average Recall: {avg_recall:.2%}")
        print(f"   Files Matched: {files_matched}/{len(successful)}")
        
        avg_time = sum(r['elapsed_time'] for r in successful) / len(successful)
        print(f"   Average Time: {avg_time:.1f}s")
    
    # Cost metrics
    metrics = solver.get_metrics()
    print(f"\n💰 Usage Metrics:")
    print(f"   Total Tokens: {metrics['total_tokens']}")
    print(f"   Estimated Cost: ${metrics['estimated_cost']:.4f}")
    print(f"   Model: {metrics['model']}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = Path(__file__).parent / f"gpt4o_benchmark_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "model": "gpt-4o",
            "num_tasks": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "metrics": metrics,
            "results": results
        }, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {results_file}")
    
    # Detailed results table
    print("\n📋 Detailed Results:")
    print("-" * 80)
    print(f"{'Instance ID':<40} {'Status':<10} {'F1':<10} {'Time':<10}")
    print("-" * 80)
    
    for r in results:
        instance_id = r.get('instance_id', 'unknown')[:38]
        status = "✅" if r.get('success') else "❌"
        f1 = f"{r['comparison']['f1_score']:.1%}" if r.get('comparison') else "N/A"
        time_str = f"{r['elapsed_time']:.1f}s" if r.get('elapsed_time') else "N/A"
        print(f"{instance_id:<40} {status:<10} {f1:<10} {time_str:<10}")
    
    print("-" * 80)
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test GPT-4o on SWE-bench tasks")
    parser.add_argument("--tasks", type=int, default=3, help="Number of tasks to test")
    parser.add_argument("--easy", action="store_true", default=True, help="Start with easier tasks")
    
    args = parser.parse_args()
    
    print("🚀 Starting GPT-4o SWE-bench Test")
    print(f"   Tasks: {args.tasks}")
    print(f"   Easy first: {args.easy}")
    
    asyncio.run(run_benchmark(num_tasks=args.tasks, easy_first=args.easy))
