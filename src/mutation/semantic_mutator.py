"""Semantic-aware code mutations that preserve program behavior"""

import ast
import random
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import astor

logger = logging.getLogger(__name__)


@dataclass
class SemanticRule:
    """Rule for semantic transformation"""
    name: str
    pattern: str
    replacement: str
    condition: Optional[str] = None


class LoopTransformer(ast.NodeTransformer):
    """Transform loop structures while preserving semantics"""
    
    def visit_For(self, node):
        """Transform for loops to while loops when possible"""
        self.generic_visit(node)
        
        # Only transform simple range loops
        if (isinstance(node.iter, ast.Call) and
            isinstance(node.iter.func, ast.Name) and
            node.iter.func.id == 'range'):
            
            # Don't transform if loop variable is modified in body
            if self._is_loop_var_modified(node):
                return node
            
            # Convert to while loop
            return self._for_to_while(node)
        
        return node
    
    def _is_loop_var_modified(self, node: ast.For) -> bool:
        """Check if loop variable is modified in loop body"""
        loop_var = node.target.id if isinstance(node.target, ast.Name) else None
        if not loop_var:
            return True
        
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == loop_var:
                        return True
        
        return False
    
    def _for_to_while(self, node: ast.For) -> List[ast.stmt]:
        """Convert for loop to while loop"""
        # Extract range arguments
        range_args = node.iter.args
        
        if len(range_args) == 1:
            start = ast.Constant(value=0)
            stop = range_args[0]
            step = ast.Constant(value=1)
        elif len(range_args) == 2:
            start, stop = range_args
            step = ast.Constant(value=1)
        elif len(range_args) == 3:
            start, stop, step = range_args
        else:
            return node
        
        # Create initialization
        loop_var = node.target
        init = ast.Assign(
            targets=[loop_var],
            value=start
        )
        
        # Create condition
        condition = ast.Compare(
            left=loop_var,
            ops=[ast.Lt()],
            comparators=[stop]
        )
        
        # Create increment
        increment = ast.AugAssign(
            target=loop_var,
            op=ast.Add(),
            value=step
        )
        
        # Create while loop
        while_loop = ast.While(
            test=condition,
            body=node.body + [increment],
            orelse=node.orelse
        )
        
        return [init, while_loop]


class ConditionalTransformer(ast.NodeTransformer):
    """Transform conditional structures"""
    
    def visit_If(self, node):
        """Transform if statements"""
        self.generic_visit(node)
        
        # Try to simplify nested ifs
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            # Can combine into elif
            pass
        
        # Transform simple if-else to ternary (in assignments)
        parent = getattr(node, 'parent', None)
        if (parent and isinstance(parent, ast.Assign) and
            len(node.body) == 1 and len(node.orelse) == 1):
            # Could transform to ternary
            pass
        
        return node
    
    def visit_Compare(self, node):
        """Transform comparisons"""
        self.generic_visit(node)
        
        # Transform chained comparisons
        if len(node.ops) > 1:
            # Could split into multiple comparisons
            pass
        
        # Normalize comparison operators
        for i, op in enumerate(node.ops):
            if isinstance(op, ast.Lt):
                # Could change to: not (a >= b)
                pass
            elif isinstance(op, ast.Gt):
                # Could change to: not (a <= b)
                pass
        
        return node


