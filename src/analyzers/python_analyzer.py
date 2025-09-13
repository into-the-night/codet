"""Python-specific code analyzer"""

from pathlib import Path
from typing import List, Dict, Any
import ast
import logging

from .analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity
from ..utils.snippet_extractor import extract_code_snippet, extract_function_snippet


logger = logging.getLogger(__name__)


class PythonAnalyzer(BaseAnalyzer):
    """Analyzer for Python code quality issues"""
    
    def analyze(self, file_path: Path) -> List[CodeIssue]:
        """Analyze Python file for quality issues"""
        issues = []
        
        if not self.supports_language(file_path.suffix):
            return issues
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content, filename=str(file_path))
            
            # Run various checks
            issues.extend(self._check_complexity(tree, file_path, content))
            issues.extend(self._check_docstrings(tree, file_path))
            issues.extend(self._check_imports(tree, file_path))

            
            
        except SyntaxError as e:
            issues.append(CodeIssue(
                category=IssueCategory.STYLE,
                severity=IssueSeverity.CRITICAL,
                title="Syntax Error",
                description=f"Python syntax error: {e.msg}",
                file_path=file_path,
                line_number=e.lineno,
                column_number=e.offset,
                suggestion="Fix the syntax error before proceeding with analysis",
                code_snippet=extract_code_snippet(file_path, e.lineno) if e.lineno else None
            ))
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
        
        return issues
    
    def _check_complexity(self, tree: ast.AST, file_path: Path, content: str) -> List[CodeIssue]:
        """Check for complexity issues"""
        issues = []
        
        class ComplexityVisitor(ast.NodeVisitor):
            def __init__(self):
                self.issues = []
            
            def visit_FunctionDef(self, node):
                # Simple complexity check: count number of branches
                complexity = 1  # Base complexity
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                        complexity += 1
                
                if complexity > 10:
                    self.issues.append(CodeIssue(
                        category=IssueCategory.COMPLEXITY,
                        severity=IssueSeverity.HIGH if complexity > 15 else IssueSeverity.MEDIUM,
                        title=f"High Cyclomatic Complexity",
                        description=f"Function '{node.name}' has complexity of {complexity}",
                        file_path=file_path,
                        line_number=node.lineno,
                        suggestion="Consider breaking this function into smaller, more focused functions",
                        code_snippet=extract_function_snippet(file_path, node.lineno)
                    ))
                
                self.generic_visit(node)
        
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        return visitor.issues
    
    def _check_docstrings(self, tree: ast.AST, file_path: Path) -> List[CodeIssue]:
        """Check for missing docstrings"""
        issues = []
        
        class DocstringVisitor(ast.NodeVisitor):
            def __init__(self):
                self.issues = []
            
            def visit_FunctionDef(self, node):
                if not ast.get_docstring(node) and not node.name.startswith('_'):
                    self.issues.append(CodeIssue(
                        category=IssueCategory.DOCUMENTATION,
                        severity=IssueSeverity.LOW,
                        title="Missing Docstring",
                        description=f"Public function '{node.name}' lacks a docstring",
                        file_path=file_path,
                        line_number=node.lineno,
                        suggestion="Add a docstring describing the function's purpose, parameters, and return value",
                        code_snippet=extract_function_snippet(file_path, node.lineno)
                    ))
                self.generic_visit(node)
            
            def visit_ClassDef(self, node):
                if not ast.get_docstring(node):
                    self.issues.append(CodeIssue(
                        category=IssueCategory.DOCUMENTATION,
                        severity=IssueSeverity.LOW,
                        title="Missing Class Docstring",
                        description=f"Class '{node.name}' lacks a docstring",
                        file_path=file_path,
                        line_number=node.lineno,
                        suggestion="Add a docstring describing the class purpose and usage",
                        code_snippet=extract_code_snippet(file_path, node.lineno)
                    ))
                self.generic_visit(node)
        
        visitor = DocstringVisitor()
        visitor.visit(tree)
        return visitor.issues
    
    def _check_imports(self, tree: ast.AST, file_path: Path) -> List[CodeIssue]:
        """Check for import issues"""
        issues = []
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    imports.append((f"{module}.{alias.name}", node.lineno))
        
        # Check for duplicate imports
        seen = {}
        for imp, line in imports:
            if imp in seen:
                issues.append(CodeIssue(
                    category=IssueCategory.STYLE,
                    severity=IssueSeverity.LOW,
                    title="Duplicate Import",
                    description=f"Module '{imp}' is imported multiple times",
                    file_path=file_path,
                    line_number=line,
                    suggestion=f"Remove duplicate import (first import at line {seen[imp]})",
                    code_snippet=extract_code_snippet(file_path, line)
                ))
            else:
                seen[imp] = line
        
        return issues
    
    def supports_language(self, language: str) -> bool:
        """Check if analyzer supports Python"""
        return language.lower() in ['.py', 'python']
    
    @property
    def name(self) -> str:
        return "Python Analyzer"
