"""
Statistical Anomaly Detection Engine.
Uses deterministic statistical baselines (Mean, Standard Deviation, Z-Scores) to detect:
1. Unexpected execution-time increases.
2. Unusual memory/CPU resource spikes.
3. Sudden surges in pipeline failure rates.
4. Abnormal test-duration changes.

Strictly avoids complex deep-learning anomaly models in favor of transparent, explainable statistics.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import numpy as np


class AnomalyType(str, Enum):
    EXECUTION_TIME_SPIKE = "EXECUTION_TIME_SPIKE"
    MEMORY_SURGE = "MEMORY_SURGE"
    CPU_SURGE = "CPU_SURGE"
    FAILURE_RATE_SURGE = "FAILURE_RATE_SURGE"
    TEST_DURATION_SURGE = "TEST_DURATION_SURGE"


class AnomalySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class AnomalyFinding:
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    metric_name: str
    observed_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    message: str


@dataclass
class AnomalyReport:
    is_anomalous: bool
    anomalies: List[AnomalyFinding]
    samples_count: int
    summary: str
    recommendation: str


class StatisticalAnomalyDetector:
    """
    Evaluates observed pipeline runs against historical statistical baselines.
    """

    def __init__(
        self,
        z_threshold: float = 2.5,
        min_historical_samples: int = 5,
    ):
        self.z_threshold = z_threshold
        self.min_samples = min_historical_samples

    def detect_anomalies(
        self,
        current_run: Dict[str, float],
        historical_runs: List[Dict[str, float]],
    ) -> AnomalyReport:
        """
        Analyzes current_run metrics against historical_runs.
        Metrics evaluated:
        - duration_sec
        - memory_mb_peak
        - cpu_percent_avg
        - failure_rate
        """
        anomalies: List[AnomalyFinding] = []
        n_samples = len(historical_runs)

        if n_samples < self.min_samples:
            return AnomalyReport(
                is_anomalous=False,
                anomalies=[],
                samples_count=n_samples,
                summary=f"Insufficient historical samples ({n_samples} < {self.min_samples}) for anomaly detection.",
                recommendation="Continue collecting pipeline execution history.",
            )

        # 1. Execution Duration Anomaly
        hist_durations = [r.get("duration_sec", 0.0) for r in historical_runs if "duration_sec" in r]
        if hist_durations:
            curr_dur = current_run.get("duration_sec", 0.0)
            finding = self._check_z_score(
                metric_name="duration_sec",
                observed=curr_dur,
                history=hist_durations,
                anomaly_type=AnomalyType.EXECUTION_TIME_SPIKE,
                label="Pipeline Execution Duration",
                unit="s",
            )
            if finding:
                anomalies.append(finding)

        # 2. Peak Memory Usage Anomaly
        hist_mem = [r.get("memory_mb_peak", 0.0) for r in historical_runs if "memory_mb_peak" in r]
        if hist_mem:
            curr_mem = current_run.get("memory_mb_peak", 0.0)
            finding = self._check_z_score(
                metric_name="memory_mb_peak",
                observed=curr_mem,
                history=hist_mem,
                anomaly_type=AnomalyType.MEMORY_SURGE,
                label="Peak Memory Consumption",
                unit="MB",
            )
            if finding:
                anomalies.append(finding)

        # 3. Average CPU Usage Anomaly
        hist_cpu = [r.get("cpu_percent_avg", 0.0) for r in historical_runs if "cpu_percent_avg" in r]
        if hist_cpu:
            curr_cpu = current_run.get("cpu_percent_avg", 0.0)
            finding = self._check_z_score(
                metric_name="cpu_percent_avg",
                observed=curr_cpu,
                history=hist_cpu,
                anomaly_type=AnomalyType.CPU_SURGE,
                label="Average CPU Utilization",
                unit="%",
            )
            if finding:
                anomalies.append(finding)

        # 4. Failure Rate Surge Check
        hist_fails = [r.get("failure_rate", 0.0) for r in historical_runs if "failure_rate" in r]
        if hist_fails:
            curr_fail = current_run.get("failure_rate", 0.0)
            avg_fail = float(np.mean(hist_fails))
            # Surge if failure rate jumped significantly above baseline
            if curr_fail > (avg_fail + 0.35) and curr_fail >= 0.50:
                anomalies.append(AnomalyFinding(
                    anomaly_type=AnomalyType.FAILURE_RATE_SURGE,
                    severity=AnomalySeverity.HIGH,
                    metric_name="failure_rate",
                    observed_value=curr_fail,
                    baseline_mean=round(avg_fail, 3),
                    baseline_std=0.0,
                    z_score=round((curr_fail - avg_fail) * 10, 2),
                    message=f"Sudden failure rate surge: observed {curr_fail:.1%} vs historical average {avg_fail:.1%}.",
                ))

        is_anomalous = len(anomalies) > 0
        summary = (
            f"Detected {len(anomalies)} statistical anomalies across {n_samples} historical runs."
            if is_anomalous else
            f"All metrics are within normal statistical tolerances (baseline sample size: {n_samples})."
        )
        recommendation = (
            "Inspect runner host resources and verify recent code changes for performance regressions."
            if is_anomalous else
            "Pipeline telemetry healthy."
        )

        return AnomalyReport(
            is_anomalous=is_anomalous,
            anomalies=anomalies,
            samples_count=n_samples,
            summary=summary,
            recommendation=recommendation,
        )

    def _check_z_score(
        self,
        metric_name: str,
        observed: float,
        history: List[float],
        anomaly_type: AnomalyType,
        label: str,
        unit: str,
    ) -> Optional[AnomalyFinding]:
        """Calculates Z-score and flags if above threshold."""
        arr = np.array(history, dtype=np.float64)
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr))

        # If zero variance in baseline, use percentage increase
        if std_val < 1e-4:
            if observed > mean_val * 2.0 and observed > 5.0:
                return AnomalyFinding(
                    anomaly_type=anomaly_type,
                    severity=AnomalySeverity.MEDIUM,
                    metric_name=metric_name,
                    observed_value=round(observed, 2),
                    baseline_mean=round(mean_val, 2),
                    baseline_std=0.0,
                    z_score=3.0,
                    message=f"{label} spiked: observed {observed}{unit} vs baseline {mean_val:.2f}{unit}.",
                )
            return None

        z = (observed - mean_val) / std_val

        if z >= self.z_threshold:
            sev = AnomalySeverity.HIGH if z >= (self.z_threshold * 1.5) else AnomalySeverity.MEDIUM
            return AnomalyFinding(
                anomaly_type=anomaly_type,
                severity=sev,
                metric_name=metric_name,
                observed_value=round(observed, 2),
                baseline_mean=round(mean_val, 2),
                baseline_std=round(std_val, 2),
                z_score=round(z, 2),
                message=f"{label} anomaly detected: Z-Score {z:.2f} >= threshold {self.z_threshold:.2f} ({observed}{unit} vs baseline {mean_val:.2f}{unit}).",
            )

        return None
