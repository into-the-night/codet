"""Individual file analysis agent that analyzes specific files"""

import logging
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from .base_agent import BaseAgent
from .schemas import (
    AnalysisResponseSchema, 
    CodeIssueSchema,
    FileAnalysisResultEnhanced,
    CodeIssue,
    IssueCategory,
    IssueSeverity
)
from ..core.config import AgentConfig
from ..core.shared_memory import SharedMemory, MemoryView, ROLE_FILE_ANALYSIS
from ..core.repository_tree import RepositoryTreeConstructor as TreeConstructor
from ..indexer import RulesIndexer
from ..utils.symbol_extractor import extract_symbols

logger = logging.getLogger(__name__)


class FileAnalysisAgent(BaseAgent):
    """Specialized agent for analyzing individual files"""
    
    def __init__(self, config: AgentConfig, shared_memory: Optional[SharedMemory] = None):
        super().__init__(config)
        self.max_file_size = 1024 * 1024  # 1MB max file size
        self.max_lines = 1000  # Max lines to analyze per file
        # Underlying memory store. Per-call, we derive a file-scoped MemoryView
        # so each analysis can only write cache entries for the file it owns.
        self.shared_memory = shared_memory
        
    @property
    def system_prompt(self) -> str:
        """System prompt for file analysis"""
        prompt ="""You are a specialized code analysis agent that analyzes individual files for quality issues.

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

SHARED MEMORY - how to use it:
You see two kinds of shared memory in the prompt:
- Notes: durable observations about the codebase (entry points, invariants,
  where a symbol lives). Append a note in `notes` when you learn something
  worth telling other agents.
- Todos: action items other agents should verify. Append to `memory_items`
  when you discover something that must be checked elsewhere (e.g.
  "Check if authenticate() has tests in test_auth.py").

Rules for file-analysis agents:
- You can READ all notes and todos.
- You can APPEND notes and todos via the response fields.
- You can only modify todos you authored or that target the file you are
  analyzing - surfaced transparently by the prompt when applicable.
- You cannot delete notes, clear memory, or touch other files' cache.

Make items specific: include function/class names and file paths.

Prioritize high-impact issues that affect security, performance, or maintainability."""
        
        return prompt

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

        # Build a file-scoped MemoryView. The view enforces that this agent can
        # only write the cache for this file and only modify todos it owns or
        # that are targeted at this file.
        memory_view = self._resolve_memory_view(repository_context, file_path)

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
                file_path=file_path,
                content=content,
                analysis_focus=analysis_focus,
                repository_context=repository_context,
                memory_view=memory_view,
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

                # Persist findings to shared memory through the scoped view.
                # Notes are about *this* file, so we scope them. Todos are
                # cross-file checks - leave them unscoped so the agent that
                # later analyzes the referenced file can see them.
                if memory_view is not None:
                    new_todos = getattr(structured_response, 'memory_items', None) or []
                    new_notes = getattr(structured_response, 'notes', None) or []
                    if new_todos:
                        memory_view.add_todos(new_todos)
                        logger.info(f"{file_path}: added {len(new_todos)} todos")
                    if new_notes:
                        memory_view.add_notes(new_notes, file_path=file_path)
                        logger.info(f"{file_path}: added {len(new_notes)} notes")

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

            # Always record that we analyzed this file, regardless of which
            # path produced the issues. Otherwise the orchestrator's "Already
            # Analyzed Files" view drifts out of sync.
            if memory_view is not None:
                memory_view.cache_file_analysis(file_path, {
                    'issues_count': len(issues),
                    'focus': analysis_focus,
                })
            
            logger.info(f"File analysis complete: {len(issues)} issues found in {file_path}")
            return issues
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return []
    
    def _resolve_memory_view(self, repository_context: Optional[Dict[str, Any]],
                             file_path: str) -> Optional[MemoryView]:
        """Return a MemoryView scoped to the given file.

        Accepts either a pre-built MemoryView (preferred) or a raw SharedMemory
        in ``repository_context['shared_memory']`` for backwards compatibility.
        """
        if repository_context and 'shared_memory' in repository_context:
            obj = repository_context['shared_memory']
            if isinstance(obj, MemoryView):
                return obj
            if isinstance(obj, SharedMemory):
                return obj.view_for(role=ROLE_FILE_ANALYSIS, file_scope=file_path)
        if isinstance(self.shared_memory, SharedMemory):
            return self.shared_memory.view_for(role=ROLE_FILE_ANALYSIS, file_scope=file_path)
        return None

    def _build_file_analysis_prompt(self, file_path: str, content: str,
                                   analysis_focus: str,
                                   repository_context: Optional[Dict[str, Any]],
                                   memory_view: Optional[MemoryView] = None) -> str:
        """Build analysis prompt for a specific file"""
        file_extension = Path(file_path).suffix.lower()
        language = self._get_language(file_extension)
        all_files = TreeConstructor.get_file_list({'tree': repository_context['tree']})
        
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

