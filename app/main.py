"""
FastAPI Application Entry Point.
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.logging import logger
from app.database.session import init_db
from app.api.routes.health import router as health_router
from app.api.routes.analysis import router as analysis_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown handler."""
    logger.info("=" * 70)
    logger.info(f"🚀 Starting {settings.PROJECT_NAME}")
    logger.info(f"📌 Environment: {settings.ENVIRONMENT} | Version: {settings.VERSION}")
    logger.info(f"🛡️  Safety Fallback Mode: {settings.STRICT_FALLBACK_MODE}")
    logger.info("=" * 70)

    # Initialize database tables
    try:
        init_db()
        logger.info("✅ Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

    yield

    logger.info("🛑 Autonomous DevOps backend shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Autonomous DevOps is an AI-driven CI/CD optimization platform that predicts "
        "pipeline failure risk, estimates execution duration, maps Python AST dependencies, "
        "and produces safe, deterministic test execution plans with strict fallback rules."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# -----------------------------------------------------------------------------
# CORS Middleware
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Global Validation Exception Handler
# -----------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field_loc = " -> ".join(str(part) for part in err.get("loc", []))
        errors.append({
            "field": field_loc,
            "message": err.get("msg"),
            "type": err.get("type"),
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Request validation failed",
            "details": errors,
        },
    )


# -----------------------------------------------------------------------------
# Root Information Endpoint
# -----------------------------------------------------------------------------
@app.get("/", tags=["Root"])
def read_root():
    """Root endpoint returning service identity, documentation links, and operational status."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "ONLINE",
        "documentation": "/docs",
        "api_v1_health": f"{settings.API_V1_PREFIX}/health",
        "api_v1_ready": f"{settings.API_V1_PREFIX}/ready",
    }


# -----------------------------------------------------------------------------
# Router Registration
# -----------------------------------------------------------------------------
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(analysis_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
