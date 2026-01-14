#!/usr/bin/env python3
"""
Full A2A Test with GPT-4o Purple Agent

Tests the complete A2A framework:
1. Green Agent loads and serves SWE-bench tasks
2. Purple Agent (GPT-4o) solves them
3. Evaluates with semantic patch comparison
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import re
import difflib

sys.path.insert(0, str(Path(__file__).parent))

from openai import AsyncOpenAI


def semantic_patch_comparison(generated: str, expected: str) -> Dict[str, Any]:
    """
    Semantically compare patches - looks for the same modifications
    regardless of exact line numbers or context
    """
    
    def extract_modifications(patch: str) -> List[Dict]:
        """Extract the actual code changes from a patch"""
        modifications = []
        current_file = None
        additions = []
        deletions = []
        
        for line in patch.split('\n'):
            # Track file
            if line.startswith('--- a/') or line.startswith('--- '):
                if current_file and (additions or deletions):
                    modifications.append({
                        'file': current_file,
                        'additions': additions.copy(),
                        'deletions': deletions.copy()
                    })
                    additions = []
                    deletions = []
                # Extract file path
                parts = line.split()
                if len(parts) >= 2:
                    current_file = parts[1].replace('a/', '').replace('b/', '')
            elif line.startswith('+++ b/') or line.startswith('+++ '):
                parts = line.split()
                if len(parts) >= 2:
                    current_file = parts[1].replace('a/', '').replace('b/', '')
            elif line.startswith('+') and not line.startswith('+++'):
                # Addition line
                additions.append(line[1:].strip())
            elif line.startswith('-') and not line.startswith('---'):
                # Deletion line
                deletions.append(line[1:].strip())
        
        # Don't forget last file
        if current_file and (additions or deletions):
            modifications.append({
                'file': current_file,
                'additions': additions.copy(),
                'deletions': deletions.copy()
            })
        
        return modifications
    
    gen_mods = extract_modifications(generated)
    exp_mods = extract_modifications(expected)
    
    # Compare files modified
    gen_files = set(m['file'] for m in gen_mods)
    exp_files = set(m['file'] for m in exp_mods)
    
    files_correct = len(gen_files & exp_files) / max(len(exp_files), 1)
    
    # Compare actual code changes
    gen_additions = set()
    gen_deletions = set()
    exp_additions = set()
    exp_deletions = set()
    
    for m in gen_mods:
        gen_additions.update(m['additions'])
        gen_deletions.update(m['deletions'])
    
    for m in exp_mods:
        exp_additions.update(m['additions'])
        exp_deletions.update(m['deletions'])
    
    # Calculate overlap
    add_overlap = len(gen_additions & exp_additions)
    del_overlap = len(gen_deletions & exp_deletions)
    
    total_exp = len(exp_additions) + len(exp_deletions)
    total_gen = len(gen_additions) + len(gen_deletions)
    total_overlap = add_overlap + del_overlap
    
    if total_exp > 0:
        recall = total_overlap / total_exp
    else:
        recall = 0.0
    
    if total_gen > 0:
        precision = total_overlap / total_gen
    else:
        precision = 0.0
    
    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0
    
    # Semantic similarity using fuzzy matching
    all_gen = list(gen_additions) + list(gen_deletions)
    all_exp = list(exp_additions) + list(exp_deletions)
    
    fuzzy_matches = 0
    for exp_line in all_exp:
        if exp_line in all_gen:
            fuzzy_matches += 1
        else:
            # Try fuzzy match
            matches = difflib.get_close_matches(exp_line, all_gen, n=1, cutoff=0.8)
            if matches:
                fuzzy_matches += 0.8  # Partial credit for fuzzy match
    
    fuzzy_recall = fuzzy_matches / max(len(all_exp), 1)
    
    return {
        "files_correct": files_correct,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "fuzzy_recall": fuzzy_recall,
        "generated_files": list(gen_files),
        "expected_files": list(exp_files),
        "gen_additions": len(gen_additions),
        "exp_additions": len(exp_additions),
        "gen_deletions": len(gen_deletions),
        "exp_deletions": len(exp_deletions)
    }


class GPT4oPurpleAgent:
    """GPT-4o Purple Agent for A2A SWE-bench"""
    
    def __init__(self, model: str = "gpt-4o"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required")
        
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.stats = {"tokens": 0, "cost": 0.0, "tasks": 0}
    
    async def solve(self, instance: Dict) -> Dict:
        """Solve a SWE-bench task"""
        
        problem = instance.get("problem_statement", "")
        repo = instance.get("repo", "")
        hints = instance.get("hints_text", "")
        test_patch = instance.get("test_patch", "")
        
        prompt = f"""You are an expert software engineer fixing a bug in {repo}.

PROBLEM:
{problem}

{'HINTS:' + hints[:1500] if hints else ''}

{'TEST CHANGES (what the tests expect):' + test_patch[:2000] if test_patch else ''}

Generate a minimal patch in unified diff format to fix this bug.
Start your patch with the correct diff headers (--- a/file and +++ b/file).
Focus only on the essential changes needed.

