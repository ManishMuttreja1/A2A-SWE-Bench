#!/usr/bin/env python3
"""Test Anti-Contamination Features: Mutations, Fresh Issues, Adversarial"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from openai import AsyncOpenAI


class AntiContaminationTester:
    """Test anti-contamination features with real models"""
    
    def __init__(self, model: str = "gpt-5.2"):
        self.model = model
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.results = {
            "verified": [],
            "mutated": [],
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "model": model
        }
        
    async def load_swebench_instances(self, num_instances: int = 10) -> List[Dict]:
        """Load SWE-bench verified instances"""
        cache_path = Path("data/swebench_cache/swebench_verified.json")
        if not cache_path.exists():
            cache_path = Path("data/cache/swebench_verified.json")
        
        with open(cache_path) as f:
            all_instances = json.load(f)
        
        # Sort by patch size (smaller first)
        sorted_instances = sorted(
            all_instances,
            key=lambda x: len(x.get("patch", ""))
        )[:num_instances]
        
        return sorted_instances
    
    def apply_mutation(self, instance: Dict, level: str = "medium") -> Dict:
        """Apply retro-holdout mutation to an instance"""
        import random
        import re
        import hashlib
        
        mutated = instance.copy()
        mutation_hash = hashlib.md5(
            f"{instance['instance_id']}_{level}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:8]
        
        mutated["instance_id"] = f"{instance['instance_id']}_mutated_{mutation_hash}"
        mutated["is_mutated"] = True
        mutated["original_instance_id"] = instance["instance_id"]
        mutated["mutation_level"] = level
        
        # Mutation mappings
        var_mappings = {
            "data": "payload", "result": "output", "user": "account",
            "item": "element", "config": "settings", "request": "query",
            "response": "reply", "error": "issue", "cache": "buffer",
            "index": "position", "count": "total", "list": "array",
            "key": "identifier", "value": "content", "model": "schema"
        }
        
        func_mappings = {
            "get_": "fetch_", "set_": "assign_", "create_": "make_",
            "delete_": "remove_", "update_": "modify_", "process_": "handle_",
            "validate_": "check_", "parse_": "analyze_"
        }
        
        # Mutation probability based on level
        prob = {"light": 0.3, "medium": 0.5, "heavy": 0.8}[level]
        
        # Mutate problem statement
        problem = mutated.get("problem_statement", "")
        for old, new in var_mappings.items():
            if random.random() < prob:
                problem = re.sub(r'\b' + old + r'\b', new, problem, flags=re.IGNORECASE)
        mutated["problem_statement"] = problem
        
        # Mutate patch (for comparison scoring)
        patch = mutated.get("patch", "")
        for old, new in var_mappings.items():
            if random.random() < prob:
                patch = re.sub(r'\b' + old + r'\b', new, patch)
        for old, new in func_mappings.items():
            if random.random() < prob:
                patch = patch.replace(old, new)
        mutated["patch"] = patch
        
        return mutated
    
    async def solve_instance(self, instance: Dict) -> Dict:
        """Use LLM to generate a patch for an instance"""
        problem = instance.get("problem_statement", "")
        repo = instance.get("repo", "")
        
        prompt = f"""You are an expert software engineer. Fix this bug:

Repository: {repo}
Problem: {problem}

Generate a minimal unified diff patch to fix this issue.
Output ONLY the diff, no explanations.
Format: 
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -line,count +line,count @@
 context