STRUCTURE:
{json.dumps(repository_context['tree'], indent=2)}

FILES:
{TreeConstructor.format_file_list(all_files)}...

ANALYSIS FOCUS: {analysis_focus.upper()}
{focus_instructions}"""

        # Query and inject relevant custom rules if RulesIndexer is available
        if hasattr(self.config, 'rules_indexer') and self.config.rules_indexer is not None:
            try:
                # Extract function and class names from file content
                functions, classes = extract_symbols(file_path, content)
                
                # Detect if this is a test file
                is_test = self._is_test_file(file_path)
                
                # Query relevant rules
                relevant_rules = self.config.rules_indexer.query_rules(
                    file_path=file_path,
                    functions=functions,
                    classes=classes,
                    is_test=is_test,
                    limit=5  # Get top 5 most relevant rules
                )
                
                if relevant_rules:
                    logger.info(f"Retrieved {len(relevant_rules)} relevant rules for {file_path}")

                    rules_text = "\n\n".join([
                        f"**Rule {i+1}** [{rule['category']}/{rule.get('subcategory', '')}] (Priority: {rule['priority']})\n{rule['content']}"
                        for i, rule in enumerate(relevant_rules)
                    ])
                    
                    prompt += f"""

RELEVANT CUSTOM RULES (HIGHEST PRIORITY):
These specific rules have been selected as most relevant for this file based on its context.
Follow these rules carefully during analysis:

{rules_text}

{"="*80}
"""
            except Exception as e:
                logger.error(f"Error querying rules RAG: {e}")
        
        # Add shared memory context (notes + todos) if available
        if memory_view is not None:
            memory_block = memory_view.format_for_prompt(file_path=file_path)
            if memory_block:
                prompt += f"""

SHARED MEMORY:
{memory_block}

Use notes as grounded context. If a todo targets this file, address it and
include a concise note in your `notes` response so other agents see the
resolution."""

        prompt += f"""

FILE CONTENT:
{self.format_code_snippet(content, language)}{truncated_note}

Provide detailed issues with exact line numbers, clear descriptions, and actionable suggestions.

RESPONSE FIELDS:
- `issues`: the code quality issues you found in this file.
- `notes`: durable observations about this file to share with other agents
  (e.g. "authenticate() at line 45 is the single login entry point").
- `memory_items`: todos (cross-file checks) for other agents to pick up
  (e.g. "Check if authenticate() has tests in test_auth.py").
"""

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
    
    def _is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file based on naming conventions"""
        test_patterns = [
            'test_', '_test.', '.test.', 'tests/', 'test/', '__tests__/', 
            'spec.', '.spec.', 'specs/', 'spec/', '__specs__/'
        ]
        path_lower = file_path.lower()
        return any(pattern in path_lower for pattern in test_patterns)
    

