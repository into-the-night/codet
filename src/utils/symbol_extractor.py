"""Utility to extract code symbols (functions, classes) from files for RAG queries"""

import ast
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def extract_symbols(file_path: str, content: str) -> Tuple[List[str], List[str]]:
    """
    Extract function and class names from a source file
    
    Args:
        file_path: Path to the file
        content: File content
        
    Returns:
        Tuple of (functions, classes)
    """
    extension = Path(file_path).suffix.lower()
    
    if extension == '.py':
        return _extract_python_symbols(content)
    elif extension in ['.js', '.jsx', '.ts', '.tsx']:
        return _extract_javascript_symbols(content)
    else:
        # Unsupported language, return empty
        return ([], [])


def _extract_python_symbols(content: str) -> Tuple[List[str], List[str]]:
    """Extract Python functions and classes using AST"""
    functions = []
    classes = []
    
    try:
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
    
    except Exception as e:
        logger.debug(f"Error parsing Python code: {e}")
    
    return (list(set(functions)), list(set(classes)))


def _extract_javascript_symbols(content: str) -> Tuple[List[str], List[str]]:
    """Extract JavaScript/TypeScript functions and classes using regex"""
    import re
    
    functions = []
    classes = []
    
    try:
        # Extract function declarations
        # function foo() { }
        func_pattern = r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\('
        functions.extend(re.findall(func_pattern, content))
        
        # Extract arrow functions assigned to variables
        # const foo = () => { }
        arrow_pattern = r'(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>'
        functions.extend(re.findall(arrow_pattern, content))
        
        # Extract classes
        # class Foo { }
        class_pattern = r'class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)'
        classes.extend(re.findall(class_pattern, content))
        
        # Extract method names from objects (limited support)
        # { foo() { }, bar: function() { } }
        method_pattern = r'([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{'
        functions.extend(re.findall(method_pattern, content))
    
    except Exception as e:
        logger.debug(f"Error parsing JavaScript code: {e}")
    
    return (list(set(functions)), list(set(classes)))
