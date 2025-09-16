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
from .tools import AnalyzeFile, AnalyzeFilesBatch, QueryCodebase, QueryFile
from ..core.message_history import MessageRole

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
        session_id: Optional[str] = None
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

        # Function handlers - will be set by the analysis engine
        self.function_handlers = {}
        
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

File Priority:
- Entry points (main.py, index.js, app.py)
- Core logic and configuration files
- Large/complex files
- Test files and documentation

Tools:
- AnalyzeFile(file_path, analysis_focus): Single file analysis
- QueryFile: Answer specific file questions"""

        # Add query_codebase if available
        if self.has_indexed_codebase:
            prompt += "\n- QueryCode: Search across indexed codebase"
        
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

Tools:
- AnalyzeFile(file_path, analysis_focus): Deep analysis of a single file
- QueryFile(file_path, question): Answer specific file questions"""
        
        # Add query_codebase to prompt if available
        if self.has_indexed_codebase:
            prompt += "\n- QueryCodebase: Search indexed codebase"
        
        prompt += "\n\nUse tool-calling interface (not Python code). After analysis, provide comprehensive answers with specific code details."
        
        return prompt

    @property
    def agent_name(self) -> str:
        return "orchestrator_agent"
    
    async def orchestrate_analysis(self, tree_data: Dict[str, Any], 
                                 root_path: Path,
                                 file_analysis_handler: Callable,
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
        
        # Set up the file analysis handler with tracking
        async def tracked_file_analysis_handler(file_path: str = None, analysis_focus: str = "general", **kwargs):
            """Wrapper to track analyzed files"""
            logger.info(f"tracked_file_analysis_handler called with: file_path={file_path}, analysis_focus={analysis_focus}, kwargs={kwargs}")
            
            # Validate required arguments
            if not file_path:
                logger.error(f"analyze_file function called without required 'file_path' argument. Received args: file_path={file_path}, analysis_focus={analysis_focus}, kwargs={kwargs}")
                return {
                    'success': False,
                    'error': 'file_path is required',
                    'issues_found': 0
                }
            
            if file_path not in self.analyzed_files:
                self.analyzed_files.add(file_path)
                logger.info(f"Analyzing file: {file_path} (focus: {analysis_focus})")
                return await file_analysis_handler(file_path, analysis_focus)
            else:
                logger.info(f"File already analyzed: {file_path}")
                return {
                    'success': True,
                    'file_path': file_path,
                    'issues_found': 0,
                    'message': 'File already analyzed'
                }
        
        # Update function handlers (don't overwrite, as batch handler may be set by orchestrator engine)
        logger.info(f"Current function handlers before update: {list(self.function_handlers.keys())}")
        self.function_handlers["AnalyzeFile"] = tracked_file_analysis_handler
        logger.info(f"Function handlers after update: {list(self.function_handlers.keys())}")
        
        # Reset state
        self.analysis_results = []
        self.analyzed_files = set()
        self.current_iteration = 0
        
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
            prompt = self._build_orchestration_prompt(tree_data, root_path)
        
        # Run the orchestration loop
        while self.current_iteration < self.max_iterations:
            self.current_iteration += 1
            logger.info(f"Orchestration iteration {self.current_iteration}")
            
            try:
                # Log available functions
                logger.info(f"Available functions for orchestrator: {list(self.function_handlers.keys())}")
                
                # Build function prompt based on available features
                function_prompt = prompt + "\n\nIMPORTANT: You have access to these functions:\n"
                function_prompt += "1. QueryFile(file_path, question) - answer a focused question about a single file\n"
                function_prompt += "2. AnalyzeFile(file_path, analysis_focus) - deep code-quality analysis when necessary\n"
                
                if self.has_indexed_codebase:
                    function_prompt += "2. QueryCodebase(question) - search the indexed codebase to find patterns and answer cross-file questions\n"
                    function_prompt += "Strategy: Use query_file for specific file questions, query_codebase for cross-file searches and AnalyzeFile to analyze files when necessary.\n"
                else:
                    function_prompt += "Strategy: Use query_file to answer specific questions about files and AnalyzeFile to analyze files when necessary.\n"
                
                if self.mode == "chat":
                    function_prompt += "Return the structured response with 'answer', 'files_to_analyze', and 'analysis_complete' fields when ready."
                else:
                    function_prompt += "Return the structured response with the 'issues' field (required) containing the list of code quality issues found."
                
                # Log handlers right before passing them
                logger.info(f"Passing function handlers to generate_structured_response_with_functions: {list(self.function_handlers.keys())}")
                for handler_name, handler_func in self.function_handlers.items():
                    logger.info(f"  {handler_name}: {'SET' if handler_func is not None else 'NOT SET'}")
                
                # Choose the appropriate schema based on mode
                response_schema = ChatResponseSchema if self.mode == "chat" else AnalysisResponseSchema
                
                # Build function declarations based on available features
                function_declarations = [
                    AnalyzeFile,
                    QueryFile
                ]
                
                # Only include query_codebase if codebase is indexed
                if self.has_indexed_codebase:
                    function_declarations.append(QueryCodebase)
                
                # Generate response with function calling
                response = await self.generate_structured_response_with_functions(
                    prompt=function_prompt,
                    response_schema=response_schema,
                    function_declarations=function_declarations,
                    function_handlers=self.function_handlers,
                    context={
                        'iteration': self.current_iteration,
                        'analyzed_files_count': len(self.analyzed_files),
                        'total_files': tree_data['statistics']['total_files'],
                        'mode': self.mode
                    }
                )
                
                # Handle response based on mode
                if self.mode == "chat":
                    # Chat mode - check if analysis is complete
                    if hasattr(response, 'analysis_complete') and response.analysis_complete:
                        # Store the final answer
                        self.chat_answer = response.answer
                        logger.info("Chat analysis complete")
                        break
                    else:
                        # Continue analyzing files if needed
                        if hasattr(response, 'files_to_analyze') and response.files_to_analyze:
                            logger.info(f"Chat mode: Need to analyze {len(response.files_to_analyze)} more files")
                        prompt = self._build_chat_iteration_prompt(user_question, tree_data, root_path)
                else:
                    # Analysis mode - check for issues
                    if hasattr(response, 'issues') and response.issues:
                        # Convert to CodeIssue objects and store
                        issues = self._convert_to_code_issues(response.issues, root_path)
                        self.analysis_results.extend(issues)
                        logger.info(f"Found {len(issues)} issues in iteration {self.current_iteration}")
                        
                        # Update prompt for next iteration
                        prompt = self._build_iteration_prompt(tree_data, root_path)
                    else:
                        # No more issues found, analysis complete
                        logger.info("Orchestration complete - no more issues found")
                        break
                    
            except Exception as e:
                logger.error(f"Error in orchestration iteration {self.current_iteration}: {e}")
                # Continue to next iteration instead of breaking completely
                # This allows the analysis to continue even if one iteration fails
                if self.current_iteration >= self.max_iterations - 1:
                    logger.warning("Reached max iterations, stopping orchestration")
                    break
                continue
        
        # Compile final results
        all_issues = []
        for result in self.analysis_results:
            if isinstance(result, list):
                all_issues.extend(result)
            else:
                all_issues.append(result)
        
        # Return based on mode
        if self.mode == "chat":
            # Return the stored chat answer
            if self.chat_answer:
                logger.info(f"Chat orchestration complete: {len(self.analyzed_files)} files analyzed")
                if self.session_id:
                    await self.message_history_manager.add_message(self.session_id, role=MessageRole.AI, content=self.chat_answer)
                return self.chat_answer
            else:
                # Fallback: generate a simple answer if no answer was stored
                logger.warning("No chat answer stored, generating fallback answer")
                return f"I analyzed {len(self.analyzed_files)} files but couldn't generate a complete answer. Please try rephrasing your question."
        else:
            logger.info(f"Analysis orchestration complete: {len(all_issues)} total issues found")
            return all_issues
    
    def _build_orchestration_prompt(self, tree_data: Dict[str, Any], root_path: Path) -> str:
        """Build the initial orchestration prompt"""
        stats = tree_data['statistics']
        all_files = self._get_file_list_from_tree(tree_data)
        
        prompt = f"""Analyzing repository: {root_path}
- Files: {stats['total_files']} ({stats['total_size'] / (1024*1024):.1f}MB)
- Types: {list(stats['file_extensions'].keys())[:5]}

STRUCTURE:
{json.dumps(tree_data['tree'], indent=2)[:1500]}...

FILES:
{self._format_file_list(all_files[:30])}

Use analyze_files_batch or analyze_file to examine critical files (entry points, configs, core logic).
After analysis, return: {{"issues": [Issues from the analysis with proper schema]}}"""
        
        return prompt
    
    def _build_iteration_prompt(self, tree_data: Dict[str, Any], root_path: Path) -> str:
        """Build prompt for subsequent iterations"""
        all_files = self._get_file_list_from_tree(tree_data)
        remaining_files = [f for f in all_files if f['path'] not in self.analyzed_files]
        
        prompt = f"""Analyzed: {len(self.analyzed_files)} files

REMAINING:
{self._format_file_list(remaining_files[:20])}

Continue with supporting files, tests, and documentation.
Use tools, then return: {{"issues": [...]}}"""
        
        return prompt
    
    def _get_file_list_from_tree(self, tree_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract file list from tree data"""
        files = []
        
        def extract_files(node, current_path=""):
            if isinstance(node, dict):
                # Check if this is a file node
                if node.get('is_file', False):
                    files.append({
                        'path': node.get('path', current_path),
                        'size': node.get('size', 0),
                        'extension': node.get('extension', ''),
                        'name': node.get('name', '')
                    })
                # Check if this is a directory node with children
                elif node.get('is_directory', False) and 'children' in node:
                    # children is a list, not a dictionary
                    for child_data in node['children']:
                        extract_files(child_data, current_path)
        
        extract_files(tree_data['tree'])
        return files
    
    def _format_file_list(self, files: List[Dict[str, Any]]) -> str:
        """Format file list for display"""
        if not files:
            return "No files available"
        
        formatted = []
        for file_info in files:
            size_kb = file_info['size'] / 1024 if file_info['size'] > 0 else 0
            formatted.append(f"- {file_info['path']} ({size_kb:.1f}KB, {file_info['extension']})")
        
        return '\n'.join(formatted)
    
    def _convert_to_code_issues(self, issues: List[CodeIssueSchema], root_path: Path) -> List[CodeIssue]:
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
                file_path = root_path / issue_schema.file_path
                
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
        all_files = self._get_file_list_from_tree(tree_data)
        
        prompt = f"""User question: "{question}"

Repository: {root_path} ({stats['total_files']} files, {stats['total_size'] / (1024*1024):.1f}MB)
Types: {list(stats['file_extensions'].keys())[:5]}

FILES:
{self._format_file_list(all_files[:30])}"""

        # Include existing analysis results if available
        if self._cached_analysis_result:
            issues_count = len(self._cached_analysis_result.issues)
            prompt += f"\n\nPrevious analysis: {issues_count} issues found"

        prompt += "\n\nAnalyze relevant files if needed using the tools. Focus on files related to the question."""
        
        return prompt
    
    def _build_chat_iteration_prompt(self, question: str, tree_data: Dict[str, Any], root_path: Path) -> str:
        """Build iteration prompt for chat mode"""
        all_files = self._get_file_list_from_tree(tree_data)
        remaining_files = [f for f in all_files if f['path'] not in self.analyzed_files]
        
        prompt = f"""Continue for: "{question}"
Analyzed: {len(self.analyzed_files)} files

REMAINING:
{self._format_file_list(remaining_files[:20])}

Analyze more files or return {{"issues": []}} if sufficient information gathered."""
        
        return prompt
    
    async def _generate_chat_answer(self, question: str, issues: List[CodeIssue], tree_data: Dict[str, Any], root_path: Path) -> str:
        """Generate the final answer for chat mode"""
        # Build context from analyzed files
        analyzed_context = {
            'question': question,
            'analyzed_files': list(self.analyzed_files),
            'analysis_results': [
                {
                    'title': issue.title,
                    'description': issue.description,
                    'file_path': str(issue.file_path.relative_to(root_path)),
                    'line_number': issue.line_number,
                    'code_snippet': issue.code_snippet,
                    'suggestion': issue.suggestion
                }
                for issue in issues
            ],
            'repository_stats': tree_data['statistics']
        }
        
        answer_prompt = f"""Based on your analysis of the codebase, provide a comprehensive answer to the user's question.

USER QUESTION: "{question}"

ANALYZED FILES: {len(self.analyzed_files)} files
- {', '.join(list(self.analyzed_files)[:10])}{'...' if len(self.analyzed_files) > 10 else ''}

ANALYSIS RESULTS: {len(issues)} pieces of information gathered

Please provide a detailed, helpful answer that:
1. Directly addresses the user's question
2. Includes specific details from the analyzed code when relevant
3. Explains the code structure, functionality, or implementation details as needed
4. Provides context about how different parts of the codebase relate to the question
5. Is clear and easy to understand

Be as specific and helpful as possible."""
        
        try:
            final_answer = await self.generate_response(answer_prompt, analyzed_context)
            return final_answer
        except Exception as e:
            logger.error(f"Error generating final answer: {e}")
            return f"I apologize, but I encountered an error while generating the final answer. However, I was able to analyze {len(self.analyzed_files)} files in the repository. Please try rephrasing your question or ask about a specific aspect of the codebase."
