"""Multi-language codebase parser using tree-sitter and AST"""

import ast
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from abc import ABC, abstractmethod
import tree_sitter
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from ..agents.schemas import CodeChunk, CodeTypeEnum
from ..utils import FileFilter


class LanguageParser(ABC):
    """Abstract base class for language-specific parsers"""
    
    @abstractmethod
    def parse_file(self, file_path: str, content: str) -> List[CodeChunk]:
        """Parse a file and return code chunks"""
        pass
    
    @abstractmethod
    def supports_file(self, file_path: str) -> bool:
        """Check if this parser supports the given file"""
        pass


class PythonASTParser(LanguageParser):
    """Python parser using AST (existing implementation)"""
    
    def supports_file(self, file_path: str) -> bool:
        return Path(file_path).suffix == '.py'
    
    def parse_file(self, file_path: str, content: str) -> List[CodeChunk]:
        """Parse Python file using AST"""
        chunks = []
        lines = content.splitlines()
        
        try:
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
            print(f"Error parsing Python file {file_path}: {e}")
        
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
                "language": "python"
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
                "language": "python"
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
                    "language": "python"
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


class JavaScriptTreeSitterParser(LanguageParser):
    """JavaScript/TypeScript parser using tree-sitter"""
    
    def __init__(self):
        # Build language library
        JS_LANGUAGE = Language(tsjavascript.language())
        TS_LANGUAGE = Language(tstypescript.language_typescript())
        
        self.js_parser = Parser(JS_LANGUAGE)
        self.ts_parser = Parser(TS_LANGUAGE)
    
    def supports_file(self, file_path: str) -> bool:
        suffix = Path(file_path).suffix
        return suffix in ['.js', '.jsx', '.ts', '.tsx', '.mjs']
    
    def parse_file(self, file_path: str, content: str) -> List[CodeChunk]:
        """Parse JavaScript/TypeScript file using tree-sitter"""
        chunks = []
        lines = content.splitlines()
        
        # Choose parser based on file extension
        suffix = Path(file_path).suffix
        if suffix in ['.ts', '.tsx']:
            parser = self.ts_parser
            language = "typescript"
        else:
            parser = self.js_parser
            language = "javascript"
        
        try:
            tree = parser.parse(bytes(content, "utf8"))
            
            # Extract functions, classes, and methods
            chunks.extend(self._extract_chunks(tree.root_node, file_path, lines, language))
            
        except Exception as e:
            print(f"Error parsing {language} file {file_path}: {e}")
        
        return chunks
    
    def _extract_chunks(self, node, file_path: str, lines: List[str], language: str, 
                       class_name: Optional[str] = None) -> List[CodeChunk]:
        """Recursively extract code chunks from tree-sitter node"""
        chunks = []
        
        # Function declarations and expressions
        if node.type in ['function_declaration', 'function_expression', 'arrow_function', 
                        'method_definition', 'generator_function_declaration']:
            chunk = self._extract_function(node, file_path, lines, language, class_name)
            if chunk:
                chunks.append(chunk)
        
        # Class declarations
        elif node.type in ['class_declaration', 'class_expression']:
            chunk = self._extract_class(node, file_path, lines, language)
            if chunk:
                chunks.append(chunk)
                # Set class name for nested methods
                name_node = node.child_by_field_name('name')
                if name_node:
                    class_name = name_node.text.decode('utf8')
        
        # Variable declarations that might contain functions
        elif node.type == 'variable_declarator':
            init_node = node.child_by_field_name('value')
            if init_node and init_node.type in ['arrow_function', 'function_expression']:
                chunk = self._extract_variable_function(node, file_path, lines, language)
                if chunk:
                    chunks.append(chunk)
        
        # Recurse through children
        for child in node.children:
            chunks.extend(self._extract_chunks(child, file_path, lines, language, class_name))
        
        return chunks
    
    def _extract_function(self, node, file_path: str, lines: List[str], language: str, 
                         class_name: Optional[str] = None) -> Optional[CodeChunk]:
        """Extract JavaScript function"""
        try:
            # Get function name
            name_node = node.child_by_field_name('name')
            if not name_node and node.type == 'method_definition':
                # For methods, get the property name
                name_node = node.child_by_field_name('property')
            
            if not name_node:
                return None
            
            name = name_node.text.decode('utf8')
            
            # Get parameters
            params_node = node.child_by_field_name('parameters')
            params = []
            if params_node:
                for param in params_node.children:
                    if param.type in ['identifier', 'rest_pattern', 'object_pattern', 'array_pattern']:
                        params.append(param.text.decode('utf8'))
            
            # Build signature
            is_async = any(child.type == 'async' for child in node.children)
            is_generator = node.type == 'generator_function_declaration'
            
            signature = f"{'async ' if is_async else ''}{'function* ' if is_generator else 'function '}{name}({', '.join(params)})"
            
            # Get the code
            start_line = node.start_point[0]
            end_line = node.end_point[0] + 1
            code_lines = lines[start_line:end_line]
            code = '\n'.join(code_lines)
            
            # Try to extract JSDoc comment
            docstring = self._extract_jsdoc(node, lines)
            
            # Create context
            context = {
                "module": Path(file_path).stem,
                "file_path": file_path,
                "file_name": Path(file_path).name,
                "language": language
            }
            
            if class_name:
                context["class_name"] = class_name
            
            code_type = CodeTypeEnum.METHOD if class_name else CodeTypeEnum.FUNCTION
            
            return CodeChunk(
                name=name,
                signature=signature,
                code_type=code_type,
                docstring=docstring,
                code=code,
                line=start_line + 1,  # Convert to 1-based
                line_from=start_line + 1,
                line_to=end_line,
                context=context,
                natural_language=self._code_to_natural_language(name, signature, docstring, code_type)
            )
            
        except Exception as e:
            print(f"Error extracting JavaScript function: {e}")
            return None
    
    def _extract_class(self, node, file_path: str, lines: List[str], language: str) -> Optional[CodeChunk]:
        """Extract JavaScript class"""
        try:
            # Get class name
            name_node = node.child_by_field_name('name')
            if not name_node:
                return None
            
            name = name_node.text.decode('utf8')
            
            # Get superclass if any
            superclass_node = node.child_by_field_name('superclass')
            superclass = superclass_node.text.decode('utf8') if superclass_node else None
            
            # Build signature
            signature = f"class {name}"
            if superclass:
                signature += f" extends {superclass}"
            
            # Get the code (just class definition)
            start_line = node.start_point[0]
            # Find the opening brace
            body_node = node.child_by_field_name('body')
            if body_node:
                end_line = body_node.start_point[0] + 1
            else:
                end_line = start_line + 1
            
            code_lines = lines[start_line:end_line]
            code = '\n'.join(code_lines)
            
            # Try to extract JSDoc comment
            docstring = self._extract_jsdoc(node, lines)
            
            return CodeChunk(
                name=name,
                signature=signature,
                code_type=CodeTypeEnum.CLASS,
                docstring=docstring,
                code=code,
                line=start_line + 1,
                line_from=start_line + 1,
                line_to=end_line,
                context={
                    "module": Path(file_path).stem,
                    "file_path": file_path,
                    "file_name": Path(file_path).name,
                    "language": language
                },
                natural_language=self._code_to_natural_language(name, signature, docstring, CodeTypeEnum.CLASS)
            )
            
        except Exception as e:
            print(f"Error extracting JavaScript class: {e}")
            return None
    
    def _extract_variable_function(self, node, file_path: str, lines: List[str], language: str) -> Optional[CodeChunk]:
        """Extract function assigned to a variable"""
        try:
            # Get variable name
            name_node = node.child_by_field_name('name')
            if not name_node:
                return None
            
            name = name_node.text.decode('utf8')
            
            # Get the function node
            value_node = node.child_by_field_name('value')
            if not value_node or value_node.type not in ['arrow_function', 'function_expression']:
                return None
            
            # Get parameters
            params_node = value_node.child_by_field_name('parameters')
            params = []
            if params_node:
                for param in params_node.children:
                    if param.type in ['identifier', 'rest_pattern', 'object_pattern', 'array_pattern']:
                        params.append(param.text.decode('utf8'))
            
            # Build signature
            is_async = any(child.type == 'async' for child in value_node.children)
            signature = f"const {name} = {'async ' if is_async else ''}({', '.join(params)}) => ..."
            
            # Get the code
            start_line = node.start_point[0]
            end_line = node.end_point[0] + 1
            code_lines = lines[start_line:end_line]
            code = '\n'.join(code_lines)
            
            # Try to extract JSDoc comment
            docstring = self._extract_jsdoc(node, lines)
            
            return CodeChunk(
                name=name,
                signature=signature,
                code_type=CodeTypeEnum.FUNCTION,
                docstring=docstring,
                code=code,
                line=start_line + 1,
                line_from=start_line + 1,
                line_to=end_line,
                context={
                    "module": Path(file_path).stem,
                    "file_path": file_path,
                    "file_name": Path(file_path).name,
                    "language": language
                },
                natural_language=self._code_to_natural_language(name, signature, docstring, CodeTypeEnum.FUNCTION)
            )
            
        except Exception as e:
            print(f"Error extracting JavaScript variable function: {e}")
            return None
    
    def _extract_jsdoc(self, node, lines: List[str]) -> Optional[str]:
        """Extract JSDoc comment preceding a node"""
        start_line = node.start_point[0]
        if start_line == 0:
            return None
        
        # Look for JSDoc comment in preceding lines
        for i in range(start_line - 1, max(-1, start_line - 10), -1):
            line = lines[i].strip()
            if line.endswith('*/'):
                # Found end of comment, extract it
                comment_lines = []
                for j in range(i, -1, -1):
                    comment_lines.insert(0, lines[j])
                    if lines[j].strip().startswith('/**'):
                        # Found start of JSDoc
                        comment = '\n'.join(comment_lines)
                        # Clean up the comment
                        comment = comment.replace('/**', '').replace('*/', '')
                        comment = '\n'.join(l.strip().lstrip('*').strip() for l in comment.split('\n'))
                        return comment.strip()
                break
            elif line and not line.startswith('*'):
                # Hit non-comment line
                break
        
        return None
    
    def _code_to_natural_language(self, name: str, signature: str, docstring: Optional[str], 
                                 code_type: CodeTypeEnum) -> str:
        """Convert code to natural language for NLP-based search"""
        parts = []
        
        # Add code type
        parts.append(f"{code_type.value.title()} {name}")
        
        # Parse signature for natural language
        if code_type in [CodeTypeEnum.FUNCTION, CodeTypeEnum.METHOD]:
            # Extract parameters from signature
            if '(' in signature and ')' in signature:
                params_str = signature[signature.find('(')+1:signature.find(')')]
                if params_str:
                    params = [p.strip() for p in params_str.split(',')]
                    parts.append(f"takes parameters {', '.join(params)}")
        
        # Add docstring if available
        if docstring:
            # Clean and add first line of docstring
            first_line = docstring.strip().split('\n')[0]
            parts.append(first_line.lower())
        
        return '. '.join(parts)


