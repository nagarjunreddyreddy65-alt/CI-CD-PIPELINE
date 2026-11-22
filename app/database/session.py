"""
SQLAlchemy Database Engine and Scoped Session Factory.
Provides seamless fallback between PostgreSQL (production) and SQLite (testing/local).
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings
from app.core.logging import logger

Base = declarative_base()


def get_engine():
    """
    Creates an engine connected to PostgreSQL. If PostgreSQL is unreachable
    and SQLITE_FALLBACK_URL is enabled, falls back to a local SQLite database.
    """
    # 1. Check if testing environment or SQLite forced
    if settings.ENVIRONMENT == "testing" or settings.USE_SQLITE_FALLBACK:
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
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection unavailable ({e}). Falling back to SQLite: {settings.SQLITE_FALLBACK_URL}"
            )
            return create_engine(
                settings.SQLITE_FALLBACK_URL,
                connect_args={"check_same_thread": False},
            )

    # 2. Strict production PostgreSQL
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


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding transactional database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
