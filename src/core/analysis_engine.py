"""Analysis engine implementing AI-powered code analysis"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from ..analyzers.analyzer import AnalysisResult
from ..core.repository_tree import RepositoryTreeConstructor
from ..core.config import Config
from ..core.orchestrator_engine import OrchestratorEngine
from ..reports.report_generator import ReportGenerator
from ..analyzers import (
    PythonAnalyzer,
    JavaScriptAnalyzer,
    DuplicationAnalyzer
)


logger = logging.getLogger(__name__)


class AnalysisEngine:
    """Analysis engine that uses orchestrator flow for comprehensive code analysis"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.tree_constructor = RepositoryTreeConstructor()
        self.report_generator = ReportGenerator()
        self.analyzers = self._initialize_analyzers()
        self.orchestrator_engine = None
        self.enable_orchestrator = False
        
    def enable_analysis(
            self,
            config_path: Optional[Path] = None,
            use_parallel: bool = True,
            has_indexed_codebase: bool = False, 
            collection_name: Optional[str] = None
        ):
        """Enable orchestrator-powered analysis (main analysis method)"""
        try:
            full_config = Config.load(config_path)
            full_config.validate()
            
            # Use standard orchestrator
            logger.info("Using orchestrator with parallel file analysis support")
            self.orchestrator_engine = OrchestratorEngine(
                full_config,
                has_indexed_codebase=has_indexed_codebase,
                collection_name=collection_name
            )
            
            self.orchestrator_engine.initialize_agents(config_path, use_parallel=use_parallel)
            self.enable_orchestrator = True
            logger.info("Orchestrator analysis enabled successfully")
        except Exception as e:
            logger.error(f"Failed to enable orchestrator analysis: {e}")
            self.enable_orchestrator = False

    def _initialize_analyzers(self) -> List:
        """Initialize all available analyzers"""
        return [
            PythonAnalyzer(self.config.get('python', {})),
            JavaScriptAnalyzer(self.config.get('javascript', {})),
            DuplicationAnalyzer(self.config.get('duplication', {}))
        ]
    
    async def analyze_repository(self, path: Path) -> AnalysisResult:
        """
        Analyze repository using the orchestrator flow
        
        Args:
            path: Path to repository
        """
        logger.info(f"Starting orchestrator analysis of {path}")
        
        if not self.enable_orchestrator or not self.orchestrator_engine:
            raise ValueError("Orchestrator analysis must be enabled")
        
        # Use the orchestrator engine for analysis
        return await self.orchestrator_engine.analyze_repository(path)
    
    
    def get_tree_summary(self, path: Path) -> str:
        """Get a summary of the repository tree structure"""
        tree_data = self.tree_constructor.construct_tree(path)
        return self.tree_constructor.get_tree_summary(tree_data)
    
    def get_file_list(self, path: Path, 
                     extensions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get a list of files in the repository"""
        tree_data = self.tree_constructor.construct_tree(path)
        
        if extensions:
            return self.tree_constructor.filter_files_by_extension(tree_data, extensions)
        else:
            return self.tree_constructor.get_file_list(tree_data)
