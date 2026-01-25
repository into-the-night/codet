"""Main orchestrator agent that coordinates the analysis flow"""

import json
import logging
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from datetime import datetime

from .base_agent import BaseAgent
from .schemas import AnalysisResponseSchema, CodeIssueSchema, ChatResponseSchema
from ..core.config import AgentConfig, RedisConfig
from ..analyzers.analyzer import CodeIssue, IssueCategory, IssueSeverity
from .tools import AnalyzeFile, QueryCodebase, QueryFile
from ..core.message_history import MessageRole
from ..core.shared_memory import SharedMemory
from ..core.repository_tree import RepositoryTreeConstructor as TreeConstructor

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Main orchestrator that decides which files to analyze and coordinates the analysis flow"""
    
    def __init__(
        self,
        config: AgentConfig,
        redis_config: Optional[RedisConfig] = None,
        mode: str = "analysis",
        custom_system_prompt: Optional[str] = None,
        has_indexed_codebase: bool = False,
        session_id: Optional[str] = None,
        shared_memory: Optional[SharedMemory] = None
        ):
        super().__init__(config, redis_config)
        self.analysis_results = []  # Store results from each analysis iteration
        self.analyzed_files = set()  # Track which files have been analyzed
        self.max_iterations = 10  # Prevent infinite loops
        self.current_iteration = 0
        self.mode = mode  # 'analysis' or 'chat'
        self.has_indexed_codebase = has_indexed_codebase  # Track if codebase is indexed
        self.custom_system_prompt = custom_system_prompt  # Allow custom prompts
        self.user_question = None  # Store user question for chat mode
        self.chat_answer = None  # Store final answer for chat mode
        self._cached_analysis_result = None  # Store cached analysis for chat mode
        self.session_id = session_id  # Store message key for chat mode
        self.shared_memory = shared_memory  # Shared memory for cross-codebase context
        
        # Event callback for streaming updates
        self._event_callback = None
        
    @property
    def system_prompt(self) -> str:
        """System prompt for the orchestrator"""
        if self.custom_system_prompt:
            return self.custom_system_prompt
        
        if self.mode == "chat":
            prompt = self._get_chat_system_prompt()
            if prompt is None:
                logger.error("_get_chat_system_prompt returned None!")
            return prompt
        else:
            prompt = self._get_analysis_system_prompt()
            if prompt is None:
                logger.error("_get_analysis_system_prompt returned None!")
            return prompt
    
    def _get_analysis_system_prompt(self) -> str:
        """Default system prompt for analysis mode"""
        prompt = """You are the main orchestrator for code analysis. Strategically select and analyze files using the provided tools.

WORKFLOW:
1. Use tools through the system's tool-calling interface (NOT Python code)
2. Wait for tool results
3. Return {"issues": [...]} with findings

SHARED MEMORY:
- Review shared memory for pending action items before selecting files
- Prioritize analyzing files related to pending action items
- After analyzing files that address action items, you can remove completed items
- Add new items when discovering cross-file dependencies or concerns
- Generate memory_items in your response for cross-codebase context

Examples of good memory items:
  * "Check if authenticate() function has tests in test_auth.py"
  * "Verify error handling in payment_processor.py matches validation.py"
  * "Ensure User class methods are documented"

File Priority:
- Entry points (main.py, index.js, app.py)
- Core logic and configuration files
- Large/complex files
- Test files and documentation
"""

        # Add query_codebase if available
        if self.has_indexed_codebase:
            prompt += "\n- QueryCode(question, search_limit): Search across indexed codebase"
        
        prompt += '\n\nReturn {"issues": []} when analysis complete.'
        
        return prompt
    
    def _get_chat_system_prompt(self) -> str:
        """System prompt for chat mode"""
        prompt = """You are an AI assistant specialized in answering questions about codebases.

When a user asks about the codebase:
1. Analyze only if needed (skip for greetings or unrelated questions)
2. Choose relevant files to examine
3. Use tools to analyze files
4. Provide comprehensive answers with code details

SHARED MEMORY:
- Review shared memory for context from previous analysis steps
- Add action items when discovering related concerns across files
- Generate memory_items in your response for cross-codebase context

