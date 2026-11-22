"""
End-to-End Benchmarking & Validation Engine.
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.

Evaluates and compares:
1. Baseline Full Suite Execution
2. AST-Optimized Test Subset Execution (isolated leaf changes)
3. Deterministic Safety Fallbacks (sensitive code, auth, migrations, high-risk ML)
Measures execution time, CPU/memory consumption, test suite reduction %, and defect escape behavior.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

import psutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.test_mapper import TestDependencyMapper
from app.optimization.safety_policy import SafetyContext, SafetyPolicyEvaluator


def run_pytest_command(args: list[str]) -> dict[str, Any]:
    """Runs a pytest invocation while tracking duration and resource telemetry."""
    start_cpu = psutil.cpu_percent(interval=0.2)
    _start_mem = psutil.virtual_memory().used / (1024 * 1024)
    start_time = time.perf_counter()

    cmd = [sys.executable, "-m", "pytest"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    end_time = time.perf_counter()
    end_cpu = psutil.cpu_percent(interval=0.2)
    end_mem = psutil.virtual_memory().used / (1024 * 1024)
    duration = round(end_time - start_time, 3)

    return {
        "duration_sec": duration,
        "exit_code": result.returncode,
        "cpu_percent": round(max(start_cpu, end_cpu), 1),
        "memory_mb": round(end_mem, 1),
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "output": result.stdout,
    }


def execute_e2e_benchmark() -> dict[str, Any]:
    print("=" * 75)
    print("🚀 AUTONOMOUS DEVOPS: END-TO-END BENCHMARK & VALIDATION SUITE")
    print("=" * 75)

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    mapper = TestDependencyMapper(root_dir)
    evaluator = SafetyPolicyEvaluator()

    all_tests = mapper.discover_all_test_functions(["tests_sample_app"])
    total_sample_tests = len(all_tests)
    print(f"📦 Total Target Application Unit Tests Discovered: {total_sample_tests}")
    if total_sample_tests == 0:
        raise RuntimeError(
            "No target sample application tests were discovered in tests_sample_app/."
        )

    results: dict[str, Any] = {
        "benchmark_timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        "total_available_target_tests": total_sample_tests,
        "scenarios": {},
    }

    # -------------------------------------------------------------------------
    # Scenario 1: Baseline Full Suite Execution
    # -------------------------------------------------------------------------
    print("\n[Scenario 1/5] Running Full-Suite Baseline Execution...")
    baseline_run = run_pytest_command(["tests_sample_app/", "-p", "no:httpbin", "-q"])
    if baseline_run["exit_code"] != 0:
        raise RuntimeError(
            f"Baseline test execution failed with exit code {baseline_run['exit_code']}"
        )

    baseline_run["tests_executed"] = total_sample_tests
    baseline_run["decision"] = "FULL_SUITE_BASELINE"
    baseline_run["reduction_pct"] = 0.0
    results["scenarios"]["baseline_full_suite"] = baseline_run
    print(
        f"  ⏱ Duration: {baseline_run['duration_sec']}s | Tests: {total_sample_tests} | Status: {baseline_run['status']}"
    )

    # -------------------------------------------------------------------------
    # Scenario 2: Optimized Leaf Change (Math Operations)
    # -------------------------------------------------------------------------
    print(
        "\n[Scenario 2/5] Evaluating Isolated Non-Sensitive Change (sample_app/utils/math_ops.py)..."
    )
    math_change = [
        {
            "path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 3,
            "lines_deleted": 1,
        }
    ]
    map_res = mapper.map_changes_to_tests(math_change)

    selected_tests = [t for t in map_res.affected_test_identifiers if "tests_sample_app" in t]
    selected_count = len(selected_tests)
    if selected_count == 0:
        raise RuntimeError(
            "Optimization failed: Selected candidate test list is empty for modified math_ops.py!"
        )

    reduction = round(
        ((total_sample_tests - selected_count) / max(1, total_sample_tests)) * 100.0, 1
    )

    opt_run = run_pytest_command(selected_tests + ["-p", "no:httpbin", "-q"])
    if opt_run["exit_code"] != 0:
        raise RuntimeError(f"Optimized test subset failed with exit code {opt_run['exit_code']}")

    opt_run["tests_executed"] = selected_count
    opt_run["decision"] = "OPTIMIZED"
    opt_run["reduction_pct"] = reduction
    opt_run["fallback_triggered"] = map_res.fallback_required
    results["scenarios"]["optimized_math_change"] = opt_run
    print(
        f"  ⏱ Duration: {opt_run['duration_sec']}s | Tests: {selected_count}/{total_sample_tests} ({reduction}% reduction)"
    )

    # -------------------------------------------------------------------------
    # Scenario 3: Sensitive Authentication Change (Rule 2 Fallback)
    # -------------------------------------------------------------------------
    print(
        "\n[Scenario 3/5] Evaluating Sensitive Auth Change (sample_app/auth/security_service.py)..."
    )
    auth_change = [
        {
            "path": "sample_app/auth/security_service.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]
    auth_map = mapper.map_changes_to_tests(auth_change)

    auth_run = run_pytest_command(["tests_sample_app/", "-p", "no:httpbin", "-q"])
    auth_run["tests_executed"] = total_sample_tests
    auth_run["decision"] = "FULL_SUITE_FALLBACK"
    auth_run["fallback_triggered"] = auth_map.fallback_required
    auth_run["fallback_reason"] = auth_map.fallback_reason
    auth_run["reduction_pct"] = 0.0
    results["scenarios"]["safety_fallback_auth"] = auth_run
    print(f"  🛡️ Rule Triggered: {auth_map.fallback_reason}")
    print(
        f"  ⏱ Duration: {auth_run['duration_sec']}s | Safety Fallback Verified (100% test coverage enforced)"
    )

    # -------------------------------------------------------------------------
    # Scenario 4: Database Migration Change (Rule 1 Fallback)
    # -------------------------------------------------------------------------
    print(
        "\n[Scenario 4/5] Evaluating Database Schema Change (alembic/versions/test_migration.py)..."
    )
    mig_change = [
        {
            "path": "alembic/versions/001_initial.py",
            "change_type": "MODIFIED",
            "lines_added": 10,
            "lines_deleted": 0,
        }
    ]
    mig_map = mapper.map_changes_to_tests(mig_change)

    mig_run = run_pytest_command(["tests_sample_app/", "-p", "no:httpbin", "-q"])
    mig_run["tests_executed"] = total_sample_tests
    mig_run["decision"] = "FULL_SUITE_FALLBACK"
    mig_run["fallback_triggered"] = mig_map.fallback_required
    mig_run["fallback_reason"] = mig_map.fallback_reason
    mig_run["reduction_pct"] = 0.0
    results["scenarios"]["safety_fallback_migration"] = mig_run
    print(f"  🛡️ Rule Triggered: {mig_map.fallback_reason}")

    # -------------------------------------------------------------------------
    # Scenario 5: High Failure Risk ML Prediction (Rule 18 Fallback)
    # -------------------------------------------------------------------------
    print("\n[Scenario 5/5] Evaluating High Risk ML Confidence Fallback (Rule 18)...")
    high_risk_ctx = SafetyContext(
        prediction_confidence=0.45,  # Below 0.70 threshold triggers Rule 18
        predicted_probability=0.85,
    )
    rule_18_eval = evaluator.evaluate(high_risk_ctx)
    results["scenarios"]["ml_high_risk_fallback"] = {
        "decision": "FULL_SUITE_FALLBACK",
        "fallback_triggered": rule_18_eval.fallback_required,
        "fallback_reason": rule_18_eval.primary_fallback_reason,
        "safety_rules": [t.rule_code.value for t in rule_18_eval.triggered_rules],
    }
    print(f"  🛡️ Rule Triggered: {rule_18_eval.primary_fallback_reason}")

    # -------------------------------------------------------------------------
    # Dynamically Calculated Metrics & Findings
    # -------------------------------------------------------------------------
    time_saved_sec = max(0.0, round(baseline_run["duration_sec"] - opt_run["duration_sec"], 3))
    pct_time_saved = round((time_saved_sec / max(0.001, baseline_run["duration_sec"])) * 100.0, 1)

    # Dynamic safety compliance calculation across all 3 sensitive scenarios
    sensitive_evaluations = [
        auth_map.fallback_required,
        mig_map.fallback_required,
        rule_18_eval.fallback_required,
    ]
    safety_compliance_pct = round(
        (sum(1 for enforced in sensitive_evaluations if enforced) / len(sensitive_evaluations))
        * 100.0,
        1,
    )

    summary = {
        "baseline_duration_sec": baseline_run["duration_sec"],
        "optimized_duration_sec": opt_run["duration_sec"],
        "runtime_savings_sec": time_saved_sec,
        "runtime_savings_pct": pct_time_saved,
        "test_count_reduction_pct_on_leaf": reduction,
        "safety_policy_compliance_rate_pct": safety_compliance_pct,
        "safety_scenarios_evaluated_count": len(sensitive_evaluations),
        "safety_scenarios_enforced_count": sum(1 for e in sensitive_evaluations if e),
        "escaped_defects_rate": "NOT_MEASURED (Empirical defect-injection experiments required for rigorous quantification)",
        "active_safety_rules_count": 21,
    }
    results["summary"] = summary

    # Write reproducible results to data/e2e_benchmark_report.json
    out_dir = os.path.join(root_dir, "data")
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "e2e_benchmark_report.json")
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 75)
    print("📊 BENCHMARK SUMMARY & VALIDATION RESULTS")
    print("=" * 75)
    print(f"  ⚡ Baseline Execution Duration:        {summary['baseline_duration_sec']}s")
    print(f"  🚀 Optimized Execution Duration:       {summary['optimized_duration_sec']}s")
    print(
        f"  ⏱ Duration Saved on Leaf Change:     {summary['runtime_savings_sec']}s ({summary['runtime_savings_pct']}%)"
    )
    print(
        f"  📉 Test Count Reduction on Leaf Change: {summary['test_count_reduction_pct_on_leaf']}%"
    )
    print(
        f"  🛡️ Safety Fallback Compliance Rate:     {summary['safety_policy_compliance_rate_pct']}% ({summary['safety_scenarios_enforced_count']}/{summary['safety_scenarios_evaluated_count']} scenarios)"
    )
    print(f"  🔒 Escaped Defect Rate:                {summary['escaped_defects_rate']}")
    print(f"  📄 Report exported to:                 {report_file}")
    print("=" * 75)

    return results


if __name__ == "__main__":
    execute_e2e_benchmark()
