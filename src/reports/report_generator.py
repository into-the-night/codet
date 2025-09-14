"""Base report generator and reporter interface"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from ..analyzers.analyzer import AnalysisResult, CodeIssue, IssueSeverity, IssueCategory


class BaseReporter(ABC):
    """Abstract base class for report formatters"""
    
    @abstractmethod
    def generate(self, analysis_result: AnalysisResult, output_path: Path) -> None:
        """Generate report in specific format"""
        pass
    
    @abstractmethod
    def get_format_name(self) -> str:
        """Return the name of the report format"""
        pass


class ReportGenerator:
    """Main report generator that coordinates different reporters"""
    
    def __init__(self):
        self.reporters = {}
    
    def register_reporter(self, reporter: BaseReporter) -> None:
        """Register a new reporter"""
        self.reporters[reporter.get_format_name()] = reporter
    
    def generate_report(self, analysis_result: AnalysisResult, 
                       output_format: str, output_path: Path) -> None:
        """Generate report in specified format"""
        if output_format not in self.reporters:
            raise ValueError(f"Unknown report format: {output_format}")
        
        reporter = self.reporters[output_format]
        reporter.generate(analysis_result, output_path)
    
    @staticmethod
    def create_summary(issues: List[CodeIssue]) -> Dict[str, Any]:
        """Create a summary of the analysis results"""
        summary = {
            'total_issues': len(issues),
            'by_severity': {},
            'by_category': {},
            'files_affected': len(set(issue.file_path for issue in issues))
        }
        
        # Count by severity
        for severity in IssueSeverity:
            count = sum(1 for issue in issues if issue.severity == severity)
            if count > 0:
                summary['by_severity'][severity.value] = count
        
        # Count by category
        for category in IssueCategory:
            count = sum(1 for issue in issues if issue.category == category)
            if count > 0:
                summary['by_category'][category.value] = count
        
        # Calculate quality score (simple formula)
        if issues:
            critical_weight = 10
            high_weight = 5
            medium_weight = 2
            low_weight = 1
            
            weighted_score = sum(
                critical_weight if issue.severity == IssueSeverity.CRITICAL else
                high_weight if issue.severity == IssueSeverity.HIGH else
                medium_weight if issue.severity == IssueSeverity.MEDIUM else
                low_weight
                for issue in issues
            )
            
            # Normalize to 0-100 scale (inverse, so higher score = better quality)
            max_possible_score = len(issues) * critical_weight
            summary['quality_score'] = max(0, 100 - (weighted_score / max_possible_score * 100))
        else:
            summary['quality_score'] = 100
        
        return summary
    
    @staticmethod
    def prioritize_issues(issues: List[CodeIssue]) -> List[CodeIssue]:
        """Sort issues by priority (severity and category)"""
        severity_order = {
            IssueSeverity.CRITICAL: 0,
            IssueSeverity.HIGH: 1,
            IssueSeverity.MEDIUM: 2,
            IssueSeverity.LOW: 3,
            IssueSeverity.INFO: 4
        }
        
        category_priority = {
            IssueCategory.SECURITY: 0,
            IssueCategory.PERFORMANCE: 1,
            IssueCategory.COMPLEXITY: 2,
            IssueCategory.DUPLICATION: 3,
            IssueCategory.TESTING: 4,
            IssueCategory.MAINTAINABILITY: 5,
            IssueCategory.DOCUMENTATION: 6,
            IssueCategory.STYLE: 7
        }
        
        return sorted(issues, key=lambda x: (
            severity_order.get(x.severity, 999),
            category_priority.get(x.category, 999),
            str(x.file_path),
            x.line_number or 0
        ))
