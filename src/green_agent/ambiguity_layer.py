"""Ambiguity Layer for preventing memorization"""

import random
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AmbiguityLayer:
    """
    Injects ambiguity into issue descriptions to prevent memorization.
    Implements lexical, syntactic, and pragmatic ambiguity.
    """
    
    def __init__(self):
        self.ambiguity_strategies = {
            "lexical": self._apply_lexical_ambiguity,
            "syntactic": self._apply_syntactic_ambiguity,
            "pragmatic": self._apply_pragmatic_ambiguity
        }
        
        # Vague replacements for specific terms
        self.vague_replacements = {
            # File/path references
            r"in\s+[\w/]+\.py": "in one of the Python files",
            r"at\s+line\s+\d+": "at a specific location",
            r"function\s+\w+": "a particular function",
            r"class\s+\w+": "a certain class",
            r"method\s+\w+": "a specific method",
            
            # Error types
            r"TypeError": "a type-related error",
            r"ValueError": "a value-related error",
            r"AttributeError": "an attribute-related issue",
            r"KeyError": "a key-related problem",
            
            # Specific values
            r"\d+\s+seconds?": "some time",
            r"\d+\s+items?": "several items",
            r"version\s+[\d\.]+": "a specific version"
        }
    
    async def inject_ambiguity(
        self,
        text: str,
        level: str = "medium",
        strategies: Optional[List[str]] = None
    ) -> str:
        """
        Inject ambiguity into text.
        
        Args:
            text: Original issue description
            level: Ambiguity level (low, medium, high)
            strategies: Specific strategies to use
            
        Returns:
            Modified text with ambiguity
        """
        if level == "low":
            probability = 0.2
        elif level == "high":
            probability = 0.8
        else:  # medium
            probability = 0.5
        
        modified_text = text
        
        # Apply selected strategies
        if not strategies:
            strategies = list(self.ambiguity_strategies.keys())
        
        for strategy_name in strategies:
            if random.random() < probability:
                strategy_func = self.ambiguity_strategies.get(strategy_name)
                if strategy_func:
                    modified_text = strategy_func(modified_text)
                    logger.debug(f"Applied {strategy_name} ambiguity")
        
        return modified_text
    
    def _apply_lexical_ambiguity(self, text: str) -> str:
        """Apply lexical ambiguity (polysemous words)"""
        # Replace specific terms with vague ones
        for pattern, replacement in self.vague_replacements.items():
            if random.random() < 0.7:  # Don't replace everything
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Add ambiguous pronouns
        sentences = text.split('. ')
        if len(sentences) > 2:
            # Replace some nouns with "it" or "this"
            for i in range(1, len(sentences)):
                if random.random() < 0.3:
                    # Find first noun-like word and replace with pronoun
                    words = sentences[i].split()
                    for j, word in enumerate(words):
                        if word[0].isupper() and j > 0:
                            words[j] = "it" if random.random() < 0.5 else "this"
                            break
                    sentences[i] = ' '.join(words)
            
            text = '. '.join(sentences)
        
        return text
    
    def _apply_syntactic_ambiguity(self, text: str) -> str:
        """Apply syntactic ambiguity (ambiguous sentence structure)"""
        # Add ambiguous conjunctions
        ambiguous_phrases = [
            " or something similar",
            " and/or related components",
            " along with other parts",
            " including but not limited to this"
        ]
        
        sentences = text.split('. ')
        for i in range(len(sentences)):
            if random.random() < 0.3 and len(sentences[i]) > 20:
                sentences[i] += random.choice(ambiguous_phrases)
        
        # Remove some punctuation to create run-on sentences
        if random.random() < 0.4:
            # Combine some sentences
            if len(sentences) > 3:
                idx = random.randint(1, len(sentences) - 2)
                sentences[idx-1] = sentences[idx-1] + " and " + sentences[idx].lower()
                sentences.pop(idx)
        
        return '. '.join(sentences)
    
    def _apply_pragmatic_ambiguity(self, text: str) -> str:
        """Apply pragmatic ambiguity (missing context)"""
        # Remove specific context
        context_patterns = [
            r"When\s+[^,]+,",  # Remove "when" clauses
            r"After\s+[^,]+,",  # Remove "after" clauses
            r"Before\s+[^,]+,", # Remove "before" clauses
            r"Using\s+[^,]+,",  # Remove "using" clauses
            r"With\s+[^,]+,",   # Remove "with" clauses
        ]
        
        for pattern in context_patterns:
            if random.random() < 0.5:
                text = re.sub(pattern, "", text, count=1)
        
        # Add vague references
        vague_intros = [
            "Under certain conditions, ",
            "In some cases, ",
            "Sometimes, ",
            "Occasionally, ",
            "It has been observed that "
        ]
        
        if random.random() < 0.4:
            text = random.choice(vague_intros) + text.lower()
        
        # Remove specific numbers/versions
        text = re.sub(r'\b\d+\.\d+\.\d+\b', 'a certain version', text)
        text = re.sub(r'\b\d+\b', 'some number', text)
        
        return text
    
    async def generate_clarification_questions(
        self,
        ambiguous_text: str,
        original_text: str
    ) -> List[str]:
        """
        Generate clarification questions that a good agent should ask.
        
        Args:
            ambiguous_text: Text with ambiguity injected
            original_text: Original clear text
            
        Returns:
            List of clarification questions
        """
        questions = []
        
        # Check what was made ambiguous
        if "certain" in ambiguous_text or "specific" in ambiguous_text:
            questions.append("Which specific file or function is affected?")
        
        if "some" in ambiguous_text or "several" in ambiguous_text:
            questions.append("What is the exact value or count?")
        
        if "it" in ambiguous_text or "this" in ambiguous_text:
            questions.append("What does 'it' or 'this' refer to specifically?")
        
        if "certain conditions" in ambiguous_text or "some cases" in ambiguous_text:
            questions.append("Under what specific conditions does this occur?")
        
        if "related" in ambiguous_text or "similar" in ambiguous_text:
            questions.append("What are the related or similar components?")
        
        # Check for missing error types
        if "error" in ambiguous_text and not any(
            err in ambiguous_text for err in ["TypeError", "ValueError", "AttributeError"]
        ):
            questions.append("What type of error is being encountered?")
        
        return questions
    
    def measure_ambiguity_level(self, text: str) -> float:
        """
        Measure the ambiguity level of text.
        
        Returns:
            Score from 0 (clear) to 1 (very ambiguous)
        """
        score = 0.0
        total_checks = 0
        
        # Check for vague terms
        vague_terms = ["certain", "specific", "some", "several", "it", "this", "that"]
        for term in vague_terms:
            if term in text.lower():
                score += 0.1
            total_checks += 0.1
        
        # Check for missing specifics
        if not re.search(r'\b\d+\b', text):  # No numbers
            score += 0.15
        total_checks += 0.15
        
        if not re.search(r'\.py\b', text):  # No file references
            score += 0.15
        total_checks += 0.15
        
        if not re.search(r'line \d+', text):  # No line numbers
            score += 0.1
        total_checks += 0.1
        
        # Check for ambiguous conjunctions
        if "and/or" in text or "or something" in text:
            score += 0.1
        total_checks += 0.1
        
        # Normalize score
        return min(score / max(total_checks, 1), 1.0)