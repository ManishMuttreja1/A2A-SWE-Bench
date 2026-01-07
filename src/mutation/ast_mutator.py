"""AST-based code mutation for Python files"""

import ast
import random
import string
import logging
from typing import Dict, Any, List, Set, Optional
from dataclasses import dataclass
import astor

logger = logging.getLogger(__name__)


@dataclass
class MutationConfig:
    """Configuration for mutations"""
    rename_variables: bool = True
    rename_functions: bool = True
    rename_classes: bool = True
    reorder_functions: bool = True
    reorder_imports: bool = True
    inject_comments: bool = True
    modify_constants: bool = True
    preserve_functionality: bool = True
    mutation_rate: float = 0.3


class VariableRenamer(ast.NodeTransformer):
    """Rename variables while preserving scope"""
    
    def __init__(self, renames: Dict[str, str]):
        self.renames = renames
        self.scope_stack = []
    
    def visit_Name(self, node):
        """Rename variable references"""
        if node.id in self.renames:
            node.id = self.renames[node.id]
        return node
    
    def visit_FunctionDef(self, node):
        """Handle function definitions"""
        # Rename function if needed
        if node.name in self.renames:
            node.name = self.renames[node.name]
        
        # Rename arguments
        for arg in node.args.args:
            if arg.arg in self.renames:
                arg.arg = self.renames[arg.arg]
        
        # Visit body
        self.generic_visit(node)
        return node
    
    def visit_ClassDef(self, node):
        """Handle class definitions"""
        if node.name in self.renames:
            node.name = self.renames[node.name]
        self.generic_visit(node)
        return node


class FunctionReorderer(ast.NodeTransformer):
    """Reorder functions while preserving dependencies"""
    
    def visit_Module(self, node):
        """Reorder functions at module level"""
        # Separate different types of statements
        imports = []
        functions = []
        classes = []
        other = []
        
        for stmt in node.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                imports.append(stmt)
            elif isinstance(stmt, ast.FunctionDef):
                functions.append(stmt)
            elif isinstance(stmt, ast.ClassDef):
                classes.append(stmt)
            else:
                other.append(stmt)
        
        # Analyze dependencies
        deps = self._analyze_dependencies(functions)
        
        # Reorder functions respecting dependencies
        reordered_functions = self._topological_sort(functions, deps)
        
        # Shuffle independent functions
        independent_groups = self._find_independent_groups(reordered_functions, deps)
        for group in independent_groups:
            random.shuffle(group)
        
        # Reconstruct body
        node.body = imports + classes + self._flatten(independent_groups) + other
        
        return node
    
    def _analyze_dependencies(self, functions: List[ast.FunctionDef]) -> Dict[str, Set[str]]:
        """Analyze function dependencies"""
        func_names = {f.name for f in functions}
        deps = {}
        
        for func in functions:
            deps[func.name] = set()
            for node in ast.walk(func):
                if isinstance(node, ast.Name) and node.id in func_names:
                    if node.id != func.name:  # Don't count self-reference
                        deps[func.name].add(node.id)
        
        return deps
    
    def _topological_sort(
        self,
        functions: List[ast.FunctionDef],
        deps: Dict[str, Set[str]]
    ) -> List[ast.FunctionDef]:
        """Sort functions by dependencies"""
        # Simple topological sort
        sorted_names = []
        remaining = set(f.name for f in functions)
        
        while remaining:
            # Find functions with no dependencies
            no_deps = [
                name for name in remaining
                if not (deps.get(name, set()) & remaining)
            ]
            
            if not no_deps:
                # Circular dependency, just take one
                no_deps = [remaining.pop()]
            
            sorted_names.extend(no_deps)
            remaining -= set(no_deps)
        
        # Return functions in sorted order
        func_dict = {f.name: f for f in functions}
        return [func_dict[name] for name in sorted_names]
    
    def _find_independent_groups(
        self,
        functions: List[ast.FunctionDef],
        deps: Dict[str, Set[str]]
    ) -> List[List[ast.FunctionDef]]:
        """Find groups of independent functions"""
        groups = []
        current_group = []
        
        for func in functions:
            # Check if function depends on any in current group
            depends_on_group = any(
                f.name in deps.get(func.name, set())
                for f in current_group
            )
            
            if depends_on_group:
                # Start new group
                if current_group:
                    groups.append(current_group)
                current_group = [func]
            else:
                current_group.append(func)
        
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def _flatten(self, groups: List[List[ast.FunctionDef]]) -> List[ast.FunctionDef]:
        """Flatten groups of functions"""
        result = []
        for group in groups:
            result.extend(group)
        return result


class ConstantModifier(ast.NodeTransformer):
    """Modify constants while preserving behavior"""
    
    def visit_Constant(self, node):
        """Modify constant values"""
        if isinstance(node.value, (int, float)):
            # Don't modify special values
            if node.value not in [0, 1, -1, None, True, False]:
                # Add small perturbation
                if isinstance(node.value, int):
                    # Keep same value but change representation
                    node.value = node.value  # Could change to hex, etc.
                elif isinstance(node.value, float):
                    # Add tiny epsilon that doesn't affect behavior
                    node.value = node.value + 0.0
        elif isinstance(node.value, str):
            # Don't modify empty strings or single chars
            if len(node.value) > 1:
                # Could add zero-width spaces or change quotes
                pass
        
        return node


