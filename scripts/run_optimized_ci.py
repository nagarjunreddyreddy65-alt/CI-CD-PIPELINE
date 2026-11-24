"""
CI/CD Runner Integration Script.
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.

Executes within the CI/CD runner environment (e.g. GitHub Actions runner):
1. Detects changed files from the current git commit / pull request.
2. Contacts the Autonomous DevOps Decision Engine API.
3. Fallback Guarantees:
   - If API is unreachable or returns 5xx -> Triggers Safety Rule 19 -> Executes FULL SUITE.
   - If safety policy mandates fallback -> Executes FULL SUITE.
   - If verified safe -> Executes OPTIMIZED selected tests.
4. Collects execution telemetry (runtime, CPU, memory).
5. Returns exit code matching test suite status.
"""

import argparse
import os
import subprocess
import sys
import time

import psutil

# Ensure python path includes repository root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import httpx
except ImportError:
    httpx = None


def get_git_changed_files(base_ref: str = "HEAD~1") -> list:
    """Extracts changed files using git diff."""
    try:
        cmd = ["git", "diff", "--name-status", base_ref, "HEAD"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        changes = []
        for line in res.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("\t")
            status = parts[0]
            file_path = parts[-1]
            change_type = "MODIFIED"
            if status.startswith("A"):
                change_type = "ADDED"
            elif status.startswith("D"):
                change_type = "DELETED"
            elif status.startswith("R"):
                change_type = "RENAMED"

            changes.append(
                {
                    "file_path": file_path.replace("\\", "/"),
                    "change_type": change_type,
                    "lines_added": 10,
                    "lines_deleted": 2,
                }
            )
        return changes
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[Autonomous DevOps] Git diff detection failed ({e}). Proceeding with fallback.")
        return []


def get_commit_metadata() -> dict:
    """Extracts commit hash, author, and message from current HEAD."""
    try:
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        author = subprocess.run(
            ["git", "log", "-1", "--format=%an"], capture_output=True, text=True, check=True
        ).stdout.strip()
        email = subprocess.run(
            ["git", "log", "-1", "--format=%ae"], capture_output=True, text=True, check=True
        ).stdout.strip()
        msg = subprocess.run(
            ["git", "log", "-1", "--format=%s"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return {
            "commit_hash": commit_hash,
            "author_name": author or "CI Runner",
            "author_email": email or "runner@github.actions",
            "commit_message": msg or "CI Execution",
        }
    except (subprocess.SubprocessError, OSError):
        return {
            "commit_hash": f"local-{int(time.time())}",
            "author_name": "CI Runner",
            "author_email": "runner@github.actions",
            "commit_message": "Automated CI Run",
        }


def request_plan_from_api(api_url: str, payload: dict) -> dict:
    """Requests execution plan from FastAPI backend with timeout and runner auth."""
    if httpx is None:
        raise RuntimeError("httpx is not installed")

    runner_token = os.getenv("RUNNER_API_KEY", "autonomous_devops_runner_dev_api_key_2026")
    endpoint = f"{api_url.rstrip('/')}/api/v1/plans/generate"
    headers = {"X-Runner-Token": runner_token}
    response = httpx.post(endpoint, json=payload, headers=headers, timeout=8.0)
    response.raise_for_status()
    return response.json()


def validate_plan_response(plan: object) -> tuple[bool, str]:
    """
    Validates execution plan payload from optimization backend.
    Enforces that untrusted or malformed API responses cannot mislead the runner into unsafe behavior.
    """
    if not isinstance(plan, dict):
        return False, "Plan response must be a JSON dictionary"

    required_keys = ["decision", "is_optimized", "fallback_triggered", "selected_tests"]
    for k in required_keys:
        if k not in plan:
            return False, f"Missing required field in plan: {k}"

    decision = plan.get("decision")
    if decision not in ("OPTIMIZED", "FULL_SUITE"):
        return False, f"Invalid execution decision: {decision}"

    is_optimized = plan.get("is_optimized")
    fallback_triggered = plan.get("fallback_triggered")
    selected_tests = plan.get("selected_tests")

    if not isinstance(is_optimized, bool) or not isinstance(fallback_triggered, bool):
        return False, "is_optimized and fallback_triggered must be booleans"

    if not isinstance(selected_tests, list):
        return False, "selected_tests must be a list"

    # Optimization consistency checks
    if decision == "OPTIMIZED":
        if not is_optimized or fallback_triggered:
            return (
                False,
                "Inconsistent plan: decision OPTIMIZED but fallback_triggered=True or is_optimized=False",
            )
        if len(selected_tests) == 0:
            return False, "Inconsistent plan: decision OPTIMIZED but selected_tests is empty"
        for t in selected_tests:
            if not isinstance(t, str) or not t.strip():
                return False, "selected_tests contains empty or invalid test identifier"
            if any(char in t for char in [";", "&", "|", "`", "$", "\n", "\r"]):
                return False, f"Test identifier contains unsafe characters: {t}"
    elif decision == "FULL_SUITE" and is_optimized:
        return False, "Inconsistent plan: decision FULL_SUITE but is_optimized=True"

    return True, "Valid plan response"


def execute_test_command(command_args: list) -> tuple:
    """Executes the test command while tracking peak CPU & memory telemetry."""
    print("\n" + "=" * 70)
    print(f"🚀 EXECUTING TEST COMMAND: {' '.join(command_args)}")
    print("=" * 70 + "\n")

    start_time = time.perf_counter()
    process = subprocess.Popen(
        command_args,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    ps_proc = None
    try:
        ps_proc = psutil.Process(process.pid)
    except (psutil.Error, OSError):
        pass

    peak_memory_mb = 0.0
    cpu_measurements = []

    while process.poll() is None:
        if ps_proc:
            try:
                mem = ps_proc.memory_info().rss / (1024 * 1024)
                cpu = ps_proc.cpu_percent(interval=None)
                peak_memory_mb = max(peak_memory_mb, mem)
                cpu_measurements.append(cpu)
            except (psutil.Error, OSError):
                pass
        time.sleep(0.05)

    duration = time.perf_counter() - start_time
    avg_cpu = sum(cpu_measurements) / len(cpu_measurements) if cpu_measurements else 0.0

    return process.returncode, round(duration, 2), round(peak_memory_mb, 2), round(avg_cpu, 2)


def main():
    parser = argparse.ArgumentParser(description="Autonomous DevOps CI Runner")
    parser.add_argument(
        "--api-url", default=os.getenv("OPTIMIZATION_API_URL", "http://localhost:8000")
    )
    parser.add_argument("--base-ref", default="HEAD~1")
    parser.add_argument("--force-full", action="store_true", help="Manually force full test suite")
    parser.add_argument("--repo-name", default="AutonomousDevOps/CI-CD-PIPELINE")
    parser.add_argument("--branch", default=os.getenv("GITHUB_REF_NAME", "main"))
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Explicit list of changed files (path:MODIFIED:added:deleted or path)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("🛡️  AUTONOMOUS DEVOPS: CI/CD PIPELINE OPTIMIZATION ENGINE")
    print("   AI Predicts. Deterministic Safety Rules Decide.")
    print("=" * 70)

    # 1. Identify Changed Files
    if args.changed_files:
        changed_files = []
        for cf in args.changed_files:
            parts = cf.split(":")
            fpath = parts[0].replace("\\", "/")
            ctype = parts[1] if len(parts) > 1 else "MODIFIED"
            ladd = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
            ldel = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 2
            changed_files.append(
                {
                    "file_path": fpath,
                    "change_type": ctype,
                    "lines_added": ladd,
                    "lines_deleted": ldel,
                }
            )
    else:
        changed_files = get_git_changed_files(args.base_ref)
    commit_meta = get_commit_metadata()

    print(f"📌 Repository: {args.repo_name} | Branch: {args.branch}")
    print(f"📌 Commit: {commit_meta['commit_hash'][:8]} - {commit_meta['commit_message']}")
    print(f"📌 Detected Changed Files: {len(changed_files)}")

    # 2. Plan Generation with Deterministic Safety Fallback (Rule 19)
    plan = None
    if not args.force_full and changed_files:
        payload = {
            "repository_name": args.repo_name,
            "commit_hash": commit_meta["commit_hash"],
            "branch": args.branch,
            "author_name": commit_meta["author_name"],
            "author_email": commit_meta["author_email"],
            "commit_message": commit_meta["commit_message"],
            "changed_files": changed_files,
            "risk_threshold": 0.50,
        }

        try:
            print(f"🔍 Requesting execution plan from: {args.api_url} ...")
            raw_plan = request_plan_from_api(args.api_url, payload)
            is_valid, validation_reason = validate_plan_response(raw_plan)
            if not is_valid:
                print(f"⚠️  [Safety Rule 21 Triggered] Plan validation failed: {validation_reason}")
                print("🛡️  Enforcing MANDATORY FULL-SUITE FALLBACK for guaranteed safety.")
                plan = {
                    "decision": "FULL_SUITE",
                    "decision_reason": f"Safety Rule 21: Malformed plan response ({validation_reason})",
                    "is_optimized": False,
                    "fallback_triggered": True,
                    "fallback_reason": f"Safety Rule 21: Malformed plan response ({validation_reason})",
                    "selected_tests": [],
                    "pytest_command": "python -m pytest tests/ tests_sample_app/ -v",
                    "selected_tests_count": 0,
                    "total_tests_count": 0,
                    "tests_reduction_pct": 0.0,
                    "predicted_failure_probability": 0.0,
                    "predicted_duration_sec": 0.0,
                    "estimated_time_saved_sec": 0.0,
                    "triggered_safety_rules": ["RULE_21_UNVERIFIABLE_SAFETY"],
                }
            else:
                plan = raw_plan
        except (httpx.HTTPError, RuntimeError, OSError) as e:
            print(f"⚠️  [Safety Rule 19 Triggered] API unreachable or error ({e}).")
            print("🛡️  Enforcing MANDATORY FULL-SUITE FALLBACK for guaranteed safety.")
            plan = {
                "decision": "FULL_SUITE",
                "decision_reason": f"Safety Rule 19: Optimization API unreachable ({e})",
                "is_optimized": False,
                "fallback_triggered": True,
                "fallback_reason": "Safety Rule 19: Optimization API unreachable",
                "selected_tests": [],
                "pytest_command": "python -m pytest tests/ tests_sample_app/ -v",
                "selected_tests_count": 0,
                "total_tests_count": 0,
                "tests_reduction_pct": 0.0,
                "predicted_failure_probability": 0.0,
                "predicted_duration_sec": 0.0,
                "estimated_time_saved_sec": 0.0,
                "triggered_safety_rules": ["RULE_19_API_UNREACHABLE"],
            }
    else:
        reason = (
            "Manual override (--force-full)" if args.force_full else "No changed files detected"
        )
        plan = {
            "decision": "FULL_SUITE",
            "decision_reason": reason,
            "is_optimized": False,
            "fallback_triggered": True,
            "fallback_reason": reason,
            "selected_tests": [],
            "pytest_command": "python -m pytest tests/ tests_sample_app/ -v",
            "selected_tests_count": 0,
            "total_tests_count": 0,
            "tests_reduction_pct": 0.0,
            "predicted_failure_probability": 0.0,
            "predicted_duration_sec": 0.0,
            "estimated_time_saved_sec": 0.0,
            "triggered_safety_rules": [],
        }

    # 3. Print Decision Summary
    print("\n" + "-" * 70)
    print("📋 DETERMINISTIC EXECUTION PLAN DECISION")
    print("-" * 70)
    print(f"Decision:               {plan['decision']}")
    print(f"Reason:                 {plan['decision_reason']}")
    print(f"Selected Tests:         {plan['selected_tests_count']} / {plan['total_tests_count']}")
    print(f"Test Suite Reduction:   {plan['tests_reduction_pct']}%")
    print(f"Predicted Failure Risk: {plan['predicted_failure_probability']:.1%}")
    print(f"Estimated Time Saved:   {plan['estimated_time_saved_sec']}s")
    if plan.get("triggered_safety_rules"):
        print(f"Triggered Safety Rules: {', '.join(plan['triggered_safety_rules'])}")
    print("-" * 70)

    # 4. Construct Command Arguments
    if plan["is_optimized"] and plan.get("selected_tests"):
        cmd = [sys.executable, "-m", "pytest", "-v"] + plan["selected_tests"]
    else:
        cmd = [sys.executable, "-m", "pytest", "tests/", "tests_sample_app/", "-v"]

    # 5. Execute Tests & Telemetry
    returncode = 1
    duration_sec = 0.0
    peak_mem = 0.0
    avg_cpu = 0.0
    try:
        returncode, duration_sec, peak_mem, avg_cpu = execute_test_command(cmd)
    except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
        print(f"❌ Execution exception during test execution: {exc}")
        returncode = 1
    finally:
        terminal_status = "SUCCESS" if returncode == 0 else "FAILED"
        if plan.get("pipeline_run_id") and httpx is not None:
            runner_token = os.getenv("RUNNER_API_KEY", "autonomous_devops_runner_dev_api_key_2026")
            headers = {"X-Runner-Token": runner_token}
            reported = False
            # 1. Primary: Record telemetry + terminal status
            try:
                telemetry_payload = {
                    "pipeline_run_id": plan["pipeline_run_id"],
                    "cpu_percent_avg": avg_cpu,
                    "memory_mb_peak": peak_mem,
                    "disk_io_mb": 0.0,
                    "runner_os": os.getenv("RUNNER_OS", "Local-Runner"),
                    "total_duration_sec": duration_sec,
                    "status": terminal_status,
                }
                res = httpx.post(
                    f"{args.api_url.rstrip('/')}/api/v1/telemetry/record",
                    json=telemetry_payload,
                    headers=headers,
                    timeout=5.0,
                )
                res.raise_for_status()
                reported = True
                print(
                    f"📡 Execution telemetry and status '{terminal_status}' reported to backend (HTTP {res.status_code})."
                )
            except (httpx.HTTPError, OSError) as e:
                print(f"⚠️  Failed to record telemetry to backend: {e}")

            # 2. Secondary fallback: Explicit run completion endpoint
            if not reported:
                try:
                    completion_payload = {
                        "status": terminal_status,
                        "total_duration_sec": duration_sec,
                        "error_message": None
                        if returncode == 0
                        else "Execution failed with non-zero exit code",
                    }
                    comp_res = httpx.post(
                        f"{args.api_url.rstrip('/')}/api/v1/plans/runs/{plan['pipeline_run_id']}/complete",
                        json=completion_payload,
                        headers=headers,
                        timeout=5.0,
                    )
                    comp_res.raise_for_status()
                    print(
                        f"📡 Terminal status '{terminal_status}' confirmed via completion endpoint (HTTP {comp_res.status_code})."
                    )
                except (httpx.HTTPError, OSError) as e:
                    print(f"⚠️  Failed to record terminal status to backend fallback: {e}")

    print("\n" + "=" * 70)
    print("📊 EXECUTION TELEMETRY & RESULTS")
    print("=" * 70)
    print(f"Status:       {'✅ PASSED' if returncode == 0 else '❌ FAILED'}")
    print(f"Duration:     {duration_sec}s")
    print(f"Peak Memory:  {peak_mem} MB")
    print(f"Average CPU:  {avg_cpu}%")
    print("=" * 70)

    sys.exit(returncode)


if __name__ == "__main__":
    main()
