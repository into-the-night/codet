from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass
from pathlib import Path


class IssueSeverity(str, Enum):
    """Severity levels for code quality issues"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategory(str, Enum):
    """Categories of code quality issues"""
    SECURITY = "security"
    PERFORMANCE = "performance"
    DUPLICATION = "duplication"
    COMPLEXITY = "complexity"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"

@dataclass
class CodeIssue:
    """Represents a code quality issue"""
    category: IssueCategory
    severity: IssueSeverity
    title: str
    description: str
    file_path: Path
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    suggestion: Optional[str] = None
    code_snippet: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AnalysisResult:
    """Result of a code analysis"""
    project_path: Path
    issues: List[CodeIssue]
    metrics: Dict[str, Any]
    summary: Dict[str, Any]
    timestamp: str
    total_issues: Optional[int] = None
    analysis_time: Optional[float] = None


## Model output schemas

class CodeIssueSchema(BaseModel):
    """Schema for a code quality issue"""
    category: IssueCategory = Field(description="Category of the issue")
    severity: IssueSeverity = Field(description="Severity level of the issue")
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
    memory_items: Optional[List[str]] = Field(
        default_factory=list,
        description=(
            "Todos: action items for cross-codebase verification (e.g., 'Check if "
            "authenticate() has tests in test_auth.py'). Each item becomes a pending "
            "todo other agents can claim."
        ),
    )
    notes: Optional[List[str]] = Field(
        default_factory=list,
        description=(
            "Durable observations about this file or the codebase (e.g., 'authenticate() "
            "in src/auth.py:45 is the single entry point for login'). Stored as notes "
            "visible to all agents."
        ),
    )

class ChatResponseSchema(BaseModel):
    """Schema for chat mode responses"""
    answer: str = Field(description="The answer to the user's question about the codebase")
    files_to_analyze: Optional[List[str]] = Field(None, description="Files that need to be analyzed to answer the question")
    analysis_complete: bool = Field(False, description="Whether the analysis is complete and ready to provide final answer")
    memory_items: Optional[List[str]] = Field(
        default_factory=list,
        description="Action items to add to shared memory as todos for cross-codebase context",
    )
    notes: Optional[List[str]] = Field(
        default_factory=list,
        description="Durable observations about the codebase to share with other agents",
    )


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
    memory_items: Optional[List[str]] = Field(default_factory=list, description="Todos: action items for cross-codebase verification")
    notes: Optional[List[str]] = Field(default_factory=list, description="Durable observations about the file for other agents")
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