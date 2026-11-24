"""
Unit & Integration Tests for CI/CD Runner Script (scripts/run_optimized_ci.py).
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.

Exercises runner logic and network boundary HTTP communication directly against scripts.run_optimized_ci.main().
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.run_optimized_ci import main, validate_plan_response

# ==============================================================================
# 1. PLAN VALIDATION UNIT TESTS
# ==============================================================================


def test_runner_validate_plan_response_valid_optimized():
    """Verifies that a valid OPTIMIZED plan response passes validation."""
    valid_plan = {
        "decision": "OPTIMIZED",
        "decision_reason": "Safe change detected",
        "is_optimized": True,
        "fallback_triggered": False,
        "selected_tests": ["tests_sample_app/test_math_ops.py::test_addition"],
        "pipeline_run_id": "run-123",
    }
    is_valid, _msg = validate_plan_response(valid_plan)
    assert is_valid is True


def test_runner_validate_plan_response_valid_full_suite():
    """Verifies that a valid FULL_SUITE plan response passes validation."""
    valid_full = {
        "decision": "FULL_SUITE",
        "decision_reason": "Safety fallback triggered",
        "is_optimized": False,
        "fallback_triggered": True,
        "selected_tests": [],
        "pipeline_run_id": "run-124",
    }
    is_valid, _msg = validate_plan_response(valid_full)
    assert is_valid is True


def test_runner_validate_plan_response_missing_fields():
    """Verifies that plans missing required fields are rejected."""
    bad_plan = {"decision": "OPTIMIZED"}
    is_valid, msg = validate_plan_response(bad_plan)
    assert is_valid is False
    assert "Missing required field" in msg


def test_runner_validate_plan_response_inconsistent_flags():
    """Verifies that OPTIMIZED decision with fallback_triggered=True is rejected."""
    inconsistent = {
        "decision": "OPTIMIZED",
        "is_optimized": True,
        "fallback_triggered": True,
        "selected_tests": ["test1"],
    }
    is_valid, msg = validate_plan_response(inconsistent)
    assert is_valid is False
    assert "Inconsistent plan" in msg


def test_runner_validate_plan_response_unsafe_characters_rejected():
    """Verifies that shell injection characters in test names are rejected."""
    unsafe = {
        "decision": "OPTIMIZED",
        "is_optimized": True,
        "fallback_triggered": False,
        "selected_tests": ["tests/test_auth.py; rm -rf /"],
    }
    is_valid, msg = validate_plan_response(unsafe)
    assert is_valid is False
    assert "unsafe characters" in msg


# ==============================================================================
# 2. RUNNER MAIN EXECUTION & NETWORK BOUNDARY TELEMETRY INTEGRATION TESTS
# ==============================================================================


def test_runner_primary_telemetry_success_no_unnecessary_fallback():
    """
    Verifies that when primary telemetry POST succeeds (HTTP 201/200):
    1. The actual runner main() executes.
    2. Primary telemetry endpoint is called with exact metrics and SUCCESS status.
    3. The secondary fallback completion endpoint is NOT called.
    4. The original test command exit code (0) is preserved.
    """
    valid_plan = {
        "decision": "OPTIMIZED",
        "decision_reason": "Safe leaf change",
        "is_optimized": True,
        "fallback_triggered": False,
        "selected_tests": ["tests_sample_app/test_math_ops.py"],
        "pipeline_run_id": "run-telemetry-success-001",
        "selected_tests_count": 1,
        "total_tests_count": 24,
        "tests_reduction_pct": 95.8,
        "predicted_failure_probability": 0.05,
        "estimated_time_saved_sec": 1.2,
        "triggered_safety_rules": [],
    }

    mock_plan_res = MagicMock(spec=httpx.Response)
    mock_plan_res.status_code = 200
    mock_plan_res.json.return_value = valid_plan
    mock_plan_res.raise_for_status.return_value = None

    mock_telemetry_res = MagicMock(spec=httpx.Response)
    mock_telemetry_res.status_code = 201
    mock_telemetry_res.raise_for_status.return_value = None

    test_args = [
        "run_optimized_ci.py",
        "--api-url",
        "http://127.0.0.1:8000",
        "--changed-files",
        "sample_app/utils/math_ops.py:MODIFIED:5:1",
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.run_optimized_ci.execute_test_command",
            return_value=(0, 1.45, 48.5, 12.0),
        ),
        patch("httpx.post", side_effect=[mock_plan_res, mock_telemetry_res]) as mock_post,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        # 1. Exit code preserved
        assert exc_info.value.code == 0

        # 2. Verify HTTP calls: exactly 2 calls (plan generate + telemetry record)
        assert mock_post.call_count == 2
        calls = mock_post.call_args_list

        plan_call = calls[0]
        assert "/api/v1/plans/generate" in plan_call.args[0]

        telemetry_call = calls[1]
        assert "/api/v1/telemetry/record" in telemetry_call.args[0]
        payload = telemetry_call.kwargs["json"]
        assert payload["pipeline_run_id"] == "run-telemetry-success-001"
        assert payload["status"] == "SUCCESS"
        assert payload["total_duration_sec"] == 1.45
        assert payload["memory_mb_peak"] == 48.5
        assert payload["cpu_percent_avg"] == 12.0

        # 3. Verify fallback completion endpoint was NOT called
        all_called_urls = [c.args[0] for c in calls]
        assert not any("/complete" in url for url in all_called_urls)


def test_runner_http_500_telemetry_failure_triggers_fallback_completion():
    """
    Verifies that when primary telemetry POST fails with HTTP 500:
    1. The failure is caught and handled cleanly.
    2. The fallback completion endpoint is attempted.
    3. Successful fallback response (HTTP 200) is recognized.
    4. The original test exit code (0) is preserved.
    """
    valid_plan = {
        "decision": "FULL_SUITE",
        "decision_reason": "Rule 2 Auth fallback",
        "is_optimized": False,
        "fallback_triggered": True,
        "selected_tests": [],
        "pipeline_run_id": "run-telemetry-500-002",
        "selected_tests_count": 0,
        "total_tests_count": 24,
        "tests_reduction_pct": 0.0,
        "predicted_failure_probability": 0.85,
        "estimated_time_saved_sec": 0.0,
        "triggered_safety_rules": ["RULE_2_AUTH"],
    }

    mock_plan_res = MagicMock(spec=httpx.Response)
    mock_plan_res.status_code = 200
    mock_plan_res.json.return_value = valid_plan
    mock_plan_res.raise_for_status.return_value = None

    mock_bad_telemetry = MagicMock(spec=httpx.Response)
    mock_bad_telemetry.status_code = 500
    mock_bad_telemetry.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=mock_bad_telemetry,
    )

    mock_fallback_comp = MagicMock(spec=httpx.Response)
    mock_fallback_comp.status_code = 200
    mock_fallback_comp.raise_for_status.return_value = None

    test_args = [
        "run_optimized_ci.py",
        "--api-url",
        "http://127.0.0.1:8000",
        "--changed-files",
        "sample_app/auth/security_service.py:MODIFIED:10:2",
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.run_optimized_ci.execute_test_command",
            return_value=(0, 2.30, 52.0, 15.0),
        ),
        patch(
            "httpx.post",
            side_effect=[mock_plan_res, mock_bad_telemetry, mock_fallback_comp],
        ) as mock_post,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_post.call_count == 3
        calls = mock_post.call_args_list

        # Fallback completion endpoint was attempted
        comp_call = calls[2]
        assert "/api/v1/plans/runs/run-telemetry-500-002/complete" in comp_call.args[0]
        comp_payload = comp_call.kwargs["json"]
        assert comp_payload["status"] == "SUCCESS"
        assert comp_payload["total_duration_sec"] == 2.30


def test_runner_http_403_telemetry_failure_triggers_fallback_completion():
    """
    Verifies that when primary telemetry fails with HTTP 403 Forbidden:
    1. HTTP 403 is caught via raise_for_status.
    2. Fallback completion endpoint is invoked with terminal status.
    3. Original test exit code (0) is preserved.
    """
    valid_plan = {
        "decision": "FULL_SUITE",
        "decision_reason": "Rule 1 Migration fallback",
        "is_optimized": False,
        "fallback_triggered": True,
        "selected_tests": [],
        "pipeline_run_id": "run-telemetry-403-003",
        "selected_tests_count": 0,
        "total_tests_count": 24,
        "tests_reduction_pct": 0.0,
        "predicted_failure_probability": 0.90,
        "estimated_time_saved_sec": 0.0,
        "triggered_safety_rules": ["RULE_1_MIGRATION"],
    }

    mock_plan_res = MagicMock(spec=httpx.Response)
    mock_plan_res.status_code = 200
    mock_plan_res.json.return_value = valid_plan
    mock_plan_res.raise_for_status.return_value = None

    mock_403_telemetry = MagicMock(spec=httpx.Response)
    mock_403_telemetry.status_code = 403
    mock_403_telemetry.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403 Forbidden",
        request=MagicMock(),
        response=mock_403_telemetry,
    )

    mock_fallback_comp = MagicMock(spec=httpx.Response)
    mock_fallback_comp.status_code = 200
    mock_fallback_comp.raise_for_status.return_value = None

    test_args = [
        "run_optimized_ci.py",
        "--api-url",
        "http://127.0.0.1:8000",
        "--changed-files",
        "alembic/versions/001_rev.py:MODIFIED:5:0",
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.run_optimized_ci.execute_test_command",
            return_value=(0, 1.80, 50.0, 14.0),
        ),
        patch(
            "httpx.post",
            side_effect=[mock_plan_res, mock_403_telemetry, mock_fallback_comp],
        ) as mock_post,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_post.call_count == 3
        comp_call = mock_post.call_args_list[2]
        assert "/api/v1/plans/runs/run-telemetry-403-003/complete" in comp_call.args[0]
        assert comp_call.kwargs["json"]["status"] == "SUCCESS"


def test_runner_timeout_telemetry_failure_triggers_fallback_completion():
    """
    Verifies that when primary telemetry times out (httpx.TimeoutException):
    1. Timeout is caught cleanly without crashing the runner.
    2. Fallback completion endpoint is invoked.
    3. Original exit code (0) is preserved.
    """
    valid_plan = {
        "decision": "OPTIMIZED",
        "decision_reason": "Safe change",
        "is_optimized": True,
        "fallback_triggered": False,
        "selected_tests": ["tests_sample_app/test_string_ops.py"],
        "pipeline_run_id": "run-telemetry-timeout-004",
        "selected_tests_count": 1,
        "total_tests_count": 24,
        "tests_reduction_pct": 95.8,
        "predicted_failure_probability": 0.05,
        "estimated_time_saved_sec": 1.1,
        "triggered_safety_rules": [],
    }

    mock_plan_res = MagicMock(spec=httpx.Response)
    mock_plan_res.status_code = 200
    mock_plan_res.json.return_value = valid_plan
    mock_plan_res.raise_for_status.return_value = None

    mock_fallback_comp = MagicMock(spec=httpx.Response)
    mock_fallback_comp.status_code = 200
    mock_fallback_comp.raise_for_status.return_value = None

    test_args = [
        "run_optimized_ci.py",
        "--api-url",
        "http://127.0.0.1:8000",
        "--changed-files",
        "sample_app/utils/string_ops.py:MODIFIED:4:1",
    ]

    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.run_optimized_ci.execute_test_command",
            return_value=(0, 1.10, 45.0, 10.0),
        ),
        patch(
            "httpx.post",
            side_effect=[
                mock_plan_res,
                httpx.TimeoutException("Network timed out"),
                mock_fallback_comp,
            ],
        ) as mock_post,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_post.call_count == 3
        comp_call = mock_post.call_args_list[2]
        assert "/api/v1/plans/runs/run-telemetry-timeout-004/complete" in comp_call.args[0]
        assert comp_call.kwargs["json"]["status"] == "SUCCESS"


def test_runner_test_failure_preserves_exit_code_and_reports_failed():
    """
    Verifies that when test execution fails (returncode=1):
    1. Telemetry payload reports status='FAILED'.
    2. Runner exits with status code 1 (preserving original pytest exit code).
    """
    valid_plan = {
        "decision": "OPTIMIZED",
        "decision_reason": "Safe change",
        "is_optimized": True,
        "fallback_triggered": False,
        "selected_tests": ["tests_sample_app/test_math_ops.py"],
        "pipeline_run_id": "run-test-failure-005",
        "selected_tests_count": 1,
        "total_tests_count": 24,
        "tests_reduction_pct": 95.8,
        "predicted_failure_probability": 0.10,
        "estimated_time_saved_sec": 1.2,
        "triggered_safety_rules": [],
    }

    mock_plan_res = MagicMock(spec=httpx.Response)
    mock_plan_res.status_code = 200
    mock_plan_res.json.return_value = valid_plan
    mock_plan_res.raise_for_status.return_value = None

    mock_telemetry_res = MagicMock(spec=httpx.Response)
    mock_telemetry_res.status_code = 201
    mock_telemetry_res.raise_for_status.return_value = None

    test_args = [
        "run_optimized_ci.py",
        "--api-url",
        "http://127.0.0.1:8000",
        "--changed-files",
        "sample_app/utils/math_ops.py:MODIFIED:5:1",
    ]

    # Returncode = 1 (test suite failure)
    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.run_optimized_ci.execute_test_command",
            return_value=(1, 2.50, 55.0, 20.0),
        ),
        patch("httpx.post", side_effect=[mock_plan_res, mock_telemetry_res]) as mock_post,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Original exit code 1 preserved
        assert exc_info.value.code == 1

        # Reported status is FAILED
        assert mock_post.call_count == 2
        telemetry_call = mock_post.call_args_list[1]
        assert telemetry_call.kwargs["json"]["status"] == "FAILED"


def test_runner_failed_reporting_does_not_create_false_success():
    """
    Verifies that if primary telemetry AND fallback completion both fail completely:
    1. A failing test run (exit code 1) still exits with code 1 (does NOT create false success).
    2. Fallback completion was attempted before failing closed.
    """
    valid_plan = {
        "decision": "OPTIMIZED",
        "decision_reason": "Safe change",
        "is_optimized": True,
        "fallback_triggered": False,
        "selected_tests": ["tests_sample_app/test_math_ops.py"],
        "pipeline_run_id": "run-network-down-006",
        "selected_tests_count": 1,
        "total_tests_count": 24,
        "tests_reduction_pct": 95.8,
        "predicted_failure_probability": 0.10,
        "estimated_time_saved_sec": 1.2,
        "triggered_safety_rules": [],
    }

    mock_plan_res = MagicMock(spec=httpx.Response)
    mock_plan_res.status_code = 200
    mock_plan_res.json.return_value = valid_plan
    mock_plan_res.raise_for_status.return_value = None

    test_args = [
        "run_optimized_ci.py",
        "--api-url",
        "http://127.0.0.1:8000",
        "--changed-files",
        "sample_app/utils/math_ops.py:MODIFIED:5:1",
    ]

    # Both telemetry and fallback completion raise network errors
    with (
        patch("sys.argv", test_args),
        patch(
            "scripts.run_optimized_ci.execute_test_command",
            return_value=(1, 3.00, 60.0, 25.0),
        ),
        patch(
            "httpx.post",
            side_effect=[
                mock_plan_res,
                httpx.ConnectError("Connection refused on telemetry"),
                httpx.ConnectError("Connection refused on fallback completion"),
            ],
        ) as mock_post,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Exit code MUST remain 1 (no false success!)
        assert exc_info.value.code == 1

        # Verified both telemetry AND fallback were attempted
        assert mock_post.call_count == 3
        comp_call = mock_post.call_args_list[2]
        assert "/api/v1/plans/runs/run-network-down-006/complete" in comp_call.args[0]
        assert comp_call.kwargs["json"]["status"] == "FAILED"
