"""Code analyzers for different languages and quality aspects"""

from .python_analyzer import PythonAnalyzer
from .javascript_analyzer import JavaScriptAnalyzer
from .duplication_analyzer import DuplicationAnalyzer

__all__ = [
    'PythonAnalyzer',
    'JavaScriptAnalyzer',
    'DuplicationAnalyzer'
]
