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

    Liveness & Reconciliation Rules:
    1. Only runs with status 'RUNNING' are inspected.
    2. Active liveness is checked via:
       - Initial creation timestamp (created_at).
       - Latest telemetry heartbeat timestamp (telemetry.collected_at).
       - Latest test execution timestamp (test_results.executed_at).
    3. If any activity occurred within stale_threshold_hours, the run is considered ACTIVE
       and is NOT aborted.
    4. Runs whose latest activity is older than stale_threshold_hours (or unset) are
       considered abandoned/orphaned executions where the runner terminated prematurely.
    5. Terminal status is set to 'ABORTED' (never 'SUCCESS' or fabricated outcomes).
    6. total_duration_sec is preserved if recorded, or derived from elapsed time to reconciliation.
    7. An AuditLog entry is recorded for every reconciled run.
    8. Idempotent: Subsequent invocations ignore already terminal (ABORTED/SUCCESS/FAILED) runs.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=stale_threshold_hours)

    all_running = db.query(PipelineRun).filter(PipelineRun.status == "RUNNING").all()

    reconciled = []
    active_skipped = []

    for run in all_running:
        # Determine latest verifiable activity
        last_activity = run.created_at
        if last_activity and last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=UTC)

        # Check telemetry heartbeat
        if run.telemetry and run.telemetry.collected_at:
            tel_at = run.telemetry.collected_at
            if tel_at.tzinfo is None:
                tel_at = tel_at.replace(tzinfo=UTC)
            if last_activity is None or tel_at > last_activity:
                last_activity = tel_at

        # Check test results execution activity
        if run.test_results:
            test_times = [
                tr.executed_at.replace(tzinfo=UTC)
                if tr.executed_at and tr.executed_at.tzinfo is None
                else tr.executed_at
                for tr in run.test_results
                if tr.executed_at
            ]
            if test_times:
                max_test_time = max(test_times)
                if last_activity is None or max_test_time > last_activity:
                    last_activity = max_test_time

        # If activity exists within the threshold window, preserve as legitimately active
        if last_activity and last_activity > cutoff:
            active_skipped.append(
                {
                    "run_id": run.id,
                    "last_activity": last_activity.isoformat(),
                    "status": "RUNNING_ACTIVE",
                }
            )
            continue

        # Stale execution confirmed: no activity within threshold window
        original_status = run.status
        reconcile_time = datetime.now(UTC)
        reconciled_info = {
            "run_id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "last_activity": last_activity.isoformat() if last_activity else None,
            "original_status": original_status,
            "new_status": "ABORTED",
            "reason": (
                f"Execution had no recorded activity for >= {stale_threshold_hours}h "
                "(abandoned or interrupted runner)."
            ),
        }
        reconciled.append(reconciled_info)

        if not dry_run:
            run.status = "ABORTED"
            run.completed_at = reconcile_time
            if not run.fallback_reason:
                run.fallback_reason = (
                    "Orphaned uncompleted execution recovered during reconciliation"
                )

            if run.total_duration_sec == 0.0 and run.created_at:
                created_tz = (
                    run.created_at if run.created_at.tzinfo else run.created_at.replace(tzinfo=UTC)
                )
                run.total_duration_sec = max(
                    0.0, round((reconcile_time - created_tz).total_seconds(), 2)
                )

            audit = AuditLog(
                event_type="STALE_RUN_RECONCILED",
                entity_type="PipelineRun",
                entity_id=run.id,
                details=(
                    f"Orphaned execution reconciled. Status: {original_status} -> ABORTED. "
                    f"Last activity: {last_activity}. Threshold: {stale_threshold_hours}h."
                ),
            )
            db.add(audit)

    if not dry_run and reconciled:
        db.commit()
        logger.info(
            f"🔄 Reconciled {len(reconciled)} stale pipeline run(s) to ABORTED; "
            f"preserved {len(active_skipped)} active run(s)."
        )

    return {
        "reconciled_count": len(reconciled),
        "active_skipped_count": len(active_skipped),
        "cutoff_threshold_hours": stale_threshold_hours,
        "dry_run": dry_run,
        "reconciled_runs": reconciled,
        "active_runs": active_skipped,
        "active_skipped": active_skipped,
    }
