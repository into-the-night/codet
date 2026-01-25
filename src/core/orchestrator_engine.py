"""Main orchestrator engine that implements the analysis flow"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import asyncio
import uuid

from ..analyzers.analyzer import AnalysisResult, CodeIssue
from ..core.repository_tree import RepositoryTreeConstructor
from .config import Config
from .shared_memory import SharedMemory
from ..agents.orchestrator_agent import OrchestratorAgent
from ..agents.file_analysis_agent import FileAnalysisAgent
from ..reports.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class OrchestratorEngine:
    """Main orchestrator engine that coordinates the analysis flow"""
    
    def __init__(
        self, 
        config: Optional[Config] = None, 
        mode: str = "analysis",
        has_indexed_codebase: bool = False, 
        collection_name: Optional[str] = None, 
        session_id: Optional[str] = None
        ):
        self.config = config or Config.load()
        self.mode = mode  # 'analysis' or 'chat'
        self.has_indexed_codebase = has_indexed_codebase
        self.collection_name = collection_name or "codebase"
        self.tree_constructor = RepositoryTreeConstructor()
        self.report_generator = ReportGenerator()
        
        # Initialize agents
        self.orchestrator_agent = None
        self.file_analysis_agent = None

        # Analysis state
        self.analysis_results = []
        self.analyzed_files = set()
        self._codebase_indexer = None
        self._cached_analysis_result = None  # Store cached analysis for chat mode
        self.session_id = session_id
        
        # Event callback for streaming updates
        self._event_callback = None
        
        # Initialize shared memory for cross-codebase context
        self.shared_memory = SharedMemory()
        logger.info("Initialized shared memory for cross-codebase context")

    def initialize_agents(
        self,
        config_path: Optional[Path] = None,
        custom_system_prompt: Optional[str] = None
        ):
        """Initialize the orchestrator and file analysis agents"""
        try:
            if config_path:
                full_config = Config.load(config_path)
            else:
                full_config = self.config
            
            full_config.validate()

            # Initialize agents with the same config and mode
            self.orchestrator_agent = OrchestratorAgent(
                full_config.agent,
                full_config.redis,
                mode=self.mode,
                custom_system_prompt=custom_system_prompt,
                has_indexed_codebase=self.has_indexed_codebase,
                session_id=self.session_id,
                shared_memory=self.shared_memory
            )
            self.file_analysis_agent = FileAnalysisAgent(full_config.agent, shared_memory=self.shared_memory)
            
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
        
        # Clear shared memory at the start of each analysis
        self.shared_memory.clear()
        logger.info("Shared memory cleared for new analysis session")
        
        # Run the orchestrator analysis
        try:
            result = await self.orchestrator_agent.orchestrate_analysis(
                tree_data=tree_data,
                root_path=root_path,
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
        summary['files_analyzed'] = list(self.analyzed_files)  # Store the list of files, not just count
        summary['files_analyzed_count'] = len(self.analyzed_files)  # Store count separately
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
    
    def set_cached_analysis(self, analysis_result: Optional[AnalysisResult]):
        """Set cached analysis result for use in chat mode"""
        self._cached_analysis_result = analysis_result
    
    def set_event_callback(self, callback):
        """
        Set callback function for streaming real-time events.
        
        The callback should accept two arguments:
        - event_type: str (e.g., 'tool_start', 'tool_complete', 'reasoning', 'memory_update')
        - data: dict (event-specific data)
        """
        self._event_callback = callback
        # Also set the callback on the orchestrator agent if it exists
        if self.orchestrator_agent:
            self.orchestrator_agent.set_event_callback(callback)
    
    def _emit_event(self, event_type: str, data: dict):
        """Emit an event to the callback if one is set"""
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"Error emitting event: {e}")