class ASTMutator:
    """
    Advanced AST-based code mutator for Python.
    Modifies code structure while preserving functionality.
    """
    
    def __init__(self, config: Optional[MutationConfig] = None):
        self.config = config or MutationConfig()
        self.stats = {
            "files_mutated": 0,
            "variables_renamed": 0,
            "functions_renamed": 0,
            "functions_reordered": 0,
            "constants_modified": 0
        }
    
    def mutate_code(self, code: str, filename: str = "unknown.py") -> str:
        """
        Mutate Python code using AST transformations.
        
        Args:
            code: Python source code
            filename: Name of file (for error reporting)
            
        Returns:
            Mutated code
        """
        try:
            # Parse code to AST
            tree = ast.parse(code, filename)
            
            # Apply mutations
            if random.random() < self.config.mutation_rate:
                tree = self._apply_mutations(tree)
                self.stats["files_mutated"] += 1
            
            # Convert back to code
            return astor.to_source(tree)
            
        except SyntaxError as e:
            logger.error(f"Syntax error in {filename}: {e}")
            return code  # Return original on error
        except Exception as e:
            logger.error(f"Mutation error in {filename}: {e}")
            return code
    
    def _apply_mutations(self, tree: ast.Module) -> ast.Module:
        """Apply various mutations to AST"""
        # Collect renameable identifiers
        identifiers = self._collect_identifiers(tree)
        
        # Generate renames
        renames = {}
        
        if self.config.rename_variables:
            var_renames = self._generate_renames(
                identifiers["variables"],
                "var"
            )
            renames.update(var_renames)
            self.stats["variables_renamed"] += len(var_renames)
        
        if self.config.rename_functions:
            func_renames = self._generate_renames(
                identifiers["functions"],
                "func"
            )
            renames.update(func_renames)
            self.stats["functions_renamed"] += len(func_renames)
        
        if self.config.rename_classes:
            class_renames = self._generate_renames(
                identifiers["classes"],
                "Class"
            )
            renames.update(class_renames)
        
        # Apply renames
        if renames:
            renamer = VariableRenamer(renames)
            tree = renamer.visit(tree)
        
        # Reorder functions
        if self.config.reorder_functions:
            reorderer = FunctionReorderer()
            tree = reorderer.visit(tree)
            self.stats["functions_reordered"] += 1
        
        # Modify constants
        if self.config.modify_constants:
            modifier = ConstantModifier()
            tree = modifier.visit(tree)
            self.stats["constants_modified"] += 1
        
        # Fix missing locations
        ast.fix_missing_locations(tree)
        
        return tree
    
    def _collect_identifiers(self, tree: ast.Module) -> Dict[str, Set[str]]:
        """Collect all identifiers in the code"""
        identifiers = {
            "variables": set(),
            "functions": set(),
            "classes": set()
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                # Check if it's not a builtin
                if not self._is_builtin(node.id):
                    identifiers["variables"].add(node.id)
            elif isinstance(node, ast.FunctionDef):
                if not node.name.startswith("__"):  # Don't rename magic methods
                    identifiers["functions"].add(node.name)
            elif isinstance(node, ast.ClassDef):
                identifiers["classes"].add(node.name)
        
        # Remove function/class names from variables
        identifiers["variables"] -= identifiers["functions"]
        identifiers["variables"] -= identifiers["classes"]
        
        return identifiers
    
    def _is_builtin(self, name: str) -> bool:
        """Check if name is a Python builtin"""
        import builtins
        return hasattr(builtins, name)
    
    def _generate_renames(
        self,
        names: Set[str],
        prefix: str
    ) -> Dict[str, str]:
        """Generate rename mapping for identifiers"""
        renames = {}
        
        for name in names:
            # Don't rename if already renamed or special
            if name.startswith("_") or name.isupper():
                continue
            
            # Random decision to rename
            if random.random() < self.config.mutation_rate:
                # Generate new name
                if self.config.preserve_functionality:
                    # Semantic renaming
                    new_name = self._semantic_rename(name, prefix)
                else:
                    # Random renaming
                    new_name = self._random_rename(prefix)
                
                renames[name] = new_name
        
        return renames
    
    def _semantic_rename(self, old_name: str, prefix: str) -> str:
        """Generate semantically similar new name"""
        # Preserve camelCase/snake_case style
        if "_" in old_name:
            # snake_case
            parts = old_name.split("_")
            return f"{prefix}_{'_'.join(parts)}"
        elif old_name[0].isupper():
            # CamelCase
            return f"{prefix}{old_name}"
        else:
            # camelCase
            return f"{prefix}{old_name[0].upper()}{old_name[1:]}"
    
    def _random_rename(self, prefix: str) -> str:
        """Generate random new name"""
        suffix = ''.join(random.choices(string.ascii_lowercase, k=6))
        return f"{prefix}_{suffix}"
    
    def mutate_file(self, filepath: str) -> bool:
        """
        Mutate a Python file in place.
        
        Args:
            filepath: Path to Python file
            
        Returns:
            Success boolean
        """
        try:
            with open(filepath, 'r') as f:
                original = f.read()
            
            mutated = self.mutate_code(original, filepath)
            
            if mutated != original:
                with open(filepath, 'w') as f:
                    f.write(mutated)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to mutate file {filepath}: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get mutation statistics"""
        return {
            **self.stats,
            "config": {
                "mutation_rate": self.config.mutation_rate,
                "preserve_functionality": self.config.preserve_functionality
            }
        }