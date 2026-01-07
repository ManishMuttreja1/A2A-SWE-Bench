"""OpenAI LLM integration for SWEbench-A2A Framework"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OpenAIModel(str, Enum):
    """Available OpenAI models"""
    GPT4_TURBO = "gpt-4-turbo-preview"
    GPT4 = "gpt-4"  
    GPT35_TURBO = "gpt-3.5-turbo"
    GPT35_TURBO_16K = "gpt-3.5-turbo-16k"


@dataclass
class OpenAIConfig:
    """OpenAI client configuration"""
    api_key: str
    model: str = OpenAIModel.GPT4_TURBO
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: int = 60
    max_retries: int = 3
    organization: Optional[str] = None


class OpenAIClient:
    """
    OpenAI API client for SWEbench-A2A Framework.
    Handles code generation, analysis, and repair tasks.
    """
    
    def __init__(self, config: Optional[OpenAIConfig] = None):
        """Initialize OpenAI client"""
        if config is None:
            # Load from environment
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")
            
            config = OpenAIConfig(
                api_key=api_key,
                model=os.getenv("OPENAI_MODEL", OpenAIModel.GPT4_TURBO),
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096"))
            )
        
        self.config = config
        self._client = None
        self._initialize_client()
        
        # Statistics
        self.stats = {
            "requests": 0,
            "tokens_used": 0,
            "errors": 0,
            "cache_hits": 0
        }
        
        # Simple cache for repeated queries
        self.cache = {}
    
    def _initialize_client(self):
        """Initialize the OpenAI client"""
        try:
            from openai import AsyncOpenAI
            
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                organization=self.config.organization,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries
            )
            logger.info(f"OpenAI client initialized with model: {self.config.model}")
        except ImportError:
            logger.error("OpenAI library not installed. Install with: pip install openai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise
    
    async def generate_code_fix(
        self,
        error_message: str,
        code_context: str,
        file_path: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Generate a code fix for an error.
        
        Args:
            error_message: The error message
            code_context: Surrounding code context
            file_path: Path to the file with error
            additional_context: Additional information
            
        Returns:
            Generated fix code or None
        """
        prompt = self._build_fix_prompt(
            error_message, 
            code_context, 
            file_path, 
            additional_context
        )
        
        try:
            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an expert programmer fixing code errors in the SWEbench-A2A evaluation framework. Provide clean, working code fixes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3  # Lower temperature for more deterministic fixes
            )
            
            if response:
                return self._extract_code_from_response(response)
            
        except Exception as e:
            logger.error(f"Failed to generate code fix: {e}")
            self.stats["errors"] += 1
        
        return None
    
    async def analyze_test_failure(
        self,
        test_output: str,
        test_code: str,
        implementation_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze test failure and suggest fixes.
        
        Args:
            test_output: Test execution output
            test_code: The test code
            implementation_code: The implementation being tested
            
        Returns:
            Analysis with suggested fixes
        """
        prompt = f"""Analyze this test failure and provide a solution:

Test Output:
```
{test_output[:2000]}
```

Test Code:
```python
{test_code[:2000]}
```

{"Implementation Code:" if implementation_code else ""}
{f"```python\n{implementation_code[:2000]}\n```" if implementation_code else ""}

Provide:
1. Root cause of the failure
2. Specific fix for the code
3. Confidence level (0-1)
"""
        
        try:
            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an expert test analyst for the SWEbench-A2A framework."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            if response:
                return self._parse_analysis_response(response)
                
        except Exception as e:
            logger.error(f"Failed to analyze test failure: {e}")
            self.stats["errors"] += 1
        
        return {
            "root_cause": "Analysis failed",
            "fix": None,
            "confidence": 0.0
        }
    
    async def synthesize_environment_fix(
        self,
        error_type: str,
        error_details: str,
        dockerfile: Optional[str] = None,
        requirements: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Synthesize fixes for environment setup issues.
        
        Args:
            error_type: Type of error (dependency, build, etc.)
            error_details: Detailed error message
            dockerfile: Current Dockerfile content
            requirements: Current requirements.txt content
            
        Returns:
            Dictionary with fixed configurations
        """
        prompt = f"""Fix this environment setup issue:

Error Type: {error_type}
Error Details:
```
{error_details[:3000]}
```

{"Current Dockerfile:" if dockerfile else ""}
{f"```dockerfile\n{dockerfile[:1000]}\n```" if dockerfile else ""}

{"Current Requirements:" if requirements else ""}
{f"```\n{requirements[:1000]}\n```" if requirements else ""}

Provide fixes for:
1. Dockerfile (if needed)
2. requirements.txt (if needed)
3. Shell commands to run (if needed)
"""
        
        try:
            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an expert in Docker and Python environment setup for the SWEbench-A2A framework."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5
            )
            
            if response:
                return self._parse_environment_fix(response)
                
        except Exception as e:
            logger.error(f"Failed to synthesize environment fix: {e}")
            self.stats["errors"] += 1
        
        return {}
    
    async def generate_test_cases(
        self,
        function_signature: str,
        function_docstring: str,
        implementation: Optional[str] = None
    ) -> List[str]:
        """
        Generate test cases for a function.
        
        Args:
            function_signature: Function signature
            function_docstring: Function documentation
            implementation: Optional implementation code
            
        Returns:
            List of generated test cases
        """
        prompt = f"""Generate comprehensive test cases for this function:

Function Signature:
```python
{function_signature}
```

Documentation:
```
{function_docstring}
```

{"Implementation:" if implementation else ""}
{f"```python\n{implementation[:1000]}\n```" if implementation else ""}

Generate at least 5 test cases including:
- Normal cases
- Edge cases
- Error cases
"""
        
        try:
            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an expert test engineer creating tests for the SWEbench-A2A framework."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            if response:
                return self._extract_test_cases(response)
                
        except Exception as e:
            logger.error(f"Failed to generate test cases: {e}")
            self.stats["errors"] += 1
        
        return []
    
    async def _make_request(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """Make a request to OpenAI API"""
        if not self._client:
            logger.error("OpenAI client not initialized")
            return None
        
        # Check cache
        cache_key = json.dumps(messages)
        if cache_key in self.cache:
            self.stats["cache_hits"] += 1
            return self.cache[cache_key]
        
        try:
            response = await self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty
            )
            
            if response and response.choices:
                content = response.choices[0].message.content
                
                # Update statistics
                self.stats["requests"] += 1
                if hasattr(response, 'usage'):
                    self.stats["tokens_used"] += response.usage.total_tokens
                
                # Cache the response
                self.cache[cache_key] = content
                
                return content
            
        except Exception as e:
            logger.error(f"OpenAI API request failed: {e}")
            self.stats["errors"] += 1
            raise
        
        return None
    
    def _build_fix_prompt(
        self,
        error_message: str,
        code_context: str,
        file_path: Optional[str],
        additional_context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for code fix generation"""
        prompt = f"""Fix this code error:

Error Message:
```
{error_message}
```

Code Context:
```python
{code_context}
```

{"File: " + file_path if file_path else ""}

{"Additional Context:" if additional_context else ""}
{json.dumps(additional_context, indent=2) if additional_context else ""}

Provide a corrected version of the code that fixes the error.
Include only the fixed code without explanations.
"""
        return prompt
    
    def _extract_code_from_response(self, response: str) -> str:
        """Extract code from LLM response"""
        # Look for code blocks
        import re
        
        # Try to find code in triple backticks
        code_pattern = r"```(?:python)?\n(.*?)\n```"
        matches = re.findall(code_pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # If no code blocks, return the entire response
        return response.strip()
    
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse test analysis response"""
        result = {
            "root_cause": "Unknown",
            "fix": None,
            "confidence": 0.5
        }
        
        # Simple parsing - could be enhanced with structured output
        lines = response.split('\n')
        
        for i, line in enumerate(lines):
            if 'root cause' in line.lower():
                result["root_cause"] = lines[i+1] if i+1 < len(lines) else line
            elif 'fix' in line.lower() or 'solution' in line.lower():
                # Extract code fix
                result["fix"] = self._extract_code_from_response('\n'.join(lines[i:]))
            elif 'confidence' in line.lower():
                # Extract confidence
                import re
                match = re.search(r'(\d+\.?\d*)', line)
                if match:
                    result["confidence"] = float(match.group(1))
        
        return result
    
    def _parse_environment_fix(self, response: str) -> Dict[str, str]:
        """Parse environment fix response"""
        fixes = {}
        
        # Extract Dockerfile
        import re
        dockerfile_pattern = r"```dockerfile\n(.*?)\n```"
        dockerfile_matches = re.findall(dockerfile_pattern, response, re.DOTALL)
        if dockerfile_matches:
            fixes["dockerfile"] = dockerfile_matches[0]
        
        # Extract requirements.txt
        requirements_pattern = r"```(?:txt|text)?\n(.*?)\n```"
        requirements_matches = re.findall(requirements_pattern, response, re.DOTALL)
        if requirements_matches:
            fixes["requirements"] = requirements_matches[0]
        
        # Extract shell commands
        shell_pattern = r"```(?:bash|shell|sh)\n(.*?)\n```"
        shell_matches = re.findall(shell_pattern, response, re.DOTALL)
        if shell_matches:
            fixes["commands"] = shell_matches[0].split('\n')
        
        return fixes
    
    def _extract_test_cases(self, response: str) -> List[str]:
        """Extract test cases from response"""
        test_cases = []
        
        # Extract all code blocks
        import re
        code_pattern = r"```(?:python)?\n(.*?)\n```"
        matches = re.findall(code_pattern, response, re.DOTALL)
        
        for match in matches:
            # Check if it looks like a test
            if 'def test_' in match or 'assert' in match:
                test_cases.append(match.strip())
        
        return test_cases
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "model": self.config.model,
            "average_tokens_per_request": (
                self.stats["tokens_used"] / self.stats["requests"]
                if self.stats["requests"] > 0 else 0
            )
        }
    
    async def clear_cache(self):
        """Clear the response cache"""
        self.cache.clear()
        logger.info("OpenAI client cache cleared")


# Singleton instance
_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get or create OpenAI client singleton"""
    global _openai_client
    
    if _openai_client is None:
        _openai_client = OpenAIClient()
    
    return _openai_client


async def test_openai_connection():
    """Test OpenAI connection and API key"""
    try:
        client = get_openai_client()
        
        # Simple test query
        response = await client._make_request(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'OpenAI connection successful' if you can read this."}
            ],
            max_tokens=50
        )
        
        if response and "successful" in response.lower():
            logger.info("OpenAI connection test successful")
            return True
        else:
            logger.error("OpenAI connection test failed")
            return False
            
    except Exception as e:
        logger.error(f"OpenAI connection test error: {e}")
        return False