"""
Model Registry & Lifecycle Manager.
Handles model artifact persistence, versioning, minimum training sample validation,
provenance metadata tracking, and synthetic historical bootstrap data generation.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import joblib
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.ml.failure_predictor import FailurePredictor
from app.ml.runtime_predictor import RuntimePredictor


@dataclass
class VerifiedTelemetryDataset:
    """
    Verified telemetry dataset extracted directly from database entities.
    Establishes an immutable provenance record ensuring genuine provenance
    cannot be asserted merely by caller-supplied flags or synthetic numpy arrays.
    """

    X: np.ndarray
    y_fail: np.ndarray
    y_time: np.ndarray
    run_ids: list[Any]
    genuine_runs_count: int
    provenance_hash: str
    extracted_at: str

    def __iter__(self):
        return iter((self.X, self.y_fail, self.y_time))

    def __len__(self):
        return len(self.X)

    def __getitem__(self, index):
        return (self.X, self.y_fail, self.y_time)[index]


class ModelManager:
    """
    Central manager for training, serializing, loading, and validating ML models.
    Enforces Safety Rule 17: Validates that minimum genuine historical samples (>= 15) are satisfied.
    Maintains rigorous provenance separation between synthetic bootstrap samples and genuine telemetry.
    """

    def __init__(self, registry_dir: str | None = None):
        self.registry_dir = os.path.abspath(registry_dir or settings.MODEL_REGISTRY_PATH)
        os.makedirs(self.registry_dir, exist_ok=True)

        self.failure_predictor = FailurePredictor()
        self.runtime_predictor = RuntimePredictor()
        self.metadata_path = os.path.join(self.registry_dir, "model_metadata.json")

    @staticmethod
    def _compute_file_sha256(path: str) -> str:
        """Computes SHA-256 checksum of a file for artifact integrity validation."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def extract_features_from_db_runs(self, runs: list[Any]) -> VerifiedTelemetryDataset:
        """
        Extracts genuine pre-execution feature vectors and execution targets from historical database records.
        Eliminates training-data leakage and undocumented fabricated defaults:
        1. NEVER incorporates post-execution fields like 'fallback_triggered' or 'error_message' into input features.
        2. NEVER uses the current run's 'total_duration_sec' as its own previous duration feature.
        3. Preceding duration and failure rate are calculated strictly from chronologically antecedent runs.
        4. Excludes runs where antecedent history cannot be derived (e.g. the first run i=0 without prior runs)
           or where required pre-execution features (commit, changed_files) are completely unavailable.
        5. Validates that labels use actual completed outcomes (SUCCESS/FAILED with duration > 0).
        6. Missing pre-execution features use documented explicit fallbacks or trigger exclusion:
           - Missing commit entity: record excluded because pre-execution context cannot be verified.
           - Commit without changed_files: file diff counts explicitly set to 0.0 (no recorded file modifications).
           - Missing execution plan: selected_tests_count defaults to actual test_results count if present,
             or explicit documented safe baseline 1.0 (minimum single test execution).
           - Target duration: strictly requires genuine completed total_duration_sec > 0.0 (never fabricated).
        Returns:
            VerifiedTelemetryDataset: verified container with X, y_fail, y_time, run_ids, provenance_hash.
        """
        # Filter for valid completed runs
        valid_runs = []
        for r in runs:
            status_val = getattr(r, "status", None)
            dur = float(getattr(r, "total_duration_sec", 0.0) or 0.0)
            if status_val in ["SUCCESS", "FAILED"] and dur > 0.0:
                valid_runs.append(r)

        # Sort chronologically by created_at if available
        def _get_sort_key(item: Any) -> float:
            created = getattr(item, "created_at", None)
            if created and hasattr(created, "timestamp"):
                return float(created.timestamp())
            return 0.0

        valid_runs.sort(key=_get_sort_key)

        X_list = []
        y_fail = []
        y_time = []
        extracted_run_ids = []

        for i, r in enumerate(valid_runs):
            feat_vec = None

            # 1. First preference: Check if pre-execution features were logged at plan-generation time
            preds = getattr(r, "predictions", None)
            pred = preds[0] if preds and len(preds) > 0 else getattr(r, "prediction", None)
            if pred and getattr(pred, "features_json", None):
                try:
                    f = json.loads(pred.features_json)
                    if isinstance(f, dict):
                        hist_rate = f.get("historical_failure_rate")
                        prev_dur = f.get("previous_execution_duration")
                        # Validate that all required pre-execution fields are present and not None
                        req_keys = [
                            "changed_files_count",
                            "lines_added",
                            "lines_deleted",
                            "total_lines_changed",
                            "affected_modules_count",
                            "selected_tests_count",
                            "is_sensitive_change",
                            "has_test_file_changes",
                        ]
                        if (
                            all(k in f and f[k] is not None for k in req_keys)
                            and hist_rate is not None
                            and prev_dur is not None
                            and float(prev_dur) > 0.0
                        ):
                            feat_vec = [
                                float(f["changed_files_count"]),
                                float(f["lines_added"]),
                                float(f["lines_deleted"]),
                                float(f["total_lines_changed"]),
                                float(f["affected_modules_count"]),
                                float(f["selected_tests_count"]),
                                float(1.0 if f["is_sensitive_change"] else 0.0),
                                float(1.0 if f["has_test_file_changes"] else 0.0),
                                float(hist_rate),
                                float(prev_dur),
                            ]
                except (json.JSONDecodeError, TypeError, KeyError):
                    feat_vec = None

            # 2. Second preference: Reconstruct strictly from pre-execution commit/file entities
            if feat_vec is None:
                # If there are no antecedent runs (i == 0), preceding duration and failure rate
                # cannot be derived without fabricating defaults. Exclude this record!
                if i == 0:
                    continue

                commit = getattr(r, "commit", None)
                if commit is None:
                    # Missing commit entity: cannot verify pre-execution context; exclude record
                    continue

                changed_files = getattr(commit, "changed_files", []) or []
                n_files = float(len(changed_files))
                lines_add = float(sum(getattr(cf, "lines_added", 0) for cf in changed_files))
                lines_del = float(sum(getattr(cf, "lines_deleted", 0) for cf in changed_files))
                tot_lines = lines_add + lines_del

                # Genuine pre-execution sensitivity: inspect file paths only; NEVER fallback_triggered!
                sensitive_keywords = [
                    "alembic",
                    "migration",
                    "auth",
                    "security",
                    "token",
                    "jwt",
                    "payment",
                    "billing",
                    "crypto",
                    "requirements",
                    "lock",
                    "workflow",
                ]
                is_sens = (
                    1.0
                    if any(
                        getattr(cf, "is_sensitive", False)
                        or any(
                            kw in getattr(cf, "file_path", "").lower() for kw in sensitive_keywords
                        )
                        for cf in changed_files
                    )
                    else 0.0
                )
                has_tests = (
                    1.0
                    if any("test" in getattr(cf, "file_path", "").lower() for cf in changed_files)
                    else 0.0
                )

                # Test selection count: read from execution plan, test results, or explicit safe fallback (1.0)
                plan = getattr(r, "execution_plan", None)
                sel_tests = float(getattr(plan, "selected_tests_count", 0) or 0)
                if sel_tests <= 0.0:
                    test_results = getattr(r, "test_results", []) or []
                    if test_results:
                        sel_tests = float(len(test_results))
                    else:
                        sel_tests = 1.0  # Documented explicit safe fallback: minimum baseline test execution

                # Preceding execution history: strictly from runs PRIOR to run i
                prior_runs = valid_runs[:i]
                prior_fails = sum(1 for p in prior_runs if getattr(p, "status", "") == "FAILED")
                hist_fail_rate = round(prior_fails / len(prior_runs), 4)

                valid_priors = [
                    p
                    for p in prior_runs
                    if float(getattr(p, "total_duration_sec", 0.0) or 0.0) > 0.0
                ]
                if not valid_priors:
                    continue  # Exclude: no prior run with valid duration
                prev_dur = float(valid_priors[-1].total_duration_sec)

                affected_mods = (
                    max(
                        1.0,
                        float(
                            len(
                                {
                                    getattr(cf, "file_path", "").split("/")[0]
                                    for cf in changed_files
                                    if getattr(cf, "file_path", "")
                                }
                            )
                        ),
                    )
                    if changed_files
                    else 0.0
                )

                feat_vec = [
                    float(n_files),
                    float(lines_add),
                    float(lines_del),
                    float(tot_lines),
                    float(affected_mods),
                    float(sel_tests),
                    float(is_sens),
                    float(has_tests),
                    float(hist_fail_rate),
                    float(prev_dur),
                ]

            X_list.append(feat_vec)

            # Target extraction: genuine completed outcome
            status_val = getattr(r, "status", "SUCCESS")
            failed = 1 if status_val == "FAILED" else 0
            y_fail.append(failed)

            dur = float(r.total_duration_sec)
            y_time.append(round(dur, 2))
            extracted_run_ids.append(getattr(r, "id", f"run-{i}"))

        X_arr = np.array(X_list, dtype=np.float64)
        y_fail_arr = np.array(y_fail, dtype=np.int32)
        y_time_arr = np.array(y_time, dtype=np.float64)

        hasher = hashlib.sha256()
        hasher.update(str(extracted_run_ids).encode("utf-8"))
        hasher.update(str(len(X_list)).encode("utf-8"))
        provenance_hash = hasher.hexdigest()

        return VerifiedTelemetryDataset(
            X=X_arr,
            y_fail=y_fail_arr,
            y_time=y_time_arr,
            run_ids=extracted_run_ids,
            genuine_runs_count=len(valid_runs),
            provenance_hash=provenance_hash,
            extracted_at=datetime.now(UTC).isoformat(),
        )

    def generate_synthetic_historical_data(
        self, n_samples: int = 50
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generates realistic synthetic pipeline history for model bootstrap & testing.
        Returns:
            X: features array (N, 10)
            y_fail: binary failure outcomes (N,)
            y_time: continuous runtime durations in seconds (N,)
        """
        np.random.seed(42)
        X_list = []
        y_fail = []
        y_time = []

        for _ in range(n_samples):
            changed_files = int(np.random.poisson(3) + 1)
            lines_add = int(np.random.exponential(40) + 5)
            lines_del = int(np.random.exponential(15) + 2)
            tot_lines = lines_add + lines_del
            affected_mods = int(np.random.poisson(2) + 1)
            selected_tests = int(np.random.randint(5, 35))
            is_sensitive = 1 if np.random.rand() < 0.15 else 0
            has_tests = 1 if np.random.rand() < 0.50 else 0
            hist_fail_rate = float(np.random.uniform(0.02, 0.20))
            prev_dur = float(np.random.uniform(5.0, 60.0))

            feature_vec = [
                changed_files,
                lines_add,
                lines_del,
                tot_lines,
                affected_mods,
                selected_tests,
                is_sensitive,
                has_tests,
                hist_fail_rate,
                prev_dur,
            ]
            X_list.append(feature_vec)

            # Failure logic: sensitive changes + large edits have higher failure probability
            fail_prob = (
                0.05
                + (0.35 if is_sensitive else 0.0)
                + (0.25 if tot_lines > 150 else 0.0)
                + hist_fail_rate
            )
            failed = 1 if np.random.rand() < fail_prob else 0
            y_fail.append(failed)

            # Runtime logic: base time + time per test + line diff penalty
            dur = max(
                2.0,
                3.0 + (selected_tests * 0.4) + (tot_lines * 0.02) + np.random.normal(0, 1.0),
            )
            y_time.append(round(dur, 2))

        return (
            np.array(X_list, dtype=np.float64),
            np.array(y_fail, dtype=np.int32),
            np.array(y_time, dtype=np.float64),
        )

    @staticmethod
    def evaluate_model_certification(
        fail_metrics: dict[str, Any],
        time_metrics: dict[str, Any],
        sample_count: int,
        genuine_historical_runs_count: int,
    ) -> tuple[bool, dict[str, Any], list[str]]:
        """
        Evaluates explicit model certification criteria based on valid holdout evaluation
        and documented minimum evidence. Models are NEVER marked production ready solely
        because 15 records exist.

        Certification criteria:
        1. Minimum evidence: sample_count >= MIN_TRAINING_RUNS and genuine_historical_runs_count >= MIN_TRAINING_RUNS.
        2. Valid holdout evaluation: both predictors evaluated on 'HOLDOUT_TEST_SPLIT' with >= 3 test samples.
        3. Failure discrimination capability:
           - Both classes present in dataset (at least 1 pass and 1 fail observed).
           - Holdout failure recall >= 0.50 or F1 >= 0.50 when failures occur in test set.
           - ROC-AUC >= 0.50 when defined.
        4. Runtime prediction accuracy:
           - R2 score >= 0.0 (better than or equal to predicting the mean).
           - MAE <= 60.0 seconds.
        """
        min_runs = settings.MIN_TRAINING_RUNS
        failure_reasons = []
        criteria = {}

        # 1. Minimum evidence
        criteria["min_samples_met"] = bool(sample_count >= min_runs)
        if not criteria["min_samples_met"]:
            failure_reasons.append(
                f"Sample count ({sample_count}) is less than required minimum ({min_runs})"
            )

        criteria["genuine_runs_met"] = bool(genuine_historical_runs_count >= min_runs)
        if not criteria["genuine_runs_met"]:
            failure_reasons.append(
                f"Genuine historical runs ({genuine_historical_runs_count}) < {min_runs}"
            )

        # 2. Holdout evaluation
        fail_eval = fail_metrics.get("evaluated_on")
        time_eval = time_metrics.get("evaluated_on")
        test_samples = fail_metrics.get("test_samples", 0)
        criteria["holdout_evaluation_valid"] = bool(
            fail_eval == "HOLDOUT_TEST_SPLIT"
            and time_eval == "HOLDOUT_TEST_SPLIT"
            and test_samples >= 3
        )
        if not criteria["holdout_evaluation_valid"]:
            failure_reasons.append(
                f"Evaluation not performed on valid holdout test split (test_samples={test_samples}, eval={fail_eval})"
            )

        # 3. Failure discrimination capability
        class_dist = fail_metrics.get("class_distribution", {})
        ds_pass = class_dist.get("dataset_pass_count", 0)
        ds_fail = class_dist.get("dataset_fail_count", 0)
        criteria["both_classes_observed"] = bool(ds_pass > 0 and ds_fail > 0)
        if not criteria["both_classes_observed"]:
            failure_reasons.append(
                f"Dataset lacks class diversity (pass={ds_pass}, fail={ds_fail}). Model cannot discriminate failure risk without observing both outcomes."
            )

        test_fail = class_dist.get("test_fail_count", 0)
        rec = fail_metrics.get("recall", 0.0)
        f1 = fail_metrics.get("f1_score", 0.0)
        auc = fail_metrics.get("roc_auc")

        if test_fail > 0:
            criteria["failure_recall_acceptable"] = bool(rec >= 0.50 or f1 >= 0.50)
            if not criteria["failure_recall_acceptable"]:
                failure_reasons.append(
                    f"Holdout failure recall ({rec}) and F1 ({f1}) below acceptable certification threshold (0.50)"
                )
        else:
            criteria["failure_recall_acceptable"] = True

        if auc is not None:
            criteria["roc_auc_acceptable"] = bool(auc >= 0.50)
            if not criteria["roc_auc_acceptable"]:
                failure_reasons.append(f"ROC-AUC ({auc}) is below random baseline (0.50)")
        else:
            criteria["roc_auc_acceptable"] = True

        # 4. Runtime estimation accuracy
        r2 = time_metrics.get("r2_score", -999.0)
        mae = time_metrics.get("mae", 999.0)
        criteria["runtime_r2_acceptable"] = bool(r2 >= 0.0)
        if not criteria["runtime_r2_acceptable"]:
            failure_reasons.append(
                f"Runtime model R2 score ({r2}) is negative (worse than mean baseline)"
            )

        criteria["runtime_mae_acceptable"] = bool(mae <= 60.0)
        if not criteria["runtime_mae_acceptable"]:
            failure_reasons.append(f"Runtime model MAE ({mae}s) exceeds maximum allowed (60.0s)")

        is_certified = len(failure_reasons) == 0
        return is_certified, criteria, failure_reasons

    def train_and_persist(
        self,
        n_samples: int = 50,
        data_source: str = "SYNTHETIC_BOOTSTRAP",
        genuine_historical_runs_count: int = 0,
        training_data: tuple[np.ndarray, np.ndarray, np.ndarray]
        | VerifiedTelemetryDataset
        | None = None,
        is_production_ready: bool | None = None,
        verified_db_source: bool = False,
    ) -> dict[str, Any]:
        """
        Trains both models on provided or generated samples and persists artifacts with provenance metadata and SHA-256 integrity hashes.
        Explicitly tracks whether training used synthetic bootstrap data or verified genuine telemetry.
        Enforces strict trust boundaries around verified_db_source and explicit certification criteria.
        """
        if data_source == "GENUINE_PIPELINE_TELEMETRY":
            if not verified_db_source:
                raise ValueError(
                    "Cannot train models with provenance GENUINE_PIPELINE_TELEMETRY without verified database source (verified_db_source=False)."
                )
            if training_data is None:
                raise ValueError(
                    "GENUINE_PIPELINE_TELEMETRY requires verified training_data extracted from database records."
                )
            if not isinstance(training_data, VerifiedTelemetryDataset):
                raise ValueError(
                    "Trust boundary violation: genuine pipeline telemetry cannot be asserted by caller-supplied arrays or metadata. "
                    "training_data must be a VerifiedTelemetryDataset extracted directly from database entities via extract_features_from_db_runs()."
                )
            if genuine_historical_runs_count < settings.MIN_TRAINING_RUNS:
                raise ValueError(
                    f"Genuine historical runs ({genuine_historical_runs_count}) is less than required minimum ({settings.MIN_TRAINING_RUNS})."
                )
            if len(training_data) < settings.MIN_TRAINING_RUNS:
                raise ValueError(
                    f"Training dataset size ({len(training_data)}) is less than required minimum ({settings.MIN_TRAINING_RUNS})."
                )
            X, y_fail, y_time = training_data.X, training_data.y_fail, training_data.y_time
            telemetry_provenance_hash = training_data.provenance_hash
        elif data_source == "SYNTHETIC_BOOTSTRAP":
            genuine_historical_runs_count = 0
            telemetry_provenance_hash = None
            if training_data is not None:
                X, y_fail, y_time = training_data
            else:
                if n_samples < settings.MIN_TRAINING_RUNS:
                    raise ValueError(
                        f"Cannot train models: {n_samples} samples is less than the required minimum of {settings.MIN_TRAINING_RUNS}"
                    )
                X, y_fail, y_time = self.generate_synthetic_historical_data(n_samples)
        else:
            raise ValueError(
                f"Unknown data_source '{data_source}'. Must be 'SYNTHETIC_BOOTSTRAP' or 'GENUINE_PIPELINE_TELEMETRY'."
            )

        fail_metrics = self.failure_predictor.train(X, y_fail)
        time_metrics = self.runtime_predictor.train(X, y_time)

        # Certification evaluation: explicit model certification based on holdout evaluation
        if data_source == "GENUINE_PIPELINE_TELEMETRY":
            is_certified, cert_criteria, failure_reasons = self.evaluate_model_certification(
                fail_metrics=fail_metrics,
                time_metrics=time_metrics,
                sample_count=len(X),
                genuine_historical_runs_count=genuine_historical_runs_count,
            )
            # If caller explicitly set is_production_ready=False, respect False; otherwise require certification
            if is_production_ready is False:
                is_prod_ready = False
            else:
                is_prod_ready = is_certified

            cert_report = {
                "is_certified": is_certified,
                "criteria": cert_criteria,
                "failure_reasons": failure_reasons,
                "evaluated_at": datetime.now(UTC).isoformat(),
            }
        else:
            is_prod_ready = False
            cert_report = {
                "is_certified": False,
                "criteria": {},
                "failure_reasons": [
                    "Synthetic bootstrap models are never certified for production"
                ],
                "evaluated_at": datetime.now(UTC).isoformat(),
            }

        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        joblib.dump(self.failure_predictor, fail_path)
        joblib.dump(self.runtime_predictor, time_path)

        fail_sha256 = self._compute_file_sha256(fail_path)
        time_sha256 = self._compute_file_sha256(time_path)

        metadata = {
            "provenance": data_source,
            "sample_count": len(X),
            "genuine_historical_runs_count": genuine_historical_runs_count,
            "is_production_ready": is_prod_ready,
            "telemetry_provenance_hash": telemetry_provenance_hash,
            "certification_report": cert_report,
            "trained_at": datetime.now(UTC).isoformat(),
            "artifact_hashes": {
                "failure_predictor_sha256": fail_sha256,
                "runtime_predictor_sha256": time_sha256,
            },
            "failure_metrics": fail_metrics,
            "runtime_metrics": time_metrics,
            "model_version": self.failure_predictor.model_version,
            "evaluation_notes": {
                "sample_size_limitation": "Small datasets (< 100 samples) exhibit higher variance.",
                "holdout_split_ratio": 0.20 if len(X) >= 15 else 0.0,
            },
        }

        try:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except OSError as e:
            logger.warning(f"Could not persist model metadata to {self.metadata_path}: {e}")

        logger.info(
            f"Successfully trained models ({data_source}) and saved artifacts to {self.registry_dir}"
        )

        return {
            "status": "TRAINED_AND_SAVED",
            "provenance": data_source,
            "samples": len(X),
            "is_production_ready": is_prod_ready,
            "certification_report": cert_report,
            "failure_metrics": fail_metrics,
            "runtime_metrics": time_metrics,
            "artifact_hashes": metadata["artifact_hashes"],
            "artifact_paths": {
                "failure_model": fail_path,
                "runtime_model": time_path,
                "metadata": self.metadata_path,
            },
        }

    def can_predict(self, genuine_historical_runs_count: int) -> tuple[bool, str]:
        """
        Validates whether models are authorized to produce optimization predictions.
        Enforces strict model provenance, SHA-256 artifact integrity, certification, and Safety Rules 14 & 17:
        1. Both failure and runtime predictors must be loaded in memory and trained.
        2. Model metadata file (model_metadata.json) must exist and be valid JSON.
        3. Metadata 'provenance' must be exactly 'GENUINE_PIPELINE_TELEMETRY'.
        4. Metadata 'is_production_ready' must be True.
        5. Metadata 'sample_count' and 'genuine_historical_runs_count' must be >= settings.MIN_TRAINING_RUNS.
        6. Metadata 'artifact_hashes' must match current SHA-256 digests of on-disk joblib files.
        7. Server-verified genuine historical runs must be >= settings.MIN_TRAINING_RUNS.
        Synthetic bootstrap models, corrupted/missing metadata, or mismatched artifacts must NEVER authorize test skipping.
        """
        min_runs = settings.MIN_TRAINING_RUNS

        # 1. Require in-memory models to be loaded and trained
        if not self.failure_predictor.is_trained or not self.runtime_predictor.is_trained:
            return (
                False,
                "Safety Rule 14: Predictive ML models are not trained or artifacts are missing.",
            )

        # 2. Check metadata file exists
        if not os.path.exists(self.metadata_path):
            return (
                False,
                "Safety Rule 14: Model metadata file is missing. Untrained or unverified models cannot authorize optimization.",
            )

        # 3. Read and parse metadata
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return (
                False,
                f"Safety Rule 14: Model metadata is corrupt or unreadable ({e}). Full suite fallback enforced.",
            )

        if not isinstance(metadata, dict):
            return (
                False,
                "Safety Rule 14: Model metadata is malformed. Full suite fallback enforced.",
            )

        provenance = metadata.get("provenance")
        is_prod_ready = metadata.get("is_production_ready")
        meta_sample_count = metadata.get("sample_count", 0)
        meta_genuine_runs = metadata.get("genuine_historical_runs_count", 0)
        artifact_hashes = metadata.get("artifact_hashes")

        # 4. Require provenance == GENUINE_PIPELINE_TELEMETRY
        if provenance != "GENUINE_PIPELINE_TELEMETRY":
            return (
                False,
                f"Safety Rule 14: Model provenance is '{provenance}', not 'GENUINE_PIPELINE_TELEMETRY'. Synthetic bootstrap models cannot authorize test skipping.",
            )

        # 5. Require is_production_ready == True
        if is_prod_ready is not True:
            cert_reasons = metadata.get("certification_report", {}).get("failure_reasons", [])
            reasons_str = f" Reason(s): {'; '.join(cert_reasons)}" if cert_reasons else ""
            return (
                False,
                f"Safety Rule 14: Model is not certified production ready (is_production_ready is false).{reasons_str} Full suite fallback enforced.",
            )

        # 6. Require metadata sample count and genuine runs >= min_runs
        if not isinstance(meta_sample_count, (int, float)) or meta_sample_count < min_runs:
            return (
                False,
                f"Safety Rule 17: Model metadata sample count ({meta_sample_count}) < minimum required ({min_runs}). Full suite fallback enforced.",
            )

        if not isinstance(meta_genuine_runs, (int, float)) or meta_genuine_runs < min_runs:
            return (
                False,
                f"Safety Rule 17: Model metadata genuine historical runs ({meta_genuine_runs}) < minimum required ({min_runs}). Full suite fallback enforced.",
            )

        # 7. Require artifact_hashes to exist and match on-disk files
        if not isinstance(artifact_hashes, dict):
            return (
                False,
                "Safety Rule 14: Model metadata is missing artifact integrity hashes. Full suite fallback enforced.",
            )
        expected_fail_sha = artifact_hashes.get("failure_predictor_sha256")
        expected_time_sha = artifact_hashes.get("runtime_predictor_sha256")
        if not expected_fail_sha or not expected_time_sha:
            return (
                False,
                "Safety Rule 14: Model metadata artifact integrity hashes are incomplete. Full suite fallback enforced.",
            )

        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")
        if not os.path.exists(fail_path) or not os.path.exists(time_path):
            return (
                False,
                "Safety Rule 14: Predictive ML models are not trained or artifacts are missing.",
            )

        try:
            actual_fail_sha = self._compute_file_sha256(fail_path)
            actual_time_sha = self._compute_file_sha256(time_path)
        except OSError as e:
            return (
                False,
                f"Safety Rule 14: Could not read model artifacts for checksum verification ({e}). Full suite fallback enforced.",
            )

        if actual_fail_sha != expected_fail_sha or actual_time_sha != expected_time_sha:
            return (
                False,
                "Safety Rule 14: Model artifact SHA-256 integrity verification failed (mismatched artifact). Full suite fallback enforced.",
            )

        # 8. Require server-verified genuine historical runs in DB >= min_runs
        if genuine_historical_runs_count < min_runs:
            return (
                False,
                (
                    f"Safety Rule 17: Genuine historical pipeline runs ({genuine_historical_runs_count}) "
                    f"is less than required minimum ({min_runs}). Full suite fallback enforced."
                ),
            )

        return True, "Models validated and ready for inference."

    def load_models(self) -> bool:
        """Loads model artifacts from disk if available."""
        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        if os.path.exists(fail_path) and os.path.exists(time_path):
            try:
                self.failure_predictor = joblib.load(fail_path)
                self.runtime_predictor = joblib.load(time_path)
                return True
            except (OSError, EOFError, ValueError, KeyError, AttributeError) as e:
                logger.error(f"Failed to load ML artifacts from {self.registry_dir}: {e}")
                return False
        return False

    def get_models_status(self) -> dict[str, Any]:
        """Returns readiness, provenance, and artifact presence for predictive models."""
        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        provenance_info: dict[str, Any] = {
            "provenance": "SYNTHETIC_BOOTSTRAP",
            "genuine_historical_runs_count": 0,
            "is_production_ready": False,
        }
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path) as f:
                    provenance_info = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        return {
            "failure_predictor": {
                "is_trained": self.failure_predictor.is_trained,
                "version": self.failure_predictor.model_version,
                "model_file_exists": os.path.exists(fail_path),
                "artifact_path": fail_path,
            },
            "runtime_predictor": {
                "is_trained": self.runtime_predictor.is_trained,
                "version": self.runtime_predictor.model_version,
                "model_file_exists": os.path.exists(time_path),
                "artifact_path": time_path,
            },
            "provenance_metadata": provenance_info,
        }
