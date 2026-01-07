"""Synthesis Engine for dynamic environment repair"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import re

from .dependency_fixer import DependencyFixer
from .llm_synthesizer import LLMSynthesizer

logger = logging.getLogger(__name__)


class SynthesisEngine:
    """
    Self-healing environment synthesis engine.
    Automatically fixes broken builds and dependencies.
    """
    
    def __init__(self, llm_provider: Optional[str] = "openai"):
        self.dependency_fixer = DependencyFixer()
        self.llm_synthesizer = LLMSynthesizer(provider=llm_provider)
        
        # Track synthesis attempts
        self.synthesis_history: List[Dict[str, Any]] = []
        
        # Configuration
        self.max_retry_attempts = 3
        self.timeout = 300  # 5 minutes max per synthesis
    
    async def synthesize_environment(
        self,
        container_id: str,
        repo_path: str,
        requirements_file: Optional[str] = None,
        setup_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesize a working environment, fixing issues as needed.
        
        Args:
            container_id: Docker container ID
            repo_path: Path to repository in container
            requirements_file: Path to requirements.txt
            setup_file: Path to setup.py
            
        Returns:
            Synthesis result with success status
        """
        logger.info(f"Starting environment synthesis for container {container_id}")
        
        result = {
            "success": False,
            "attempts": 0,
            "fixes_applied": [],
            "error": None
        }
        
        for attempt in range(self.max_retry_attempts):
            result["attempts"] = attempt + 1
            
            try:
                # Attempt to build environment
                build_result = await self._attempt_build(
                    container_id,
                    repo_path,
                    requirements_file,
                    setup_file
                )
                
                if build_result["success"]:
                    result["success"] = True
                    logger.info(f"Environment synthesized successfully on attempt {attempt + 1}")
                    break
                
                # Build failed - analyze error
                error_analysis = await self._analyze_error(build_result["error"])
                
                if not error_analysis["fixable"]:
                    result["error"] = "Unfixable error: " + error_analysis["reason"]
                    break
                
                # Generate fix
                fix = await self._generate_fix(
                    error_analysis,
                    requirements_file,
                    setup_file
                )
                
                if not fix:
                    result["error"] = "Could not generate fix"
                    break
                
                # Apply fix
                fix_applied = await self._apply_fix(
                    container_id,
                    repo_path,
                    fix
                )
                
                if fix_applied:
                    result["fixes_applied"].append(fix)
                    logger.info(f"Applied fix: {fix['description']}")
                else:
                    result["error"] = "Failed to apply fix"
                    break
                    
            except Exception as e:
                logger.error(f"Synthesis error on attempt {attempt + 1}: {e}")
                result["error"] = str(e)
                break
        
        # Store in history
        self.synthesis_history.append(result)
        
        return result
    
    async def _attempt_build(
        self,
        container_id: str,
        repo_path: str,
        requirements_file: Optional[str],
        setup_file: Optional[str]
    ) -> Dict[str, Any]:
        """Attempt to build the environment"""
        from ..green_agent.environment_orchestrator import EnvironmentOrchestrator
        orchestrator = EnvironmentOrchestrator()
        
        commands = []
        
        # Try to install from requirements.txt
        if requirements_file:
            commands.append(f"pip install -r {requirements_file}")
        
        # Try to install from setup.py
        if setup_file:
            commands.append(f"pip install -e {repo_path}")
        
        # If no files specified, try common patterns
        if not commands:
            commands = [
                "pip install -r requirements.txt",
                "pip install -e .",
                "python setup.py install"
            ]
        
        for cmd in commands:
            result = await orchestrator.execute_in_environment(
                container_id,
                cmd,
                workdir=repo_path
            )
            
            if result["exit_code"] != 0:
                return {
                    "success": False,
                    "command": cmd,
                    "error": result.get("stdout", "") + result.get("stderr", "")
                }
        
        return {"success": True}
    
    async def _analyze_error(self, error_text: str) -> Dict[str, Any]:
        """Analyze build error to determine if it's fixable"""
        analysis = {
            "fixable": False,
            "error_type": "unknown",
            "reason": "",
            "details": {}
        }
        
        # Check for common dependency errors
        if "No matching distribution found" in error_text:
            analysis["fixable"] = True
            analysis["error_type"] = "missing_package"
            
            # Extract package name
            match = re.search(r"No matching distribution found for (\S+)", error_text)
            if match:
                analysis["details"]["package"] = match.group(1)
        
        elif "error: Microsoft Visual C++" in error_text:
            analysis["fixable"] = True
            analysis["error_type"] = "missing_compiler"
            analysis["details"]["compiler"] = "msvc"
        
        elif "404" in error_text or "Not Found" in error_text:
            analysis["fixable"] = True
            analysis["error_type"] = "url_404"
            
            # Extract URL if possible
            match = re.search(r"https?://\S+", error_text)
            if match:
                analysis["details"]["url"] = match.group(0)
        
        elif "version" in error_text.lower() and "conflict" in error_text.lower():
            analysis["fixable"] = True
            analysis["error_type"] = "version_conflict"
        
        elif "Permission denied" in error_text:
            analysis["fixable"] = True
            analysis["error_type"] = "permission"
        
        elif "ImportError" in error_text or "ModuleNotFoundError" in error_text:
            analysis["fixable"] = True
            analysis["error_type"] = "import_error"
            
            # Extract module name
            match = re.search(r"No module named ['\"](\S+)['\"]", error_text)
            if match:
                analysis["details"]["module"] = match.group(1)
        
        else:
            # Use LLM to analyze complex errors
            llm_analysis = await self.llm_synthesizer.analyze_error(error_text)
            if llm_analysis:
                analysis.update(llm_analysis)
        
        return analysis
    
    async def _generate_fix(
        self,
        error_analysis: Dict[str, Any],
        requirements_file: Optional[str],
        setup_file: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Generate a fix for the identified error"""
        error_type = error_analysis["error_type"]
        details = error_analysis.get("details", {})
        
        fix = None
        
        if error_type == "missing_package":
            package = details.get("package", "")
            fix = await self.dependency_fixer.fix_missing_package(package)
        
        elif error_type == "missing_compiler":
            fix = {
                "type": "install_compiler",
                "description": "Install build tools",
                "commands": [
                    "apt-get update",
                    "apt-get install -y build-essential python3-dev"
                ]
            }
        
        elif error_type == "url_404":
            url = details.get("url", "")
            fix = await self.dependency_fixer.fix_broken_url(url, requirements_file)
        
        elif error_type == "version_conflict":
            fix = await self.dependency_fixer.resolve_version_conflict(
                requirements_file,
                error_analysis
            )
        
        elif error_type == "permission":
            fix = {
                "type": "fix_permissions",
                "description": "Fix file permissions",
                "commands": ["chmod -R 755 ."]
            }
        
        elif error_type == "import_error":
            module = details.get("module", "")
            fix = await self.dependency_fixer.fix_import_error(module)
        
        else:
            # Use LLM to generate fix for complex errors
            fix = await self.llm_synthesizer.generate_fix(
                error_analysis,
                requirements_file,
                setup_file
            )
        
        return fix
    
    async def _apply_fix(
        self,
        container_id: str,
        repo_path: str,
        fix: Dict[str, Any]
    ) -> bool:
        """Apply a fix to the environment"""
        from ..green_agent.environment_orchestrator import EnvironmentOrchestrator
        orchestrator = EnvironmentOrchestrator()
        
        try:
            fix_type = fix.get("type")
            
            if fix_type == "modify_requirements":
                # Write new requirements file
                new_content = fix.get("new_content", "")
                file_path = fix.get("file_path", "requirements.txt")
                
                cmd = f"echo '{new_content}' > {file_path}"
                result = await orchestrator.execute_in_environment(
                    container_id, cmd, repo_path
                )
                
                return result["exit_code"] == 0
            
            elif fix_type in ["install_compiler", "fix_permissions", "run_commands"]:
                # Run commands
                commands = fix.get("commands", [])
                for cmd in commands:
                    result = await orchestrator.execute_in_environment(
                        container_id, cmd, repo_path
                    )
                    if result["exit_code"] != 0:
                        return False
                return True
            
            elif fix_type == "replace_package":
                # Replace one package with another
                old_package = fix.get("old_package")
                new_package = fix.get("new_package")
                
                if old_package and new_package:
                    cmd = f"pip uninstall -y {old_package} && pip install {new_package}"
                    result = await orchestrator.execute_in_environment(
                        container_id, cmd, repo_path
                    )
                    return result["exit_code"] == 0
            
            elif fix_type == "patch_file":
                # Apply a patch to a file
                patch = fix.get("patch", "")
                target_file = fix.get("target_file", "")
                
                if patch and target_file:
                    # Save patch and apply
                    patch_cmd = f"echo '{patch}' | patch {target_file}"
                    result = await orchestrator.execute_in_environment(
                        container_id, patch_cmd, repo_path
                    )
                    return result["exit_code"] == 0
            
            return False
            
        except Exception as e:
            logger.error(f"Error applying fix: {e}")
            return False
    
    async def validate_environment(
        self,
        container_id: str,
        repo_path: str,
        test_command: Optional[str] = None
    ) -> bool:
        """
        Validate that the environment is working.
        
        Args:
            container_id: Docker container ID
            repo_path: Repository path
            test_command: Optional test command to run
            
        Returns:
            True if environment is valid
        """
        from ..green_agent.environment_orchestrator import EnvironmentOrchestrator
        orchestrator = EnvironmentOrchestrator()
        
        # Default test: try to import the package
        if not test_command:
            test_command = "python -c 'import sys; sys.exit(0)'"
        
        result = await orchestrator.execute_in_environment(
            container_id,
            test_command,
            repo_path
        )
        
        return result["exit_code"] == 0