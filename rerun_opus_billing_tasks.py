#!/usr/bin/env python3
"""
Rerun the 10 Opus tasks that originally had billing errors.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx

# Tasks that had billing errors
BILLING_ERROR_TASKS = [
    'django__django-10097', 'django__django-12273', 
    'scikit-learn__scikit-learn-13779', 'sympy__sympy-15017',
    'pytest-dev__pytest-7205', 'sphinx-doc__sphinx-8721',
    'django__django-11451', 'scikit-learn__scikit-learn-11578',
    'django__django-11179', 'django__django-12663'
]


async def solve_with_opus(api_key, instance):
    """Generate a patch using Claude Opus."""
    problem = instance.get("problem_statement", "")
    repo = instance.get("repo", "")
    
    prompt = f"""You are an expert software engineer. Fix the following bug:

Repository: {repo}

Problem Description:
{problem[:3000]}

Requirements:
1. Generate a minimal patch that fixes the bug
2. Use unified diff format
3. Only include necessary changes

Return ONLY the patch in unified diff format (starting with --- and +++), nothing else."""
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-opus-4-20250514",
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"API error {response.status_code}: {response.text[:200]}"
                }
            
            data = response.json()
            patch = data["content"][0]["text"]
            usage = data.get("usage", {})
            
            return {
                "success": True,
                "patch": patch,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0)
            }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def compute_semantic_match(generated, expected):
    """Simple semantic match computation."""
    if not generated or not expected:
        return 0.0
    
    gen_tokens = set(generated.split())
    exp_tokens = set(expected.split())
    
    if not exp_tokens:
        return 0.0
    
    intersection = gen_tokens & exp_tokens
    precision = len(intersection) / len(gen_tokens) if gen_tokens else 0
    recall = len(intersection) / len(exp_tokens) if exp_tokens else 0
    
    if precision + recall == 0:
        return 0.0
    
    return 2 * precision * recall / (precision + recall)


async def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║     RERUN OPUS BILLING ERROR TASKS                               ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set")
        return
    
    # Load dataset
    with open("data/swebench_cache/swebench_verified.json") as f:
        all_instances = json.load(f)
    
    # Filter to billing error tasks
    instances = [i for i in all_instances if i['instance_id'] in BILLING_ERROR_TASKS]
    print(f"Found {len(instances)} tasks to rerun\n")
    
    results = []
    
    for i, instance in enumerate(instances, 1):
        iid = instance['instance_id']
        print(f"[{i}/{len(instances)}] {iid}...", end=" ", flush=True)
        
        result = await solve_with_opus(api_key, instance)
        
        if result['success']:
            expected = instance.get('patch', '')
            generated = result.get('patch', '')
            semantic = compute_semantic_match(generated, expected)
            
            print(f"✅ {semantic*100:.0f}%")
            
            results.append({
                "instance_id": iid,
                "success": True,
                "semantic_match": semantic,
                "input_tokens": result.get('input_tokens', 0),
                "output_tokens": result.get('output_tokens', 0)
            })
        else:
            print(f"❌ {result.get('error', 'unknown')[:50]}")
            results.append({
                "instance_id": iid,
                "success": False,
                "error": result.get('error'),
                "semantic_match": 0
            })
        
        await asyncio.sleep(1)  # Rate limit
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in results if r['success']]
    print(f"Successful: {len(successful)}/{len(results)}")
    
    if successful:
        avg_score = sum(r['semantic_match'] for r in successful) / len(successful)
        print(f"Avg semantic match: {avg_score*100:.1f}%")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "model": "claude-opus-4-20250514",
        "purpose": "rerun_billing_error_tasks",
        "results": results
    }
    
    output_file = f"opus_billing_rerun_{timestamp}.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Saved to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