class MultiLanguageCodebaseParser:
    """Main parser that delegates to language-specific parsers"""
    
    def __init__(self, file_filter: Optional[FileFilter] = None):
        """
        Initialize the parser with optional file filtering
        
        Args:
            file_filter: FileFilter instance for consistent file filtering
        """
        self.parsers: List[LanguageParser] = [
            PythonASTParser(),
            JavaScriptTreeSitterParser(),
        ]
        self.chunks: List[CodeChunk] = []
        self.file_filter = file_filter
    
    def parse_file(self, file_path: str) -> List[CodeChunk]:
        """Parse a single file using the appropriate parser"""
        chunks = []
        
        # Find the right parser
        parser = None
        for p in self.parsers:
            if p.supports_file(file_path):
                parser = p
                break
        
        if not parser:
            print(f"No parser available for file: {file_path}")
            return chunks
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            chunks = parser.parse_file(file_path, content)
            
        except Exception as e:
            print(f"Error reading/parsing {file_path}: {e}")
        
        return chunks
    
    def parse_directory(self, directory: str, extensions: Optional[List[str]] = None) -> List[CodeChunk]:
        """Parse all supported files in a directory recursively"""
        if extensions is None:
            # Default to all supported extensions
            extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.mjs']
        
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
    
    def get_supported_languages(self) -> Dict[str, List[str]]:
        """Return supported languages and their file extensions"""
        return {
            "Python": [".py"],
            "JavaScript": [".js", ".jsx", ".mjs"],
            "TypeScript": [".ts", ".tsx"]
        }
