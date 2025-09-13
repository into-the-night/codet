"""JavaScript/TypeScript code analyzer"""

from pathlib import Path
from typing import List, Dict, Any
import re
import logging

from .analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity
from ..utils.snippet_extractor import extract_code_snippet, extract_block_snippet


logger = logging.getLogger(__name__)


class JavaScriptAnalyzer(BaseAnalyzer):
    """Analyzer for JavaScript/TypeScript code quality issues"""
    
    def analyze(self, file_path: Path) -> List[CodeIssue]:
        """Analyze JavaScript/TypeScript file for quality issues"""
        issues = []
        
        if not self.supports_language(file_path.suffix):
            return issues
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            # Run various checks
            issues.extend(self._check_console_logs(lines, file_path))
            issues.extend(self._check_long_functions(content, file_path))
            issues.extend(self._check_callback_hell(content, file_path))
            issues.extend(self._check_var_usage(lines, file_path))
            
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
        
        return issues
    
    def _check_console_logs(self, lines: List[str], file_path: Path) -> List[CodeIssue]:
        """Check for console.log statements"""
        issues = []
        
        for i, line in enumerate(lines, 1):
            if re.search(r'console\.(log|debug|info|warn|error)', line):
                issues.append(CodeIssue(
                    category=IssueCategory.STYLE,
                    severity=IssueSeverity.LOW,
                    title="Console Statement Found",
                    description="Console statements should be removed in production code",
                    file_path=file_path,
                    line_number=i,
                    suggestion="Use a proper logging library or remove the console statement",
                    code_snippet=extract_code_snippet(file_path, i)
                ))
        
        return issues
    
    def _check_long_functions(self, content: str, file_path: Path) -> List[CodeIssue]:
        """Check for overly long functions"""
        issues = []
        
        # Simple regex-based function detection
        function_pattern = r'(function\s+\w+\s*\([^)]*\)|const\s+\w+\s*=\s*\([^)]*\)\s*=>|\w+\s*:\s*function\s*\([^)]*\))'
        
        for match in re.finditer(function_pattern, content):
            start_pos = match.start()
            line_start = content.rfind('\n', 0, start_pos) + 1
            line_num = content[:start_pos].count('\n') + 1
            
            # Find the function body (simplified)
            brace_count = 0
            in_function = False
            func_lines = 0
            
            for i, char in enumerate(content[start_pos:], start_pos):
                if char == '{':
                    brace_count += 1
                    in_function = True
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and in_function:
                        func_content = content[start_pos:i+1]
                        func_lines = func_content.count('\n')
                        break
            
            if func_lines > 50:
                func_name = match.group(0).split('(')[0].strip().split()[-1]
                issues.append(CodeIssue(
                    category=IssueCategory.COMPLEXITY,
                    severity=IssueSeverity.MEDIUM if func_lines < 100 else IssueSeverity.HIGH,
                    title="Long Function",
                    description=f"Function '{func_name}' has {func_lines} lines",
                    file_path=file_path,
                    line_number=line_num,
                    suggestion="Consider breaking this function into smaller, more focused functions",
                    code_snippet=extract_code_snippet(file_path, line_num)
                ))
        
        return issues
    
    def _check_callback_hell(self, content: str, file_path: Path) -> List[CodeIssue]:
        """Check for deeply nested callbacks"""
        issues = []
        
        # Look for nested function patterns
        nested_pattern = r'function\s*\([^)]*\)\s*{\s*[^}]*function\s*\([^)]*\)\s*{\s*[^}]*function\s*\([^)]*\)'
        
        for match in re.finditer(nested_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                category=IssueCategory.COMPLEXITY,
                severity=IssueSeverity.MEDIUM,
                title="Callback Hell Detected",
                description="Deeply nested callbacks make code hard to read and maintain",
                file_path=file_path,
                line_number=line_num,
                suggestion="Consider using Promises or async/await to flatten the callback structure",
                code_snippet=extract_code_snippet(file_path, line_num)
            ))
        
        return issues
    
    def _check_var_usage(self, lines: List[str], file_path: Path) -> List[CodeIssue]:
        """Check for 'var' usage instead of 'let' or 'const'"""
        issues = []
        
        for i, line in enumerate(lines, 1):
            if re.search(r'\bvar\s+\w+', line):
                issues.append(CodeIssue(
                    category=IssueCategory.STYLE,
                    severity=IssueSeverity.LOW,
                    title="Using 'var' Instead of 'let' or 'const'",
                    description="'var' has function scope which can lead to bugs",
                    file_path=file_path,
                    line_number=i,
                    suggestion="Use 'let' for variables that change or 'const' for constants",
                    code_snippet=extract_code_snippet(file_path, i)
                ))
        
        return issues
    
    def supports_language(self, language: str) -> bool:
        """Check if analyzer supports JavaScript/TypeScript"""
        return language.lower() in ['.js', '.ts', '.jsx', '.tsx', 'javascript', 'typescript']
    
    @property
    def name(self) -> str:
        return "JavaScript/TypeScript Analyzer"
