"""Python codebase parser using AST"""

import ast
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from ..agents.schemas import CodeChunk, CodeTypeEnum
from ..utils import FileFilter


class CodebaseParser:
    """Parser for extracting code chunks from Python files using AST"""
    
    def __init__(self, file_filter: Optional[FileFilter] = None):
        """
        Initialize the parser with optional file filtering
        
        Args:
            file_filter: FileFilter instance for consistent file filtering
        """
        self.chunks: List[CodeChunk] = []
        self.file_filter = file_filter
    
    def parse_file(self, file_path: str) -> List[CodeChunk]:
        """Parse a single Python file and extract code chunks"""
        chunks = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            tree = ast.parse(content, filename=file_path)
            
            # Extract module-level docstring
            module_docstring = ast.get_docstring(tree)
            if module_docstring:
                chunks.append(self._create_module_chunk(file_path, module_docstring, len(lines)))
            
            # Walk through the AST
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    chunk = self._extract_function(node, file_path, lines, is_method=False)
                    if chunk:
                        chunks.append(chunk)
                
                elif isinstance(node, ast.ClassDef):
                    class_chunk = self._extract_class(node, file_path, lines)
                    if class_chunk:
                        chunks.append(class_chunk)
                    
                    # Extract methods within the class
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_chunk = self._extract_function(item, file_path, lines, 
                                                                is_method=True, 
                                                                class_name=node.name)
                            if method_chunk:
                                chunks.append(method_chunk)
        
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
        
        return chunks
    
    def parse_directory(self, directory: str, extensions: List[str] = None) -> List[CodeChunk]:
        """Parse all Python files in a directory recursively"""
        if extensions is None:
            extensions = ['.py']
        
        chunks = []
        path = Path(directory)
        
        # Use file filter if provided, otherwise create a default one
        if self.file_filter:
            file_filter = self.file_filter
        else:
            # Create a file filter with default patterns and gitignore support
            file_filter = FileFilter.from_path(path)
        
        # Get filtered files
        files = file_filter.iter_files(path, extensions=extensions)
        
        for file_path in files:
            file_chunks = self.parse_file(str(file_path))
            chunks.extend(file_chunks)
        
        return chunks
    
    def _create_module_chunk(self, file_path: str, docstring: str, total_lines: int) -> CodeChunk:
        """Create a chunk for module-level documentation"""
        return CodeChunk(
            name=Path(file_path).stem,
            signature=f"module {Path(file_path).stem}",
            code_type=CodeTypeEnum.MODULE,
            docstring=docstring,
            code=docstring,
            line=1,
            line_from=1,
            line_to=total_lines,
            context={
                "module": Path(file_path).stem,
                "file_path": file_path,
                "file_name": Path(file_path).name,
            }
        )
    
    def _extract_function(self, node: ast.FunctionDef, file_path: str, lines: List[str], 
                         is_method: bool = False, class_name: Optional[str] = None) -> Optional[CodeChunk]:
        """Extract function or method information"""
        try:
            # Get function signature
            signature = self._get_function_signature(node, is_method)
            
            # Get docstring
            docstring = ast.get_docstring(node)
            
            # Get the actual code
            start_line = node.lineno - 1  # AST uses 1-based indexing
            end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 10
            
            # Ensure end_line doesn't exceed file length
            end_line = min(end_line, len(lines))
            
            code_lines = lines[start_line:end_line]
            code = '\n'.join(code_lines)
            
            # Create context
            context = {
                "module": Path(file_path).stem,
                "file_path": file_path,
                "file_name": Path(file_path).name,
            }
            
            if class_name:
                context["class_name"] = class_name
            
            # Determine code type
            code_type = CodeTypeEnum.METHOD if is_method else CodeTypeEnum.FUNCTION
            
            # Handle property decorators
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == 'property':
                    code_type = CodeTypeEnum.PROPERTY
                    break
            
            return CodeChunk(
                name=node.name,
                signature=signature,
                code_type=code_type,
                docstring=docstring,
                code=code,
                line=node.lineno,
                line_from=node.lineno,
                line_to=end_line,
                context=context,
                natural_language=self._code_to_natural_language(node.name, signature, docstring, code_type)
            )
        
        except Exception as e:
            print(f"Error extracting function {node.name}: {e}")
            return None
    
    def _extract_class(self, node: ast.ClassDef, file_path: str, lines: List[str]) -> Optional[CodeChunk]:
        """Extract class information"""
        try:
            # Get class signature
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(f"{base.value.id if isinstance(base.value, ast.Name) else '...'}.{base.attr}")
            
            signature = f"class {node.name}"
            if bases:
                signature += f"({', '.join(bases)})"
            
            # Get docstring
            docstring = ast.get_docstring(node)
            
            # Get class definition (just the class statement and docstring)
            start_line = node.lineno - 1
            
            # Find the end of the class docstring
            end_line = start_line + 5  # Default
            for item in node.body:
                if isinstance(item, ast.Expr) and isinstance(item.value, ast.Str):
                    end_line = item.end_lineno if hasattr(item, 'end_lineno') else start_line + 5
                    break
                else:
                    # First non-docstring item
                    end_line = item.lineno - 1 if hasattr(item, 'lineno') else start_line + 5
                    break
            
            end_line = min(end_line, len(lines))
            
            code_lines = lines[start_line:end_line]
            code = '\n'.join(code_lines)
            
            # Check if it's an Enum
            code_type = CodeTypeEnum.CLASS
            for base in node.bases:
                if isinstance(base, ast.Name) and 'Enum' in base.id:
                    code_type = CodeTypeEnum.ENUM
                    break
            
            return CodeChunk(
                name=node.name,
                signature=signature,
                code_type=code_type,
                docstring=docstring,
                code=code,
                line=node.lineno,
                line_from=node.lineno,
                line_to=end_line,
                context={
                    "module": Path(file_path).stem,
                    "file_path": file_path,
                    "file_name": Path(file_path).name,
                },
                natural_language=self._code_to_natural_language(node.name, signature, docstring, code_type)
            )
        
        except Exception as e:
            print(f"Error extracting class {node.name}: {e}")
            return None
    
    def _get_function_signature(self, node: ast.FunctionDef, is_method: bool) -> str:
        """Generate function signature from AST node"""
        args = []
        
        # Handle arguments
        for i, arg in enumerate(node.args.args):
            # Skip 'self' for methods
            if is_method and i == 0 and arg.arg == 'self':
                continue
            
            arg_str = arg.arg
            
            # Add type annotation if available
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            
            args.append(arg_str)
        
        # Handle *args
        if node.args.vararg:
            arg_str = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                arg_str += f": {ast.unparse(node.args.vararg.annotation)}"
            args.append(arg_str)
        
        # Handle **kwargs
        if node.args.kwarg:
            arg_str = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                arg_str += f": {ast.unparse(node.args.kwarg.annotation)}"
            args.append(arg_str)
        
        # Build signature
        signature = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({', '.join(args)})"
        
        # Add return type if available
        if node.returns:
            signature += f" -> {ast.unparse(node.returns)}"
        
        return signature
    
    def _code_to_natural_language(self, name: str, signature: str, docstring: Optional[str], 
                                 code_type: CodeTypeEnum) -> str:
        """Convert code to natural language for NLP-based search"""
        parts = []
        
        # Add code type
        if code_type == CodeTypeEnum.FUNCTION:
            parts.append(f"Function {name}")
        elif code_type == CodeTypeEnum.METHOD:
            parts.append(f"Method {name}")
        elif code_type == CodeTypeEnum.CLASS:
            parts.append(f"Class {name}")
        elif code_type == CodeTypeEnum.PROPERTY:
            parts.append(f"Property {name}")
        elif code_type == CodeTypeEnum.ENUM:
            parts.append(f"Enumeration {name}")
        
        # Parse signature for natural language
        if code_type in [CodeTypeEnum.FUNCTION, CodeTypeEnum.METHOD]:
            # Extract parameters from signature
            if '(' in signature and ')' in signature:
                params_str = signature[signature.find('(')+1:signature.find(')')]
                if params_str:
                    params = [p.strip().split(':')[0] for p in params_str.split(',')]
                    parts.append(f"takes parameters {', '.join(params)}")
            
            # Extract return type
            if '->' in signature:
                return_type = signature.split('->')[-1].strip()
                parts.append(f"returns {return_type}")
        
        # Add docstring if available
        if docstring:
            # Clean and add first line of docstring
            first_line = docstring.strip().split('\n')[0]
            parts.append(first_line.lower())
        
        return '. '.join(parts)
