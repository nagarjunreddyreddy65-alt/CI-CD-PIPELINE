"""
Unit Tests for Deterministic Failure Event Correlator.
Verifies failure signature normalization and systemic failure clustering.
"""

from datetime import UTC, datetime, timedelta

from app.telemetry.event_correlator import (
    EventCorrelator,
    FailureEvent,
)


def test_signature_normalization_strips_addresses_and_paths():
    correlator = EventCorrelator()

    raw_err = "AssertionError: object at 0x7fa3b421 failed at C:\\CI\\app\\test.py:42"
    sig = correlator.normalize_failure_signature(raw_err)
    assert "0x7fa" not in sig
    assert "C:\\CI" not in sig
    assert "AssertionError:" in sig


def test_event_correlation_groups_systemic_failures():
    correlator = EventCorrelator(time_window_seconds=3600)
    now = datetime.now(UTC)

    # 3 failures across 2 different commits with the exact same failure signature
    events = [
        FailureEvent(
            event_id="e1",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="commit-aaa-111",
            workflow_name="CI Pipeline",
            error_message="KeyError: 'database_url'",
            timestamp=now - timedelta(minutes=15),
            test_identifier="tests/test_db.py::test_conn",
        ),
        FailureEvent(
            event_id="e2",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="commit-aaa-111",
            workflow_name="Staging Pipeline",
            error_message="KeyError: 'database_url'",
            timestamp=now - timedelta(minutes=10),
            test_identifier="tests/test_db.py::test_conn",
        ),
        FailureEvent(
            event_id="e3",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="commit-bbb-222",
            workflow_name="CI Pipeline",
            error_message="KeyError: 'database_url'",
            timestamp=now - timedelta(minutes=5),
            test_identifier="tests/test_db.py::test_conn",
        ),
        # 1 isolated different failure
        FailureEvent(
            event_id="e4",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="commit-ccc-333",
            workflow_name="CI Pipeline",
            error_message="AssertionError: 4 != 5",
            timestamp=now,
            test_identifier="tests/test_math.py::test_add",
        ),
    ]

    groups = correlator.correlate_events(events)
    assert len(groups) == 2

    # Find the KeyError group
    key_error_group = next(g for g in groups if "KeyError" in g.failure_signature)
    assert key_error_group.occurrence_count == 3
    assert len(key_error_group.affected_commits) == 2
    assert key_error_group.is_systemic is True
    assert "Systemic failure" in key_error_group.description

    # Find the AssertionError group
    assert_group = next(g for g in groups if "AssertionError" in g.failure_signature)
    assert assert_group.occurrence_count == 1
    assert assert_group.is_systemic is False
    assert "Isolated failure" in assert_group.description


def test_events_outside_configured_time_window_split():
    """Verifies that failures outside the configured sliding window form separate incident groups."""
    correlator = EventCorrelator(time_window_seconds=1800)  # 30 minute window
    t0 = datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)

    events = [
        FailureEvent(
            event_id="e1",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="c1",
            workflow_name="CI",
            error_message="ValueError: invalid port",
            timestamp=t0,
        ),
        # 10 minutes later (inside 30m window)
        FailureEvent(
            event_id="e2",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="c2",
            workflow_name="CI",
            error_message="ValueError: invalid port",
            timestamp=t0 + timedelta(minutes=10),
        ),
        # 2 hours later (outside 30m window)
        FailureEvent(
            event_id="e3",
            repository="AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash="c3",
            workflow_name="CI",
            error_message="ValueError: invalid port",
            timestamp=t0 + timedelta(hours=2),
        ),
    ]

    groups = correlator.correlate_events(events)
    # Must produce 2 separate incident groups despite having the exact same error signature
    assert len(groups) == 2
    g1 = groups[0]
    g2 = groups[1]
    assert g1.occurrence_count == 2
    assert g2.occurrence_count == 1


