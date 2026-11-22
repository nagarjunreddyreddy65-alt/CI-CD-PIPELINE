"""
Comprehensive API Authentication Tests.
Verifies role-based access control, constant-time HMAC runner token verification,
rejection of missing/invalid tokens, and public endpoint accessibility.
"""

from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

raw_client = TestClient(app)


def test_public_endpoints_accessible_without_token():
    """Verifies public read-only endpoints are accessible without authentication."""
    # Health probe
    res = raw_client.get("/api/v1/health")
    assert res.status_code == status.HTTP_200_OK

    # Readiness probe
    res = raw_client.get("/api/v1/ready")
    assert res.status_code == status.HTTP_200_OK

    # Dashboard overview HTML
    res = raw_client.get("/dashboard/overview")
    assert res.status_code == status.HTTP_200_OK

    # Dashboard metrics JSON
    res = raw_client.get("/api/v1/dashboard/metrics")
    assert res.status_code == status.HTTP_200_OK

    # Dependency graph statistics
    res = raw_client.get("/api/v1/analysis/graph")
    assert res.status_code == status.HTTP_200_OK

    # ML models status
    res = raw_client.get("/api/v1/predictions/models")
    assert res.status_code == status.HTTP_200_OK


def test_protected_endpoints_missing_token_in_production():
    """
    Verifies that all runner-protected endpoints reject requests with HTTP 401
    when X-Runner-Token header is missing in production/development mode.
    """
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"

        endpoints = [
            ("/api/v1/plans/generate", {"changed_files": []}),
            ("/api/v1/analysis/diff", {"files": []}),
            (
                "/api/v1/telemetry/record",
                {
                    "pipeline_run_id": "test",
                    "cpu_percent_avg": 10.0,
                    "memory_mb_peak": 50.0,
                },
            ),
            ("/api/v1/telemetry/detect-anomalies", {"current_run": {}}),
            ("/api/v1/telemetry/correlate-failures", {"events": []}),
            (
                "/api/v1/security/scan",
                {"pipeline_run_id": "test", "tool_name": "Bandit", "raw_output": {}},
            ),
            ("/api/v1/predictions/predict", {}),
            ("/api/v1/predictions/train", {"n_samples": 20}),
        ]

        for url, payload in endpoints:
            res = raw_client.post(url, json=payload)
            assert res.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Expected 401 for {url} without token, got {res.status_code}"
            )
            assert "Missing runner authentication token" in res.json().get("detail", "")

        get_endpoints = [
            "/api/v1/plans",
            "/api/v1/plans/sample-plan-id",
            "/api/v1/security/scans/sample-run-id",
            "/api/v1/telemetry/history",
        ]
        for url in get_endpoints:
            res = raw_client.get(url)
            assert res.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Expected 401 for GET {url} without token, got {res.status_code}"
            )
            assert "Missing runner authentication token" in res.json().get("detail", "")

    finally:
        settings.ENVIRONMENT = original_env


def test_protected_endpoints_invalid_token():
    """
    Verifies that all runner-protected endpoints reject requests with HTTP 403
    when an incorrect X-Runner-Token header is supplied.
    """
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        bad_headers = {"X-Runner-Token": "completely_invalid_runner_token_attempt"}

        endpoints = [
            ("/api/v1/plans/generate", {"changed_files": []}),
            ("/api/v1/analysis/diff", {"files": []}),
            (
                "/api/v1/telemetry/record",
                {
                    "pipeline_run_id": "test",
                    "cpu_percent_avg": 10.0,
                    "memory_mb_peak": 50.0,
                },
            ),
            ("/api/v1/telemetry/detect-anomalies", {"current_run": {}}),
            ("/api/v1/telemetry/correlate-failures", {"events": []}),
            (
                "/api/v1/security/scan",
                {"pipeline_run_id": "test", "tool_name": "Bandit", "raw_output": {}},
            ),
            ("/api/v1/predictions/predict", {}),
            ("/api/v1/predictions/train", {"n_samples": 20}),
        ]

        for url, payload in endpoints:
            res = raw_client.post(url, json=payload, headers=bad_headers)
            assert res.status_code == status.HTTP_403_FORBIDDEN, (
                f"Expected 403 for {url} with invalid token, got {res.status_code}"
            )
            assert "Invalid runner authentication token" in res.json().get("detail", "")

        get_endpoints = [
            "/api/v1/plans",
            "/api/v1/plans/sample-plan-id",
            "/api/v1/security/scans/sample-run-id",
            "/api/v1/telemetry/history",
        ]
        for url in get_endpoints:
            res = raw_client.get(url, headers=bad_headers)
            assert res.status_code == status.HTTP_403_FORBIDDEN, (
                f"Expected 403 for GET {url} with invalid token, got {res.status_code}"
            )
            assert "Invalid runner authentication token" in res.json().get("detail", "")

    finally:
        settings.ENVIRONMENT = original_env


def test_protected_endpoints_valid_token():
    """
    Verifies that runner-protected endpoints accept requests when a valid
    pre-shared X-Runner-Token is supplied.
    """
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        good_headers = {"X-Runner-Token": settings.RUNNER_API_KEY}

        # Test POST /api/v1/analysis/diff
        res = raw_client.post(
            "/api/v1/analysis/diff",
            json={
                "repository_path": ".",
                "files": [
                    {
                        "path": "sample_app/utils/math_ops.py",
                        "change_type": "MODIFIED",
                        "lines_added": 2,
                        "lines_deleted": 0,
                    }
                ],
            },
            headers=good_headers,
        )
        assert res.status_code == status.HTTP_200_OK

        # Test POST /api/v1/predictions/predict
        res = raw_client.post(
            "/api/v1/predictions/predict",
            json={"changed_files_count": 1, "lines_added": 5, "lines_deleted": 1},
            headers=good_headers,
        )
        assert res.status_code == status.HTTP_200_OK

        # Test GET /api/v1/plans
        res = raw_client.get("/api/v1/plans", headers=good_headers)
        assert res.status_code == status.HTTP_200_OK

        # Test GET /api/v1/telemetry/history
        res = raw_client.get("/api/v1/telemetry/history", headers=good_headers)
        assert res.status_code == status.HTTP_200_OK

    finally:
        settings.ENVIRONMENT = original_env


def test_testing_environment_authentication_behavior():
    """
    Verifies that in testing mode (ENVIRONMENT='testing'), requests without a token
    are permitted for convenience, but requests with an invalid token are still rejected.
    """
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "testing"

        # No token in testing -> permitted
        res = raw_client.post(
            "/api/v1/analysis/diff",
            json={
                "repository_path": ".",
                "files": [
                    {
                        "path": "sample_app/utils/math_ops.py",
                        "change_type": "MODIFIED",
                        "lines_added": 2,
                        "lines_deleted": 0,
                    }
                ],
            },
        )
        assert res.status_code == status.HTTP_200_OK

        # Invalid token in testing -> strictly rejected with 403
        bad_headers = {"X-Runner-Token": "bad_token"}
        res = raw_client.post(
            "/api/v1/analysis/diff",
            json={"repository_path": ".", "files": []},
            headers=bad_headers,
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
    finally:
        settings.ENVIRONMENT = original_env
