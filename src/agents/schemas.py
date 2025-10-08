"""Pydantic schemas for structured output with Google GenAI"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class IssueSeverityEnum(str, Enum):
    """Severity levels for code quality issues"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategoryEnum(str, Enum):
    """Categories of code quality issues"""
    SECURITY = "security"
    PERFORMANCE = "performance"
    DUPLICATION = "duplication"
    COMPLEXITY = "complexity"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"


class CodeIssueSchema(BaseModel):
    """Schema for a code quality issue"""
    category: IssueCategoryEnum = Field(description="Category of the issue")
    severity: IssueSeverityEnum = Field(description="Severity level of the issue")
    title: str = Field(description="Brief descriptive title of the issue")
    description: str = Field(description="Detailed explanation of the issue")
    line_number: Optional[int] = Field(None, description="Line number where the issue occurs")
    column_number: Optional[int] = Field(None, description="Column number where the issue occurs")
    suggestion: Optional[str] = Field(None, description="Specific recommendation to fix the issue")
    code_snippet: Optional[str] = Field(None, description="Relevant code snippet if applicable")
    impact: Optional[str] = Field(None, description="Potential impact description")


class AnalysisResponseSchema(BaseModel):
    """Schema for the complete analysis response"""
    issues: List[CodeIssueSchema] = Field(description="List of code quality issues found")

class ChatResponseSchema(BaseModel):
    """Schema for chat mode responses"""
    answer: str = Field(description="The answer to the user's question about the codebase")
    files_to_analyze: Optional[List[str]] = Field(None, description="Files that need to be analyzed to answer the question")
    analysis_complete: bool = Field(False, description="Whether the analysis is complete and ready to provide final answer")


class FileAnalysisRequestSchema(BaseModel):
    """Schema for file analysis requests"""
    file_path: str = Field(description="Path to the file to analyze")
    analysis_type: str = Field(description="Type of analysis to perform")


class RepositoryAnalysisRequestSchema(BaseModel):
    """Schema for repository analysis requests"""
    repository_path: str = Field(description="Path to the repository root")
    analysis_type: str = Field(description="Type of analysis to perform")
    target_files: Optional[List[str]] = Field(None, description="Specific files to analyze")


class FileAnalysisResultEnhanced(BaseModel):
    """Enhanced file analysis response that includes next steps"""
    file_path: str = Field(description="Path to the analyzed file")
    issues: List[CodeIssueSchema] = Field(default_factory=list, description="Issues found in the file")
    next_steps: List[str] = Field(default_factory=list, description="Suggested next steps for the orchestrator (e.g., 'check if calculate_total function has tests in test_calculator.py')")
    summary: Optional[str] = Field(None, description="Brief summary of the file analysis")


class CodeTypeEnum(str, Enum):
    """Types of code constructs"""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    PROPERTY = "property"
    ENUM = "enum"
    IMPORT = "import"


class CodeChunk(BaseModel):
    """Schema for a code chunk to be embedded"""
    name: str = Field(description="Name of the code construct")
    signature: str = Field(description="Function/method signature or class definition")
    code_type: CodeTypeEnum = Field(description="Type of code construct")
    docstring: Optional[str] = Field(None, description="Docstring or comments")
    code: str = Field(description="The actual code content")
    line: int = Field(description="Starting line number")
    line_from: int = Field(description="Starting line number (inclusive)")
    line_to: int = Field(description="Ending line number (inclusive)")
    context: Dict[str, Any] = Field(description="Additional context (module, file path, class name, etc.)")
    natural_language: Optional[str] = Field(None, description="Natural language representation of the code")