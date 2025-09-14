"""Repository size checker utility for determining if a codebase needs indexing"""

from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Set
import logging
from .file_filter import FileFilter

logger = logging.getLogger(__name__)


class RepoSizeChecker:
    """Check if a repository is too large and needs indexing"""
    
    # Supported code file extensions
    SUPPORTED_EXTENSIONS = {
        '.py',    # Python
        '.js',    # JavaScript
        '.jsx',   # React JavaScript
        '.mjs',   # ES Modules
        '.ts',    # TypeScript
        '.tsx',   # React TypeScript
    }
    
    # Default thresholds
    DEFAULT_FILE_COUNT_THRESHOLD = 100     # Number of code files
    DEFAULT_TOTAL_SIZE_THRESHOLD = 10     # Total size in MB
    DEFAULT_SINGLE_FILE_THRESHOLD = 1     # Single file size in MB
    
    def __init__(self, 
                 file_count_threshold: int = DEFAULT_FILE_COUNT_THRESHOLD,
                 total_size_threshold: float = DEFAULT_TOTAL_SIZE_THRESHOLD,
                 single_file_threshold: float = DEFAULT_SINGLE_FILE_THRESHOLD):
        """
        Initialize the repository size checker
        
        Args:
            file_count_threshold: Number of files before considering repo "large"
            total_size_threshold: Total size in MB before considering repo "large"
            single_file_threshold: Max single file size in MB to include in calculation
        """
        self.file_count_threshold = file_count_threshold
        self.total_size_threshold = total_size_threshold * 1024 * 1024  # Convert to bytes
        self.single_file_threshold = single_file_threshold * 1024 * 1024  # Convert to bytes
    
    def check_repository(self, path: Path) -> Dict[str, Any]:
        """
        Check if a repository is too large and needs indexing
        
        Args:
            path: Path to the repository
            
        Returns:
            Dict containing:
                - needs_indexing: bool - Whether the repo should be indexed
                - reason: str - Explanation of the decision
                - stats: dict - Statistics about the repository
                    - total_files: int - Total number of code files
                    - total_size_mb: float - Total size in MB
                    - largest_file_mb: float - Size of largest file in MB
                    - file_types: dict - Count by file extension
        """
        if not path.exists():
            return {
                "needs_indexing": False,
                "reason": f"Path does not exist: {path}",
                "stats": {}
            }
        
        # Initialize file filter to respect .gitignore
        file_filter = FileFilter.from_path(path)
        
        # Collect statistics
        stats = self._collect_stats(path, file_filter)
        
        # Determine if indexing is needed
        needs_indexing, reason = self._determine_indexing_needed(stats)
        
        return {
            "needs_indexing": needs_indexing,
            "reason": reason,
            "stats": {
                "total_files": stats['file_count'],
                "total_size_mb": round(stats['total_size'] / (1024 * 1024), 2),
                "largest_file_mb": round(stats['largest_file_size'] / (1024 * 1024), 2),
                "file_types": stats['file_types']
            }
        }
    
    def _collect_stats(self, path: Path, file_filter: FileFilter) -> Dict[str, Any]:
        """Collect statistics about code files in the repository"""
        stats = {
            'file_count': 0,
            'total_size': 0,
            'largest_file_size': 0,
            'file_types': {}
        }
        
        # Walk through directory or handle single file
        if path.is_file():
            if self._is_supported_file(path) and not file_filter.should_ignore(path):
                self._update_stats(path, stats)
        else:
            for file_path in self._walk_directory(path, file_filter):
                self._update_stats(file_path, stats)
        
        return stats
    
    def _walk_directory(self, directory: Path, file_filter: FileFilter):
        """Walk directory yielding only supported, non-ignored files"""
        try:
            for item in directory.rglob('*'):
                if item.is_file() and self._is_supported_file(item) and not file_filter.should_ignore(item):
                    yield item
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not access path during walk: {e}")
    
    def _is_supported_file(self, path: Path) -> bool:
        """Check if file has a supported code extension"""
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def _update_stats(self, file_path: Path, stats: Dict[str, Any]) -> None:
        """Update statistics with information from a single file"""
        try:
            file_size = file_path.stat().st_size
            
            # Skip files that are too large
            if file_size > self.single_file_threshold:
                logger.debug(f"Skipping large file: {file_path} ({file_size / (1024*1024):.2f} MB)")
                return
            
            stats['file_count'] += 1
            stats['total_size'] += file_size
            stats['largest_file_size'] = max(stats['largest_file_size'], file_size)
            
            # Track file types
            ext = file_path.suffix.lower()
            stats['file_types'][ext] = stats['file_types'].get(ext, 0) + 1
            
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not stat file {file_path}: {e}")
    
    def _determine_indexing_needed(self, stats: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if indexing is needed based on collected statistics
        
        Returns:
            Tuple of (needs_indexing: bool, reason: str)
        """
        file_count = stats['file_count']
        total_size = stats['total_size']
        
        # No code files found
        if file_count == 0:
            return False, "No supported code files found"
        
        # Check file count threshold
        if file_count >= self.file_count_threshold:
            return True, f"Repository has {file_count} code files (threshold: {self.file_count_threshold})"
        
        # Check total size threshold
        if total_size >= self.total_size_threshold:
            size_mb = total_size / (1024 * 1024)
            threshold_mb = self.total_size_threshold / (1024 * 1024)
            return True, f"Repository size is {size_mb:.1f} MB (threshold: {threshold_mb:.1f} MB)"
        
        # Repository is small enough
        size_mb = total_size / (1024 * 1024)
        return False, f"Repository is small ({file_count} files, {size_mb:.1f} MB)"


def check_repository_size(path: str, 
                         file_count_threshold: Optional[int] = None,
                         total_size_threshold: Optional[float] = None) -> Dict[str, Any]:
    """
    Convenience function to check repository size
    
    Args:
        path: Path to the repository
        file_count_threshold: Optional custom file count threshold
        total_size_threshold: Optional custom size threshold in MB
        
    Returns:
        Dict with indexing recommendation and statistics
    """
    checker = RepoSizeChecker(
        file_count_threshold=file_count_threshold or RepoSizeChecker.DEFAULT_FILE_COUNT_THRESHOLD,
        total_size_threshold=total_size_threshold or RepoSizeChecker.DEFAULT_TOTAL_SIZE_THRESHOLD
    )
    
    return checker.check_repository(Path(path))
