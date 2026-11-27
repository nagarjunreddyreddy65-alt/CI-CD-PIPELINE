"""
Analysis API Routes.
Exposes endpoints for code change analysis and AST dependency graph queries.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.analysis.dependency_analyzer import ASTDependencyAnalyzer
from app.analysis.test_mapper import TestDependencyMapper
from app.core.security import verify_runner_token

router = APIRouter(prefix="/analysis", tags=["Code & AST Dependency Analysis"])


class FileChangeItem(BaseModel):
    path: str = Field(..., max_length=1024, description="Relative file path in repository")
    change_type: str = Field(
        default="MODIFIED", max_length=50, description="ADDED | MODIFIED | DELETED | RENAMED"
    )
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)
    old_path: str | None = Field(default=None, max_length=1024)


class DiffAnalysisRequest(BaseModel):
    repository_path: str | None = Field(
        default=".", max_length=1024, description="Path to repository root"
    )
    files: list[FileChangeItem] = Field(
        ..., max_length=1000, description="List of changed files in commit/PR"
    )


def _validate_repo_path(repo_input: str | None) -> str:
    """Validates and resolves repository root path, strictly forbidding path traversal."""
    path_val = repo_input or "."
    clean_repo = os.path.normpath(path_val).replace("\\", "/")
    if (
        os.path.isabs(path_val)
        or clean_repo.startswith(("../", "..", "//", "\\\\"))
        or "/../" in clean_repo
        or bool(len(clean_repo) > 1 and clean_repo[1] == ":")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid repository path: path traversal or absolute/drive/UNC path is forbidden ('{path_val}')",
        )

    approved_root = os.path.abspath(os.getcwd())
    candidate_dir = os.path.abspath(os.path.join(approved_root, clean_repo))
    real_candidate = os.path.realpath(candidate_dir)
    real_approved = os.path.realpath(approved_root)
    try:
        if os.path.commonpath([real_approved, real_candidate]) != real_approved:
            raise ValueError("Boundary escape")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository path: path escapes approved workspace boundary",
        )
    return real_candidate


@router.post(
    "/diff",
    summary="Analyze Code Diff and Map Dependencies",
    description="Processes file changes, checks deterministic safety rules, and maps affected tests.",
)
def analyze_diff(
    payload: DiffAnalysisRequest,
    _authorized: bool = Depends(verify_runner_token),
):
    """Analyzes commit diff and maps downstream test dependencies."""
    root_dir = _validate_repo_path(payload.repository_path)

    # Reject path traversal attempts in file paths
    for f in payload.files:
        clean = os.path.normpath(f.path).replace("\\", "/")
        if clean.startswith("../") or clean == ".." or "/../" in clean or os.path.isabs(f.path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file path: path traversal is forbidden ('{f.path}')",
            )
        if f.old_path:
            clean_old = os.path.normpath(f.old_path).replace("\\", "/")
            if (
                clean_old.startswith("../")
                or clean_old == ".."
                or "/../" in clean_old
                or os.path.isabs(f.old_path)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid old file path: path traversal is forbidden ('{f.old_path}')",
                )

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
def get_graph_summary(
    repository_path: str = ".",
):
    """Builds current AST dependency graph and returns topology statistics."""
    target_dir = _validate_repo_path(repository_path)
    analyzer = ASTDependencyAnalyzer(target_dir)
    graph = analyzer.build_graph()

    return {
        "success": True,
        "total_modules": graph.graph.number_of_nodes(),
        "total_dependencies": graph.graph.number_of_edges(),
        "dynamic_imports_count": len(graph.dynamic_imports_detected),
        "parsing_errors_count": len(graph.parsing_errors),
        "modules": sorted(graph.graph.nodes()),
    }
