"""
Analysis API Routes.
Exposes endpoints for code change analysis and AST dependency graph queries.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import os

from app.core.config import settings
from app.analysis.change_analyzer import ChangeAnalyzer
from app.analysis.dependency_analyzer import ASTDependencyAnalyzer
from app.analysis.test_mapper import TestDependencyMapper
from app.api.dependencies import verify_runner_token

router = APIRouter(prefix="/analysis", tags=["Code & AST Dependency Analysis"])


class FileChangeItem(BaseModel):
    path: str = Field(..., description="Relative file path in repository")
    change_type: str = Field(default="MODIFIED", description="ADDED | MODIFIED | DELETED | RENAMED")
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = 0
    old_path: Optional[str] = None


class DiffAnalysisRequest(BaseModel):
    repository_path: Optional[str] = Field(default=".", description="Path to repository root")
    files: List[FileChangeItem] = Field(..., description="List of changed files in commit/PR")


@router.post(
    "/diff",
    summary="Analyze Code Diff and Map Dependencies",
    description="Processes file changes, checks deterministic safety rules, and maps affected tests.",
)
def analyze_diff(payload: DiffAnalysisRequest):
    """Analyzes commit diff and maps downstream test dependencies."""
    root_dir = os.path.abspath(payload.repository_path)
    if not os.path.exists(root_dir):
        root_dir = os.getcwd()

    mapper = TestDependencyMapper(root_dir)
    file_dicts = [f.model_dump() for f in payload.files]

    result = mapper.map_changes_to_tests(file_dicts)

    return {
        "success": True,
        "fallback_required": result.fallback_required,
        "fallback_reason": result.fallback_reason,
        "triggered_safety_rules": result.triggered_safety_rules,
        "changed_modules": result.changed_modules,
        "affected_modules": result.affected_modules,
        "affected_test_files": result.affected_test_files,
        "affected_test_identifiers": result.affected_test_identifiers,
        "total_repository_tests": result.total_repository_tests,
        "selected_tests_count": result.selected_tests_count,
        "estimated_test_reduction_pct": result.estimated_test_reduction_pct,
    }


@router.get(
    "/graph",
    summary="Get Dependency Graph Statistics",
    description="Returns current dependency graph node count, edge count, and density.",
)
def get_graph_summary():
    """Builds current AST dependency graph and returns topology statistics."""
    analyzer = ASTDependencyAnalyzer(os.getcwd())
    graph = analyzer.build_graph()

    return {
        "success": True,
        "total_modules": graph.graph.number_of_nodes(),
        "total_dependencies": graph.graph.number_of_edges(),
        "dynamic_imports_count": len(graph.dynamic_imports_detected),
        "parsing_errors_count": len(graph.parsing_errors),
        "modules": sorted(list(graph.graph.nodes())),
    }
