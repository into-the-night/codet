from pydantic import BaseModel, Field
from typing import Optional, List


class AnalyzeFile(BaseModel):
    """Analyzes a specific file to understand its content, structure, and functionality for answering questions about the codebase."""
    file_path: str = Field(..., description="The path to the file to analyze, relative to the repository root.")
    analysis_focus: Optional[str] = Field("general", description="Specific focus area for analysis (e.g., 'security', 'performance', 'general')")

class AnalyzeFilesBatch(BaseModel):
    """Analyzes a batch of files to understand their content, structure, and functionality for answering questions about the codebase."""
    file_paths: List[str] = Field(..., description="A list of file paths to analyze.")
    analysis_focus: Optional[str] = Field("general", description="Specific focus area for analysis (e.g., 'security', 'performance', 'general')")

class QueryFile(BaseModel):
    """Queries a specific file to retrieve relevant information for answering questions about that file."""
    file_path: str = Field(..., description="The path to the file to query, relative to the repository root.")
    question: str = Field(..., description="The question to ask about the file.")

class QueryCodebase(BaseModel):
    """Queries the indexed codebase to retrieve relevant information for answering questions about the codebase."""
    question: str = Field(..., description="The question to ask about the codebase.")
    search_limit: Optional[int] = Field(10, description="The maximum number of search results to return.")