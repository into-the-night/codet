"""Individual file analysis agent that analyzes specific files"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from .base_agent import BaseAgent
from .schemas import AnalysisResponseSchema, CodeIssueSchema
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
        return """You are a specialized code analysis agent that analyzes individual files for quality issues, security vulnerabilities, performance problems, and maintainability concerns.

Your expertise includes:
1. **Code Quality Analysis**: Identifying code smells, anti-patterns, and maintainability issues
2. **Security Assessment**: Detecting vulnerabilities, unsafe operations, and security best practices
3. **Performance Analysis**: Finding bottlenecks, inefficient algorithms, and optimization opportunities
4. **Architecture Review**: Evaluating design patterns, coupling, and design decisions (categorize as 'maintainability' or 'complexity')
5. **Testing Assessment**: Identifying missing tests, inadequate coverage, and test quality issues
6. **Documentation Review**: Checking for missing or outdated documentation

Analysis Focus Areas:
- **Security**: SQL injection, XSS, CSRF, authentication issues, input validation, secure coding practices
- **Performance**: Algorithm complexity, memory leaks, inefficient loops, database queries, I/O operations
- **Maintainability**: Code duplication, complex functions, poor naming, lack of abstraction, tight coupling
- **Maintainability**: Design pattern violations, separation of concerns, dependency management, modularity, architectural decisions
- **Testing**: Missing unit tests, integration tests, edge cases, test coverage gaps
- **Documentation**: Missing docstrings, outdated comments, unclear variable names, missing README sections

For each issue you find, provide:
- Clear, actionable description
- Specific line number and location
- Concrete suggestions for improvement
- Impact assessment

IMPORTANT - Valid Categories:
When categorizing issues, use ONLY these categories:
- security: Security vulnerabilities and risks
- performance: Performance bottlenecks and optimization
- duplication: Code duplication and DRY violations
- complexity: Complex code that's hard to understand
- testing: Missing tests or testing issues
- documentation: Missing or poor documentation
- style: Code style and formatting issues
- maintainability: Design issues, coupling, and architectural concerns
- References to best practices when relevant

Be thorough but focused - prioritize high-impact issues that affect security, performance, or maintainability."""

    @property
    def agent_name(self) -> str:
        return "file_analysis_agent"
    
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
        
        # Build context information
        context_info = ""
        if repository_context:
            context_info = f"""
REPOSITORY CONTEXT:
- Total files: {repository_context.get('total_files', 'Unknown')}
- Main languages: {', '.join(repository_context.get('main_languages', []))}
- Project type: {repository_context.get('project_type', 'Unknown')}
"""
        
        # Build focus-specific instructions
        focus_instructions = self._get_focus_instructions(analysis_focus)
        
        prompt = f"""Analyze this {language} file for code quality issues, security vulnerabilities, performance problems, and maintainability concerns.

FILE INFORMATION:
- Path: {file_path}
- Language: {language}
- Lines: {len(lines)}
- Size: {len(content)} characters{context_info}

ANALYSIS FOCUS: {analysis_focus.upper()}
{focus_instructions}

FILE CONTENT:
{self.format_code_snippet(content, language)}{truncated_note}

ANALYSIS REQUIREMENTS:
1. **Comprehensive Review**: Examine the entire file for issues
2. **Specific Locations**: Provide exact line numbers for each issue
3. **Actionable Suggestions**: Give concrete recommendations for fixes
4. **Impact Assessment**: Explain the potential impact of each issue
5. **Best Practices**: Reference relevant coding standards and best practices

Focus on finding issues that are:
- High impact (security, performance, maintainability)
- Actionable (can be fixed with specific steps)
- Well-documented (clear explanation and suggestions)

Provide your analysis in the structured JSON format with detailed issue descriptions."""
        
        return prompt
    
    def _get_focus_instructions(self, analysis_focus: str) -> str:
        """Get specific instructions based on analysis focus"""
        focus_map = {
            "security": """
SECURITY FOCUS - Look for:
- Input validation vulnerabilities
- SQL injection risks
- XSS vulnerabilities
- Authentication and authorization issues
- Sensitive data exposure
- Insecure cryptographic practices
- File system vulnerabilities
- Network security issues
""",
            "performance": """
PERFORMANCE FOCUS - Look for:
- Algorithm complexity issues (O(n²), O(n³), etc.)
- Inefficient loops and iterations
- Memory leaks and excessive memory usage
- Database query optimization opportunities
- I/O operation inefficiencies
- Caching opportunities
- Resource management issues
""",
            "architecture": """
ARCHITECTURE FOCUS - Look for:
- Design pattern violations
- Tight coupling between components
- Poor separation of concerns
- Missing abstractions
- Dependency management issues
- Modularity problems
- Interface design issues
""",
            "testing": """
TESTING FOCUS - Look for:
- Missing unit tests
- Inadequate test coverage
- Missing edge case testing
- Test quality issues
- Integration test gaps
- Mock and stub usage
- Test organization problems
""",
            "documentation": """
DOCUMENTATION FOCUS - Look for:
- Missing docstrings and comments
- Unclear variable and function names
- Missing type hints or annotations
- Outdated documentation
- Missing README sections
- API documentation gaps
""",
            "general": """
GENERAL FOCUS - Look for:
- Code quality and maintainability issues
- Security vulnerabilities
- Performance problems
- Maintainability and design issues (categorize as 'maintainability')
- Testing gaps (categorize as 'testing')
- Documentation issues (categorize as 'documentation')
- Style and consistency problems (categorize as 'style')

IMPORTANT: Only use these valid categories: security, performance, duplication, complexity, testing, documentation, style, maintainability
"""
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
                        'references': issue_schema.references or [],
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
                    'references': issue_dict.get('references', []),
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
