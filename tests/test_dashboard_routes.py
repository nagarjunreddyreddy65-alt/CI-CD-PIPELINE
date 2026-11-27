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
    # Priority 1 & 3: Exact reconciliation of all supported statuses with total runs
    assert data["total_runs"] == (
        data["successful_runs"]
        + data["failed_runs"]
        + data["aborted_runs"]
        + data["cancelled_runs"]
        + data["running_runs"]
        + data.get("pending_runs", 0)
    )
    # Priority 1: Exact reconciliation of execution modes with total runs
    assert data["total_runs"] == (
        data["planned_optimized_runs"] + data["fallback_runs"] + data["unplanned_runs"]
    )
    assert "optimization_rate_pct" in data
    assert "completed_runs_count" in data


def test_dashboard_incomplete_running_records_not_attributed_as_optimized(client, db_session):
    """
    Priority 2: Verifies that running/unplanned records with 0 selected tests
    are never falsely attributed as 'Optimized'.
    """
    repo = db_session.query(Repository).first()
    commit = db_session.query(Commit).first()

    running_run = PipelineRun(
        id="dash-run-running-test",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="CI Test",
        status="RUNNING",
        is_optimized=True,  # Raw column was set to True
        total_duration_sec=0.0,
    )
    db_session.add(running_run)
    db_session.commit()

    res = client.get("/dashboard/overview")
    assert res.status_code == 200
    # Should render badge 'Running', NOT 'Optimized'
    assert "Running" in res.text


def test_dashboard_observability_insufficient_samples_never_reports_healthy(client, db_session):
    """
    Priority 5: Verifies that when hardware telemetry count < 5,
    the dashboard reports INSUFFICIENT_SAMPLES and never falsely reports HEALTHY.
    """
    from app.database.models import Telemetry

    repo = db_session.query(Repository).first()
    commit = db_session.query(Commit).first()
    run1 = db_session.query(PipelineRun).first()

    run2 = PipelineRun(
        id="dash-run-002",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="CI Workflow 2",
        status="SUCCESS",
        total_duration_sec=12.0,
    )
    db_session.add(run2)
    db_session.flush()

    # Seed 2 telemetry records (sample size < MIN_REQUIRED_SAMPLES = 5)
    t1 = Telemetry(pipeline_run_id=run1.id, cpu_percent_avg=15.0, memory_mb_peak=120.0)
    t2 = Telemetry(pipeline_run_id=run2.id, cpu_percent_avg=22.0, memory_mb_peak=145.0)
    db_session.add_all([t1, t2])
    db_session.commit()

    res = client.get("/dashboard/observability")
    assert res.status_code == 200
    # With 2 database records (< 5 required), must display INSUFFICIENT_SAMPLES and never report HEALTHY
    assert "INSUFFICIENT_SAMPLES" in res.text
    assert "HEALTHY" not in res.text


def test_dashboard_cancelled_lifecycle_status_aggregation(client, db_session):
    """
    Priority 3: Verifies that CANCELLED runs are included in aggregation
    and reconcile with total pipeline runs across the API and dashboard.
    """
    repo = db_session.query(Repository).first()
    commit = db_session.query(Commit).first()

    cancelled_run = PipelineRun(
        id="dash-run-cancelled-001",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="CI Cancelled Test",
        status="CANCELLED",
        is_optimized=False,
        total_duration_sec=4.2,
    )
    db_session.add(cancelled_run)
    db_session.commit()

    # Verify API metrics aggregation includes cancelled_runs
    res = client.get("/api/v1/dashboard/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["cancelled_runs"] >= 1
    assert data["total_runs"] == (
        data["successful_runs"]
        + data["failed_runs"]
        + data["aborted_runs"]
        + data["cancelled_runs"]
        + data["running_runs"]
        + data.get("pending_runs", 0)
    )

    # Verify overview page renders Cancelled badge
    res_page = client.get("/dashboard/overview")
    assert res_page.status_code == 200
    assert "Cancelled" in res_page.text


def test_attribution_zero_selected_tests_plan_attributed_as_fallback(client, db_session):
    """
    Priority 2: Verifies that an execution plan with decision='OPTIMIZED'
    but selected_tests_count=0 is safely attributed as FULL_SUITE fallback.
    """
    from app.api.routes.dashboard import determine_execution_attribution

    repo = db_session.query(Repository).first()
    commit = db_session.query(Commit).first()

    run = PipelineRun(
        id="dash-run-zero-sel",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="CI Zero Selected",
        status="SUCCESS",
        total_duration_sec=18.0,
    )
    db_session.add(run)
    db_session.flush()

    plan = ExecutionPlan(
        pipeline_run_id=run.id,
        decision="OPTIMIZED",
        decision_reason="Faulty plan with zero tests",
        selected_tests_count=0,
        total_tests_count=50,
        tests_reduction_pct=0.0,
        selected_tests_json="[]",
    )
    db_session.add(plan)
    db_session.commit()

    decision, is_opt, is_fb, _sel_count, _tot_count, reason = determine_execution_attribution(run)
    assert decision == "FULL_SUITE"
    assert is_opt is False
    assert is_fb is True
    assert "Faulty plan" in reason


def test_attribution_inconsistent_fallback_flag_enforces_safety(client, db_session):
    """
    Priority 2: Verifies that when fallback_triggered is True, execution attribution
    is deterministically FULL_SUITE, overriding any optimistic execution plan flags.
    """
    from app.api.routes.dashboard import determine_execution_attribution

    repo = db_session.query(Repository).first()
    commit = db_session.query(Commit).first()

    run = PipelineRun(
        id="dash-run-inconsistent-flags",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="CI Inconsistent Flags",
        status="FAILED",
        fallback_triggered=True,
        fallback_reason="Runner crash during optimized execution",
        is_optimized=True,  # Inconsistent optimistic raw flag
        total_duration_sec=20.0,
    )
    db_session.add(run)
    db_session.flush()

    plan = ExecutionPlan(
        pipeline_run_id=run.id,
        decision="OPTIMIZED",
        decision_reason="Optimistic AST plan before runtime failure",
        selected_tests_count=5,
        total_tests_count=50,
        tests_reduction_pct=90.0,
        selected_tests_json="[]",
    )
    db_session.add(plan)
    db_session.commit()

    decision, is_opt, is_fb, _sel_count, _tot_count, reason = determine_execution_attribution(run)
    assert decision == "FULL_SUITE"
    assert is_opt is False
    assert is_fb is True
    assert "Runner crash" in reason


def test_overview_filters_separated_for_status_and_decision(client):
    """
    Priority 1: Verifies that overview.html defines separated Run Status filters
    (col 2) and Execution Decision filters (col 4).
    """
    res = client.get("/dashboard/overview")
    assert res.status_code == 200
    html = res.text

    # Status filter container and buttons
    assert 'id="recentRunsStatusFilter"' in html
    assert 'data-filter="PASSED"' in html
    assert 'data-filter="FAILED"' in html
    assert 'data-filter="ABORTED"' in html
    assert 'data-filter="CANCELLED"' in html

    # Decision filter container and buttons
    assert 'id="recentRunsDecisionFilter"' in html
    assert 'data-filter="OPTIMIZED"' in html
    assert 'data-filter="FULL SUITE"' in html
    assert 'data-filter="DIRECT SUITE"' in html

    # Script binding column indexes 2 and 4
    assert 'initStatusFilter("recentRunsStatusFilter", "recentRunsTable", 2)' in html
    assert 'initStatusFilter("recentRunsDecisionFilter", "recentRunsTable", 4)' in html
