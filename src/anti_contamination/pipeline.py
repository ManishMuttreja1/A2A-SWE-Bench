"""Anti-Contamination Pipeline - Orchestrates mutation and slice management"""

import logging
import random
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from .config import (
    AntiContaminationConfig,
    EvaluationSlice,
    RunMode,
    TaskMetadata,
)
from ..mutation.retro_holdout import RetroHoldoutGenerator

logger = logging.getLogger(__name__)


class AntiContaminationPipeline:
    """
    Orchestrates anti-contamination strategies:
    - Retro-holdout mutations
    - Fresh issue integration
    - Slice-based evaluation
    - Heuristic control
    """
    
    def __init__(self, config: Optional[AntiContaminationConfig] = None):
        self.config = config or AntiContaminationConfig()
        
        # Initialize retro-holdout generator
        self.retro_holdout = RetroHoldoutGenerator(
            mutation_seed=self.config.mutation_seed
        )
        
        # Track processed instances
        self.processed_instances: Dict[str, TaskMetadata] = {}
        
        # Statistics
        self.stats = {
            "verified_count": 0,
            "mutated_count": 0,
            "fresh_count": 0,
            "post_cutoff_count": 0,
            "adversarial_count": 0,
            "heuristic_runs": 0,
            "llm_only_runs": 0,
        }
    
    async def prepare_task(
        self,
        instance: Dict[str, Any],
        repo_path: Path,
        evaluation_slice: Optional[EvaluationSlice] = None,
        force_heuristics: Optional[bool] = None,
    ) -> tuple[Dict[str, Any], TaskMetadata]:
        """
        Prepare a task with anti-contamination measures.
        
        Args:
            instance: Original SWE-bench instance
            repo_path: Path to repository
            evaluation_slice: Override slice selection
            force_heuristics: Override heuristic setting
            
        Returns:
            Tuple of (prepared_instance, task_metadata)
        """
        instance_id = instance["instance_id"]
        
        # Determine slice
        slice_type = evaluation_slice or self._select_slice(instance)
        
        # Determine heuristics setting
        heuristics_allowed = force_heuristics if force_heuristics is not None else self.config.allow_heuristics
        
        # Create base metadata
        metadata = TaskMetadata(
            evaluation_slice=slice_type,
            run_mode=RunMode.HEURISTIC_ASSISTED if heuristics_allowed else RunMode.LLM_ONLY,
            heuristics_allowed=heuristics_allowed,
            base_commit=instance.get("base_commit"),
            model_training_cutoff=self.config.model_training_cutoff,
        )
        
        # Apply slice-specific processing
        prepared_instance = instance.copy()
        
        if slice_type == EvaluationSlice.MUTATED and self.config.enable_mutations:
            prepared_instance, metadata = await self._apply_mutations(
                instance, repo_path, metadata
            )
            self.stats["mutated_count"] += 1
            
        elif slice_type == EvaluationSlice.FRESH:
            metadata.harvested_at = instance.get("harvested_at") or datetime.utcnow()
            self.stats["fresh_count"] += 1
            
        elif slice_type == EvaluationSlice.POST_CUTOFF:
            self.stats["post_cutoff_count"] += 1
            
        elif slice_type == EvaluationSlice.ADVERSARIAL:
            # Add adversarial test hooks (placeholder)
            prepared_instance["adversarial_enabled"] = True
            self.stats["adversarial_count"] += 1
            
        else:  # VERIFIED
            self.stats["verified_count"] += 1
        
        # Track mode
        if heuristics_allowed:
            self.stats["heuristic_runs"] += 1
        else:
            self.stats["llm_only_runs"] += 1
        
        # Store metadata
        self.processed_instances[instance_id] = metadata
        
        logger.info(
            f"Prepared task {instance_id}: slice={slice_type.value}, "
            f"mode={metadata.run_mode.value}, mutation={metadata.mutation_applied}"
        )
        
        return prepared_instance, metadata
    
    def _select_slice(self, instance: Dict[str, Any]) -> EvaluationSlice:
        """Select evaluation slice for an instance"""
        # Check if instance is fresh (harvested)
        if instance.get("is_fresh") or instance.get("source") == "harvested":
            if EvaluationSlice.FRESH in self.config.enabled_slices:
                return EvaluationSlice.FRESH
        
        # Check if instance is post-cutoff
        if self.config.model_training_cutoff and instance.get("created_at"):
            created = datetime.fromisoformat(instance["created_at"].replace("Z", "+00:00"))
            if created > self.config.model_training_cutoff:
                if EvaluationSlice.POST_CUTOFF in self.config.enabled_slices:
                    return EvaluationSlice.POST_CUTOFF
        
        # Randomly assign to mutated slice if enabled
        if (
            self.config.enable_mutations
            and EvaluationSlice.MUTATED in self.config.enabled_slices
            and random.random() < 0.5  # 50% chance for mutation
        ):
            return EvaluationSlice.MUTATED
        
        # Default to verified
        return EvaluationSlice.VERIFIED
    
    async def _apply_mutations(
        self,
        instance: Dict[str, Any],
        repo_path: Path,
        metadata: TaskMetadata,
    ) -> tuple[Dict[str, Any], TaskMetadata]:
        """Apply retro-holdout mutations to an instance"""
        try:
            mutated_instance = await self.retro_holdout.generate_retro_holdout(
                instance=instance,
                repo_path=repo_path,
                level=self.config.mutation_level,
            )
            
            # Update metadata
            metadata.mutation_applied = True
            metadata.mutation_seed = self.config.mutation_seed
            metadata.mutation_level = self.config.mutation_level
            
            # Verify semantic equivalence if configured
            if self.config.verify_semantic_equivalence:
                test_commands = instance.get("test_commands", [])
                if test_commands:
                    is_equivalent = await self.retro_holdout.verify_semantic_equivalence(
                        original_path=repo_path,
                        mutated_path=repo_path,  # In-place mutation
                        test_commands=test_commands,
                    )
                    if not is_equivalent:
                        logger.warning(f"Mutation broke semantic equivalence for {instance['instance_id']}")
                        # Revert to original
                        return instance, metadata
            
            return mutated_instance, metadata
            
        except Exception as e:
            logger.error(f"Mutation failed for {instance['instance_id']}: {e}")
            return instance, metadata
    
    def get_task_metadata(self, instance_id: str) -> Optional[TaskMetadata]:
        """Get metadata for a processed task"""
        return self.processed_instances.get(instance_id)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            **self.stats,
            "config": self.config.to_dict(),
            "retro_holdout_stats": self.retro_holdout.get_statistics(),
            "total_processed": len(self.processed_instances),
        }
    
    def calculate_contamination_score(
        self,
        verified_results: Dict[str, float],
        mutated_results: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Calculate contamination score by comparing verified vs mutated performance.
        
        Large performance drops on mutated instances suggest memorization.
        """
        contamination_scores = {}
        
        for instance_id in verified_results:
            if instance_id in mutated_results:
                original = verified_results[instance_id]
                mutated = mutated_results[instance_id]
                
                score = self.retro_holdout.calculate_contamination_score(
                    original_performance=original,
                    mutated_performance=mutated,
                )
                contamination_scores[instance_id] = score
        
        # Aggregate
        if contamination_scores:
            avg_contamination = sum(contamination_scores.values()) / len(contamination_scores)
        else:
            avg_contamination = 0.0
        
        return {
            "per_instance": contamination_scores,
            "average_contamination": avg_contamination,
            "high_contamination_count": sum(1 for s in contamination_scores.values() if s > 0.5),
            "instances_compared": len(contamination_scores),
        }
    
    def filter_results_by_mode(
        self,
        results: List[Dict[str, Any]],
        mode: RunMode = RunMode.LLM_ONLY,
    ) -> List[Dict[str, Any]]:
        """Filter results to only include specific run mode"""
        return [
            r for r in results
            if r.get("metadata", {}).get("run_mode") == mode.value
        ]
    
    def filter_results_by_slice(
        self,
        results: List[Dict[str, Any]],
        slice_type: EvaluationSlice,
    ) -> List[Dict[str, Any]]:
        """Filter results to only include specific evaluation slice"""
        return [
            r for r in results
            if r.get("metadata", {}).get("evaluation_slice") == slice_type.value
        ]
