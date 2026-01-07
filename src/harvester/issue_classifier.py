"""Issue classifier for determining SWE-bench suitability"""

import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of issue classification"""
    suitable: bool
    category: str  # bug_fix, feature, refactor, test
    difficulty: str  # easy, medium, hard
    confidence: float  # 0-1
    reasons: List[str]
    tags: List[str]


class IssueClassifier:
    """
    Classifies GitHub issues for SWE-bench suitability.
    Uses heuristics and pattern matching.
    """
    
    def __init__(self):
        self.patterns = self._load_patterns()
        self.keywords = self._load_keywords()
    
    def _load_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Load classification patterns"""
        return {
            "bug_patterns": [
                re.compile(r"\berror\b", re.IGNORECASE),
                re.compile(r"\bexception\b", re.IGNORECASE),
                re.compile(r"\bfail(s|ed|ing)?\b", re.IGNORECASE),
                re.compile(r"\bcrash(es|ed|ing)?\b", re.IGNORECASE),
                re.compile(r"\bbroke(n)?\b", re.IGNORECASE),
                re.compile(r"\bissue\b", re.IGNORECASE),
                re.compile(r"\bproblem\b", re.IGNORECASE),
                re.compile(r"\bwrong\b", re.IGNORECASE),
                re.compile(r"\bunexpected\b", re.IGNORECASE),
                re.compile(r"\bincorrect\b", re.IGNORECASE),
            ],
            "feature_patterns": [
                re.compile(r"\badd(s|ed|ing)?\b", re.IGNORECASE),
                re.compile(r"\bnew\s+\w+", re.IGNORECASE),
                re.compile(r"\bimplement\b", re.IGNORECASE),
                re.compile(r"\bfeature\b", re.IGNORECASE),
                re.compile(r"\benhance(ment)?\b", re.IGNORECASE),
                re.compile(r"\bsupport\b", re.IGNORECASE),
                re.compile(r"\brequest\b", re.IGNORECASE),
            ],
            "test_patterns": [
                re.compile(r"\btest(s|ing)?\b", re.IGNORECASE),
                re.compile(r"\bunit\s+test\b", re.IGNORECASE),
                re.compile(r"\bcoverage\b", re.IGNORECASE),
                re.compile(r"\bassertion\b", re.IGNORECASE),
            ],
            "code_patterns": [
                re.compile(r"```[\w]*\n.*?\n```", re.DOTALL),
                re.compile(r"`[^`]+`"),
                re.compile(r"\bTraceback\b"),
                re.compile(r"\bFile\s+\".*?\",\s+line\s+\d+"),
                re.compile(r"def\s+\w+\s*\("),
                re.compile(r"class\s+\w+"),
                re.compile(r"import\s+\w+"),
            ],
            "unsui

table_patterns": [
                re.compile(r"\bdocument(ation)?\b", re.IGNORECASE),
                re.compile(r"\btypo\b", re.IGNORECASE),
                re.compile(r"\bcomment\b", re.IGNORECASE),
                re.compile(r"\breadme\b", re.IGNORECASE),
                re.compile(r"\bspelling\b", re.IGNORECASE),
                re.compile(r"\bgrammar\b", re.IGNORECASE),
            ]
        }
    
    def _load_keywords(self) -> Dict[str, List[str]]:
        """Load classification keywords"""
        return {
            "easy_keywords": [
                "simple", "trivial", "easy", "quick", "minor",
                "small", "typo", "rename", "cleanup"
            ],
            "medium_keywords": [
                "moderate", "standard", "normal", "typical",
                "regular", "common"
            ],
            "hard_keywords": [
                "complex", "difficult", "hard", "challenging",
                "major", "significant", "critical", "performance",
                "optimization", "architecture", "design"
            ],
            "unsuitable_keywords": [
                "documentation", "docs", "readme", "comment",
                "style", "format", "lint", "typo", "spelling",
                "grammar", "translation", "i18n", "l10n"
            ]
        }
    
    async def classify_issue(
        self,
        issue: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Classify a GitHub issue.
        
        Args:
            issue: GitHub issue data
            
        Returns:
            Classification result
        """
        title = issue.get("title", "")
        body = issue.get("body", "")
        labels = [label["name"].lower() for label in issue.get("labels", [])]
        
        combined_text = f"{title} {body}"
        
        # Initialize result
        result = {
            "suitable": False,
            "category": "unknown",
            "difficulty": "medium",
            "confidence": 0.0,
            "reasons": [],
            "tags": []
        }
        
        # Check for unsuitable patterns
        unsuitable_count = sum(
            1 for pattern in self.patterns["unsuitable_patterns"]
            if pattern.search(combined_text)
        )
        
        unsuitable_keyword_count = sum(
            1 for keyword in self.keywords["unsuitable_keywords"]
            if keyword.lower() in combined_text.lower()
        )
        
        if unsuitable_count > 2 or unsuitable_keyword_count > 3:
            result["reasons"].append("Appears to be documentation-only")
            return result
        
        # Categorize issue
        bug_score = self._calculate_pattern_score(
            combined_text,
            self.patterns["bug_patterns"]
        )
        
        feature_score = self._calculate_pattern_score(
            combined_text,
            self.patterns["feature_patterns"]
        )
        
        test_score = self._calculate_pattern_score(
            combined_text,
            self.patterns["test_patterns"]
        )
        
        # Determine category
        if bug_score > feature_score and bug_score > test_score:
            result["category"] = "bug_fix"
            result["tags"].append("bug")
        elif feature_score > bug_score and feature_score > test_score:
            result["category"] = "feature"
            result["tags"].append("enhancement")
        elif test_score > 0:
            result["category"] = "test"
            result["tags"].append("testing")
        else:
            result["category"] = "refactor"
            result["tags"].append("refactoring")
        
        # Check for code snippets
        code_score = self._calculate_pattern_score(
            combined_text,
            self.patterns["code_patterns"]
        )
        
        has_code = code_score > 0
        has_traceback = "Traceback" in body or "File \"" in body
        
        if has_code:
            result["tags"].append("has_code")
        if has_traceback:
            result["tags"].append("has_traceback")
        
        # Determine difficulty
        result["difficulty"] = self._determine_difficulty(
            combined_text,
            labels,
            len(body)
        )
        
        # Calculate confidence
        confidence_factors = []
        
        # Factor 1: Has code or traceback
        if has_code or has_traceback:
            confidence_factors.append(0.3)
            result["reasons"].append("Contains code or error traceback")
        
        # Factor 2: Clear category
        if result["category"] != "unknown":
            confidence_factors.append(0.2)
            result["reasons"].append(f"Clear {result['category']} issue")
        
        # Factor 3: Appropriate length
        if 100 < len(body) < 5000:
            confidence_factors.append(0.2)
            result["reasons"].append("Appropriate issue description length")
        
        # Factor 4: Has labels
        if labels:
            confidence_factors.append(0.15)
            result["reasons"].append("Has classification labels")
        
        # Factor 5: Not too complex
        if result["difficulty"] in ["easy", "medium"]:
            confidence_factors.append(0.15)
            result["reasons"].append(f"Manageable difficulty ({result['difficulty']})")
        
        result["confidence"] = sum(confidence_factors)
        
        # Determine suitability
        result["suitable"] = (
            result["confidence"] >= 0.5 and
            result["category"] != "unknown" and
            len(result["reasons"]) >= 2
        )
        
        return result
    
    def _calculate_pattern_score(
        self,
        text: str,
        patterns: List[re.Pattern]
    ) -> int:
        """Calculate pattern matching score"""
        score = 0
        for pattern in patterns:
            matches = pattern.findall(text)
            score += len(matches)
        return score
    
    def _determine_difficulty(
        self,
        text: str,
        labels: List[str],
        text_length: int
    ) -> str:
        """Determine issue difficulty"""
        text_lower = text.lower()
        
        # Check keywords
        easy_count = sum(
            1 for keyword in self.keywords["easy_keywords"]
            if keyword in text_lower
        )
        
        hard_count = sum(
            1 for keyword in self.keywords["hard_keywords"]
            if keyword in text_lower
        )
        
        # Check labels
        if any("easy" in label or "good first issue" in label for label in labels):
            return "easy"
        
        if any("hard" in label or "complex" in label for label in labels):
            return "hard"
        
        # Use heuristics
        if easy_count > hard_count:
            return "easy"
        elif hard_count > easy_count:
            return "hard"
        elif text_length < 200:
            return "easy"
        elif text_length > 2000:
            return "hard"
        else:
            return "medium"
    
    def batch_classify(
        self,
        issues: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Classify multiple issues.
        
        Args:
            issues: List of GitHub issues
            
        Returns:
            List of classification results
        """
        results = []
        
        for issue in issues:
            try:
                result = asyncio.run(self.classify_issue(issue))
                results.append({
                    "issue_number": issue["number"],
                    "classification": result
                })
            except Exception as e:
                logger.error(f"Failed to classify issue #{issue['number']}: {e}")
                results.append({
                    "issue_number": issue["number"],
                    "classification": {
                        "suitable": False,
                        "error": str(e)
                    }
                })
        
        return results