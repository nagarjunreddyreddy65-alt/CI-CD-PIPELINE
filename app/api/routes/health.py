"""
Health and System Readiness Endpoints.
Provides live health checks, database readiness status, and platform metadata.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db

router = APIRouter(tags=["Health & Diagnostics"])


@router.get(
    "/health",
    summary="Application Health Probe",
    description="Returns current operational status, version, and server timestamp.",
)
def get_health():
    """Liveness probe: verifies that the FastAPI web service is responsive."""
    return {
        "status": "HEALTHY",
        "service": "Autonomous DevOps Backend",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/ready",
    summary="System Readiness Probe",
    description="Verifies database connectivity and readiness to process CI/CD events.",
)
def get_readiness(db: Session = Depends(get_db)):
    """Readiness probe: validates database connection and query capability."""
    db_status = "CONNECTED"
    db_type = "PostgreSQL" if "postgresql" in settings.DATABASE_URL else "SQLite"

    try:
        # Run a simple, fast query to test database connectivity
        db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as e:
        db_status = f"DISCONNECTED: {e!s}"

    is_ready = "CONNECTED" in db_status

    return {
        "ready": is_ready,
        "database_status": db_status,
        "database_type": db_type,
        "fallback_active": settings.USE_SQLITE_FALLBACK and "SQLite" in db_type,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
