#!/usr/bin/env python3
"""Benchmark Claude Models (Opus and Sonnet) on SWE-bench tasks"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import difflib
import httpx


class ClaudeBenchmarkAgent:
    """Benchmark agent for Claude models using Messages API directly"""
    
    # Model mapping - correct model names for 2025
    MODELS = {
        "opus": "claude-opus-4-1",
        "opus-4.1": "claude-opus-4-1",
        "sonnet": "claude-sonnet-4-5-20250929",
        "sonnet-4.5": "claude-sonnet-4-5-20250929",
        "haiku": "claude-3-haiku-20240307",
    }
    
    API_URL = "https://api.anthropic.com/v1/messages"
    
    def __init__(self, model: str = "sonnet"):
        self.model_key = model.lower()
        self.model = self.MODELS.get(self.model_key, model)
        
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        print(f"Initialized Claude agent with model: {self.model}")
        
    async def solve(self, instance: Dict) -> Dict:
        """Solve a SWE-bench instance"""
        instance_id = instance.get("instance_id", "unknown")
        problem = instance.get("problem_statement", "")
        repo = instance.get("repo", "")
        
        prompt = f"""You are an expert software engineer. Fix the following bug:

Repository: {repo}

Problem Description:
{problem}

Requirements:
1. Generate a minimal patch that fixes the bug
2. Use unified diff format
3. Only include necessary changes
4. Follow existing code style

Return ONLY the patch in unified diff format (starting with --- and +++), nothing else."""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.API_URL,
                    headers=self.headers,
                    json={
                        "model": self.model,
                        "max_tokens": 2048,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                
                if response.status_code != 200:
                    return {
                        "instance_id": instance_id,
                        "success": False,
                        "error": f"API error {response.status_code}: {response.text[:200]}",
                        "semantic_match": 0.0,
                        "model": self.model,
                    }
                
                data = response.json()
                generated_patch = data["content"][0]["text"]
                
                # Calculate semantic similarity with expected patch
                expected_patch = instance.get("patch", "")
                similarity = self._calculate_similarity(generated_patch, expected_patch)
                
                usage = data.get("usage", {})
                
                return {
                    "instance_id": instance_id,
                    "success": True,
                    "generated_patch": generated_patch,
                    "expected_patch": expected_patch,
                    "semantic_match": similarity,
                    "model": self.model,
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                }
                
        except Exception as e:
            return {
                "instance_id": instance_id,
                "success": False,
                "error": str(e),
                "semantic_match": 0.0,
                "model": self.model,
            }
    
    def _calculate_similarity(self, generated: str, expected: str) -> float:
        """Calculate semantic similarity between patches"""
        # Normalize patches
        gen_lines = [l.strip() for l in generated.split('\n') if l.strip() and not l.startswith('```')]
        exp_lines = [l.strip() for l in expected.split('\n') if l.strip()]
        
        if not gen_lines or not exp_lines:
            return 0.0
        
        # Use difflib sequence matcher
        matcher = difflib.SequenceMatcher(None, '\n'.join(gen_lines), '\n'.join(exp_lines))
        return matcher.ratio()


async def run_claude_benchmark(model: str, num_tasks: int = 100):
    """Run benchmark with specified Claude model"""
    
    print(f"\n{'='*70}")
    print(f"CLAUDE BENCHMARK: {model.upper()}")
    print(f"{'='*70}")
    print(f"Model: {model}")
    print(f"Tasks: {num_tasks}")
    print()
    
    # Load SWE-bench instances
    cache_path = Path("data/swebench_cache/swebench_verified.json")
    if not cache_path.exists():
        cache_path = Path("data/cache/swebench_verified.json")
    
    if not cache_path.exists():
        print(f"Error: SWE-bench cache not found at {cache_path}")
        return None
    
    with open(cache_path) as f:
        all_instances = json.load(f)
    
    # Sort by patch size (smaller = easier)
    sorted_instances = sorted(all_instances, key=lambda x: len(x.get("patch", "")))
    instances = sorted_instances[:num_tasks]
    
    print(f"Loaded {len(instances)} instances\n")
    
    # Initialize agent
    try:
        agent = ClaudeBenchmarkAgent(model=model)
    except ValueError as e:
        print(f"Error: {e}")
        print("\nSet your API key:")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        return None
    
    results = []
    total_input_tokens = 0
    total_output_tokens = 0
    
    for i, instance in enumerate(instances):
        instance_id = instance.get("instance_id", f"task_{i}")
        print(f"[{i+1}/{num_tasks}] {instance_id}...", end=" ", flush=True)
        
        result = await agent.solve(instance)
        results.append(result)
        
        if result["success"]:
            total_input_tokens += result.get("input_tokens", 0)
            total_output_tokens += result.get("output_tokens", 0)
            print(f"✓ {result['semantic_match']:.1%}")
        else:
            error_msg = result.get('error', 'unknown error')
            print(f"✗ {error_msg[:60]}")
        
        # Rate limiting - Claude has rate limits
        await asyncio.sleep(1.0)
    
    # Calculate statistics
    successful = [r for r in results if r["success"]]
    avg_match = sum(r["semantic_match"] for r in successful) / len(successful) if successful else 0
    high_match = len([r for r in successful if r["semantic_match"] >= 0.7])
    perfect = len([r for r in successful if r["semantic_match"] >= 0.95])
    
    summary = {
        "model": model,
        "model_id": agent.model,
        "num_tasks": num_tasks,
        "successful": len(successful),
        "failed": len(results) - len(successful),
        "avg_semantic_match": avg_match,
        "high_match_count": high_match,
        "perfect_count": perfect,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "timestamp": datetime.now().isoformat(),
        "results": results,
    }
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"RESULTS: {model.upper()}")
    print(f"{'='*70}")
    print(f"Tasks Completed: {len(successful)}/{num_tasks} ({len(successful)/num_tasks*100:.1f}%)")
    print(f"Avg Semantic Match: {avg_match:.1%}")
    print(f"High Match (≥70%): {high_match}")
    print(f"Perfect Match (≥95%): {perfect}")
    print(f"Total Tokens: {total_input_tokens + total_output_tokens:,}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"claude_{model.replace('.', '_')}_results_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to: {output_file}")
    
    return summary


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Benchmark Claude models on SWE-bench")
    parser.add_argument("--model", type=str, default="sonnet", 
                        choices=["opus", "opus-4.1", "sonnet", "sonnet-4.5", "haiku"],
                        help="Claude model to use")
    parser.add_argument("--tasks", type=int, default=100, help="Number of tasks to run")
    args = parser.parse_args()
    
    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        print("\nSet your API key:")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        sys.exit(1)
    
    await run_claude_benchmark(args.model, args.tasks)


if __name__ == "__main__":
    asyncio.run(main())
