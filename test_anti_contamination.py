#!/usr/bin/env python3
"""Test Anti-Contamination Features: Mutations, Fresh Issues, Adversarial"""

import asyncio
import json
import os
import sys
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from openai import AsyncOpenAI

from src.scoring.semantic_patch import semantic_match_score
from src.anti_contamination import (
    AntiContaminationPipeline,
    AntiContaminationConfig,
    EvaluationSlice,
)
from git import Repo


class AntiContaminationTester:
    """Test anti-contamination features with real models"""
    
    def __init__(
        self,
        model: str = "gpt-5.2",
        mutation_level: str = "medium",
        mutation_seed: Optional[int] = None,
    ):
        self.model = model
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.results = {
            "verified": [],
            "mutated": [],
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "model": model,
            "metric": "semantic_patch_f1",
            "reproduction_gate_enforced": False,
            "heuristics_allowed": False,
        }
        self.repo_cache_dir = Path("data/repo_cache")
        self.repo_cache_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline = AntiContaminationPipeline(
            config=AntiContaminationConfig(
                enable_mutations=True,
                mutation_level=mutation_level,
                mutation_seed=mutation_seed,
                verify_semantic_equivalence=True,
                allow_heuristics=False,
            )
        )
        
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
    
    def _repo_cache_path(self, repo_name: str) -> Path:
        safe_name = repo_name.replace("/", "__")
        return self.repo_cache_dir / f"{safe_name}.git"

    def _ensure_repo_cache(self, repo_url: str, cache_path: Path) -> None:
        if cache_path.exists():
            return
        Repo.clone_from(repo_url, cache_path, bare=True)

    def _checkout_repo(self, instance: Dict) -> Path:
        repo_name = instance.get("repo", "")
        repo_url = instance.get("repo_url") or f"https://github.com/{repo_name}.git"
        cache_path = self._repo_cache_path(repo_name)
        self._ensure_repo_cache(repo_url, cache_path)
        workdir = Path(tempfile.mkdtemp(prefix="swebench_ac_"))
        repo = Repo.clone_from(cache_path.as_posix(), workdir)
        base_commit = instance.get("base_commit")
        if base_commit:
            repo.git.checkout(base_commit)
        return workdir

    def _cleanup_repo(self, repo_path: Path) -> None:
        shutil.rmtree(repo_path, ignore_errors=True)
    
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
        return semantic_match_score(generated, expected)
    
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
            repo_path = None
            prepared_instance = instance
            metadata = None
            try:
                repo_path = self._checkout_repo(instance)
                prepared_instance, metadata = await self.pipeline.prepare_task(
                    instance=instance,
                    repo_path=repo_path,
                    evaluation_slice=EvaluationSlice.VERIFIED,
                    force_heuristics=False,
                )
            except Exception as e:
                print(f"✗ Repo prep failed: {e}")
                result = {
                    "instance_id": instance["instance_id"],
                    "success": False,
                    "error": f"repo_prep_failed: {e}",
                    "similarity": 0,
                }
                self.results["verified"].append(result)
                if repo_path:
                    self._cleanup_repo(repo_path)
                continue

            result = await self.solve_instance(prepared_instance)
            
            if result["success"]:
                similarity = self.calculate_similarity(
                    result["generated_patch"],
                    result["expected_patch"]
                )
                result["similarity"] = similarity
                if metadata:
                    result["metadata"] = metadata.to_dict()
                print(f"✓ {similarity*100:.0f}%")
            else:
                result["similarity"] = 0
                print(f"✗ Error")
            
            self.results["verified"].append(result)
            if repo_path:
                self._cleanup_repo(repo_path)
        
        # Create MUTATED versions and test
        print(f"\n--- Testing MUTATED instances ---")
        for i, instance in enumerate(instances, 1):
            repo_path = None
            prepared_instance = instance
            metadata = None
            try:
                repo_path = self._checkout_repo(instance)
                prepared_instance, metadata = await self.pipeline.prepare_task(
                    instance=instance,
                    repo_path=repo_path,
                    evaluation_slice=EvaluationSlice.MUTATED,
                    force_heuristics=False,
                )
            except Exception as e:
                print(f"✗ Repo prep failed: {e}")
                result = {
                    "instance_id": instance["instance_id"],
                    "success": False,
                    "error": f"repo_prep_failed: {e}",
                    "similarity": 0,
                }
                self.results["mutated"].append(result)
                if repo_path:
                    self._cleanup_repo(repo_path)
                continue

            print(f"[{i}/{num_instances}] {prepared_instance['instance_id'][:40]}...", end=" ")
            
            result = await self.solve_instance(prepared_instance)
            result["original_instance_id"] = prepared_instance.get("original_instance_id", instance["instance_id"])
            
            if result["success"]:
                # Compare to MUTATED expected patch
                similarity = self.calculate_similarity(
                    result["generated_patch"],
                    result["expected_patch"]
                )
                result["similarity"] = similarity
                if metadata:
                    result["metadata"] = metadata.to_dict()
                print(f"✓ {similarity*100:.0f}%")
            else:
                result["similarity"] = 0
                print(f"✗ Error")
            
            self.results["mutated"].append(result)
            if repo_path:
                self._cleanup_repo(repo_path)
        
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
