"""Dependency Fixer for resolving package issues"""

import re
import logging
from typing import Dict, Any, Optional, List
import json

logger = logging.getLogger(__name__)


class DependencyFixer:
    """
    Fixes common dependency issues in Python projects.
    """
    
    def __init__(self):
        # Known package replacements
        self.package_replacements = {
            "tensorflow-gpu": "tensorflow",
            "pyyaml": "PyYAML",
            "mysqlclient": "pymysql",
            "python-opencv": "opencv-python",
            "pillow": "Pillow",
            "sklearn": "scikit-learn",
            "cv2": "opencv-python"
        }
        
        # Known version fixes
        self.version_fixes = {
            "numpy": {
                "1.19.0": "1.19.5",  # Fix for Python 3.9
                "1.20.0": "1.21.0"   # Fix for M1 Macs
            },
            "scipy": {
                "1.5.0": "1.5.4",
                "1.6.0": "1.6.3"
            }
        }
        
        # Package alternatives
        self.alternatives = {
            "mysqlclient": ["pymysql", "mysql-connector-python"],
            "psycopg2": ["psycopg2-binary"],
            "tensorflow": ["tensorflow-cpu"],
            "torch": ["torch-cpu"]
        }
    
    async def fix_missing_package(self, package_name: str) -> Optional[Dict[str, Any]]:
        """
        Fix a missing package error.
        
        Args:
            package_name: Name of the missing package
            
        Returns:
            Fix dictionary or None
        """
        # Clean package name (remove version specifiers)
        clean_name = re.sub(r'[<>=!~].*', '', package_name).strip()
        
        # Check if we have a known replacement
        if clean_name.lower() in self.package_replacements:
            replacement = self.package_replacements[clean_name.lower()]
            return {
                "type": "replace_package",
                "description": f"Replace {package_name} with {replacement}",
                "old_package": package_name,
                "new_package": replacement
            }
        
        # Check if we have alternatives
        if clean_name.lower() in self.alternatives:
            alternatives = self.alternatives[clean_name.lower()]
            # Try the first alternative
            return {
                "type": "replace_package",
                "description": f"Replace {package_name} with alternative {alternatives[0]}",
                "old_package": package_name,
                "new_package": alternatives[0]
            }
        
        # Try to find on PyPI (simplified - would need actual API call)
        # For now, try common patterns
        patterns = [
            clean_name.lower(),
            clean_name.replace("_", "-"),
            clean_name.replace("-", "_"),
            f"py{clean_name}",
            f"python-{clean_name}"
        ]
        
        for pattern in patterns:
            if pattern != clean_name:
                return {
                    "type": "replace_package",
                    "description": f"Try alternative package name {pattern}",
                    "old_package": package_name,
                    "new_package": pattern
                }
        
        # Last resort: skip the package
        return {
            "type": "modify_requirements",
            "description": f"Remove problematic package {package_name}",
            "action": "remove",
            "package": package_name
        }
    
    async def fix_broken_url(
        self,
        url: str,
        requirements_file: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Fix a broken URL in dependencies.
        
        Args:
            url: The broken URL
            requirements_file: Path to requirements file
            
        Returns:
            Fix dictionary or None
        """
        # Extract package name from URL if possible
        package_match = re.search(r'/([^/]+)\.(tar\.gz|whl|zip)$', url)
        if package_match:
            package_name = package_match.group(1)
            # Remove version from package name
            package_name = re.sub(r'-\d+\..*', '', package_name)
            
            return {
                "type": "replace_package",
                "description": f"Replace URL {url} with package from PyPI",
                "old_package": url,
                "new_package": package_name
            }
        
        # If it's a git URL, try HTTPS instead of SSH
        if url.startswith("git@"):
            https_url = url.replace("git@github.com:", "https://github.com/")
            return {
                "type": "modify_requirements",
                "description": "Replace SSH URL with HTTPS",
                "old_url": url,
                "new_url": https_url
            }
        
        # Remove the problematic URL
        return {
            "type": "modify_requirements",
            "description": f"Remove broken URL {url}",
            "action": "remove",
            "url": url
        }
    
    async def resolve_version_conflict(
        self,
        requirements_file: Optional[str],
        error_analysis: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve version conflicts between packages.
        
        Args:
            requirements_file: Path to requirements file
            error_analysis: Error analysis details
            
        Returns:
            Fix dictionary or None
        """
        # Extract conflicting packages from error
        # This is simplified - would need proper parsing
        
        # Common fix: remove version pins
        return {
            "type": "modify_requirements",
            "description": "Remove version pins to resolve conflicts",
            "action": "unpin_versions",
            "file_path": requirements_file or "requirements.txt"
        }
    
    async def fix_import_error(self, module_name: str) -> Optional[Dict[str, Any]]:
        """
        Fix an import error by installing the right package.
        
        Args:
            module_name: Name of the module that can't be imported
            
        Returns:
            Fix dictionary or None
        """
        # Map common module names to packages
        module_to_package = {
            "cv2": "opencv-python",
            "sklearn": "scikit-learn",
            "PIL": "Pillow",
            "yaml": "PyYAML",
            "MySQLdb": "mysqlclient",
            "psycopg2": "psycopg2-binary",
            "wx": "wxPython",
            "cairo": "pycairo",
            "gi": "PyGObject"
        }
        
        if module_name in module_to_package:
            package = module_to_package[module_name]
            return {
                "type": "run_commands",
                "description": f"Install package for module {module_name}",
                "commands": [f"pip install {package}"]
            }
        
        # Try installing module name directly
        return {
            "type": "run_commands",
            "description": f"Try installing {module_name} directly",
            "commands": [f"pip install {module_name}"]
        }
    
    def parse_requirements(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse requirements.txt content.
        
        Args:
            content: Requirements file content
            
        Returns:
            List of parsed requirements
        """
        requirements = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse different formats
            if line.startswith('-e'):
                # Editable install
                requirements.append({
                    "type": "editable",
                    "line": line
                })
            elif line.startswith('git+'):
                # Git URL
                requirements.append({
                    "type": "git",
                    "url": line
                })
            elif '://' in line:
                # URL
                requirements.append({
                    "type": "url",
                    "url": line
                })
            else:
                # Regular package
                match = re.match(r'^([a-zA-Z0-9\-_]+)(.*)$', line)
                if match:
                    requirements.append({
                        "type": "package",
                        "name": match.group(1),
                        "version_spec": match.group(2).strip()
                    })
        
        return requirements
    
    def generate_requirements(self, requirements: List[Dict[str, Any]]) -> str:
        """
        Generate requirements.txt content from parsed requirements.
        
        Args:
            requirements: List of requirement dictionaries
            
        Returns:
            Requirements file content
        """
        lines = []
        
        for req in requirements:
            if req["type"] == "editable":
                lines.append(req["line"])
            elif req["type"] == "git":
                lines.append(req["url"])
            elif req["type"] == "url":
                lines.append(req["url"])
            elif req["type"] == "package":
                line = req["name"]
                if req.get("version_spec"):
                    line += req["version_spec"]
                lines.append(line)
        
        return '\n'.join(lines)