-old line
+new line
 context"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert bug fixer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            generated_patch = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            
            return {
                "instance_id": instance["instance_id"],
                "generated_patch": generated_patch,
                "expected_patch": instance.get("patch", ""),
                "tokens": tokens,
                "success": True
            }
            
        except Exception as e:
            return {
                "instance_id": instance["instance_id"],
                "error": str(e),
                "success": False
            }
    
    def calculate_similarity(self, generated: str, expected: str) -> float:
        """Calculate semantic similarity between patches"""
        if not generated or not expected:
            return 0.0
        
        # Extract meaningful lines (not headers or context markers)
        def extract_changes(patch: str) -> set:
            changes = set()
            for line in patch.split('\n'):
                line = line.strip()
                if line.startswith('+') and not line.startswith('+++'):
                    changes.add(line[1:].strip())
                elif line.startswith('-') and not line.startswith('---'):
                    changes.add(line[1:].strip())
            return changes
        
        gen_changes = extract_changes(generated)
        exp_changes = extract_changes(expected)
        
        if not exp_changes:
            return 0.0
        
        intersection = gen_changes & exp_changes
        recall = len(intersection) / len(exp_changes) if exp_changes else 0
        
        return recall
    
    async def test_verified_vs_mutated(self, num_instances: int = 10):
        """Compare performance on verified vs mutated instances"""
        print(f"\n{'='*70}")
        print("ANTI-CONTAMINATION TEST: Verified vs Mutated")
        print(f"{'='*70}")
        print(f"Model: {self.model}")
        print(f"Instances: {num_instances}")
        print()
        
        # Load instances
        instances = await self.load_swebench_instances(num_instances)
        print(f"Loaded {len(instances)} instances")
        
        # Test on VERIFIED (original) instances
        print(f"\n--- Testing VERIFIED instances ---")
        for i, instance in enumerate(instances, 1):
            print(f"[{i}/{num_instances}] {instance['instance_id'][:40]}...", end=" ")
            result = await self.solve_instance(instance)
            
            if result["success"]:
                similarity = self.calculate_similarity(
                    result["generated_patch"],
                    result["expected_patch"]
                )
                result["similarity"] = similarity
                print(f"✓ {similarity*100:.0f}%")
            else:
                result["similarity"] = 0
                print(f"✗ Error")
            
            self.results["verified"].append(result)
        
        # Create MUTATED versions and test
        print(f"\n--- Testing MUTATED instances ---")
        for i, instance in enumerate(instances, 1):
            mutated = self.apply_mutation(instance, level="medium")
            print(f"[{i}/{num_instances}] {mutated['instance_id'][:40]}...", end=" ")
            
            result = await self.solve_instance(mutated)
            result["original_instance_id"] = instance["instance_id"]
            
            if result["success"]:
                # Compare to ORIGINAL expected patch
                similarity = self.calculate_similarity(
                    result["generated_patch"],
                    instance["patch"]  # Compare to original, not mutated
                )
                result["similarity"] = similarity
                print(f"✓ {similarity*100:.0f}%")
            else:
                result["similarity"] = 0
                print(f"✗ Error")
            
            self.results["mutated"].append(result)
        
        # Calculate contamination scores
        self._calculate_contamination()
        
        # Save results
        self._save_results()
        
        return self.results
    
    def _calculate_contamination(self):
        """Calculate contamination scores"""
        print(f"\n{'='*70}")
        print("CONTAMINATION ANALYSIS")
        print(f"{'='*70}")
        
        verified_scores = {r["instance_id"]: r["similarity"] for r in self.results["verified"]}
        
        contamination_scores = []
        for mutated_result in self.results["mutated"]:
            original_id = mutated_result.get("original_instance_id")
            if original_id and original_id in verified_scores:
                original_score = verified_scores[original_id]
                mutated_score = mutated_result["similarity"]
                
                # Contamination = performance drop
                if original_score > 0:
                    drop = (original_score - mutated_score) / original_score
                else:
                    drop = 0
                
                contamination_scores.append({
                    "instance": original_id,
                    "verified_score": original_score,
                    "mutated_score": mutated_score,
                    "contamination": max(0, drop)
                })
        
        # Summary
        verified_avg = sum(r["similarity"] for r in self.results["verified"]) / len(self.results["verified"])
        mutated_avg = sum(r["similarity"] for r in self.results["mutated"]) / len(self.results["mutated"])
        avg_contamination = sum(c["contamination"] for c in contamination_scores) / len(contamination_scores) if contamination_scores else 0
        
        print(f"\nVerified Avg Similarity:  {verified_avg*100:.1f}%")
        print(f"Mutated Avg Similarity:   {mutated_avg*100:.1f}%")
        print(f"Performance Drop:         {(verified_avg - mutated_avg)*100:.1f}%")
        print(f"Avg Contamination Score:  {avg_contamination*100:.1f}%")
        
        high_contamination = sum(1 for c in contamination_scores if c["contamination"] > 0.3)
        print(f"High Contamination (>30%): {high_contamination}/{len(contamination_scores)}")
        
        self.results["summary"] = {
            "verified_avg": verified_avg,
            "mutated_avg": mutated_avg,
            "performance_drop": verified_avg - mutated_avg,
            "avg_contamination": avg_contamination,
            "high_contamination_count": high_contamination,
            "per_instance": contamination_scores
        }
        
        # Per-instance breakdown
        print(f"\nPer-Instance Contamination:")
        print("-" * 70)
        for c in sorted(contamination_scores, key=lambda x: -x["contamination"])[:10]:
            print(f"  {c['instance'][:35]:<35} V:{c['verified_score']*100:>5.0f}% M:{c['mutated_score']*100:>5.0f}% C:{c['contamination']*100:>5.0f}%")
    
    def _save_results(self):
        """Save results to file"""
        filename = f"anti_contamination_results_{self.results['timestamp']}.json"
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {filename}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test anti-contamination features")
    parser.add_argument("--tasks", type=int, default=10, help="Number of tasks")
    parser.add_argument("--model", type=str, default="gpt-5.2", help="Model to use")
    args = parser.parse_args()
    
    tester = AntiContaminationTester(model=args.model)
    await tester.test_verified_vs_mutated(num_instances=args.tasks)


if __name__ == "__main__":
    asyncio.run(main())
