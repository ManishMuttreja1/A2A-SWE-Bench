"""Anti-Contamination Configuration and Types"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class EvaluationSlice(str, Enum):
    """Evaluation slice types for contamination resistance"""
    VERIFIED = "verified"       # Standard SWE-bench Verified instances
    MUTATED = "mutated"         # Retro-holdout transformed versions
    FRESH = "fresh"             # Freshly harvested issues (<24h)
    POST_CUTOFF = "post_cutoff" # Commits after model training cutoff
    ADVERSARIAL = "adversarial" # Instances with fuzz/mutation testing


class RunMode(str, Enum):
    """Run mode for tracking heuristic usage"""
    LLM_ONLY = "llm_only"                   # Pure LLM solving, no heuristics
    HEURISTIC_ASSISTED = "heuristic_assisted"  # May use hardcoded fallbacks


@dataclass
class TaskMetadata:
    """Metadata attached to each task for provenance tracking"""
    evaluation_slice: EvaluationSlice = EvaluationSlice.VERIFIED
    run_mode: RunMode = RunMode.LLM_ONLY
    mutation_applied: bool = False
    mutation_seed: Optional[int] = None
    mutation_level: Optional[str] = None  # light, medium, heavy
    heuristics_allowed: bool = False
    base_commit: Optional[str] = None
    harvested_at: Optional[datetime] = None
    model_training_cutoff: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "evaluation_slice": self.evaluation_slice.value,
            "run_mode": self.run_mode.value,
            "mutation_applied": self.mutation_applied,
            "mutation_seed": self.mutation_seed,
            "mutation_level": self.mutation_level,
            "heuristics_allowed": self.heuristics_allowed,
            "base_commit": self.base_commit,
            "harvested_at": self.harvested_at.isoformat() if self.harvested_at else None,
            "model_training_cutoff": self.model_training_cutoff.isoformat() if self.model_training_cutoff else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskMetadata":
        """Create from dictionary"""
        return cls(
            evaluation_slice=EvaluationSlice(data.get("evaluation_slice", "verified")),
            run_mode=RunMode(data.get("run_mode", "llm_only")),
            mutation_applied=data.get("mutation_applied", False),
            mutation_seed=data.get("mutation_seed"),
            mutation_level=data.get("mutation_level"),
            heuristics_allowed=data.get("heuristics_allowed", False),
            base_commit=data.get("base_commit"),
            harvested_at=datetime.fromisoformat(data["harvested_at"]) if data.get("harvested_at") else None,
            model_training_cutoff=datetime.fromisoformat(data["model_training_cutoff"]) if data.get("model_training_cutoff") else None,
        )


@dataclass
class AntiContaminationConfig:
    """Configuration for anti-contamination features"""
    
    # Enable/disable features
    enable_mutations: bool = True
    enable_fresh_harvesting: bool = True
    enable_post_cutoff_filter: bool = True
    enable_adversarial_tests: bool = False  # Off by default (slow)
    
    # Mutation settings
    mutation_level: str = "medium"  # light, medium, heavy
    mutation_seed: Optional[int] = None  # For reproducibility
    verify_semantic_equivalence: bool = True
    
    # Fresh harvesting settings
    max_issue_age_hours: int = 24
    min_repo_stars: int = 100
    
    # Model cutoff date (for post_cutoff slice)
    model_training_cutoff: Optional[datetime] = None
    
    # Heuristic control
    allow_heuristics: bool = False  # Default: pure LLM only for reporting
    
    # Slices to run
    enabled_slices: list = field(default_factory=lambda: [
        EvaluationSlice.VERIFIED,
        EvaluationSlice.MUTATED,
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "enable_mutations": self.enable_mutations,
            "enable_fresh_harvesting": self.enable_fresh_harvesting,
            "enable_post_cutoff_filter": self.enable_post_cutoff_filter,
            "enable_adversarial_tests": self.enable_adversarial_tests,
            "mutation_level": self.mutation_level,
            "mutation_seed": self.mutation_seed,
            "verify_semantic_equivalence": self.verify_semantic_equivalence,
            "max_issue_age_hours": self.max_issue_age_hours,
            "min_repo_stars": self.min_repo_stars,
            "model_training_cutoff": self.model_training_cutoff.isoformat() if self.model_training_cutoff else None,
            "allow_heuristics": self.allow_heuristics,
            "enabled_slices": [s.value for s in self.enabled_slices],
        }
