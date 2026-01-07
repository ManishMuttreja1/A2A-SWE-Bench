"""Interactive Dialogue Manager for Requirements Engineering"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import re

from ..a2a.protocol import Message, MessageType, A2AProtocol
from .ambiguity_layer import AmbiguityLayer

logger = logging.getLogger(__name__)


class DialogueState(str, Enum):
    INITIAL = "initial"
    CLARIFYING = "clarifying"
    INFORMATION_GATHERING = "information_gathering"
    CONFIRMING = "confirming"
    COMPLETE = "complete"


class InformationGainMetrics:
    """Tracks information gain efficiency during dialogue"""
    
    def __init__(self):
        self.total_questions = 0
        self.relevant_questions = 0
        self.information_revealed = 0.0
        self.information_total = 1.0
        self.redundant_questions = 0
        self.question_quality_scores: List[float] = []
    
    def add_question(self, question: str, is_relevant: bool, quality_score: float):
        """Record a question and its metrics"""
        self.total_questions += 1
        if is_relevant:
            self.relevant_questions += 1
        else:
            self.redundant_questions += 1
        self.question_quality_scores.append(quality_score)
    
    def reveal_information(self, amount: float):
        """Record information revelation"""
        self.information_revealed = min(
            self.information_revealed + amount,
            self.information_total
        )
    
    def get_efficiency_score(self) -> float:
        """Calculate information gain efficiency"""
        if self.total_questions == 0:
            return 0.0
        
        relevance_rate = self.relevant_questions / self.total_questions
        information_rate = self.information_revealed / max(self.total_questions, 1)
        avg_quality = sum(self.question_quality_scores) / len(self.question_quality_scores) if self.question_quality_scores else 0
        
        # Weighted combination
        efficiency = (
            relevance_rate * 0.4 +
            information_rate * 0.4 +
            avg_quality * 0.2
        )
        
        # Penalize redundant questions
        redundancy_penalty = self.redundant_questions * 0.05
        
        return max(0.0, min(1.0, efficiency - redundancy_penalty))


class DialogueManager:
    """
    Manages interactive dialogue between Green Agent and Purple Agent.
    Implements progressive information release based on question quality.
    """
    
    def __init__(
        self,
        ambiguity_layer: Optional[AmbiguityLayer] = None,
        strict_mode: bool = False
    ):
        """
        Args:
            ambiguity_layer: Ambiguity injection layer
            strict_mode: If True, requires specific questions for information
        """
        self.ambiguity_layer = ambiguity_layer or AmbiguityLayer()
        self.strict_mode = strict_mode
        
        # Track dialogues per task
        self.task_dialogues: Dict[str, Dict[str, Any]] = {}
        
        # Information templates
        self.information_chunks = {
            "error_type": {
                "keywords": ["error", "exception", "traceback", "type"],
                "info": "The specific error type is: {error_type}",
                "value": 0.2
            },
            "location": {
                "keywords": ["where", "file", "line", "location", "module"],
                "info": "The issue occurs in: {file_location}",
                "value": 0.2
            },
            "reproduction": {
                "keywords": ["reproduce", "steps", "how", "trigger"],
                "info": "To reproduce: {reproduction_steps}",
                "value": 0.15
            },
            "environment": {
                "keywords": ["version", "environment", "system", "dependencies"],
                "info": "Environment details: {environment_info}",
                "value": 0.1
            },
            "expected": {
                "keywords": ["expected", "should", "correct", "behavior"],
                "info": "Expected behavior: {expected_behavior}",
                "value": 0.15
            },
            "actual": {
                "keywords": ["actual", "current", "wrong", "incorrect"],
                "info": "Actual behavior: {actual_behavior}",
                "value": 0.15
            },
            "context": {
                "keywords": ["context", "background", "related", "history"],
                "info": "Additional context: {context_info}",
                "value": 0.05
            }
        }
    
    async def initiate_dialogue(
        self,
        task_id: str,
        original_description: str,
        ambiguity_level: str = "medium"
    ) -> Dict[str, Any]:
        """
        Initiate a dialogue for a task with ambiguous description
        
        Args:
            task_id: Task identifier
            original_description: Original clear description
            ambiguity_level: Level of ambiguity to inject
            
        Returns:
            Initial dialogue state with ambiguous description
        """
        # Inject ambiguity
        ambiguous_description = await self.ambiguity_layer.inject_ambiguity(
            original_description,
            level=ambiguity_level
        )
        
        # Parse original description for information chunks
        parsed_info = self._parse_description(original_description)
        
        # Initialize dialogue tracking
        self.task_dialogues[task_id] = {
            "state": DialogueState.INITIAL,
            "original_description": original_description,
            "ambiguous_description": ambiguous_description,
            "parsed_information": parsed_info,
            "revealed_information": set(),
            "conversation": [],
            "metrics": InformationGainMetrics(),
            "started_at": datetime.utcnow().isoformat(),
            "ambiguity_level": ambiguity_level
        }
        
        # Generate expected questions
        expected_questions = await self.ambiguity_layer.generate_clarification_questions(
            ambiguous_description,
            original_description
        )
        self.task_dialogues[task_id]["expected_questions"] = expected_questions
        
        return {
            "task_id": task_id,
            "description": ambiguous_description,
            "state": DialogueState.INITIAL,
            "hint": "This description may be incomplete. Feel free to ask clarifying questions.",
            "ambiguity_score": self.ambiguity_layer.measure_ambiguity_level(ambiguous_description)
        }
    
    def _parse_description(self, description: str) -> Dict[str, str]:
        """Parse description to extract information chunks"""
        parsed = {}
        
        # Extract error type
        error_match = re.search(r'(TypeError|ValueError|AttributeError|KeyError|[A-Z]\w*Error)', description)
        if error_match:
            parsed["error_type"] = error_match.group(1)
        
        # Extract file location
        file_match = re.search(r'(?:in |at |file:?\s*)([/\w]+\.py)', description)
        if file_match:
            parsed["file_location"] = file_match.group(1)
        elif re.search(r'line \d+', description):
            line_match = re.search(r'line (\d+)', description)
            parsed["file_location"] = f"Line {line_match.group(1)}"
        
        # Extract version info
        version_match = re.search(r'version[:\s]+([0-9.]+)', description, re.IGNORECASE)
        if version_match:
            parsed["environment_info"] = f"Version {version_match.group(1)}"
        
        # Simple heuristics for other info
        if "should" in description.lower():
            should_idx = description.lower().index("should")
            parsed["expected_behavior"] = description[should_idx:should_idx+100].strip()
        
        if "but" in description.lower() or "instead" in description.lower():
            but_idx = description.lower().index("but" if "but" in description.lower() else "instead")
            parsed["actual_behavior"] = description[but_idx:but_idx+100].strip()
        
        return parsed
    
    async def process_question(
        self,
        task_id: str,
        question: str,
        agent_id: str
    ) -> Dict[str, Any]:
        """
        Process a clarification question from an agent
        
        Args:
            task_id: Task identifier
            question: The question asked
            agent_id: ID of the asking agent
            
        Returns:
            Response with revealed information
        """
        if task_id not in self.task_dialogues:
            return {
                "error": "No dialogue initiated for this task",
                "task_id": task_id
            }
        
        dialogue = self.task_dialogues[task_id]
        dialogue["state"] = DialogueState.CLARIFYING
        
        # Evaluate question quality
        quality_score, relevant_info = self._evaluate_question(question, dialogue)
        
        # Track metrics
        is_relevant = len(relevant_info) > 0
        dialogue["metrics"].add_question(question, is_relevant, quality_score)
        
        # Record in conversation
        dialogue["conversation"].append({
            "type": "question",
            "agent_id": agent_id,
            "content": question,
            "timestamp": datetime.utcnow().isoformat(),
            "quality_score": quality_score
        })
        
        # Generate response based on question quality
        response = await self._generate_response(
            question,
            relevant_info,
            dialogue,
            quality_score
        )
        
        # Record response
        dialogue["conversation"].append({
            "type": "answer",
            "content": response["answer"],
            "timestamp": datetime.utcnow().isoformat(),
            "information_revealed": response.get("revealed_info", [])
        })
        
        # Update revealed information
        for info_type in response.get("revealed_info", []):
            dialogue["revealed_information"].add(info_type)
            dialogue["metrics"].reveal_information(
                self.information_chunks[info_type]["value"]
            )
        
        # Check if enough information revealed
        if dialogue["metrics"].information_revealed >= 0.8:
            dialogue["state"] = DialogueState.COMPLETE
        
        return response
    
    def _evaluate_question(
        self,
        question: str,
        dialogue: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """
        Evaluate question quality and identify relevant information
        
        Returns:
            (quality_score, list of relevant information types)
        """
        question_lower = question.lower()
        relevant_info = []
        
        # Check for relevant keywords
        for info_type, info_data in self.information_chunks.items():
            # Skip already revealed information
            if info_type in dialogue["revealed_information"]:
                continue
            
            # Check if question targets this information
            for keyword in info_data["keywords"]:
                if keyword in question_lower:
                    relevant_info.append(info_type)
                    break
        
        # Calculate quality score
        quality_score = 0.0
        
        # Specificity bonus
        if len(question.split()) > 5:
            quality_score += 0.2
        
        # Relevance bonus
        if relevant_info:
            quality_score += 0.4 * min(len(relevant_info) / 2, 1.0)
        
        # Check if question is in expected questions
        expected = dialogue.get("expected_questions", [])
        for exp_q in expected:
            if any(word in question.lower() for word in exp_q.lower().split()):
                quality_score += 0.3
                break
        
        # Penalty for vague questions
        vague_patterns = ["tell me more", "what else", "anything else", "more information"]
        if any(pattern in question_lower for pattern in vague_patterns):
            quality_score -= 0.2
        
        # Penalty for redundant questions
        for conv_item in dialogue["conversation"]:
            if conv_item["type"] == "question":
                similarity = self._calculate_similarity(question, conv_item["content"])
                if similarity > 0.8:
                    quality_score -= 0.3
                    break
        
        return max(0.0, min(1.0, quality_score)), relevant_info
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    async def _generate_response(
        self,
        question: str,
        relevant_info: List[str],
        dialogue: Dict[str, Any],
        quality_score: float
    ) -> Dict[str, Any]:
        """Generate response based on question quality"""
        response = {
            "question": question,
            "quality_score": quality_score,
            "revealed_info": []
        }
        
        # In strict mode, only reveal info for high-quality questions
        if self.strict_mode and quality_score < 0.5:
            response["answer"] = "Could you please be more specific about what you need to know?"
            response["hint"] = "Try asking about specific aspects like error types, file locations, or reproduction steps."
            return response
        
        # Reveal information based on relevance
        if not relevant_info:
            response["answer"] = "I'm not sure what specific information you're looking for. " \
                               "Could you ask about the error type, location, or how to reproduce the issue?"
        else:
            # Build answer from relevant information
            answer_parts = []
            for info_type in relevant_info[:2]:  # Limit to 2 pieces per question
                template = self.information_chunks[info_type]["info"]
                if info_type in dialogue["parsed_information"]:
                    value = dialogue["parsed_information"][info_type]
                    answer_parts.append(template.format(**{info_type: value}))
                    response["revealed_info"].append(info_type)
                else:
                    # Generic response if info not parsed
                    answer_parts.append(f"Information about {info_type.replace('_', ' ')} is not available.")
            
            response["answer"] = " ".join(answer_parts)
        
        # Add encouragement for good questions
        if quality_score >= 0.7:
            response["feedback"] = "Good question! This helps narrow down the issue."
        elif quality_score >= 0.4:
            response["feedback"] = "Thanks for the question. Let me provide what I can."
        
        return response
    
    def get_dialogue_state(self, task_id: str) -> Dict[str, Any]:
        """Get current dialogue state for a task"""
        if task_id not in self.task_dialogues:
            return {
                "error": "No dialogue found",
                "task_id": task_id
            }
        
        dialogue = self.task_dialogues[task_id]
        metrics = dialogue["metrics"]
        
        return {
            "task_id": task_id,
            "state": dialogue["state"],
            "turns": len(dialogue["conversation"]) // 2,
            "information_revealed": metrics.information_revealed,
            "efficiency_score": metrics.get_efficiency_score(),
            "questions_asked": metrics.total_questions,
            "relevant_questions": metrics.relevant_questions,
            "revealed_chunks": list(dialogue["revealed_information"])
        }
    
    def calculate_requirements_quality_score(self, task_id: str) -> float:
        """
        Calculate Requirements Engineering quality score
        
        Returns:
            Score from 0 to 1
        """
        if task_id not in self.task_dialogues:
            return 0.0
        
        dialogue = self.task_dialogues[task_id]
        metrics = dialogue["metrics"]
        
        # Component scores
        efficiency = metrics.get_efficiency_score()
        completeness = metrics.information_revealed
        
        # Question quality average
        avg_quality = sum(metrics.question_quality_scores) / len(metrics.question_quality_scores) \
                     if metrics.question_quality_scores else 0
        
        # Precision (relevant vs total questions)
        precision = metrics.relevant_questions / max(metrics.total_questions, 1)
        
        # Weighted combination
        score = (
            efficiency * 0.3 +
            completeness * 0.3 +
            avg_quality * 0.2 +
            precision * 0.2
        )
        
        return min(1.0, score)
    
    async def provide_full_description(self, task_id: str) -> str:
        """Provide full description after dialogue completion"""
        if task_id not in self.task_dialogues:
            return ""
        
        dialogue = self.task_dialogues[task_id]
        
        # Check if enough effort was made
        if dialogue["metrics"].total_questions < 2:
            return "Please ask clarifying questions first to better understand the issue."
        
        dialogue["state"] = DialogueState.COMPLETE
        return dialogue["original_description"]
    
    def get_dialogue_transcript(self, task_id: str) -> List[Dict[str, Any]]:
        """Get full dialogue transcript"""
        if task_id not in self.task_dialogues:
            return []
        
        return self.task_dialogues[task_id]["conversation"]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get dialogue manager statistics"""
        total_dialogues = len(self.task_dialogues)
        completed = sum(1 for d in self.task_dialogues.values() 
                       if d["state"] == DialogueState.COMPLETE)
        
        all_scores = []
        total_questions = 0
        
        for dialogue in self.task_dialogues.values():
            score = self.calculate_requirements_quality_score(dialogue.get("task_id", ""))
            if score > 0:
                all_scores.append(score)
            total_questions += dialogue["metrics"].total_questions
        
        return {
            "total_dialogues": total_dialogues,
            "completed_dialogues": completed,
            "average_requirements_score": sum(all_scores) / len(all_scores) if all_scores else 0,
            "total_questions_asked": total_questions,
            "average_questions_per_dialogue": total_questions / max(total_dialogues, 1)
        }