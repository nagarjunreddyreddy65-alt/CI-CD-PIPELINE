"""Pipeline analytics, throughput, and performance metrics."""

from typing import List, Dict, Any
from sample_app.utils.math_ops import compute_average, compute_standard_deviation


def calculate_pipeline_throughput(completed_runs: int, time_window_hours: float) -> float:
    """Calculates pipelines completed per hour."""
    if time_window_hours <= 0:
        return 0.0
    return round(completed_runs / time_window_hours, 2)


def calculate_percentiles(durations: List[float]) -> Dict[str, float]:
    """Computes p50, p90, and p95 latency/duration percentiles."""
    if not durations:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0}

    sorted_vals = sorted(durations)
    n = len(sorted_vals)

    def get_percentile(p: float) -> float:
        idx = int(math_ceil(p * n)) - 1
        return sorted_vals[max(0, min(idx, n - 1))]

    from math import ceil as math_ceil
    return {
        "p50": round(get_percentile(0.50), 2),
        "p90": round(get_percentile(0.90), 2),
        "p95": round(get_percentile(0.95), 2),
    }


def analyze_test_run_stability(historical_durations: List[float]) -> Dict[str, Any]:
    """Calculates mean, std-dev, and stability score (lower coefficient of variation = more stable)."""
    mean = compute_average(historical_durations)
    std = compute_standard_deviation(historical_durations)
    cv = (std / mean) if mean > 0 else 0.0

    return {
        "mean_duration": round(mean, 2),
        "std_duration": round(std, 2),
        "coefficient_of_variation": round(cv, 4),
        "is_stable": cv < 0.25,
    }
