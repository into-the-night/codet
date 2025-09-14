"""Shared file filtering utilities for consistent file handling across the codebase"""

from pathlib import Path
from typing import Optional, List, Any, Callable
import gitignore_parser
import logging

logger = logging.getLogger(__name__)


class FileFilter:
    """Centralized file filtering for consistent behavior across the codebase"""
    
    DEFAULT_IGNORE_PATTERNS = [
        '*.pyc', '*.pyo', '*.pyd', '__pycache__', '.git', '.svn', 
        'node_modules', '.env', '*.log', '*.tmp', '.DS_Store',
        '*.egg-info', 'dist', 'build', '.pytest_cache', '.coverage',
        '.next', 'coverage', '.venv', 'venv', 'env'
    ]
    
    def __init__(self, 
                 ignore_patterns: Optional[List[str]] = None,
                 include_hidden: bool = False,
                 gitignore_parser: Optional[Callable] = None):
        """
        Initialize the file filter
        
        Args:
            ignore_patterns: List of patterns to ignore (uses defaults if None)
            include_hidden: Whether to include hidden files/directories
            gitignore_parser: Parsed .gitignore function (from gitignore_parser.parse_gitignore)
        """
        self.ignore_patterns = ignore_patterns or self.DEFAULT_IGNORE_PATTERNS
        self.include_hidden = include_hidden
        self._gitignore = gitignore_parser
        
    @classmethod
    def from_path(cls, path: Path, 
                  ignore_patterns: Optional[List[str]] = None,
                  include_hidden: bool = False) -> 'FileFilter':
        """
        Create a FileFilter with gitignore support for the given path
        
        Args:
            path: Path to look for .gitignore file
            ignore_patterns: Additional ignore patterns
            include_hidden: Whether to include hidden files
        """
        gitignore_func = cls._load_gitignore(path)
        return cls(ignore_patterns=ignore_patterns, 
                  include_hidden=include_hidden,
                  gitignore_parser=gitignore_func)
    
    @staticmethod
    def _load_gitignore(path: Path) -> Optional[Callable]:
        """Load .gitignore file if it exists"""
        # Look for .gitignore in the directory or parent if path is a file
        if path.is_file():
            gitignore_path = path.parent / ".gitignore"
        else:
            gitignore_path = path / ".gitignore"
            
        if gitignore_path.exists():
            try:
                return gitignore_parser.parse_gitignore(gitignore_path)
            except Exception as e:
                logger.warning(f"Failed to parse .gitignore: {e}")
        return None
    
    def should_ignore(self, path: Path) -> bool:
        """
        Check if a path should be ignored based on patterns and gitignore
        
        Args:
            path: Path to check
            
        Returns:
            bool: True if the path should be ignored
        """
        path_str = str(path)
        
        # Check if it's a hidden file/directory
        if not self.include_hidden and any(part.startswith('.') for part in path.parts):
            return True
            
        # Check against ignore patterns
        for pattern in self.ignore_patterns:
            if pattern.startswith('*'):
                # Wildcard pattern for file extensions
                if path.name.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                # Directory or substring pattern
                return True
                
        # Check gitignore
        if self._gitignore and self._gitignore(str(path)):
            return True
            
        return False
    
    def filter_paths(self, paths: List[Path]) -> List[Path]:
        """
        Filter a list of paths based on ignore patterns
        
        Args:
            paths: List of paths to filter
            
        Returns:
            List of paths that should not be ignored
        """
        return [p for p in paths if not self.should_ignore(p)]
    
    def iter_files(self, root_path: Path, 
                   extensions: Optional[List[str]] = None) -> List[Path]:
        """
        Iterate through files in a directory, respecting ignore patterns
        
        Args:
            root_path: Root directory to search
            extensions: Optional list of file extensions to include (e.g., ['.py', '.js'])
            
        Returns:
            List of file paths that pass the filter
        """
        files = []
        
        if root_path.is_file():
            if not self.should_ignore(root_path):
                if not extensions or root_path.suffix in extensions:
                    files.append(root_path)
        else:
            for file_path in root_path.rglob("*"):
                if file_path.is_file():
                    if not self.should_ignore(file_path):
                        if not extensions or file_path.suffix in extensions:
                            files.append(file_path)
        
        return sorted(files)
