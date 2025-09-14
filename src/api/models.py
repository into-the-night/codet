"""Pydantic models for API requests and responses"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class AnalysisRequest(BaseModel):
    """Request model for code analysis"""
    path: str = Field(..., description="Path to the repository or directory to analyze")
    include_patterns: Optional[List[str]] = Field(None, description="File patterns to include")
    exclude_patterns: Optional[List[str]] = Field(None, description="File patterns to exclude")
    enable_ai: Optional[bool] = Field(True, description="Enable AI-powered analysis")
    config_path: Optional[str] = Field(None, description="Path to configuration file for AI analysis")


class GitHubAnalysisRequest(BaseModel):
    """Request model for GitHub repository analysis"""
    github_url: str = Field(..., description="GitHub repository URL to clone and analyze")
    include_patterns: Optional[List[str]] = Field(None, description="File patterns to include")
    exclude_patterns: Optional[List[str]] = Field(None, description="File patterns to exclude")
    enable_ai: Optional[bool] = Field(True, description="Enable AI-powered analysis")
    config_path: Optional[str] = Field(None, description="Path to configuration file for AI analysis")


class AnalysisResponse(BaseModel):
    """Response model for analysis results"""
    analysis_id: str = Field(..., description="Unique identifier for this analysis")
    status: str = Field(..., description="Status of the analysis")
    summary: Dict[str, Any] = Field(..., description="Summary of analysis results")
    issues_count: int = Field(..., description="Total number of issues found")
    quality_score: float = Field(..., description="Overall quality score (0-100)")
    timestamp: str = Field(..., description="Timestamp of analysis")


class CodebaseQuestion(BaseModel):
    """Model for asking questions about the codebase"""
    question: str = Field(..., description="Natural language question about the codebase")
    context: Optional[List[str]] = Field(None, description="Additional context or file paths")


class QuestionResponse(BaseModel):
    """Response model for codebase questions"""
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="AI-generated answer")
    context: List[Dict[str, Any]] = Field(..., description="Relevant code context")
    confidence: float = Field(..., description="Confidence score of the answer (0-1)")
    
    
class IssueDetail(BaseModel):
    """Detailed information about a code issue"""
    category: str
    severity: str
    title: str
    description: str
    file_path: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    suggestion: Optional[str] = None
    code_snippet: Optional[str] = None


class FileAnalysis(BaseModel):
    """Analysis results for a single file"""
    file_path: str
    language: str
    issues: List[IssueDetail]
    metrics: Dict[str, Any]


