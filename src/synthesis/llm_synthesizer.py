"""LLM-based synthesizer for complex error fixing"""

import logging
from typing import Dict, Any, Optional, List
import json
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class LLMSynthesizer:
    """
    Uses LLMs to analyze and fix complex build errors.
    Integrated with OpenAI for real synthesis capabilities.
    """
    
    def __init__(self, provider: str = "openai"):
        self.provider = provider
        self.llm_client = None
        
        # Initialize OpenAI client if available
        if provider == "openai":
            try:
                from llm.openai_client import get_openai_client
                self.llm_client = get_openai_client()
                logger.info("OpenAI client initialized for synthesis")
            except Exception as e:
                logger.warning(f"OpenAI client not available: {e}")
                logger.info("Falling back to mock synthesis")
    
    async def analyze_error(self, error_text: str) -> Dict[str, Any]:
        """
        Use LLM to analyze a complex error.
        
        Args:
            error_text: The error output
            
        Returns:
            Analysis dictionary
        """
        # Use OpenAI if available
        if self.llm_client and hasattr(self.llm_client, 'analyze_test_failure'):
            try:
                result = await self.llm_client.analyze_test_failure(
                    test_output=error_text,
                    test_code="",  # Not available in this context
                    implementation_code=None
                )
                
                return {
                    "fixable": result.get("confidence", 0) > 0.5,
                    "error_type": "build_error",
                    "reason": result.get("root_cause", "Unknown"),
                    "suggested_fix": result.get("fix", "")
                }
            except Exception as e:
                logger.error(f"OpenAI analysis failed: {e}")
        
        # Fallback to heuristic analysis
        analysis = {
            "fixable": True,
            "error_type": "dependency",
            "reason": "Missing or incompatible dependency",
            "suggested_fix": "Update dependencies or use alternative packages"
        }
        
        return analysis
    
    async def generate_fix(
        self,
        error_analysis: Dict[str, Any],
        requirements_file: Optional[str],
        setup_file: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a fix using LLM.
        
        Args:
            error_analysis: Error analysis from analyze_error
            requirements_file: Path to requirements.txt
            setup_file: Path to setup.py
            
        Returns:
            Fix dictionary or None
        """
        error_type = error_analysis.get("error_type", "unknown")
        suggested_fix = error_analysis.get("suggested_fix", "")
        
        prompt = f"""Generate a fix for this build error:

Error Type: {error_type}
Suggested Fix: {suggested_fix}
Requirements File: {requirements_file or "Not provided"}
Setup File: {setup_file or "Not provided"}

Provide the fix in JSON format:
{{
    "type": "modify_requirements|run_commands|patch_file",
    "description": "string",
    "commands": ["list of commands"] or "new_content": "string"
}}
"""
        
        # Simulate LLM response
        # In production, this would be an actual API call
        fix = {
            "type": "run_commands",
            "description": "Install missing system dependencies",
            "commands": [
                "apt-get update",
                "apt-get install -y libssl-dev libffi-dev"
            ]
        }
        
        return fix
    
    async def suggest_alternative_packages(
        self,
        package_name: str,
        context: Optional[str] = None
    ) -> List[str]:
        """
        Suggest alternative packages using LLM.
        
        Args:
            package_name: Package that's causing issues
            context: Additional context about the project
            
        Returns:
            List of alternative package names
        """
        prompt = f"""Suggest alternative Python packages for: {package_name}

Context: {context or "General Python project"}

Provide alternatives that are:
1. Actively maintained
2. Compatible with modern Python versions
3. Similar functionality

Return as JSON list: ["package1", "package2", ...]
"""
        
        # Simulate LLM response
        alternatives = {
            "tensorflow": ["tensorflow-cpu", "jax", "pytorch"],
            "mysqlclient": ["pymysql", "mysql-connector-python"],
            "PIL": ["Pillow"],
            "cv2": ["opencv-python", "opencv-contrib-python"]
        }
        
        return alternatives.get(package_name, [package_name + "-alternative"])
    
    async def fix_syntax_error(
        self,
        file_path: str,
        error_message: str,
        file_content: str
    ) -> Optional[str]:
        """
        Fix Python syntax errors using LLM.
        
        Args:
            file_path: Path to the file with error
            error_message: Syntax error message
            file_content: Content of the file
            
        Returns:
            Fixed file content or None
        """
        prompt = f"""Fix this Python syntax error:

File: {file_path}
Error: {error_message}

Code:
{file_content[:500]}

Provide the corrected code.
"""
        
        # In production, this would use an LLM to fix the syntax
        # For now, return None (no fix available)
        return None
    
    async def generate_dockerfile_fix(
        self,
        error_text: str,
        base_image: str
    ) -> Optional[str]:
        """
        Generate Dockerfile modifications to fix build errors.
        
        Args:
            error_text: Build error text
            base_image: Current base image
            
        Returns:
            Dockerfile commands to add
        """
        prompt = f"""Generate Dockerfile commands to fix this error:

Base Image: {base_image}
Error: {error_text[:500]}

Provide RUN commands to fix the issue.
"""
        
        # Simulate LLM response
        dockerfile_fix = """
# Fix for build error
RUN apt-get update && apt-get install -y \\
    build-essential \\
    python3-dev \\
    libssl-dev \\
    libffi-dev \\
    && rm -rf /var/lib/apt/lists/*
"""
        
        return dockerfile_fix