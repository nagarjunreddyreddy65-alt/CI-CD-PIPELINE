"""
Baseline CI/CD Benchmarking Script.
Runs the complete test suite, measures execution duration, collects telemetry,
and outputs performance baselines for ML evaluation.
"""

import json
import os
import subprocess
import sys
import time

import psutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_baseline_benchmark():
    print("=" * 70)
    print("🚀 Running Baseline CI/CD Test Suite Benchmark...")
    print("=" * 70)

    start_cpu = psutil.cpu_percent(interval=0.5)
    _start_memory = psutil.virtual_memory().used / (1024 * 1024)
    start_time = time.perf_counter()

    # Execute full pytest suite
    cmd = [sys.executable, "-m", "pytest", "tests/", "tests_sample_app/", "-v"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    end_time = time.perf_counter()
    duration_sec = round(end_time - start_time, 3)
    end_cpu = psutil.cpu_percent(interval=0.5)
    end_memory = psutil.virtual_memory().used / (1024 * 1024)

    print(result.stdout)

    benchmark_data = {
        "benchmark_type": "FULL_SUITE_BASELINE",
        "total_duration_sec": duration_sec,
        "exit_code": result.returncode,
        "cpu_start_pct": start_cpu,
        "cpu_end_pct": end_cpu,
        "memory_used_mb": round(end_memory, 2),
        "status": "PASSED" if result.returncode == 0 else "FAILED",
    }

    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", "baseline_run.json")
    with open(out_path, "w") as f:
        json.dump(benchmark_data, f, indent=2)

    print("=" * 70)
    print(f"✅ Baseline Run Completed in {duration_sec}s (Status: {benchmark_data['status']})")
    print(f"📊 Metrics written to {out_path}")
    print("=" * 70)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_baseline_benchmark())
