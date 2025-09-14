"""Repository management and code loading"""

from pathlib import Path
from typing import List, Set, Optional, Dict, Any
import gitignore_parser
import logging
from ..utils import FileFilter


logger = logging.getLogger(__name__)


class Repository:
    """Manages code repository loading and file discovery"""
    
    def __init__(self, path: Path):
        self.path = path.resolve()
        self._validate_path()
        self._gitignore = self._load_gitignore()
        # Create file filter for consistent file handling
        self.file_filter = FileFilter.from_path(self.path)
        
    def _validate_path(self) -> None:
        """Validate that the path exists and is accessible"""
        if not self.path.exists():
            raise ValueError(f"Path does not exist: {self.path}")
        if not (self.path.is_file() or self.path.is_dir()):
            raise ValueError(f"Path must be a file or directory: {self.path}")
    
    def _load_gitignore(self) -> Optional[Any]:
        """Load .gitignore file if it exists"""
        gitignore_path = self.path / ".gitignore" if self.path.is_dir() else self.path.parent / ".gitignore"
        if gitignore_path.exists():
            try:
                return gitignore_parser.parse_gitignore(gitignore_path)
            except Exception as e:
                logger.warning(f"Failed to parse .gitignore: {e}")
        return None
    
    def get_files(self, extensions: Optional[Set[str]] = None) -> List[Path]:
        """Get all files in the repository with optional extension filtering"""
        # Use file filter for consistent filtering
        return self.file_filter.iter_files(self.path, extensions=list(extensions) if extensions else None)
    
    def get_language_stats(self) -> Dict[str, int]:
        """Get statistics about languages in the repository"""
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.cs': 'C#',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.r': 'R',
        }
        
        stats = {}
        for file_path in self.get_files():
            lang = language_map.get(file_path.suffix.lower(), 'Other')
            stats[lang] = stats.get(lang, 0) + 1
        
        return stats
