"""
Code Change and Python AST Dependency Analysis Engine.
Extracts code diffs, constructs directed dependency graphs via NetworkX,
and maps changed modules to affected test cases.
"""

from app.analysis.change_analyzer import ChangeAnalyzer, FileChange, ChangeAnalysisResult
from app.analysis.dependency_analyzer import ASTDependencyAnalyzer, DependencyGraph
from app.analysis.test_mapper import TestDependencyMapper, TestMappingResult

__all__ = [
    "ChangeAnalyzer",
    "FileChange",
    "ChangeAnalysisResult",
    "ASTDependencyAnalyzer",
    "DependencyGraph",
    "TestDependencyMapper",
    "TestMappingResult",
]
