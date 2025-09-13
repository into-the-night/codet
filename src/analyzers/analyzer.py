"""Main analyzer interface for code quality analysis"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass


class IssueSeverity(Enum):
    """Severity levels for code quality issues"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategory(Enum):
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

class BaseAnalyzer(ABC):
    """Abstract base class for all code analyzers"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
    
    @abstractmethod
    def analyze(self, file_path: Path) -> List[CodeIssue]:
        """Analyze a single file and return issues"""
        pass
    
    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """Check if analyzer supports the given language"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the analyzer"""
        pass
