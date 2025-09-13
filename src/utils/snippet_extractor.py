"""Utility functions for extracting code snippets with context"""

from pathlib import Path
from typing import Optional, List


def extract_code_snippet(file_path: Path, line_number: int, context_lines: int = 3) -> Optional[str]:
    """
    Extract a code snippet with context around a specific line number.
    
    Args:
        file_path: Path to the file
        line_number: Line number where the issue occurs (1-indexed)
        context_lines: Number of lines to include before and after the target line
    
    Returns:
        Code snippet with line numbers, or None if extraction fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number < 1 or line_number > len(lines):
            return None
        
        # Convert to 0-indexed
        target_line_idx = line_number - 1
        
        # Calculate start and end indices
        start_idx = max(0, target_line_idx - context_lines)
        end_idx = min(len(lines), target_line_idx + context_lines + 1)
        
        # Extract snippet with line numbers
        snippet_lines = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            line_content = lines[i].rstrip('\n')
            
            # Highlight the target line
            if i == target_line_idx:
                snippet_lines.append(f"{line_num:4d}|>>> {line_content}")
            else:
                snippet_lines.append(f"{line_num:4d}|    {line_content}")
        
        return '\n'.join(snippet_lines)
        
    except Exception:
        return None


def extract_function_snippet(file_path: Path, line_number: int) -> Optional[str]:
    """
    Extract a code snippet for a function definition.
    
    Args:
        file_path: Path to the file
        line_number: Line number where the function starts (1-indexed)
    
    Returns:
        Function snippet with line numbers, or None if extraction fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number < 1 or line_number > len(lines):
            return None
        
        # Convert to 0-indexed
        start_idx = line_number - 1
        
        # Find the end of the function (simple heuristic: look for next function/class or end of file)
        end_idx = start_idx + 1
        indent_level = None
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # Determine indentation level of the function
            if indent_level is None:
                indent_level = len(line) - len(line.lstrip())
                continue
            
            current_indent = len(line) - len(line.lstrip())
            
            # If we hit a line with less or equal indentation (and it's not empty/comment),
            # we've reached the end of the function
            if current_indent <= indent_level and stripped:
                end_idx = i
                break
        else:
            # If we didn't find an end, use the rest of the file
            end_idx = len(lines)
        
        # Limit to reasonable size (max 20 lines)
        end_idx = min(end_idx, start_idx + 20)
        
        # Extract snippet with line numbers
        snippet_lines = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            line_content = lines[i].rstrip('\n')
            snippet_lines.append(f"{line_num:4d}|{line_content}")
        
        return '\n'.join(snippet_lines)
        
    except Exception:
        return None


def extract_block_snippet(file_path: Path, start_line: int, end_line: int) -> Optional[str]:
    """
    Extract a code snippet for a specific block of lines.
    
    Args:
        file_path: Path to the file
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed)
    
    Returns:
        Block snippet with line numbers, or None if extraction fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return None
        
        # Convert to 0-indexed
        start_idx = start_line - 1
        end_idx = end_line
        
        # Extract snippet with line numbers
        snippet_lines = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            line_content = lines[i].rstrip('\n')
            snippet_lines.append(f"{line_num:4d}|{line_content}")
        
        return '\n'.join(snippet_lines)
        
    except Exception:
        return None
