"""
API Router for CI/CD Execution Plans.
Provides endpoints to generate, query, and audit deterministic optimization plans.
"""

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.core.security import verify_runner_token
from app.database.models import ExecutionPlan
from app.database.session import get_db
from app.optimization.decision_engine import DecisionEngine, ExecutionPlanResult

router = APIRouter(prefix="/plans", tags=["Execution Plans"])


class ChangedFileItem(BaseModel):
    file_path: str = Field(
        ...,
        max_length=1024,
        json_schema_extra={"example": "sample_app/utils/math_ops.py"},
    )
    change_type: str = Field(
        "MODIFIED",
        max_length=50,
        json_schema_extra={"example": "MODIFIED"},
    )
    lines_added: int = Field(5, ge=0)
    lines_deleted: int = Field(2, ge=0)


class PlanGenerationRequest(BaseModel):
    repository_name: str = Field(
        "AutonomousDevOps/CI-CD-PIPELINE",
        max_length=255,
        json_schema_extra={"example": "AutonomousDevOps/CI-CD-PIPELINE"},
    )
    commit_hash: str = Field(
        ...,
        max_length=64,
        json_schema_extra={"example": "c81a293f0b4d"},
    )
    branch: str = Field(
        "main",
        max_length=100,
        json_schema_extra={"example": "main"},
    )
    author_name: str = Field(
        "MCA Student",
        max_length=150,
        json_schema_extra={"example": "MCA Student"},
    )
    author_email: str = Field(
        "student@example.edu",
        max_length=255,
        json_schema_extra={"example": "student@example.edu"},
    )
    commit_message: str = Field(
        "Update math operation utility functions",
        max_length=1000,
        json_schema_extra={"example": "Update math ops"},
    )
    changed_files: list[ChangedFileItem] = Field(..., max_length=1000)
    historical_failure_rate: float = Field(0.05, ge=0.0, le=1.0)
    previous_execution_duration: float = Field(25.0, ge=0.0)
    historical_runs_count: int = Field(20, ge=0)
    risk_threshold: float = Field(0.50, ge=0.0, le=1.0)


class PlanGenerationResponse(BaseModel):
    plan_id: str | None
    pipeline_run_id: str | None
    decision: str
    decision_reason: str
    is_optimized: bool
    fallback_triggered: bool
    fallback_reason: str | None
    selected_tests_count: int
    total_tests_count: int
    tests_reduction_pct: float
    selected_tests: list[str]
    pytest_command: str
    predicted_failure_probability: float
    predicted_duration_sec: float
    estimated_time_saved_sec: float
    triggered_safety_rules: list[str]
    model_version: str


@router.post("/generate", response_model=PlanGenerationResponse, status_code=status.HTTP_200_OK)
def generate_execution_plan(
    req: PlanGenerationRequest,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_runner_token),
):
    """
    Generates a deterministic CI/CD execution plan:
    1. Analyzes changed files and AST dependencies.
    2. Runs ML failure risk & runtime prediction.
    3. Evaluates 21 Safety Policy rules.
    4. Issues OPTIMIZED or FULL_SUITE plan and persists to DB.
    """
    # Reject path traversal in changed files
    for cf in req.changed_files:
        clean = os.path.normpath(cf.file_path).replace("\\", "/")
        if (
            clean.startswith("../")
            or clean == ".."
            or "/../" in clean
            or os.path.isabs(cf.file_path)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file path: path traversal is forbidden ('{cf.file_path}')",
            )

    engine = DecisionEngine(root_dir=".")

    file_entries = [
        {
            "file_path": cf.file_path,
            "change_type": cf.change_type,
            "lines_added": cf.lines_added,
            "lines_deleted": cf.lines_deleted,
        }
        for cf in req.changed_files
    ]

    plan_result: ExecutionPlanResult = engine.generate_plan(
        changed_file_entries=file_entries,
        historical_failure_rate=req.historical_failure_rate,
        previous_execution_duration=req.previous_execution_duration,
        historical_runs_count=req.historical_runs_count,
        risk_threshold=req.risk_threshold,
        db=db,
        repository_name=req.repository_name,
        commit_hash=req.commit_hash,
        branch=req.branch,
        author_name=req.author_name,
        author_email=req.author_email,
        commit_message=req.commit_message,
    )

    return PlanGenerationResponse(
        plan_id=plan_result.plan_id,
        pipeline_run_id=plan_result.pipeline_run_id,
        decision=plan_result.decision.value,
        decision_reason=plan_result.decision_reason,
        is_optimized=plan_result.is_optimized,
        fallback_triggered=plan_result.fallback_triggered,
        fallback_reason=plan_result.fallback_reason,
        selected_tests_count=plan_result.selected_tests_count,
        total_tests_count=plan_result.total_tests_count,
        tests_reduction_pct=plan_result.tests_reduction_pct,
        selected_tests=plan_result.selected_tests,
        pytest_command=plan_result.pytest_command,
        predicted_failure_probability=plan_result.predicted_failure_probability,
        predicted_duration_sec=plan_result.predicted_duration_sec,
        estimated_time_saved_sec=plan_result.estimated_time_saved_sec,
        triggered_safety_rules=plan_result.triggered_safety_rules,
        model_version=plan_result.model_version,
    )


@router.get("/{plan_id}")
def get_execution_plan(plan_id: str, db: Session = Depends(get_db)):
    """Retrieves an existing execution plan by ID."""
    plan = db.query(ExecutionPlan).filter(ExecutionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Execution plan '{plan_id}' not found")

    selected_tests = []
    if plan.selected_tests_json:
        try:
            selected_tests = json.loads(plan.selected_tests_json)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse selected_tests_json for plan '{plan_id}': {e}")

    return {
        "id": plan.id,
        "pipeline_run_id": plan.pipeline_run_id,
        "decision": plan.decision,
        "decision_reason": plan.decision_reason,
        "selected_tests_count": plan.selected_tests_count,
        "total_tests_count": plan.total_tests_count,
        "tests_reduction_pct": plan.tests_reduction_pct,
        "selected_tests": selected_tests,
        "safety_rule_triggered": plan.safety_rule_triggered,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


@router.get("")
def list_execution_plans(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lists recent execution plans with pagination."""
    plans = (
        db.query(ExecutionPlan)
        .order_by(ExecutionPlan.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    results = []
    for p in plans:
        results.append(
            {
                "id": p.id,
                "pipeline_run_id": p.pipeline_run_id,
                "decision": p.decision,
                "decision_reason": p.decision_reason,
                "selected_tests_count": p.selected_tests_count,
                "total_tests_count": p.total_tests_count,
                "tests_reduction_pct": p.tests_reduction_pct,
                "safety_rule_triggered": p.safety_rule_triggered,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        )
    return {"plans": results, "count": len(results), "limit": limit, "offset": offset}
