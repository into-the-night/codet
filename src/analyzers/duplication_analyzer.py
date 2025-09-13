"""Code duplication analyzer"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
import re
import hashlib
import logging
from collections import defaultdict

from .analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity
from ..utils.snippet_extractor import extract_block_snippet


logger = logging.getLogger(__name__)


class DuplicationAnalyzer(BaseAnalyzer):
    """Detects code duplication within and across files"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.min_duplicate_lines = config.get('min_duplicate_lines', 5) if config else 5
        self.min_duplicate_tokens = config.get('min_duplicate_tokens', 50) if config else 50
        self._file_hashes = defaultdict(list)
    
    def analyze(self, file_path: Path) -> List[CodeIssue]:
        """Analyze file for code duplication"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            # Check for duplicate blocks within the file
            issues.extend(self._check_internal_duplication(lines, file_path))
            
            # Store file content for cross-file duplication analysis
            self._store_file_blocks(lines, file_path)
            
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
        
        return issues
    
    def _check_internal_duplication(self, lines: List[str], file_path: Path) -> List[CodeIssue]:
        """Check for duplicate code blocks within a single file"""
        issues = []
        
        # Create blocks of consecutive non-empty lines
        blocks = []
        current_block = []
        start_line = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(('#', '//', '/*', '*')):
                if not current_block:
                    start_line = i + 1
                current_block.append(line)
            else:
                if len(current_block) >= self.min_duplicate_lines:
                    blocks.append((start_line, current_block))
                current_block = []
        
        if len(current_block) >= self.min_duplicate_lines:
            blocks.append((start_line, current_block))
        
        # Find duplicate blocks
        seen_blocks = {}
        
        for start_line, block in blocks:
            block_text = '\n'.join(block)
            block_hash = hashlib.md5(block_text.encode()).hexdigest()
            
            if block_hash in seen_blocks:
                original_line = seen_blocks[block_hash]
                end_line = start_line + len(block) - 1
                issues.append(CodeIssue(
                    category=IssueCategory.DUPLICATION,
                    severity=IssueSeverity.MEDIUM,
                    title="Duplicate Code Block",
                    description=f"This {len(block)}-line block is duplicated from line {original_line}",
                    file_path=file_path,
                    line_number=start_line,
                    suggestion="Extract duplicated code into a reusable function or module",
                    code_snippet=extract_block_snippet(file_path, start_line, end_line)
                ))
            else:
                seen_blocks[block_hash] = start_line
        
        return issues
    
    def _store_file_blocks(self, lines: List[str], file_path: Path) -> None:
        """Store file blocks for cross-file duplication analysis"""
        # This would be used in a full implementation to detect duplication across files
        # For now, we'll just store the blocks
        blocks = self._extract_meaningful_blocks(lines)
        
        for block, start_line in blocks:
            block_hash = hashlib.md5('\n'.join(block).encode()).hexdigest()
            self._file_hashes[block_hash].append({
                'file': file_path,
                'line': start_line,
                'block': block
            })
    
    def _extract_meaningful_blocks(self, lines: List[str]) -> List[Tuple[List[str], int]]:
        """Extract meaningful code blocks for analysis"""
        blocks = []
        current_block = []
        start_line = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip comments and empty lines
            if stripped and not stripped.startswith(('#', '//', '/*', '*')):
                if not current_block:
                    start_line = i + 1
                current_block.append(line)
            else:
                if len(current_block) >= self.min_duplicate_lines:
                    blocks.append((current_block, start_line))
                current_block = []
        
        if len(current_block) >= self.min_duplicate_lines:
            blocks.append((current_block, start_line))
        
        return blocks
    
    def find_cross_file_duplicates(self) -> List[CodeIssue]:
        """Find duplicates across multiple files (to be called after analyzing all files)"""
        issues = []
        
        for block_hash, occurrences in self._file_hashes.items():
            if len(occurrences) > 1:
                # Group by file to avoid reporting internal duplicates again
                files = defaultdict(list)
                for occ in occurrences:
                    files[occ['file']].append(occ)
                
                if len(files) > 1:
                    # Cross-file duplication found
                    first_occ = occurrences[0]
                    for occ in occurrences[1:]:
                        if occ['file'] != first_occ['file']:
                            issues.append(CodeIssue(
                                category=IssueCategory.DUPLICATION,
                                severity=IssueSeverity.HIGH,
                                title="Cross-File Duplication",
                                description=f"Code duplicated from {first_occ['file'].name}:{first_occ['line']}",
                                file_path=occ['file'],
                                line_number=occ['line'],
                                suggestion="Consider extracting shared code into a common module",
                                metadata={
                                    'original_file': str(first_occ['file']),
                                    'original_line': first_occ['line']
                                }
                            ))
        
        return issues
    
    def supports_language(self, language: str) -> bool:
        """Duplication analyzer supports all languages"""
        return True
    
    @property
    def name(self) -> str:
        return "Duplication Analyzer"
