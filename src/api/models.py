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


class ChatRequest(BaseModel):
    """Request model for chat/QnA"""
    question: str = Field(..., description="The question to ask about the codebase")
    path: str = Field(..., description="Path to the repository or directory")
    config_path: Optional[str] = Field(None, description="Path to configuration file for AI analysis")


class ChatResponse(BaseModel):
    """Response model for chat/QnA"""
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="AI-generated answer")
    analyzed_files: List[str] = Field(..., description="List of files that were analyzed")
    files_analyzed_count: int = Field(..., description="Number of files analyzed")
    timestamp: str = Field(..., description="Timestamp of the response")


class CodebaseIndexRequest(BaseModel):
    """Request model for indexing codebase"""
    path: str = Field(..., description="Path to the repository or directory to index")
    collection_name: str = Field("codebase", description="Qdrant collection name")
    batch_size: int = Field(100, description="Batch size for indexing")


class CodebaseIndexResponse(BaseModel):
    """Response model for codebase indexing"""
    status: str = Field(..., description="Status of indexing operation")
    total_chunks: int = Field(..., description="Total number of code chunks indexed")
    type_counts: Dict[str, int] = Field(..., description="Count of chunks by type")
    collection_name: str = Field(..., description="Name of the Qdrant collection")
    timestamp: str = Field(..., description="Timestamp of indexing")


class CodebaseSearchRequest(BaseModel):
    """Request model for searching indexed codebase"""
    query: str = Field(..., description="Search query (natural language or code)")
    search_type: str = Field("hybrid", description="Search type: nlp, code, or hybrid")
    limit: int = Field(10, description="Number of results to return")
    collection_name: str = Field("codebase", description="Qdrant collection name")
    filter: Optional[Dict[str, Any]] = Field(None, description="Optional filters")


class CodeSearchResult(BaseModel):
    """Single code search result"""
    name: str = Field(..., description="Name of the code construct")
    signature: str = Field(..., description="Function/method signature or class definition")
    code_type: str = Field(..., description="Type of code construct")
    file_path: str = Field(..., description="Path to the file")
    line_from: int = Field(..., description="Starting line number")
    line_to: int = Field(..., description="Ending line number")
    score: float = Field(..., description="Relevance score")
    docstring: Optional[str] = Field(None, description="Docstring if available")
    code_preview: str = Field(..., description="Code snippet preview")


class CodebaseSearchResponse(BaseModel):
    """Response model for codebase search"""
    query: str = Field(..., description="The search query")
    results: List[CodeSearchResult] = Field(..., description="Search results")
    total_results: int = Field(..., description="Total number of results found")
    search_type: str = Field(..., description="Type of search performed")
    timestamp: str = Field(..., description="Timestamp of search")
