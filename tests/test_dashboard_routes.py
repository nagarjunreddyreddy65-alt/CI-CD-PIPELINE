"""
Unit and Integration Tests for Web Dashboard Routes.
Verifies that all 7 dashboard views and aggregation APIs render successfully.
"""

import pytest

from app.database.models import Commit, ExecutionPlan, PipelineRun, Repository


@pytest.fixture(autouse=True)
def seed_dashboard_data(db_session):
    """Seeds sample pipeline runs and execution plans to verify dashboard rendering with live entities."""
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    commit = Commit(
        repository_id=repo.id,
        commit_hash="dash-test-commit-001",
        branch="main",
        author_name="DevOps Lead",
        author_email="devops@example.com",
        message="Optimize pipeline test selection",
    )
    db_session.add(commit)
    db_session.flush()

    run = PipelineRun(
        id="dash-run-001",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="CI Workflow",
        status="SUCCESS",
        is_optimized=True,
        total_duration_sec=14.5,
    )
    db_session.add(run)
    db_session.flush()

    plan = ExecutionPlan(
        pipeline_run_id=run.id,
        decision="OPTIMIZED",
        decision_reason="Selected 5 impacted unit tests",
        selected_tests_count=5,
        total_tests_count=50,
        tests_reduction_pct=90.0,
        selected_tests_json="[]",
    )
    db_session.add(plan)
    db_session.commit()


def test_dashboard_root_overview(client):
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Overview" in res.text
    assert "Total Pipeline Runs" in res.text


def test_dashboard_overview_page(client):
    res = client.get("/dashboard/overview")
    assert res.status_code == 200
    assert "Executive Pipeline Overview" in res.text
    assert "Optimization Rate" in res.text


def test_dashboard_history_page(client):
    res = client.get("/dashboard/history")
    assert res.status_code == 200
    assert "Historical Pipeline Executions" in res.text
    assert "dash-test-commit-001"[:8] in res.text


def test_dashboard_ai_insights_page(client):
    res = client.get("/dashboard/ai-insights")
    assert res.status_code == 200
    assert "AI Predictive Insights" in res.text
    assert "Failure Risk Classifier" in res.text


def test_dashboard_optimization_page(client):
    res = client.get("/dashboard/optimization")
    assert res.status_code == 200
    assert "AST Test Optimization" in res.text
    assert "The 21 Fallback Scenarios" in res.text


def test_dashboard_security_page(client):
    res = client.get("/dashboard/security")
    assert res.status_code == 200
    assert "Security & Compliance" in res.text
    assert "Secret Protection Audit" in res.text


def test_dashboard_observability_page(client):
    res = client.get("/dashboard/observability")
    assert res.status_code == 200
    assert "Observability & Telemetry" in res.text
    assert "Hardware Telemetry Over Time" in res.text


def test_dashboard_health_page(client):
    res = client.get("/dashboard/health")
    assert res.status_code == 200
    assert "System Health" in res.text
    assert "API Service" in res.text


def test_api_dashboard_metrics(client):
    res = client.get("/api/v1/dashboard/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["total_runs"] >= 1
    assert data["successful_runs"] >= 1
    assert "optimization_rate_pct" in data
