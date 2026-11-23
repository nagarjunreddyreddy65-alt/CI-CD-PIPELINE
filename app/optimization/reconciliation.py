"""
Pipeline Run Lifecycle Reconciliation Module.
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.

Recovers orphaned or stale pipeline executions without fabricating synthetic outcome data.
Enforces deterministic lifecycle transitions from uncompleted RUNNING states to terminal ABORTED status.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.database.models import AuditLog, PipelineRun


def reconcile_stale_runs(
    db: Session,
    stale_threshold_hours: float = 2.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Safely reconciles orphaned historical pipeline runs currently in RUNNING status.

    Reconciliation Rules:
    1. Only runs with status 'RUNNING' are inspected.
    2. Runs whose created_at timestamp is older than stale_threshold_hours (default 2 hours)
       are considered abandoned/interrupted executions where the runner did not report terminal status.
    3. Terminal status is set to 'ABORTED' (never 'SUCCESS' or fabricated outcomes).
    4. total_duration_sec is preserved as recorded or calculated from elapsed time up to completion,
       without fabricating artificial hardware execution times.
    5. fallback_reason is recorded as 'Orphaned uncompleted execution recovered during reconciliation'.
    6. An immutable AuditLog entry is recorded for every reconciled run.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=stale_threshold_hours)

    # Query all RUNNING runs created before or at cutoff
    all_running = db.query(PipelineRun).filter(PipelineRun.status == "RUNNING").all()

    reconciled = []
    for run in all_running:
        run_created = run.created_at
        if run_created and run_created.tzinfo is None:
            run_created = run_created.replace(tzinfo=UTC)

        # Reconcile if created_at is older than cutoff (or if created_at is unset)
        if not run_created or run_created <= cutoff:
            original_status = run.status
            reconcile_time = datetime.now(UTC)
            reconciled_info = {
                "run_id": run.id,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "original_status": original_status,
                "new_status": "ABORTED",
                "reason": "Execution timed out or abandoned without runner reporting terminal status",
            }
            reconciled.append(reconciled_info)

            if not dry_run:
                run.status = "ABORTED"
                run.completed_at = reconcile_time
                if not run.fallback_reason:
                    run.fallback_reason = (
                        "Orphaned uncompleted execution recovered during reconciliation"
                    )

                audit = AuditLog(
                    event_type="STALE_RUN_RECONCILED",
                    entity_type="PipelineRun",
                    entity_id=run.id,
                    details=(
                        f"Orphaned execution reconciled. Original status: {original_status} -> ABORTED. "
                        f"Threshold: {stale_threshold_hours}h. Created: {run.created_at}"
                    ),
                )
                db.add(audit)

    if not dry_run and reconciled:
        db.commit()
        logger.info(
            f"🔄 Reconciled {len(reconciled)} stale pipeline run(s) from RUNNING to ABORTED."
        )

    return {
        "reconciled_count": len(reconciled),
        "cutoff_threshold_hours": stale_threshold_hours,
        "dry_run": dry_run,
        "reconciled_runs": reconciled,
    }
