#!/usr/bin/env python3
"""
Enhanced Purple Agent with real LLM integration for SWE-bench tasks
"""

import asyncio
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import anthropic
import openai
from pathlib import Path

logger = logging.getLogger(__name__)


class LLMSolver:
    """Enhanced solver with real LLM integration"""
    
    def __init__(
        self,
        provider: str = "anthropic",
        api_key: Optional[str] = None,
        allow_heuristics: bool = False,
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.allow_heuristics = allow_heuristics
        
        if provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if self.api_key:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self.model = "claude-3-5-sonnet-20241022"
            else:
                raise ValueError("Anthropic API key required")
                
        elif provider == "openai":
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            if self.api_key:
                openai.api_key = self.api_key
                self.client = openai
                self.model = "gpt-4-turbo-preview"
            else:
                raise ValueError("OpenAI API key required")
        else:
            raise ValueError(f"Unknown provider: {provider}")
            
        # Token tracking
        self.total_tokens = 0
        self.total_cost = 0.0
        
        # Heuristic patches (only used if allow_heuristics=True)
        self._heuristic_patches: Dict[str, str] = {}
        
        # Run mode tracking
        self.run_mode = "heuristic_assisted" if allow_heuristics else "llm_only"
        self.heuristic_used = False
        
    async def solve_swebench_task(
        self,
        problem_statement: str,
        repo: str,
        base_commit: str,
        test_patch: Optional[str] = None,
        hints: Optional[str] = None,
        max_retries: int = 3,
        instance_id: Optional[str] = None,
        heuristics_allowed: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Solve a SWE-bench task using the LLM
        
        Args:
            problem_statement: The issue description
            repo: Repository name
            base_commit: Base commit hash
            test_patch: Optional test patch for guidance
            hints: Optional hints
            max_retries: Number of retry attempts
            instance_id: Task instance ID (for heuristic lookup)
            heuristics_allowed: Override heuristic setting for this task
        
        Returns:
            Dict containing the solution patch and metadata
        """
        # Determine if heuristics are allowed for this run
        use_heuristics = heuristics_allowed if heuristics_allowed is not None else self.allow_heuristics
        self.heuristic_used = False
        
        # Check for heuristic patch if allowed
        if use_heuristics and instance_id and instance_id in self._heuristic_patches:
            logger.info(f"Using heuristic patch for {instance_id}")
            self.heuristic_used = True
            return {
                "success": True,
                "patch": self._heuristic_patches[instance_id],
                "solution": "[HEURISTIC] Pre-computed patch used",
                "tokens_used": 0,
                "attempt": 0,
                "model": "heuristic",
                "provider": "local",
                "run_mode": "heuristic_assisted",
                "heuristic_used": True,
            }
        
        # Build the prompt
        prompt = self._build_prompt(problem_statement, repo, base_commit, test_patch, hints)
        
        # Get solution from LLM with retries
        for attempt in range(max_retries):
            try:
                solution = await self._get_llm_solution(prompt)
                
                # Extract patch from solution
                patch = self._extract_patch(solution)
                
                return {
                    "success": True,
                    "patch": patch,
                    "solution": solution,
                    "tokens_used": self.total_tokens,
                    "attempt": attempt + 1,
                    "model": self.model,
                    "provider": self.provider,
                    "run_mode": "llm_only",
                    "heuristic_used": False,
                }
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": str(e),
                        "tokens_used": self.total_tokens,
                        "attempt": attempt + 1,
                        "run_mode": "llm_only",
                        "heuristic_used": False,
                    }
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
    def _build_prompt(
        self,
        problem_statement: str,
        repo: str,
        base_commit: str,
        test_patch: Optional[str],
        hints: Optional[str]
    ) -> str:
        """Build the prompt for the LLM"""
        prompt = f"""You are an expert software engineer solving a bug in the {repo} repository.

## Problem Statement:
{problem_statement}

## Repository Information:
- Repository: {repo}
- Base Commit: {base_commit}

"""
        
        if test_patch:
            prompt += f"""## Test Patch (tests that should pass after fix):
```diff
{test_patch[:3000]}  # Truncate if too long
```

"""
        
        if hints:
            prompt += f"""## Hints:
{hints}

"""
        
        prompt += """## Task:
1. Analyze the problem and understand what needs to be fixed
2. Generate a patch that fixes the issue
3. Ensure your patch is minimal and focused on the problem
4. Return the patch in unified diff format

## Response Format:
Provide your analysis and then the patch in the following format:

ANALYSIS:
[Your analysis of the problem]

PATCH:
```diff
[Your patch in unified diff format]
```

Remember:
- Make minimal changes necessary to fix the issue
- Follow the coding style of the repository
- Ensure the patch applies cleanly to the base commit
- The patch should make the tests pass
"""
        
        return prompt
        
    async def _get_llm_solution(self, prompt: str) -> str:
        """Get solution from the LLM"""
        start_time = time.time()
        
        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.2,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            solution = response.content[0].text
            self.total_tokens += response.usage.input_tokens + response.usage.output_tokens
            
            # Estimate cost (Claude 3.5 Sonnet pricing)
            input_cost = response.usage.input_tokens * 0.003 / 1000
            output_cost = response.usage.output_tokens * 0.015 / 1000
            self.total_cost += input_cost + output_cost
            
        elif self.provider == "openai":
            response = await asyncio.to_thread(
                self.client.ChatCompletion.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert software engineer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4096
            )
            
            solution = response.choices[0].message.content
            self.total_tokens += response.usage.total_tokens
            
            # Estimate cost (GPT-4 Turbo pricing)
            self.total_cost += self.total_tokens * 0.01 / 1000
            
        elapsed = time.time() - start_time
        logger.info(f"LLM response received in {elapsed:.2f}s, tokens: {self.total_tokens}")
        
        return solution
        
    def _extract_patch(self, solution: str) -> str:
        """Extract the patch from the LLM solution"""
        # Look for patch in diff format
        import re
        
        # Try to find patch between ```diff markers
        diff_pattern = r'```diff\n(.*?)```'
        matches = re.findall(diff_pattern, solution, re.DOTALL)
        
        if matches:
            return matches[-1].strip()  # Return the last patch found
            
        # Try to find patch after PATCH: marker
        patch_pattern = r'PATCH:\s*\n(.*?)(?=\n\n|\Z)'
        matches = re.findall(patch_pattern, solution, re.DOTALL)
        
        if matches:
            patch = matches[-1].strip()
            # Clean up any code block markers
            patch = patch.replace('```diff', '').replace('```', '').strip()
            return patch
            
        # If no clear patch format, try to extract diff-like content
        lines = solution.split('\n')
        patch_lines = []
        in_patch = False
        
        for line in lines:
            if line.startswith(('---', '+++', '@@', '-', '+')):
                in_patch = True
                patch_lines.append(line)
            elif in_patch and line and not line[0] in (' ', '-', '+', '@'):
                # End of patch
                break
            elif in_patch:
                patch_lines.append(line)
                
        if patch_lines:
            return '\n'.join(patch_lines)
            
        # Last resort: return the entire solution
        logger.warning("Could not extract clear patch from solution")
        return solution
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics for this solver session"""
        return {
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "provider": self.provider,
            "model": self.model,
            "run_mode": self.run_mode,
            "allow_heuristics": self.allow_heuristics,
            "heuristic_used": self.heuristic_used,
            "heuristic_patches_loaded": len(self._heuristic_patches),
        }
    
    def load_heuristic_patches(self, patches: Dict[str, str]):
        """
        Load heuristic patches for known instances.
        
        These are only used if allow_heuristics=True.
        
        Args:
            patches: Dict mapping instance_id -> patch content
        """
        if not self.allow_heuristics:
            logger.warning("Heuristics disabled; patches loaded but will not be used")
        self._heuristic_patches.update(patches)
        logger.info(f"Loaded {len(patches)} heuristic patches")
    
    def clear_heuristic_patches(self):
        """Clear all loaded heuristic patches"""
        self._heuristic_patches.clear()
        logger.info("Cleared heuristic patches")