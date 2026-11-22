"""
API tests for Code Analysis & Graph Endpoints.
"""

from fastapi import status


def test_analysis_diff_api_optimized(client):
    """Tests POST /api/v1/analysis/diff on non-sensitive util change."""
    payload = {
        "repository_path": ".",
        "files": [
            {
                "path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ],
    }
    response = client.post("/api/v1/analysis/diff", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert data["fallback_required"] is False
    assert data["selected_tests_count"] > 0
    assert data["estimated_test_reduction_pct"] > 0.0


def test_analysis_diff_api_auth_fallback(client):
    """Tests POST /api/v1/analysis/diff on sensitive auth change."""
    payload = {
        "repository_path": ".",
        "files": [
            {
                "path": "sample_app/auth/security_service.py",
                "change_type": "MODIFIED",
                "lines_added": 1,
                "lines_deleted": 0,
            }
        ],
    }
    response = client.post("/api/v1/analysis/diff", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert data["fallback_required"] is True
    assert "Safety Rule 2" in data["fallback_reason"]
    assert data["selected_tests_count"] == data["total_repository_tests"]


def test_analysis_graph_summary(client):
    """Tests GET /api/v1/analysis/graph returns topology metrics."""
    response = client.get("/api/v1/analysis/graph")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert data["total_modules"] > 0
    assert data["total_dependencies"] > 0
    assert "sample_app.utils.math_ops" in data["modules"]
