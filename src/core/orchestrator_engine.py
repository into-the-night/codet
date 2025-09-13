"""Main orchestrator engine that implements the analysis flow"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import asyncio

from ..analyzers.analyzer import AnalysisResult, CodeIssue
from ..core.repository_tree import RepositoryTreeConstructor
from .config import Config
from ..agents.orchestrator_agent import OrchestratorAgent
from ..agents.file_analysis_agent import FileAnalysisAgent
from ..reports.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class OrchestratorEngine:
    """Main orchestrator engine that coordinates the analysis flow"""
    
    def __init__(self, config: Optional[Config] = None, mode: str = "analysis"):
        self.config = config or Config.load()
        self.mode = mode  # 'analysis' or 'chat'
        self.tree_constructor = RepositoryTreeConstructor()
        self.report_generator = ReportGenerator()
        
        # Initialize agents
        self.orchestrator_agent = None
        self.file_analysis_agent = None
        
        # Analysis state
        self.analysis_results = []
        self.analyzed_files = set()
        
    def initialize_agents(self, config_path: Optional[Path] = None, custom_system_prompt: Optional[str] = None):
        """Initialize the orchestrator and file analysis agents"""
        try:
            if config_path:
                full_config = Config.load(config_path)
            else:
                full_config = self.config
            
            full_config.validate()
            
            # Initialize agents with the same config and mode
            self.orchestrator_agent = OrchestratorAgent(full_config.agent, mode=self.mode, custom_system_prompt=custom_system_prompt)
            self.file_analysis_agent = FileAnalysisAgent(full_config.agent)
            
            logger.info(f"Orchestrator agents initialized successfully for {self.mode} mode")
            
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator agents: {e}")
            raise
    
    async def analyze_repository(self, path: Path,
                               user_question: Optional[str] = None) -> Any:
        """
        Main analysis method that implements the orchestrator flow
        
        Args:
            path: Path to repository
            user_question: Optional question for chat mode
            
        Returns:
            AnalysisResult for analysis mode, or answer string for chat mode
        """
        logger.info(f"Starting orchestrator analysis of {path}")
        
        if not self.orchestrator_agent or not self.file_analysis_agent:
            raise ValueError("Agents must be initialized before analysis")
        
        # Step 1: Construct repository tree
        logger.info("Step 1: Constructing repository tree...")
        tree_data = self.tree_constructor.construct_tree(path)

        # Step 2: Run the orchestrator flow
        logger.info(f"Step 4: Running orchestrator {self.mode} flow...")
        result = await self._run_orchestrator_flow(tree_data, path, user_question)
        
        # Step 3: Return based on mode
        if self.mode == "chat":
            logger.info(f"Chat orchestration complete: {len(self.analyzed_files)} files analyzed")
            return result  # result is already the answer string
        else:
            logger.info("Step 5: Compiling analysis results...")
            analysis_result = self._compile_analysis_result(path, result, tree_data)
            logger.info(f"Orchestrator analysis complete: {len(result)} total issues found")
            return analysis_result
    
    async def _run_orchestrator_flow(self, tree_data: Dict[str, Any], root_path: Path, user_question: Optional[str] = None) -> Any:
        """
        Run the main orchestrator flow:
        1. Pass tree to orchestrator
        2. Orchestrator picks files to analyze
        3. Pass individual files to analysis agent
        4. Collect results and continue until no more tool calls
        
        Returns:
            List of CodeIssue objects for analysis mode, or answer string for chat mode
        """
        logger.info("Starting orchestrator flow")
        
        # Reset state
        self.analysis_results = []
        self.analyzed_files = set()
        
        # Create the file analysis handler that will be called by the orchestrator
        async def file_analysis_handler(file_path: str, analysis_focus: str = "general") -> Dict[str, Any]:
            """Handle file analysis requests from the orchestrator"""
            logger.info(f"Orchestrator requested analysis of: {file_path} (focus: {analysis_focus})")
            
            # Track that we're analyzing this file
            self.analyzed_files.add(file_path)
            
            # Get repository context
            repository_context = {
                'total_files': tree_data['statistics']['total_files'],
                'main_languages': list(tree_data['statistics']['file_extensions'].keys())[:5],
                'project_type': self._detect_project_type(tree_data)
            }
            
            # Add user question context for chat mode
            if self.mode == "chat" and user_question:
                repository_context['user_question'] = user_question
            
            # Analyze the file
            issues = await self.file_analysis_agent.analyze_file(
                file_path=file_path,
                root_path=root_path,
                analysis_focus=analysis_focus,
                repository_context=repository_context
            )
            
            # Store results
            self.analysis_results.extend(issues)
            
            # Return summary for the orchestrator
            return {
                'success': True,
                'file_path': file_path,
                'issues_found': len(issues),
                'analysis_focus': analysis_focus,
                'issues': [
                    {
                        'title': issue.title,
                        'category': issue.category.value,
                        'severity': issue.severity.value,
                        'line_number': issue.line_number
                    }
                    for issue in issues
                ]
            }
        
        # Create batch file analysis handler
        async def batch_file_analysis_handler(files: List[Dict[str, str]]) -> Dict[str, Any]:
            """Handle batch file analysis requests from the orchestrator"""
            logger.info(f"Orchestrator requested batch analysis of {len(files)} files")
            
            # Get repository context
            repository_context = {
                'total_files': tree_data['statistics']['total_files'],
                'main_languages': list(tree_data['statistics']['file_extensions'].keys())[:5],
                'project_type': self._detect_project_type(tree_data)
            }
            
            # Add user question context for chat mode
            if self.mode == "chat" and user_question:
                repository_context['user_question'] = user_question
            
            # Create tasks for parallel analysis
            analysis_tasks = []
            for file_info in files:
                file_path = file_info.get('file_path', '')
                analysis_focus = file_info.get('analysis_focus', 'general')
                
                # Skip if already analyzed
                if file_path in self.analyzed_files:
                    continue
                    
                self.analyzed_files.add(file_path)
                
                # Create analysis task
                task = self.file_analysis_agent.analyze_file(
                    file_path=file_path,
                    root_path=root_path,
                    analysis_focus=analysis_focus,
                    repository_context=repository_context
                )
                analysis_tasks.append((file_path, task))
            
            # Run all analyses in parallel
            results = []
            if analysis_tasks:
                logger.info(f"Running {len(analysis_tasks)} file analyses in parallel")
                
                # Execute tasks concurrently
                task_results = await asyncio.gather(*[task for _, task in analysis_tasks], return_exceptions=True)
                
                # Process results
                for (file_path, _), task_result in zip(analysis_tasks, task_results):
                    if isinstance(task_result, Exception):
                        logger.error(f"Error analyzing {file_path}: {task_result}")
                        results.append({
                            'success': False,
                            'file_path': file_path,
                            'error': str(task_result)
                        })
                    else:
                        issues = task_result
                        self.analysis_results.extend(issues)
                        results.append({
                            'success': True,
                            'file_path': file_path,
                            'issues_found': len(issues),
                            'issues': [
                                {
                                    'title': issue.title,
                                    'category': issue.category.value,
                                    'severity': issue.severity.value,
                                    'line_number': issue.line_number
                                }
                                for issue in issues
                            ]
                        })
            
            return {
                'success': True,
                'batch_results': results,
                'total_files_analyzed': len(results),
                'total_issues_found': sum(r.get('issues_found', 0) for r in results if r.get('success', False))
            }
        
        # Set up handlers for both single and batch analysis
        logger.info("Setting up function handlers in orchestrator engine")
        self.orchestrator_agent.function_handlers = {
            "analyze_file": file_analysis_handler,
            "analyze_files_batch": batch_file_analysis_handler
        }
        logger.info(f"Function handlers set: {list(self.orchestrator_agent.function_handlers.keys())}")
        
        # Run the orchestrator analysis
        try:
            result = await self.orchestrator_agent.orchestrate_analysis(
                tree_data=tree_data,
                root_path=root_path,
                file_analysis_handler=file_analysis_handler,
                user_question=user_question
            )
            
            if self.mode == "chat":
                # For chat mode, result is the answer string
                return result
            else:
                # For analysis mode, return the accumulated issues
                # (result from orchestrator is already included in self.analysis_results)
                return self.analysis_results
            
        except Exception as e:
            logger.error(f"Error in orchestrator flow: {e}")
            if self.mode == "chat":
                return f"I apologize, but I encountered an error while analyzing the codebase. Error: {str(e)}"
            else:
                return self.analysis_results
    
    def _detect_project_type(self, tree_data: Dict[str, Any]) -> str:
        """Detect the type of project based on file structure"""
        file_extensions = tree_data['statistics']['file_extensions']
        
        # Check for common project indicators
        if 'package.json' in str(tree_data.get('tree', {})):
            return 'Node.js/JavaScript'
        elif '.py' in file_extensions and 'requirements.txt' in str(tree_data.get('tree', {})):
            return 'Python'
        elif '.java' in file_extensions:
            return 'Java'
        elif '.go' in file_extensions:
            return 'Go'
        elif '.rs' in file_extensions:
            return 'Rust'
        elif '.cpp' in file_extensions or '.c' in file_extensions:
            return 'C/C++'
        elif '.cs' in file_extensions:
            return 'C#'
        elif '.rb' in file_extensions:
            return 'Ruby'
        elif '.php' in file_extensions:
            return 'PHP'
        else:
            return 'Mixed/Unknown'
    
    def _compile_analysis_result(self, path: Path, 
                               issues: List[CodeIssue],
                               tree_data: Dict[str, Any],
                               languages: Optional[List[str]] = None) -> AnalysisResult:
        """Compile the final analysis result"""
        
        # Create summary
        summary = ReportGenerator.create_summary(issues)
        summary['analysis_type'] = 'orchestrator_analysis'
        summary['tree_statistics'] = tree_data['statistics']
        summary['languages_analyzed'] = 'all'
        summary['files_analyzed'] = len(self.analyzed_files)
        summary['orchestrator_iterations'] = getattr(self.orchestrator_agent, 'current_iteration', 0)
        
        # Add orchestrator-specific metrics
        orchestrator_issues = [i for i in issues if i.metadata and i.metadata.get('orchestrator_managed')]
        file_analysis_issues = [i for i in issues if i.metadata and i.metadata.get('file_analysis_agent')]
        
        summary['orchestrator_issues_count'] = len(orchestrator_issues)
        summary['file_analysis_issues_count'] = len(file_analysis_issues)
        summary['orchestrator_analysis_enabled'] = True
        
        # Prioritize issues
        prioritized_issues = ReportGenerator.prioritize_issues(issues)
        
        # Create metrics
        metrics = {
            'total_files': tree_data['statistics']['total_files'],
            'total_directories': tree_data['statistics']['total_directories'],
            'total_size': tree_data['statistics']['total_size'],
            'file_extensions': tree_data['statistics']['file_extensions'],
            'largest_files': tree_data['statistics']['largest_files'],
            'deepest_path': tree_data['statistics']['deepest_path'],
            'analysis_method': 'orchestrator_analysis',
            'tree_constructed_at': tree_data['constructed_at'],
            'files_analyzed': list(self.analyzed_files),
            'analyzed_files_count': len(self.analyzed_files)
        }
        
        return AnalysisResult(
            project_path=path,
            issues=prioritized_issues,
            metrics=metrics,
            summary=summary,
            timestamp=datetime.now().isoformat()
        )
    
    def get_file_list(self, path: Path, 
                     extensions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get a list of files in the repository"""
        tree_data = self.tree_constructor.construct_tree(path)
        
        if extensions:
            return self.tree_constructor.filter_files_by_extension(tree_data, extensions)
        else:
            return self.tree_constructor.get_file_list(tree_data)
    
    async def answer_question(self, question: str, 
                            path: Path) -> str:
        """
        Convenience method for chat mode - answer a question about the codebase
        
        Args:
            question: The user's question
            path: Path to repository
            
        Returns:
            str: Answer to the user's question
        """
        if self.mode != "chat":
            raise ValueError("answer_question can only be used in chat mode")
        
        return await self.analyze_repository(
            path=path,
            user_question=question
        )
