"""
Pytest Fixtures for Autonomous DevOps.
Provides isolated in-memory SQLite database sessions and FastAPI TestClient.
"""

import os
import sys

# Ensure CI-CD-PIPELINE root is in Python path and testing environment is active
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["ENVIRONMENT"] = "testing"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure all database models are imported and registered on Base.metadata
from app.core.config import settings
from app.database import models as _models  # noqa: F401
from app.database.session import Base, get_db
from app.main import app

# In-memory SQLite with StaticPool so all connections and threads share the same database
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Creates a fresh, isolated database schema for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden database dependency and testing auth header."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.headers.update({"X-Runner-Token": settings.RUNNER_API_KEY})
        yield test_client
    app.dependency_overrides.clear()
