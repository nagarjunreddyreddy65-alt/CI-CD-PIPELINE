"""
Unit Tests for Deterministic Failure Event Correlator.
Verifies failure signature normalization and systemic failure clustering.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.telemetry.event_correlator import (
    EventCorrelator,
    FailureEvent,
    CorrelatedEventGroup,
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
    now = datetime.now(timezone.utc)

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