Examples: "Check if process_order() has proper error handling", "Verify API authentication is consistent"
"""
        
        # Add query_codebase to prompt if available
        if self.has_indexed_codebase:
            prompt += "\n- QueryCodebase(question, search_limit): Search indexed codebase"
        
        prompt += "\n\nUse tool-calling interface (not Python code). After analysis, provide comprehensive answers with specific code details."
        
        return prompt

    @property
    def agent_name(self) -> str:
        return "orchestrator_agent"
    
    async def orchestrate_analysis(self, tree_data: Dict[str, Any], 
                                 root_path: Path,
                                 user_question: Optional[str] = None) -> Any:
        """
        Main orchestration method that runs the analysis loop
        
        Args:
            tree_data: Repository tree structure
            root_path: Path to repository root
            file_analysis_handler: Function to handle file analysis requests
            user_question: Optional question for chat mode
            
        Returns:
            List of CodeIssue objects for analysis mode, or answer string for chat mode
        """
        logger.info(f"Starting orchestrated {self.mode}")
        self.user_question = user_question

        # Reset state
        self.analysis_results = []
        self.analyzed_files = set()
        self.current_iteration = 0
        
        # Build prompt
        if self.mode == "chat" and user_question:
            prompt = self._build_chat_prompt(user_question, tree_data, root_path)
            await self.initialize_redis()
            if self.session_id is None:
                self.session_id = await self.message_history_manager.create_session(agent_name=self.agent_name)
            else:
                message_history = await self.message_history_manager.get_recent_messages(session_id=self.session_id, count=5)
                if message_history:
                    prompt += "This is the message history:"
                    prompt += json.dumps(message_history, indent=2)
        else:
            prompt = self._build_analysis_prompt(tree_data, root_path)
        
        # Tool processor callback
        async def tool_processor(tool_name: str, result: Any) -> str:
            if tool_name == "AnalyzeFile":
                # Extract issues and add to local results
                if isinstance(result, dict) and 'issues' in result:
                    # Convert to CodeIssue objects and store
                    issues = self._convert_to_code_issues(
                        [CodeIssueSchema(**i) for i in result['issues']], 
                        root_path,
                        file_path=result.get('file_path')
                    )
                    self.analysis_results.extend(issues)
                    
                    return f"Analysis complete for {result.get('file_path', 'unknown')}. Found {len(issues)} issues: {[i.title for i in issues]}"
                return str(result)
            return str(result)

        # Prepare tools
        tools = [AnalyzeFile, QueryFile]
        if self.has_indexed_codebase:
            tools.append(QueryCodebase)

        # Run the autonomous loop
        try:
            final_response = await self.run_tool_loop(
                user_input=prompt,
                system_message=self.system_prompt,
                tools=tools,
                tool_output_processor=tool_processor
            )
        except Exception as e:
            logger.error(f"Error in orchestration loop: {e}")
            final_response = "Error during orchestration."

        # Return based on mode
        if self.mode == "chat":
             if self.session_id:
                  await self.message_history_manager.add_message(self.session_id, role=MessageRole.AI, content=final_response)
             return final_response
        else:
            logger.info(f"Analysis orchestration complete: {len(self.analysis_results)} total issues found")
            return self.analysis_results
    
    def _build_analysis_prompt(self, tree_data: Dict[str, Any], root_path: Path) -> str:
        """Build the initial orchestration prompt"""
        stats = tree_data['statistics']
        all_files = TreeConstructor.get_file_list(tree_data)
        
        prompt = f"""Analyzing repository: {root_path}
- Files: {stats['total_files']} ({stats['total_size'] / (1024*1024):.1f}MB)
- Types: {list(stats['file_extensions'].keys())[:5]}

STRUCTURE:
{json.dumps(tree_data['tree'], indent=2)}...

FILES:
{TreeConstructor.format_file_list(all_files)}"""

        # Add shared memory content if available
        if self.shared_memory and len(self.shared_memory) > 0:
            memory_items = self.shared_memory.format_items()
            prompt += f"""

SHARED MEMORY - Pending Action Items:
{memory_items}

Priority: Address these action items first by analyzing relevant files."""
        
        prompt += "\n\nUse analyze_file to examine critical files (entry points, configs, core logic).\nAfter analysis, return: {\"issues\": [Issues from the analysis with proper schema]}"
        
        return prompt
    
    
    def _convert_to_code_issues(self, issues: List[CodeIssueSchema], root_path: Path, file_path: Optional[str] = None) -> List[CodeIssue]:
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
                
                # Create file path
                if file_path:
                    issue_file_path = root_path / file_path
                elif hasattr(issue_schema, 'file_path') and issue_schema.file_path:
                    issue_file_path = root_path / issue_schema.file_path
                else:
                    logger.warning("No file path provided for issue")
                    continue
                
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
                    file_path=issue_file_path,
                    line_number=issue_schema.line_number,
                    column_number=issue_schema.column_number,
                    suggestion=issue_schema.suggestion,
                    code_snippet=issue_schema.code_snippet,
                    metadata={
                        'ai_detected': True,
                        'orchestrator_managed': True,
                        'impact': issue_schema.impact or '',
                        'detection_timestamp': datetime.now().isoformat(),
                        'iteration': self.current_iteration
                    }
                )
                
                code_issues.append(issue)
                
            except Exception as e:
                logger.warning(f"Failed to convert orchestrator issue: {e}")
                continue
        
        return code_issues
    
    def set_cached_analysis(self, analysis_result):
        """Set cached analysis result for use in chat mode"""
        self._cached_analysis_result = analysis_result
    
    def _build_chat_prompt(self, question: str, tree_data: Dict[str, Any], root_path: Path) -> str:
        """Build the initial prompt for chat mode"""
        stats = tree_data['statistics']
        all_files = TreeConstructor.get_file_list(tree_data)
        
        prompt = f"""User question: "{question}"

Repository: {root_path} ({stats['total_files']} files, {stats['total_size'] / (1024*1024):.1f}MB)
Types: {list(stats['file_extensions'].keys())[:5]}

FILES:
{TreeConstructor.format_file_list(all_files)}"""

        # Include existing analysis results if available
        if self._cached_analysis_result:
            issues_count = len(self._cached_analysis_result.issues)
            prompt += f"\n\nPrevious analysis: {issues_count} issues found"

        # Add shared memory content if available
        if self.shared_memory and len(self.shared_memory) > 0:
            memory_items = self.shared_memory.format_items()
            prompt += f"""

SHARED MEMORY - Context from Previous Analysis:
{memory_items}"""

        prompt += "\n\nYou can query relevant files if needed using the tools. Focus on files related to the user's question ONLY. DO NOT ASSUME ANYTHING."""
        
        return prompt
    
    def set_event_callback(self, callback):
        """
        Set callback function for streaming real-time events.
        
        The callback should accept two arguments:
        - event_type: str (e.g., 'tool_start', 'tool_complete', 'reasoning', 'memory_update')
        - data: dict (event-specific data)
        """
        self._event_callback = callback
    
    def _emit_event(self, event_type: str, data: dict):
        """Emit an event to the callback if one is set"""
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"Error emitting event: {e}")
