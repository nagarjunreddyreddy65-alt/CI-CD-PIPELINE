"""
SQLAlchemy Database Engine and Scoped Session Factory.
Provides seamless fallback between PostgreSQL (production) and SQLite (testing/local).
"""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings
from app.core.logging import logger

Base = declarative_base()


def get_engine():
    """
    Creates an engine connected to PostgreSQL. If PostgreSQL is unreachable
    and SQLITE_FALLBACK_URL is enabled (non-production only), falls back to a local SQLite database.
    In production mode, failing to connect to PostgreSQL will never fall back to SQLite.
    """
    # 1. Strict production mode - PostgreSQL only, never fall back to SQLite
    if settings.ENVIRONMENT == "production":
        return create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=15,
            max_overflow=25,
        )

    # 2. Testing environment - use SQLite directly for fast, isolated test execution
    if settings.ENVIRONMENT == "testing":
        return create_engine(
            settings.SQLITE_FALLBACK_URL,
            connect_args={"check_same_thread": False},
        )

    # 3. Local development with optional SQLite fallback
    if settings.USE_SQLITE_FALLBACK:
        try:
            # First attempt connecting to PostgreSQL
            engine = create_engine(
                settings.DATABASE_URL,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                connect_args={"connect_timeout": 3},
            )
            # Test immediate connectivity
            with engine.connect():
                logger.info("Successfully connected to primary PostgreSQL database.")
                return engine
        except (SQLAlchemyError, OSError, ImportError) as e:
            logger.warning(
                f"PostgreSQL connection unavailable ({e}). Falling back to SQLite: {settings.SQLITE_FALLBACK_URL}"
            )
            return create_engine(
                settings.SQLITE_FALLBACK_URL,
                connect_args={"check_same_thread": False},
            )

    # 3. Default fallback for other environments
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=15,
        max_overflow=25,
    )


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initializes schema tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def get_db_info(session: Session | None = None) -> dict[str, Any]:
    """Returns runtime database dialect, connectivity status, and fallback status."""
    try:
        active_engine = session.get_bind() if session else engine
        driver = active_engine.url.drivername.lower() if active_engine else "sqlite"
    except (SQLAlchemyError, AttributeError, RuntimeError):
        driver = "sqlite"

    is_postgres = "postgresql" in driver
    is_sqlite = "sqlite" in driver
    engine_name = "PostgreSQL" if is_postgres else ("SQLite" if is_sqlite else driver.capitalize())
    fallback_active = is_sqlite and settings.ENVIRONMENT != "testing"
    return {
        "engine_name": engine_name,
        "driver": driver,
        "is_postgres": is_postgres,
        "is_sqlite": is_sqlite,
        "fallback_active": fallback_active,
    }


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding transactional database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
