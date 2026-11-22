"""
Tests for SQLAlchemy Relational Models and Entity Relationships.
"""

from app.database.models import (
    AuditLog,
    Commit,
    ExecutionPlan,
    PipelineRun,
    Repository,
)


def test_repository_and_commit_creation(db_session):
    """Tests creating repository and linked commit with relationship integrity."""
    repo = Repository(
        name="sample-python-app",
        owner="nagarjunreddyreddy65-alt",
        clone_url="https://github.com/nagarjunreddyreddy65-alt/sample-python-app.git",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    assert repo.id is not None
    assert repo.name == "sample-python-app"

    commit = Commit(
        repository_id=repo.id,
        commit_hash="a1b2c3d4e5f6789012345678901234567890abcd",
        branch="main",
        author_name="Nagarjun Reddy",
        author_email="developer@autonomousdevops.local",
        message="feat: initial commit",
    )
    db_session.add(commit)
    db_session.commit()
    db_session.refresh(commit)

    assert commit.id is not None
    assert commit.repository.name == "sample-python-app"
    assert len(repo.commits) == 1


def test_pipeline_run_and_execution_plan(db_session):
    """Tests creating pipeline run linked to an execution plan with JSON test payload."""
    repo = Repository(
        name="test-repo",
        owner="test-owner",
        clone_url="https://github.com/test-owner/test-repo.git",
    )
    db_session.add(repo)
    db_session.commit()

    pipeline_run = PipelineRun(
        repository_id=repo.id,
        workflow_name="CI Test Suite",
        status="RUNNING",
        trigger_event="push",
        is_optimized=True,
    )
    db_session.add(pipeline_run)
    db_session.commit()
    db_session.refresh(pipeline_run)

    plan = ExecutionPlan(
        pipeline_run_id=pipeline_run.id,
        decision="OPTIMIZED",
        decision_reason="Only test_auth affected by changes in auth/service.py",
        selected_tests_count=2,
        total_tests_count=10,
        tests_reduction_pct=80.0,
        selected_tests_json='["tests/test_auth.py::test_login", "tests/test_auth.py::test_jwt"]',
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(pipeline_run)

    assert pipeline_run.execution_plan is not None
    assert pipeline_run.execution_plan.decision == "OPTIMIZED"
    assert pipeline_run.execution_plan.tests_reduction_pct == 80.0


def test_audit_log_recording(db_session):
    """Tests recording auditable governance events."""
    audit = AuditLog(
        event_type="SAFETY_POLICY_FALLBACK",
        entity_type="PIPELINE_RUN",
        entity_id="run_12345",
        details="Fallback triggered: Database migration file detected in commit",
        performed_by="DeterministicDecisionEngine",
    )
    db_session.add(audit)
    db_session.commit()
    db_session.refresh(audit)

    assert audit.id is not None
    assert audit.event_type == "SAFETY_POLICY_FALLBACK"
    assert "Database migration" in audit.details