def test_same_signature_across_different_repositories_remain_isolated():
    """Verifies that identical signatures from different repositories are never merged."""
    correlator = EventCorrelator(time_window_seconds=3600)
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)

    events = [
        FailureEvent(
            event_id="e1",
            repository="OrgA/RepoOne",
            commit_hash="c1",
            workflow_name="CI",
            error_message="TimeoutError: connection timed out",
            timestamp=now,
        ),
        FailureEvent(
            event_id="e2",
            repository="OrgB/RepoTwo",
            commit_hash="c2",
            workflow_name="CI",
            error_message="TimeoutError: connection timed out",
            timestamp=now + timedelta(minutes=5),
        ),
    ]

    groups = correlator.correlate_events(events)
    assert len(groups) == 2
    repos = {g.repository for g in groups}
    assert repos == {"OrgA/RepoOne", "OrgB/RepoTwo"}


def test_different_signatures_in_same_repository():
    """Verifies that different error signatures in the same repository stay separate."""
    correlator = EventCorrelator(time_window_seconds=3600)
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)

    events = [
        FailureEvent(
            event_id="e1",
            repository="RepoA",
            commit_hash="c1",
            workflow_name="CI",
            error_message="SyntaxError: invalid syntax",
            timestamp=now,
        ),
        FailureEvent(
            event_id="e2",
            repository="RepoA",
            commit_hash="c1",
            workflow_name="CI",
            error_message="ZeroDivisionError: division by zero",
            timestamp=now + timedelta(minutes=5),
        ),
    ]

    groups = correlator.correlate_events(events)
    assert len(groups) == 2
    sigs = {g.failure_signature for g in groups}
    assert any("SyntaxError" in s for s in sigs)
    assert any("ZeroDivisionError" in s for s in sigs)


def test_timezone_aware_and_out_of_order_events():
    """Verifies out-of-order events with different timezone offsets are sorted and clustered accurately."""
    from datetime import timezone

    correlator = EventCorrelator(time_window_seconds=3600)

    # 12:30 UTC
    t_utc = datetime(2026, 11, 24, 12, 30, 0, tzinfo=UTC)
    # 17:35 at +05:00 = 12:35 UTC (5 minutes later)
    tz_plus5 = timezone(timedelta(hours=5))
    t_plus5 = datetime(2026, 11, 24, 17, 35, 0, tzinfo=tz_plus5)
    # Naive timestamp representing 12:15 UTC (15 minutes earlier)
    t_naive = datetime(2026, 11, 24, 12, 15, 0)

    # Pass in reverse chronological order
    events = [
        FailureEvent(
            event_id="e2",
            repository="RepoX",
            commit_hash="c2",
            workflow_name="CI",
            error_message="TypeError: expected str, got int",
            timestamp=t_plus5,
        ),
        FailureEvent(
            event_id="e1",
            repository="RepoX",
            commit_hash="c1",
            workflow_name="CI",
            error_message="TypeError: expected str, got int",
            timestamp=t_utc,
        ),
        FailureEvent(
            event_id="e0",
            repository="RepoX",
            commit_hash="c0",
            workflow_name="CI",
            error_message="TypeError: expected str, got int",
            timestamp=t_naive,
        ),
    ]

    groups = correlator.correlate_events(events)
    assert len(groups) == 1
    g = groups[0]
    assert g.occurrence_count == 3
    # Check that first_seen corresponds to the earliest event (12:15 UTC)
    assert "12:15:00" in g.first_seen


def test_api_correlation_with_timestamps(client):
    """Verifies the /api/v1/telemetry/correlate-failures endpoint preserves timestamps and handles missing/invalid."""
    payload = {
        "time_window_seconds": 1800,
        "events": [
            {
                "event_id": "api-1",
                "repository": "Test/Repo",
                "commit_hash": "c1",
                "workflow_name": "CI",
                "error_message": "IndexError: list index out of range",
                "timestamp": "2026-11-24T14:00:00Z",
            },
            {
                "event_id": "api-2",
                "repository": "Test/Repo",
                "commit_hash": "c2",
                "workflow_name": "CI",
                "error_message": "IndexError: list index out of range",
                "timestamp": "2026-11-24T14:10:00+00:00",
            },
            {
                "event_id": "api-3",
                "repository": "Test/Repo",
                "commit_hash": "c3",
                "workflow_name": "CI",
                "error_message": "IndexError: list index out of range",
                "timestamp": "invalid-timestamp-format",
            },
        ],
    }

    res = client.post(
        "/api/v1/telemetry/correlate-failures",
        json=payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "groups" in data
    assert data["correlated_groups_count"] >= 1