class FunctionInliner(ast.NodeTransformer):
    """Inline small functions when safe"""
    
    def __init__(self):
        self.functions = {}
        self.inlinable = set()
    
    def visit_Module(self, node):
        """Analyze module for inlinable functions"""
        # First pass: collect functions
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                self.functions[stmt.name] = stmt
                if self._is_inlinable(stmt):
                    self.inlinable.add(stmt.name)
        
        # Second pass: inline calls
        self.generic_visit(node)
        
        return node
    
    def visit_Call(self, node):
        """Inline function calls when possible"""
        self.generic_visit(node)
        
        if (isinstance(node.func, ast.Name) and
            node.func.id in self.inlinable):
            
            func = self.functions[node.func.id]
            
            # Only inline if arguments match parameters
            if self._can_inline_call(func, node):
                return self._inline_function(func, node)
        
        return node
    
    def _is_inlinable(self, func: ast.FunctionDef) -> bool:
        """Check if function can be inlined"""
        # Only inline small, simple functions
        if len(func.body) > 3:
            return False
        
        # Don't inline recursive functions
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == func.name:
                    return False
        
        # Don't inline functions with complex control flow
        for node in ast.walk(func):
            if isinstance(node, (ast.While, ast.For, ast.Try)):
                return False
        
        # Must have single return
        returns = [n for n in ast.walk(func) if isinstance(n, ast.Return)]
        if len(returns) != 1:
            return False
        
        return True
    
    def _can_inline_call(self, func: ast.FunctionDef, call: ast.Call) -> bool:
        """Check if specific call can be inlined"""
        # Check argument count
        if len(call.args) != len(func.args.args):
            return False
        
        # Don't inline if has keyword args
        if call.keywords:
            return False
        
        return True
    
    def _inline_function(self, func: ast.FunctionDef, call: ast.Call) -> ast.expr:
        """Inline function call"""
        # Get return statement
        for stmt in func.body:
            if isinstance(stmt, ast.Return):
                # Substitute parameters with arguments
                return self._substitute_params(stmt.value, func, call)
        
        return call
    
    def _substitute_params(
        self,
        expr: ast.expr,
        func: ast.FunctionDef,
        call: ast.Call
    ) -> ast.expr:
        """Substitute function parameters with call arguments"""
        # Create mapping
        param_map = {}
        for param, arg in zip(func.args.args, call.args):
            param_map[param.arg] = arg
        
        # Substitute in expression
        class ParamSubstitutor(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id in param_map:
                    return param_map[node.id]
                return node
        
        return ParamSubstitutor().visit(expr)


class SemanticMutator:
    """
    Semantic-aware code mutator that preserves program behavior.
    Applies transformations that maintain correctness.
    """
    
    def __init__(self):
        self.transformers = [
            LoopTransformer(),
            ConditionalTransformer(),
            FunctionInliner()
        ]
        
        self.stats = {
            "loops_transformed": 0,
            "conditionals_transformed": 0,
            "functions_inlined": 0,
            "expressions_simplified": 0
        }
    
    def mutate_code(self, code: str) -> str:
        """
        Apply semantic-preserving mutations to code.
        
        Args:
            code: Python source code
            
        Returns:
            Mutated code
        """
        try:
            # Parse code
            tree = ast.parse(code)
            
            # Apply transformations
            for transformer in self.transformers:
                tree = transformer.visit(tree)
            
            # Apply additional semantic transforms
            tree = self._apply_semantic_transforms(tree)
            
            # Fix locations
            ast.fix_missing_locations(tree)
            
            # Convert back to code
            return astor.to_source(tree)
            
        except Exception as e:
            logger.error(f"Semantic mutation error: {e}")
            return code
    
    def _apply_semantic_transforms(self, tree: ast.Module) -> ast.Module:
        """Apply additional semantic transformations"""
        # Constant folding
        tree = self._fold_constants(tree)
        
        # Dead code elimination
        tree = self._eliminate_dead_code(tree)
        
        # Expression simplification
        tree = self._simplify_expressions(tree)
        
        return tree
    
    def _fold_constants(self, tree: ast.Module) -> ast.Module:
        """Fold constant expressions"""
        class ConstantFolder(ast.NodeTransformer):
            def visit_BinOp(self, node):
                self.generic_visit(node)
                
                # Try to evaluate if both operands are constants
                if (isinstance(node.left, ast.Constant) and
                    isinstance(node.right, ast.Constant)):
                    
                    try:
                        # Evaluate the operation
                        left_val = node.left.value
                        right_val = node.right.value
                        
                        if isinstance(node.op, ast.Add):
                            result = left_val + right_val
                        elif isinstance(node.op, ast.Sub):
                            result = left_val - right_val
                        elif isinstance(node.op, ast.Mult):
                            result = left_val * right_val
                        elif isinstance(node.op, ast.Div) and right_val != 0:
                            result = left_val / right_val
                        else:
                            return node
                        
                        return ast.Constant(value=result)
                    except:
                        return node
                
                return node
        
        folder = ConstantFolder()
        return folder.visit(tree)
    
    def _eliminate_dead_code(self, tree: ast.Module) -> ast.Module:
        """Remove unreachable code"""
        class DeadCodeEliminator(ast.NodeTransformer):
            def visit_If(self, node):
                self.generic_visit(node)
                
                # Check for constant conditions
                if isinstance(node.test, ast.Constant):
                    if node.test.value:
                        # Always true, keep only body
                        return node.body
                    else:
                        # Always false, keep only orelse
                        return node.orelse if node.orelse else []
                
                return node
            
            def visit_While(self, node):
                self.generic_visit(node)
                
                # Check for constant false condition
                if isinstance(node.test, ast.Constant) and not node.test.value:
                    # Loop never executes
                    return node.orelse if node.orelse else []
                
                return node
        
        eliminator = DeadCodeEliminator()
        return eliminator.visit(tree)
    
    def _simplify_expressions(self, tree: ast.Module) -> ast.Module:
        """Simplify complex expressions"""
        class ExpressionSimplifier(ast.NodeTransformer):
            def visit_BoolOp(self, node):
                self.generic_visit(node)
                
                # Simplify boolean expressions
                if isinstance(node.op, ast.And):
                    # Remove True values
                    values = [v for v in node.values
                             if not (isinstance(v, ast.Constant) and v.value is True)]
                    
                    if not values:
                        return ast.Constant(value=True)
                    elif len(values) == 1:
                        return values[0]
                    else:
                        node.values = values
                
                elif isinstance(node.op, ast.Or):
                    # Remove False values
                    values = [v for v in node.values
                             if not (isinstance(v, ast.Constant) and v.value is False)]
                    
                    if not values:
                        return ast.Constant(value=False)
                    elif len(values) == 1:
                        return values[0]
                    else:
                        node.values = values
                
                return node
            
            def visit_UnaryOp(self, node):
                self.generic_visit(node)
                
                # Simplify double negation
                if (isinstance(node.op, ast.Not) and
                    isinstance(node.operand, ast.UnaryOp) and
                    isinstance(node.operand.op, ast.Not)):
                    
                    return node.operand.operand
                
                return node
        
        simplifier = ExpressionSimplifier()
        tree = simplifier.visit(tree)
        self.stats["expressions_simplified"] += 1
        
        return tree
    
    def apply_equivalence_transform(self, code: str) -> str:
        """
        Apply mathematically equivalent transformations.
        
        Args:
            code: Python source code
            
        Returns:
            Transformed code
        """
        try:
            tree = ast.parse(code)
            
            # Apply De Morgan's laws
            tree = self._apply_de_morgan(tree)
            
            # Apply distributive property
            tree = self._apply_distributive(tree)
            
            # Apply associative property
            tree = self._apply_associative(tree)
            
            ast.fix_missing_locations(tree)
            return astor.to_source(tree)
            
        except Exception as e:
            logger.error(f"Equivalence transform error: {e}")
            return code
    
    def _apply_de_morgan(self, tree: ast.Module) -> ast.Module:
        """Apply De Morgan's laws to boolean expressions"""
        class DeMorganTransformer(ast.NodeTransformer):
            def visit_UnaryOp(self, node):
                self.generic_visit(node)
                
                if isinstance(node.op, ast.Not):
                    # Check for negated And/Or
                    if isinstance(node.operand, ast.BoolOp):
                        if isinstance(node.operand.op, ast.And):
                            # not (A and B) -> (not A) or (not B)
                            new_values = [
                                ast.UnaryOp(op=ast.Not(), operand=v)
                                for v in node.operand.values
                            ]
                            return ast.BoolOp(op=ast.Or(), values=new_values)
                        
                        elif isinstance(node.operand.op, ast.Or):
                            # not (A or B) -> (not A) and (not B)
                            new_values = [
                                ast.UnaryOp(op=ast.Not(), operand=v)
                                for v in node.operand.values
                            ]
                            return ast.BoolOp(op=ast.And(), values=new_values)
                
                return node
        
        return DeMorganTransformer().visit(tree)
    
    def _apply_distributive(self, tree: ast.Module) -> ast.Module:
        """Apply distributive property"""
        # A * (B + C) -> A * B + A * C
        # This is complex for general cases, simplified here
        return tree
    
    def _apply_associative(self, tree: ast.Module) -> ast.Module:
        """Apply associative property"""
        # (A + B) + C -> A + (B + C)
        # This changes grouping but not result
        return tree