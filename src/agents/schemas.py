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
    file_path: str = Field(description="Path to the file containing the issue")
    line_number: Optional[int] = Field(None, description="Line number where the issue occurs")
    column_number: Optional[int] = Field(None, description="Column number where the issue occurs")
    suggestion: Optional[str] = Field(None, description="Specific recommendation to fix the issue")
    code_snippet: Optional[str] = Field(None, description="Relevant code snippet if applicable")
    impact: Optional[str] = Field(None, description="Potential impact description")
    references: Optional[List[str]] = Field(None, description="Links to best practices or documentation")


class AnalysisResponseSchema(BaseModel):
    """Schema for the complete analysis response"""
    issues: List[CodeIssueSchema] = Field(description="List of code quality issues found")
    summary: Optional[Dict[str, Any]] = Field(None, description="Summary of the analysis")


class FileAnalysisRequestSchema(BaseModel):
    """Schema for file analysis requests"""
    file_path: str = Field(description="Path to the file to analyze")
    analysis_type: str = Field(description="Type of analysis to perform")


class RepositoryAnalysisRequestSchema(BaseModel):
    """Schema for repository analysis requests"""
    repository_path: str = Field(description="Path to the repository root")
    analysis_type: str = Field(description="Type of analysis to perform")
    target_files: Optional[List[str]] = Field(None, description="Specific files to analyze")