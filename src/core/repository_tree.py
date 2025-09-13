"""Repository tree constructor for AI-powered analysis"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import os
import logging
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FileNode:
    """Represents a file in the repository tree"""
    name: str
    path: str
    extension: Optional[str]
    size: int
    is_file: bool = True
    is_directory: bool = False
    modified_time: Optional[str] = None
    children: Optional[List['FileNode']] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        if self.children:
            result['children'] = [child.to_dict() for child in self.children]
        return result


@dataclass
class DirectoryNode:
    """Represents a directory in the repository tree"""
    name: str
    path: str
    children: List[Union['FileNode', 'DirectoryNode']]
    is_file: bool = False
    is_directory: bool = True
    modified_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result['children'] = [child.to_dict() for child in self.children]
        return result


class RepositoryTreeConstructor:
    """Constructs a tree structure of repository files and directories"""
    
    def __init__(self, 
                 ignore_patterns: Optional[List[str]] = None,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB default
                 include_hidden: bool = False):
        """
        Initialize the repository tree constructor
        
        Args:
            ignore_patterns: List of patterns to ignore (e.g., ['*.pyc', '__pycache__'])
            max_file_size: Maximum file size to include in tree (bytes)
            include_hidden: Whether to include hidden files/directories
        """
        self.ignore_patterns = ignore_patterns or [
            '*.pyc', '*.pyo', '*.pyd', '__pycache__', '.git', '.svn', 
            'node_modules', '.env', '*.log', '*.tmp', '.DS_Store',
            '*.egg-info', 'dist', 'build', '.pytest_cache', '.coverage'
        ]
        self.max_file_size = max_file_size
        self.include_hidden = include_hidden
        
    def should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored based on patterns"""
        path_str = str(path)
        
        # Check if it's a hidden file/directory
        if not self.include_hidden and any(part.startswith('.') for part in path.parts):
            return True
            
        # Check against ignore patterns
        for pattern in self.ignore_patterns:
            if pattern.startswith('*'):
                # Wildcard pattern
                if path.name.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
                
        return False
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get information about a file"""
        try:
            stat = file_path.stat()
            return {
                'size': stat.st_size,
                'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'extension': file_path.suffix if file_path.suffix else None
            }
        except (OSError, IOError) as e:
            logger.warning(f"Could not get info for {file_path}: {e}")
            return {
                'size': 0,
                'modified_time': None,
                'extension': file_path.suffix if file_path.suffix else None
            }
    
    def construct_tree(self, root_path: Path) -> Dict[str, Any]:
        """
        Construct a tree structure of the repository
        
        Args:
            root_path: Path to the repository root
            
        Returns:
            Dictionary representation of the tree structure
        """
        logger.info(f"Constructing repository tree for {root_path}")
        
        if not root_path.exists():
            raise ValueError(f"Path does not exist: {root_path}")
        
        if not root_path.is_dir():
            raise ValueError(f"Path is not a directory: {root_path}")
        
        # Start with the root directory
        tree = self._build_node(root_path, root_path)
        
        # Add metadata
        result = {
            'root_path': str(root_path.absolute()),
            'tree': tree.to_dict(),
            'statistics': self._calculate_statistics(tree),
            'constructed_at': datetime.now().isoformat()
        }
        
        logger.info(f"Repository tree constructed with {result['statistics']['total_files']} files")
        return result
    
    def _build_node(self, path: Path, root_path: Path) -> Union[FileNode, DirectoryNode]:
        """Recursively build a node in the tree"""
        
        if self.should_ignore(path):
            return None
            
        if path.is_file():
            # Handle file
            file_info = self.get_file_info(path)
            
            # Skip files that are too large
            if file_info['size'] > self.max_file_size:
                logger.debug(f"Skipping large file: {path} ({file_info['size']} bytes)")
                return None
            
            return FileNode(
                name=path.name,
                path=str(path.relative_to(root_path)),
                extension=file_info['extension'],
                size=file_info['size'],
                modified_time=file_info['modified_time']
            )
        
        elif path.is_dir():
            # Handle directory
            children = []
            
            try:
                for child_path in sorted(path.iterdir()):
                    child_node = self._build_node(child_path, root_path)
                    if child_node is not None:
                        children.append(child_node)
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not access directory {path}: {e}")
            
            return DirectoryNode(
                name=path.name,
                path=str(path.relative_to(root_path)),
                children=children,
                modified_time=self.get_file_info(path)['modified_time']
            )
        
        return None
    
    def _calculate_statistics(self, node: Union[FileNode, DirectoryNode]) -> Dict[str, Any]:
        """Calculate statistics about the repository tree"""
        stats = {
            'total_files': 0,
            'total_directories': 0,
            'total_size': 0,
            'file_extensions': {},
            'largest_files': [],
            'deepest_path': 0
        }
        
        def traverse(node, depth=0):
            if isinstance(node, FileNode):
                stats['total_files'] += 1
                stats['total_size'] += node.size
                
                # Track file extensions
                ext = node.extension or 'no_extension'
                stats['file_extensions'][ext] = stats['file_extensions'].get(ext, 0) + 1
                
                # Track largest files
                stats['largest_files'].append({
                    'path': node.path,
                    'size': node.size,
                    'name': node.name
                })
                
                # Track deepest path
                stats['deepest_path'] = max(stats['deepest_path'], depth)
                
            elif isinstance(node, DirectoryNode):
                stats['total_directories'] += 1
                stats['deepest_path'] = max(stats['deepest_path'], depth)
                
                for child in node.children:
                    traverse(child, depth + 1)
        
        traverse(node)
        
        # Sort largest files and keep top 10
        stats['largest_files'].sort(key=lambda x: x['size'], reverse=True)
        stats['largest_files'] = stats['largest_files'][:10]
        
        # Sort file extensions by count
        stats['file_extensions'] = dict(
            sorted(stats['file_extensions'].items(), key=lambda x: x[1], reverse=True)
        )
        
        return stats
    
    def get_file_list(self, tree_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract a flat list of all files from the tree"""
        files = []
        
        def extract_files(node_dict):
            if node_dict.get('is_file', False):
                files.append({
                    'name': node_dict['name'],
                    'path': node_dict['path'],
                    'extension': node_dict.get('extension'),
                    'size': node_dict.get('size', 0),
                    'modified_time': node_dict.get('modified_time')
                })
            elif node_dict.get('is_directory', False):
                for child in node_dict.get('children', []):
                    extract_files(child)
        
        extract_files(tree_data['tree'])
        return files
    
    def filter_files_by_extension(self, tree_data: Dict[str, Any], 
                                 extensions: List[str]) -> List[Dict[str, Any]]:
        """Filter files by extension"""
        all_files = self.get_file_list(tree_data)
        extension_set = set(ext.lower() for ext in extensions)
        
        return [
            file_info for file_info in all_files
            if file_info.get('extension', '').lower() in extension_set
        ]
    
    def get_tree_summary(self, tree_data: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the repository tree"""
        stats = tree_data['statistics']
        
        summary = f"Repository Tree Summary:\n"
        summary += f"- Root: {tree_data['root_path']}\n"
        summary += f"- Total files: {stats['total_files']}\n"
        summary += f"- Total directories: {stats['total_directories']}\n"
        summary += f"- Total size: {stats['total_size'] / (1024*1024):.2f} MB\n"
        summary += f"- Deepest path: {stats['deepest_path']} levels\n"
        
        summary += f"\nTop file extensions:\n"
        for ext, count in list(stats['file_extensions'].items())[:5]:
            summary += f"- {ext}: {count} files\n"
        
        if stats['largest_files']:
            summary += f"\nLargest files:\n"
            for file_info in stats['largest_files'][:3]:
                size_mb = file_info['size'] / (1024*1024)
                summary += f"- {file_info['path']}: {size_mb:.2f} MB\n"
        
        return summary
