#!/usr/bin/env python3
"""
Rerun failed Claude tests with retry logic.

Usage:
    export ANTHROPIC_API_KEY='your-key'
    python rerun_failed_claude.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import httpx

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Failed instances from previous runs
OPUS_FAILURES = [
    'django__django-10097', 'django__django-12273', 'scikit-learn__scikit-learn-13779',
    'sympy__sympy-15017', 'pytest-dev__pytest-7205', 'sphinx-doc__sphinx-8721',
    'django__django-11451', 'scikit-learn__scikit-learn-11578', 'django__django-11179',
    'django__django-12663'
]

HAIKU_FAILURES = [
    'scikit-learn__scikit-learn-12585', 'django__django-10999'
]


class ClaudeRetryAgent:
    """Claude agent with retry logic."""
    
    def __init__(self, model: str, api_key: str):
        self.api_key = api_key
        self.model = self._get_full_model_name(model)
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        self.http_client = httpx.AsyncClient(timeout=120.0)
    
    def _get_full_model_name(self, short_name: str) -> str:
        mapping = {
            "haiku": "claude-3-haiku-20240307",
            "sonnet": "claude-sonnet-4-5-20250929",
            "opus": "claude-opus-4-1"
        }
        return mapping.get(short_name.lower(), short_name)
    
    async def generate_patch(self, instance: dict, max_retries: int = 3) -> dict:
        """Generate a patch with retry logic."""
        instance_id = instance.get("instance_id", "unknown")
        problem = instance.get("problem_statement", "")
        
        prompt = f"""You are an expert software engineer. Fix this bug:

Instance: {instance_id}
Repository: {instance.get('repo', '')}

Problem Statement:
{problem[:3000]}

Generate a minimal diff patch to fix this issue. Output ONLY the patch in unified diff format.
"""
        
        for attempt in range(max_retries):
            try:
                payload = {
                    "model": self.model,
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}]
                }
                
                response = await self.http_client.post(
                    self.base_url, 
                    headers=self.headers, 
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    patch = data["content"][0]["text"]
                    return {
                        "success": True,
                        "instance_id": instance_id,
                        "generated_patch": patch,
                        "model": self.model,
                        "attempts": attempt + 1
                    }
                elif response.status_code == 529:  # Overloaded
                    print(f"    ⏳ API overloaded, waiting 30s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(30)
                elif response.status_code == 400:  # Invalid request - try shorter prompt
                    print(f"    ⚠️ Request too large, trying shorter prompt (attempt {attempt+1}/{max_retries})")
                    prompt = prompt[:2000]  # Truncate prompt
                    await asyncio.sleep(2)
                else:
                    error = response.text[:200]
                    print(f"    ❌ API error {response.status_code}: {error}")
                    await asyncio.sleep(5)
                    
            except Exception as e:
                print(f"    ❌ Exception: {e}")
                await asyncio.sleep(5)
        
        return {
            "success": False,
            "instance_id": instance_id,
            "error": f"Failed after {max_retries} attempts",
            "model": self.model
        }


async def load_instances_from_cache() -> dict:
    """Load SWE-bench instances from cache."""
    cache_file = Path("data/swebench_cache/swebench_verified.json")
    if cache_file.exists():
        with open(cache_file) as f:
            instances = json.load(f)
        return {i["instance_id"]: i for i in instances}
    return {}


async def rerun_failed_tests(model: str, failed_ids: list) -> list:
    """Rerun failed tests for a specific model."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set!")
        print("   Run: export ANTHROPIC_API_KEY='your-key'")
        return []
    
    print(f"\n{'='*60}")
    print(f"Rerunning {len(failed_ids)} failed {model.upper()} tests")
    print(f"{'='*60}\n")
    
    # Load instances
    all_instances = await load_instances_from_cache()
    if not all_instances:
        print("❌ Could not load SWE-bench instances from cache")
        return []
    
    agent = ClaudeRetryAgent(model, api_key)
    results = []
    
    for i, instance_id in enumerate(failed_ids):
        print(f"[{i+1}/{len(failed_ids)}] {instance_id}...")
        
        instance = all_instances.get(instance_id)
        if not instance:
            print(f"    ⚠️ Instance not found in cache, skipping")
            continue
        
        result = await agent.generate_patch(instance, max_retries=3)
        
        if result["success"]:
            print(f"    ✅ Success (attempts: {result['attempts']})")
        else:
            print(f"    ❌ Failed: {result.get('error', 'unknown')}")
        
        results.append(result)
        await asyncio.sleep(2)  # Rate limiting
    
    return results


async def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           RERUN FAILED CLAUDE TESTS                              ║
╚══════════════════════════════════════════════════════════════════╝
""")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set!")
        print("\nTo run this script:")
        print("  export ANTHROPIC_API_KEY='your-anthropic-api-key'")
        print("  python rerun_failed_claude.py")
        return
    
    all_results = {}
    
    # Rerun Opus failures
    if OPUS_FAILURES:
        opus_results = await rerun_failed_tests("opus", OPUS_FAILURES)
        all_results["opus"] = opus_results
        
        successes = sum(1 for r in opus_results if r.get("success"))
        print(f"\nOpus: {successes}/{len(OPUS_FAILURES)} recovered")
    
    # Rerun Haiku failures  
    if HAIKU_FAILURES:
        haiku_results = await rerun_failed_tests("haiku", HAIKU_FAILURES)
        all_results["haiku"] = haiku_results
        
        successes = sum(1 for r in haiku_results if r.get("success"))
        print(f"\nHaiku: {successes}/{len(HAIKU_FAILURES)} recovered")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"claude_rerun_results_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for model, results in all_results.items():
        successes = sum(1 for r in results if r.get("success"))
        total = len(results)
        print(f"  {model.upper()}: {successes}/{total} recovered")


if __name__ == "__main__":
    asyncio.run(main())