PATCH:
```diff
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert bug fixer. Generate minimal, focused patches."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            
            # Track stats
            if response.usage:
                self.stats["tokens"] += response.usage.total_tokens
                self.stats["cost"] += response.usage.prompt_tokens * 0.005 / 1000
                self.stats["cost"] += response.usage.completion_tokens * 0.015 / 1000
            self.stats["tasks"] += 1
            
            # Extract patch
            patch = self._extract_patch(content)
            
            return {"success": True, "patch": patch, "raw": content}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _extract_patch(self, content: str) -> str:
        """Extract patch from response"""
        # Look for diff blocks
        match = re.search(r'```diff\n(.*?)```', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Look for diff-like content
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


async def run_a2a_test(num_tasks: int = 5, model: str = "gpt-4o"):
    """Run the A2A test"""
    
    print("""
╔══════════════════════════════════════════════════════════════════╗
║       SWE-bench A2A Framework Test with GPT-4o Purple Agent      ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Load dataset
    data_path = Path(__file__).parent / "data" / "swebench_cache" / "swebench_verified.json"
    with open(data_path) as f:
        instances = json.load(f)
    
    # Sort by patch size (easier tasks first)
    instances = sorted(instances, key=lambda x: len(x.get('patch', '')))[:num_tasks]
    
    print(f"📚 Testing on {len(instances)} SWE-bench tasks")
    print(f"🤖 Purple Agent Model: {model}")
    print()
    
    agent = GPT4oPurpleAgent(model=model)
    results = []
    
    for i, instance in enumerate(instances, 1):
        iid = instance['instance_id']
        repo = instance['repo']
        
        print(f"{'='*70}")
        print(f"[{i}/{num_tasks}] {iid}")
        print(f"    Repo: {repo}")
        
        start = datetime.now()
        result = await agent.solve(instance)
        elapsed = (datetime.now() - start).total_seconds()
        
        if result['success']:
            expected = instance.get('patch', '')
            generated = result.get('patch', '')
            
            # Semantic comparison
            comparison = semantic_patch_comparison(generated, expected)
            
            status = "✅" if comparison['files_correct'] > 0 else "⚠️"
            score_status = "✅" if comparison['fuzzy_recall'] > 0.5 else "⚠️" if comparison['fuzzy_recall'] > 0 else "❌"
            
            print(f"    {status} Generated patch in {elapsed:.1f}s")
            print(f"    {score_status} Semantic Match: {comparison['fuzzy_recall']:.0%}")
            print(f"    Files: {comparison['expected_files']} → {comparison['generated_files']}")
            
            results.append({
                "instance_id": iid,
                "repo": repo,
                "success": True,
                "comparison": comparison,
                "elapsed": elapsed,
                "patch": generated[:500]
            })
        else:
            print(f"    ❌ Failed: {result.get('error', 'Unknown')}")
            results.append({
                "instance_id": iid,
                "repo": repo,
                "success": False,
                "error": result.get('error')
            })
        
        await asyncio.sleep(0.5)  # Rate limit
    
    # Summary
    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)
    
    successful = [r for r in results if r['success']]
    
    if successful:
        avg_fuzzy = sum(r['comparison']['fuzzy_recall'] for r in successful) / len(successful)
        files_correct = sum(1 for r in successful if r['comparison']['files_correct'] == 1.0)
        high_match = sum(1 for r in successful if r['comparison']['fuzzy_recall'] > 0.5)
        
        print(f"\nTotal: {len(results)}")
        print(f"Successful: {len(successful)}")
        print(f"Correct Files: {files_correct}/{len(successful)}")
        print(f"High Match (>50%): {high_match}/{len(successful)}")
        print(f"Average Semantic Match: {avg_fuzzy:.1%}")
    
    print(f"\n💰 Cost: ${agent.stats['cost']:.4f}")
    print(f"📊 Tokens: {agent.stats['tokens']}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).parent / f"a2a_gpt4o_results_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "model": "gpt-4o",
            "num_tasks": len(results),
            "stats": agent.stats,
            "results": results
        }, f, indent=2)
    
    print(f"\n💾 Saved: {output_file}")
    
    # Results table
    print("\n📋 Results Table:")
    print("-"*80)
    print(f"{'Instance':<45} {'Match':<10} {'Files':<10} {'Time':<10}")
    print("-"*80)
    
    for r in results:
        iid = r['instance_id'][:43]
        if r['success']:
            match = f"{r['comparison']['fuzzy_recall']:.0%}"
            files = "✅" if r['comparison']['files_correct'] == 1.0 else "⚠️"
            time = f"{r['elapsed']:.1f}s"
        else:
            match = "FAIL"
            files = "❌"
            time = "-"
        print(f"{iid:<45} {match:<10} {files:<10} {time:<10}")
    
    print("-"*80)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=5, help="Number of tasks")
    parser.add_argument("--model", type=str, default="gpt-4o", help="OpenAI model name (e.g., gpt-4o, gpt-4.1, gpt-5.1)")
    args = parser.parse_args()
    
    asyncio.run(run_a2a_test(args.tasks, args.model))
