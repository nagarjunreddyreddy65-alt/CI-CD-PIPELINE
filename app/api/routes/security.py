"""
API Router for Security Scanning & Compliance.
Provides endpoints to submit, evaluate, and audit SAST, SCA, and Secret Detection scans.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import json

from app.database.session import get_db
from app.database.models import SecurityScan, PipelineRun
from app.security.scanner import SecurityScanner, ScanResult

router = APIRouter(prefix="/security", tags=["Security & Compliance"])


class SecurityScanRequest(BaseModel):
    pipeline_run_id: str = Field(..., json_schema_extra={"example": "run-uuid-12345"})
    tool_name: str = Field(..., json_schema_extra={"example": "Bandit"})
    raw_output: Any = Field(..., json_schema_extra={"example": {"results": []}})


class SecurityScanResponse(BaseModel):
    id: Optional[str]
    pipeline_run_id: str
    tool_name: str
    status: str
    highest_severity: str
    findings_count: int
    should_block_release: bool
    summary: str
    findings: List[Dict[str, Any]]
    executed_at: str


@router.post("/scan", response_model=SecurityScanResponse, status_code=status.HTTP_200_OK)
def submit_security_scan(
    req: SecurityScanRequest,
    db: Session = Depends(get_db),
):
    """
    Submits and evaluates a security scan report (Bandit, pip-audit, Gitleaks):
    1. Parses findings and categorizes severity (NONE, LOW, MEDIUM, HIGH, CRITICAL).
    2. Enforces release-blocking security policy.
    3. Redacts secrets/passwords before persistence.
    4. Records findings in database.
    """
    scan_result: ScanResult = SecurityScanner.evaluate_scan(req.tool_name, req.raw_output)

    # Persist to database
    db_scan = SecurityScan(
        pipeline_run_id=req.pipeline_run_id,
        tool_name=scan_result.tool_name,
        status=scan_result.status.value,
        highest_severity=scan_result.highest_severity.value,
        findings_count=scan_result.findings_count,
        summary=scan_result.summary,
    )
    db.add(db_scan)
    db.commit()
    db.refresh(db_scan)

    return SecurityScanResponse(
        id=db_scan.id,
        pipeline_run_id=req.pipeline_run_id,
        tool_name=scan_result.tool_name,
        status=scan_result.status.value,
        highest_severity=scan_result.highest_severity.value,
        findings_count=scan_result.findings_count,
        should_block_release=scan_result.should_block_release,
        summary=scan_result.summary,
        findings=[f.to_dict() for f in scan_result.findings],
        executed_at=scan_result.executed_at,
    )


@router.get("/scans/{pipeline_run_id}", status_code=status.HTTP_200_OK)
def get_security_scans_by_run(
    pipeline_run_id: str,
    db: Session = Depends(get_db),
):
    """Retrieves all security scan records for a given pipeline run."""
    scans = db.query(SecurityScan).filter(SecurityScan.pipeline_run_id == pipeline_run_id).all()
    results = []
    has_blocking_failure = False

    for s in scans:
        if s.status == "FAILED" or s.highest_severity in ("HIGH", "CRITICAL"):
            has_blocking_failure = True
        results.append({
            "id": s.id,
            "tool_name": s.tool_name,
            "status": s.status,
            "highest_severity": s.highest_severity,
            "findings_count": s.findings_count,
            "summary": s.summary,
            "executed_at": s.executed_at.isoformat() if s.executed_at else None,
        })

    return {
        "pipeline_run_id": pipeline_run_id,
        "scans": results,
        "total_scans": len(results),
        "is_release_blocked": has_blocking_failure,
    }
