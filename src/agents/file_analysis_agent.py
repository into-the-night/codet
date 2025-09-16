"""Individual file analysis agent that analyzes specific files"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from .base_agent import BaseAgent
from .schemas import (
    AnalysisResponseSchema, 
    CodeIssueSchema,
    FileAnalysisResultEnhanced
)
from ..core.config import AgentConfig
from ..analyzers.analyzer import CodeIssue, IssueCategory, IssueSeverity

logger = logging.getLogger(__name__)


class FileAnalysisAgent(BaseAgent):
    """Specialized agent for analyzing individual files"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.max_file_size = 1024 * 1024  # 1MB max file size
        self.max_lines = 1000  # Max lines to analyze per file
        
    @property
    def system_prompt(self) -> str:
        """System prompt for file analysis"""
        return """You are a specialized code analysis agent that analyzes individual files for quality issues.

For each issue found, provide:
- Clear, actionable description with specific line number
- Concrete suggestions for improvement
- Impact assessment

Valid Categories (use ONLY these):
- security: Vulnerabilities, authentication issues, input validation
- performance: Bottlenecks, algorithm complexity, resource usage
- duplication: Code duplication and DRY violations
- complexity: Hard to understand/maintain code
- testing: Missing tests or coverage gaps
- documentation: Missing/poor documentation
- style: Code formatting issues
- maintainability: Design issues, coupling, architectural concerns

Prioritize high-impact issues that affect security, performance, or maintainability."""

    @property
    def agent_name(self) -> str:
        return "file_analysis_agent"
    
    async def answer_file_query(self, file_path: str,
                               root_path: Path,
                               question: str,
                               repository_context: Optional[Dict[str, Any]] = None) -> str:
        """Answer a focused question about a specific file by reading its content.

        Returns a concise, source-grounded answer. If the answer cannot be determined
        from the file, explicitly state that it's not present.
        """
        logger.info(f"Answering file query for: {file_path} (question: {question[:80]}...) ")

        full_path = root_path / file_path
        if not full_path.exists() or not full_path.is_file():
            return f"File not found: {file_path}"

        try:
            # Read file content
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Truncate very long files by lines to keep context sensible
            lines = content.splitlines()
            truncated = False
            if len(lines) > self.max_lines:
                content = '\n'.join(lines[:self.max_lines])
                truncated = True

            prompt = self._build_file_query_prompt(
                file_path=file_path,
                content=content,
                question=question,
                repository_context=repository_context,
                truncated=truncated,
            )

            answer = await self.generate_response(
                prompt=prompt,
                context={
                    'file_path': file_path,
                    'analysis_type': 'file_query',
                    'question_len': len(question),
                }
            )
            return answer
        except Exception as e:
            logger.error(f"Error answering file query for {file_path}: {e}")
            return f"Error reading or analyzing {file_path}: {e}"

    async def analyze_file(self, file_path: str, 
                          root_path: Path,
                          analysis_focus: str = "general",
                          repository_context: Optional[Dict[str, Any]] = None) -> List[CodeIssue]:
        """
        Analyze a specific file for issues
        
        Args:
            file_path: Path to the file to analyze (relative to root)
            root_path: Path to repository root
            analysis_focus: Specific focus area for analysis
            repository_context: Additional context about the repository
            
        Returns:
            List of CodeIssue objects found in the file
        """
        logger.info(f"Analyzing file: {file_path} (focus: {analysis_focus})")
        
        full_path = root_path / file_path
        
        if not full_path.exists():
            logger.warning(f"File not found: {full_path}")
            return []
        
        if not full_path.is_file():
            logger.warning(f"Path is not a file: {full_path}")
            return []
        
        try:
            # Read file content
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check file size
            if len(content) > self.max_file_size:
                logger.warning(f"File too large, truncating: {full_path}")
                content = content[:self.max_file_size] + "\n... [truncated]"
            
            # Build analysis prompt
            prompt = self._build_file_analysis_prompt(
                file_path, content, analysis_focus, repository_context
            )
            
            # Generate structured analysis
            try:
                structured_response = await self.generate_structured_response(
                    prompt=prompt,
                    response_schema=AnalysisResponseSchema,
                    context={
                        'file_path': file_path,
                        'file_size': len(content),
                        'analysis_focus': analysis_focus,
                        'analysis_type': 'individual_file'
                    }
                )
                
                # Convert to CodeIssue objects
                issues = self._convert_to_code_issues(structured_response.issues, full_path)
                
            except Exception as e:
                logger.warning(f"Structured analysis failed, falling back to text parsing: {e}")
                # Fallback to text-based analysis
                response = await self.generate_response(
                    prompt=prompt,
                    context={
                        'file_path': file_path,
                        'file_size': len(content),
                        'analysis_focus': analysis_focus,
                        'analysis_type': 'individual_file'
                    }
                )
                issues = self._parse_text_response(response, full_path)
            
            logger.info(f"File analysis complete: {len(issues)} issues found in {file_path}")
            return issues
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return []
    
    def _build_file_analysis_prompt(self, file_path: str, content: str,
                                   analysis_focus: str,
                                   repository_context: Optional[Dict[str, Any]]) -> str:
        """Build analysis prompt for a specific file"""
        file_extension = Path(file_path).suffix.lower()
        language = self._get_language(file_extension)
        
        # Truncate very long files
        lines = content.splitlines()
        if len(lines) > self.max_lines:
            content = '\n'.join(lines[:self.max_lines])
            truncated_note = f"\n\n[Note: File truncated to first {self.max_lines} lines]"
        else:
            truncated_note = ""
        
        # Build focus-specific instructions
        focus_instructions = self._get_focus_instructions(analysis_focus)
        
        prompt = f"""Analyze this {language} file:
Path: {file_path} ({len(lines)} lines)

ANALYSIS FOCUS: {analysis_focus.upper()}
{focus_instructions}

FILE CONTENT:
{self.format_code_snippet(content, language)}{truncated_note}

Provide detailed issues with exact line numbers, clear descriptions, and actionable suggestions."""
        
        return prompt

    def _build_file_query_prompt(self, *, file_path: str, content: str, question: str,
                                 repository_context: Optional[Dict[str, Any]], truncated: bool) -> str:
        """Build a question-focused prompt for a specific file."""
        file_extension = Path(file_path).suffix.lower()
        language = self._get_language(file_extension)
        truncated_note = f"\n\n[Note: File truncated to first {self.max_lines} lines]" if truncated else ""

        prompt = f"""Answer this question based ONLY on the {language} file content:

QUESTION: {question}

FILE: {file_path}
{self.format_code_snippet(content, language)}{truncated_note}

Answer directly citing exact code. If not found in this file, say so and suggest where else to look. Don't speculate."""
        
        return prompt
    
    def _get_focus_instructions(self, analysis_focus: str) -> str:
        """Get specific instructions based on analysis focus"""
        focus_map = {
            "security": "Focus on: input validation, injection risks, authentication, data exposure, crypto issues",
            "performance": "Focus on: algorithm complexity, inefficient loops, memory usage, query optimization, I/O operations",
            "architecture": "Focus on: design patterns, coupling, separation of concerns, abstractions, dependencies",
            "testing": "Focus on: missing tests, coverage gaps, edge cases, test quality",
            "documentation": "Focus on: missing docstrings, unclear names, type hints, outdated docs",
            "general": "Analyze all aspects: security, performance, maintainability, testing, documentation"
        }
        
        return focus_map.get(analysis_focus.lower(), focus_map["general"])
    
    def _convert_to_code_issues(self, issues: List[CodeIssueSchema], file_path: Path) -> List[CodeIssue]:
        """Convert schema issues to CodeIssue objects"""
        code_issues = []
        
        for issue_schema in issues:
            try:
                # Map categories
                category_map = {
                    'security': IssueCategory.SECURITY,
                    'performance': IssueCategory.PERFORMANCE,
                    'complexity': IssueCategory.COMPLEXITY,
                    'maintainability': IssueCategory.MAINTAINABILITY,
                    'documentation': IssueCategory.DOCUMENTATION,
                    'style': IssueCategory.STYLE,
                    'testing': IssueCategory.TESTING,
                    'duplication': IssueCategory.DUPLICATION,
                }
                
                # Map severities
                severity_map = {
                    'critical': IssueSeverity.CRITICAL,
                    'high': IssueSeverity.HIGH,
                    'medium': IssueSeverity.MEDIUM,
                    'low': IssueSeverity.LOW,
                    'info': IssueSeverity.INFO
                }
                
                # Create CodeIssue
                issue = CodeIssue(
                    category=category_map.get(
                        issue_schema.category.value.lower(),
                        IssueCategory.MAINTAINABILITY
                    ),
                    severity=severity_map.get(
                        issue_schema.severity.value.lower(),
                        IssueSeverity.MEDIUM
                    ),
                    title=issue_schema.title,
                    description=issue_schema.description,
                    file_path=file_path,
                    line_number=issue_schema.line_number,
                    column_number=issue_schema.column_number,
                    suggestion=issue_schema.suggestion,
                    code_snippet=issue_schema.code_snippet,
                    metadata={
                        'ai_detected': True,
                        'file_analysis_agent': True,
                        'impact': issue_schema.impact or '',
                        'detection_timestamp': datetime.now().isoformat()
                    }
                )
                
                code_issues.append(issue)
                
            except Exception as e:
                logger.warning(f"Failed to convert file analysis issue: {e}")
                continue
        
        return code_issues
    
    def _parse_text_response(self, response: str, file_path: Path) -> List[CodeIssue]:
        """Parse text response into CodeIssue objects (fallback method)"""
        try:
            # Try to parse as JSON first
            issues_data = self.parse_json_response(response)
            
            if isinstance(issues_data, list):
                issues = []
                for issue_dict in issues_data:
                    issue = self._create_issue_from_dict(issue_dict, file_path)
                    if issue:
                        issues.append(issue)
                return issues
            elif isinstance(issues_data, dict) and 'issues' in issues_data:
                issues = []
                for issue_dict in issues_data['issues']:
                    issue = self._create_issue_from_dict(issue_dict, file_path)
                    if issue:
                        issues.append(issue)
                return issues
            
        except Exception as e:
            logger.warning(f"Failed to parse text response as JSON: {e}")
        
        # If JSON parsing fails, return empty list
        return []
    
    def _create_issue_from_dict(self, issue_dict: Dict[str, Any], file_path: Path) -> Optional[CodeIssue]:
        """Create a CodeIssue from a dictionary"""
        try:
            # Map categories
            category_map = {
                'security': IssueCategory.SECURITY,
                'performance': IssueCategory.PERFORMANCE,
                'complexity': IssueCategory.COMPLEXITY,
                'maintainability': IssueCategory.MAINTAINABILITY,
                'documentation': IssueCategory.DOCUMENTATION,
                'style': IssueCategory.STYLE,
                'testing': IssueCategory.TESTING,
                'duplication': IssueCategory.DUPLICATION,
            }
            
            # Map severities
            severity_map = {
                'critical': IssueSeverity.CRITICAL,
                'high': IssueSeverity.HIGH,
                'medium': IssueSeverity.MEDIUM,
                'low': IssueSeverity.LOW,
                'info': IssueSeverity.INFO
            }
            
            # Create CodeIssue
            issue = CodeIssue(
                category=category_map.get(
                    issue_dict.get('category', 'maintainability').lower(),
                    IssueCategory.MAINTAINABILITY
                ),
                severity=severity_map.get(
                    issue_dict.get('severity', 'medium').lower(),
                    IssueSeverity.MEDIUM
                ),
                title=issue_dict.get('title', 'AI-detected issue'),
                description=issue_dict.get('description', ''),
                file_path=file_path,
                line_number=issue_dict.get('line_number'),
                suggestion=issue_dict.get('suggestion'),
                code_snippet=issue_dict.get('code_snippet'),
                metadata={
                    'ai_detected': True,
                    'file_analysis_agent': True,
                    'text_parsed': True,
                    'impact': issue_dict.get('impact', ''),
                    'detection_timestamp': datetime.now().isoformat()
                }
            )
            
            return issue
            
        except Exception as e:
            logger.warning(f"Failed to create issue from dict: {e}")
            return None
    
    def _get_language(self, extension: str) -> str:
        """Map file extension to language name"""
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.jsx': 'JavaScript/React',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript/React',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.cs': 'C#',
            '.go': 'Go',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.rs': 'Rust',
            '.scala': 'Scala',
            '.r': 'R',
            '.m': 'MATLAB',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.json': 'JSON',
            '.xml': 'XML',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.vue': 'Vue',
            '.dart': 'Dart',
        }
        return language_map.get(extension.lower(), 'Unknown')
    
    async def analyze_file_enhanced(self, file_path: str, 
                                  root_path: Path,
                                  analysis_focus: str = "general",
                                  repository_context: Optional[Dict[str, Any]] = None) -> FileAnalysisResultEnhanced:
        """
        Enhanced file analysis that returns results with next steps suggestions
        
        Args:
            file_path: Path to the file to analyze (relative to root)
            root_path: Path to repository root
            analysis_focus: Specific focus area for analysis
            repository_context: Additional context about the repository
            
        Returns:
            FileAnalysisResultEnhanced with issues and next steps
        """
        logger.info(f"Enhanced analysis of file: {file_path} (focus: {analysis_focus})")
        
        full_path = root_path / file_path
        
        if not full_path.exists() or not full_path.is_file():
            return FileAnalysisResultEnhanced(
                file_path=file_path,
                issues=[],
                summary=f"File not found: {file_path}"
            )
        
        try:
            # Read file content
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check file size
            if len(content) > self.max_file_size:
                logger.warning(f"File too large, truncating: {full_path}")
                content = content[:self.max_file_size] + "\n... [truncated]"
            
            # Determine file type
            file_extension = Path(file_path).suffix.lower()
            is_test_file = self._is_test_file(file_path)
            
            # Build enhanced analysis prompt
            prompt = self._build_enhanced_analysis_prompt(
                file_path, content, analysis_focus, repository_context, is_test_file
            )
            
            # Generate structured analysis with enhanced schema
            structured_response = await self.generate_structured_response(
                prompt=prompt,
                response_schema=FileAnalysisResultEnhanced,
                context={
                    'file_path': file_path,
                    'file_size': len(content),
                    'analysis_focus': analysis_focus,
                    'is_test_file': is_test_file,
                    'analysis_type': 'enhanced_file_analysis'
                }
            )
            
            # Convert issues to CodeIssue objects
            if structured_response.issues:
                code_issues = self._convert_to_code_issues(structured_response.issues, full_path)
                structured_response.issues = code_issues
            
            logger.info(f"Enhanced analysis complete: {len(structured_response.issues)} issues, "
                       f"{len(structured_response.next_steps)} next steps suggested")
            
            return structured_response
            
        except Exception as e:
            logger.error(f"Error in enhanced file analysis {file_path}: {e}")
            return FileAnalysisResultEnhanced(
                file_path=file_path,
                issues=[],
                summary=f"Error analyzing file: {str(e)}"
            )
    
    def _is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file based on naming conventions"""
        test_patterns = [
            'test_', '_test.', '.test.', 'tests/', 'test/', '__tests__/', 
            'spec.', '.spec.', 'specs/', 'spec/', '__specs__/'
        ]
        path_lower = file_path.lower()
        return any(pattern in path_lower for pattern in test_patterns)
    
    def _build_enhanced_analysis_prompt(self, file_path: str, content: str,
                                      analysis_focus: str,
                                      repository_context: Optional[Dict[str, Any]],
                                      is_test_file: bool) -> str:
        """Build enhanced analysis prompt that requests next steps"""
        file_extension = Path(file_path).suffix.lower()
        language = self._get_language(file_extension)
        
        # Truncate very long files
        lines = content.splitlines()
        if len(lines) > self.max_lines:
            content = '\n'.join(lines[:self.max_lines])
            truncated_note = f"\n\n[Note: File truncated to first {self.max_lines} lines]"
        else:
            truncated_note = ""
        
        focus_instructions = self._get_focus_instructions(analysis_focus)
        
        prompt = f"""Analyze {language} file and suggest next steps:
Path: {file_path} ({len(lines)} lines)

ANALYSIS FOCUS: {analysis_focus.upper()}
{focus_instructions}

FILE CONTENT:
{self.format_code_snippet(content, language)}{truncated_note}

Return FileAnalysisResultEnhanced with:
- issues: Code issues with line numbers and fixes
- next_steps: Specific suggestions (e.g., "check if X function has tests in test_X.py")
- summary: Brief file purpose and quality summary"""
        
        return prompt
