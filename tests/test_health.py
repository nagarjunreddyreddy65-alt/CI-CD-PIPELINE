"""
Tests for Health, Readiness, and Root API Endpoints.
"""

from fastapi import status


def test_root_endpoint(client):
    """Verifies that root endpoint returns service info, project title, and docs URL."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Autonomous DevOps" in data["project"]
    assert data["status"] == "ONLINE"
    assert data["documentation"] == "/docs"


def test_health_endpoint(client):
    """Verifies liveness health check returns healthy status and UTC timestamp."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["service"] == "Autonomous DevOps Backend"
    assert "timestamp_utc" in data


def test_readiness_endpoint(client):
    """Verifies readiness check queries database successfully."""
    response = client.get("/api/v1/ready")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["ready"] is True
    assert "CONNECTED" in data["database_status"]
    assert "timestamp_utc" in data
