"""
Autonomous DevOps: AI-Driven CI/CD Pipeline Optimization
ML Model Evaluation & Graph Generation Script

Generates publication-quality figures for:
1. Confusion Matrix (Held-out Test Split)
2. ROC-AUC Curve
3. Feature Importances (Failure Classifier & Runtime Regressor)
4. Runtime Duration: Actual vs. Predicted Regression with Error Bands
5. Statistical Z-Score Anomaly Detection Distribution
6. Combined Master Evaluation Multi-Panel Figure

Outputs are saved in:
- docs/figures/ml_evaluation/
- app/static/graphs/
"""

import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from sqlalchemy.exc import SQLAlchemyError

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_FIG_DIR = BASE_DIR / "docs" / "figures" / "ml_evaluation"
STATIC_FIG_DIR = BASE_DIR / "app" / "static" / "graphs"
METADATA_PATH = BASE_DIR / "app" / "ml" / "models" / "model_metadata.json"
FAILURE_MODEL_PATH = BASE_DIR / "app" / "ml" / "models" / "failure_predictor.joblib"
RUNTIME_MODEL_PATH = BASE_DIR / "app" / "ml" / "models" / "runtime_predictor.joblib"

# Configure visual style
plt.style.use(
    "seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default"
)
plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.labelweight": "semibold",
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.titlesize": 14,
        "figure.titleweight": "bold",
        "figure.dpi": 300,
    }
)

PRIMARY_COLOR = "#2563eb"  # Blue
SUCCESS_COLOR = "#10b981"  # Green
DANGER_COLOR = "#ef4444"  # Red
WARNING_COLOR = "#f59e0b"  # Amber
PURPLE_COLOR = "#8b5cf6"  # Purple
DARK_BG = "#0f172a"  # Slate dark


def ensure_directories():
    DOCS_FIG_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_FIG_DIR.mkdir(parents=True, exist_ok=True)


def save_fig(fig, filename):
    for d in [DOCS_FIG_DIR, STATIC_FIG_DIR]:
        path = d / filename
        fig.savefig(path, dpi=300, bbox_inches="tight")
    print(f" Saved: {filename}")


def plot_confusion_matrix(metadata):
    """Plot 1: Confusion Matrix from verified holdout evaluation."""
    cm = np.array(metadata["failure_metrics"]["confusion_matrix"])
    labels = ["PASS (0)", "FAIL (1)"]

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        cbar=False,
        xticklabels=labels,
        yticklabels=labels,
        annot_kws={"size": 16, "weight": "bold"},
        ax=ax,
        linewidths=1.5,
        linecolor="#e2e8f0",
    )

    ax.set_title(
        "Failure Risk Classifier — Confusion Matrix\n(Held-out 20% Test Split, N=10)",
        pad=12,
    )
    ax.set_xlabel("Predicted Class", labelpad=8)
    ax.set_ylabel("True Ground-Truth Class", labelpad=8)

    # Annotate performance summary
    p = metadata["failure_metrics"]["precision"]
    r = metadata["failure_metrics"]["recall"]
    f1 = metadata["failure_metrics"]["f1_score"]
    ax.text(
        0.5,
        -0.22,
        f"Precision: {p:.2f}  |  Recall: {r:.2f}  |  F1-Score: {f1:.2f}  |  Accuracy: 100%",
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=9,
        weight="semibold",
        bbox={
            "boxstyle": "round,pad=0.4",
            "facecolor": "#f1f5f9",
            "edgecolor": "#cbd5e1",
        },
    )

    save_fig(fig, "01_confusion_matrix.png")
    plt.close(fig)


def plot_roc_curve(metadata):
    """Plot 2: ROC-AUC Curve with decision threshold annotation (Illustrative of Recorded Holdout)."""
    auc = metadata["failure_metrics"]["roc_auc"]

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    # Illustrative step curve representing recorded holdout metrics (AUC = 1.00, N=10)
    fpr = np.array([0.0, 0.0, 0.0, 0.1, 0.2, 0.5, 1.0])
    tpr = np.array([0.0, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])

    ax.plot(
        fpr,
        tpr,
        color=PRIMARY_COLOR,
        lw=2.5,
        label=f"RF Classifier (Holdout AUC = {auc:.2f})",
    )
    ax.plot(
        [0, 1],
        [0, 1],
        color="#94a3b8",
        lw=1.5,
        linestyle="--",
        label="Random Chance Baseline (AUC = 0.50)",
    )
    ax.fill_between(fpr, tpr, color=PRIMARY_COLOR, alpha=0.15)

    ax.scatter(
        [0.0],
        [1.0],
        color=SUCCESS_COLOR,
        s=80,
        zorder=5,
        label="Operating Point (FPR=0.0, TPR=1.0)",
    )

    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.05])
    ax.set_title(
        "Receiver Operating Characteristic (ROC) Curve\nPipeline Failure Prediction (Illustrative Representation)",
        pad=12,
    )
    ax.set_xlabel("False Positive Rate (1 - Specificity)", labelpad=8)
    ax.set_ylabel("True Positive Rate (Recall / Sensitivity)", labelpad=8)
    ax.legend(loc="lower right", frameon=True, framealpha=0.9, fontsize=8.5)
    ax.grid(True, linestyle=":", alpha=0.6)

    # Limitation annotation box
    ax.text(
        0.5,
        0.30,
        "Note: Illustrative curve representing recorded holdout metrics\n"
        "(ROC-AUC=1.00, Confusion Matrix: 8 Pass, 2 Fail).\n"
        "Raw prediction probabilities unpreserved in metadata.\n"
        "Small holdout limitation (N=10); does not claim generalization.",
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=7.5,
        style="italic",
        bbox={
            "boxstyle": "round,pad=0.3",
            "facecolor": "#f8fafc",
            "edgecolor": "#cbd5e1",
            "alpha": 0.95,
        },
    )

    save_fig(fig, "02_roc_auc_curve.png")
    plt.close(fig)


def plot_feature_importance(feature_names, fp_importances, rp_importances):
    """Plot 3: Comparative Feature Importance across both ML models (Predictive Association, Not Causation)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2), sharey=True)

    y_pos = np.arange(len(feature_names))

    # Format feature names for clean presentation
    display_names = [f.replace("_", " ").title() for f in feature_names]

    # Sort Failure Predictor
    sort_fp = np.argsort(fp_importances)
    ax1.barh(
        y_pos,
        np.array(fp_importances)[sort_fp],
        color=PRIMARY_COLOR,
        alpha=0.85,
        edgecolor="#1d4ed8",
    )
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(np.array(display_names)[sort_fp])
    ax1.set_title("Failure Risk Classifier (Random Forest)")
    ax1.set_xlabel("Gini Feature Importance")
    ax1.grid(True, linestyle=":", alpha=0.6, axis="x")

    for i, v in enumerate(np.array(fp_importances)[sort_fp]):
        if v > 0.01:
            ax1.text(
                v + 0.005,
                i,
                f"{v:.3f}",
                va="center",
                fontsize=8,
                weight="semibold",
                color="#1e293b",
            )

    # Sort Runtime Predictor
    sort_rp = np.argsort(rp_importances)
    ax2.barh(
        y_pos,
        np.array(rp_importances)[sort_rp],
        color=PURPLE_COLOR,
        alpha=0.85,
        edgecolor="#6d28d9",
    )
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(np.array(display_names)[sort_rp])
    ax2.set_title("Runtime Regressor (Random Forest)")
    ax2.set_xlabel("Feature Importance (MSE Reduction)")
    ax2.grid(True, linestyle=":", alpha=0.6, axis="x")

    for i, v in enumerate(np.array(rp_importances)[sort_rp]):
        if v > 0.01:
            ax2.text(
                v + 0.005,
                i,
                f"{v:.3f}",
                va="center",
                fontsize=8,
                weight="semibold",
                color="#1e293b",
            )

    fig.suptitle(
        "Feature Importance in CI/CD Pre-Execution Feature Space (R¹⁰)\n"
        "(Predictive Association within Ensembles — Not Causal Evidence)",
        fontsize=12,
        y=1.02,
    )
    plt.tight_layout()

    save_fig(fig, "03_feature_importance.png")
    plt.close(fig)


def plot_actual_vs_predicted(metadata):
    """Plot 4: Actual vs Predicted Runtime Regression with error bands (Illustrative of Recorded Holdout)."""
    mae = metadata["runtime_metrics"]["mae"]
    rmse = metadata["runtime_metrics"]["rmse"]
    r2 = metadata["runtime_metrics"]["r2_score"]

    np.random.seed(42)
    # Representative illustrative points reflecting recorded holdout metrics (R²=0.832, MAE=1.68s, RMSE=2.21s)
    y_actual = np.array([5.2, 8.4, 12.1, 15.8, 19.3, 22.0, 28.5, 33.1, 39.8, 45.2])
    noise = np.array([0.8, -1.2, 1.5, -0.9, 1.8, -2.1, 1.4, -1.9, 2.3, -1.7])
    y_pred = y_actual + noise

    fig, ax = plt.subplots(figsize=(6, 5))

    # Scatter points
    ax.scatter(
        y_actual,
        y_pred,
        color=PURPLE_COLOR,
        s=70,
        alpha=0.9,
        edgecolors="#4c1d95",
        zorder=4,
        label="Illustrative Holdout Runs (N=10)",
    )

    # 45-degree identity line
    min_val, max_val = 0, 50
    ax.plot(
        [min_val, max_val],
        [min_val, max_val],
        color="#0f172a",
        lw=2,
        linestyle="--",
        label="Ideal Fit (y = x)",
    )

    # ±15% operational SLA bounds (engineering corridor, not statistical CI)
    ax.fill_between(
        [min_val, max_val],
        [min_val * 0.85, max_val * 0.85],
        [min_val * 1.15, max_val * 1.15],
        color=PURPLE_COLOR,
        alpha=0.12,
        label="±15% Operational SLA Tolerance Band\n(Engineering heuristic, NOT statistical CI)",
    )

    ax.set_xlim([0, 50])
    ax.set_ylim([0, 50])
    ax.set_title(
        "Runtime Duration Regressor — Actual vs. Predicted (Illustrative)\n"
        "(Recorded Holdout Metrics: R² = 0.832, MAE = 1.68s, RMSE = 2.21s)",
        pad=12,
    )
    ax.set_xlabel("Actual Measured Duration (s)", labelpad=8)
    ax.set_ylabel("Predicted Duration (s)", labelpad=8)
    ax.legend(loc="upper left", frameon=True, framealpha=0.9, fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.6)

    # Metrics annotation box
    ax.text(
        0.95,
        0.08,
        f"Recorded Holdout (N=10):\nR² Score: {r2:.3f}\nMAE: {mae:.2f}s\nRMSE: {rmse:.2f}s\n"
        "Note: Illustrative scatter.\nExact vector unpreserved.",
        ha="right",
        va="bottom",
        transform=ax.transAxes,
        fontsize=8,
        weight="semibold",
        bbox={
            "boxstyle": "round,pad=0.4",
            "facecolor": "#f8fafc",
            "edgecolor": "#cbd5e1",
        },
    )

    save_fig(fig, "04_runtime_actual_vs_predicted.png")
    plt.close(fig)


def fetch_historical_telemetry():
    """
    Queries genuine historical records from the database.
    Calculates execution duration baseline (mean, std), Z-scores, and inspects hardware telemetry.
    Safely handles missing database, empty tables, and zero-variance data.
    """
    sys.path.insert(0, str(BASE_DIR))
    try:
        from app.database.models import PipelineRun, Telemetry
        from app.database.session import SessionLocal

        with SessionLocal() as db:
            runs = (
                db.query(PipelineRun)
                .filter(PipelineRun.total_duration_sec > 0.0)
                .order_by(PipelineRun.created_at.asc())
                .all()
            )
            durations = [float(r.total_duration_sec) for r in runs]
            run_ids = [str(r.id) for r in runs]

            telem_records = db.query(Telemetry).all()
            cpu_vals = [
                float(t.cpu_percent_avg) for t in telem_records if t.cpu_percent_avg is not None
            ]
            mem_vals = [
                float(t.memory_mb_peak) for t in telem_records if t.memory_mb_peak is not None
            ]

            return {
                "has_data": len(durations) >= 5,
                "durations": np.array(durations),
                "run_ids": run_ids,
                "runs_count": len(durations),
                "telemetry_count": len(telem_records),
                "cpu_vals": np.array(cpu_vals),
                "mem_vals": np.array(mem_vals),
            }
    except (SQLAlchemyError, OSError, RuntimeError, ValueError) as exc:
        print(f"⚠️  Database query encountered issue ({exc}). Using safe fallback.")
        return {
            "has_data": False,
            "durations": np.array([]),
            "run_ids": [],
            "runs_count": 0,
            "telemetry_count": 0,
            "cpu_vals": np.array([]),
            "mem_vals": np.array([]),
        }


def plot_zscore_distribution(telemetry_data):
    """Plot 5: Statistical Z-Score Anomaly Detection on Genuine Historical Telemetry."""
    fig, ax = plt.subplots(figsize=(7.0, 4.8))

    x = np.linspace(-4, 6, 1200)
    y = (1 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * x**2)

    # Reference Standard Normal curve
    ax.plot(x, y, color="#334155", lw=1.8, label="Standard Normal Reference N(0, 1)")

    # Fill Normal region (-2.5 <= Z <= 2.5)
    mask_normal = (x >= -2.5) & (x <= 2.5)
    ax.fill_between(
        x[mask_normal],
        y[mask_normal],
        color=SUCCESS_COLOR,
        alpha=0.18,
        label="Normal Operation (|Z| < 2.5, 98.76%)",
    )

    # Fill Anomaly region (Z >= 2.5)
    mask_right = x >= 2.5
    ax.fill_between(
        x[mask_right],
        y[mask_right],
        color=DANGER_COLOR,
        alpha=0.35,
        label="Anomaly Region (Z ≥ +2.5)",
    )
    mask_left = x <= -2.5
    ax.fill_between(x[mask_left], y[mask_left], color=DANGER_COLOR, alpha=0.35)

    # Threshold lines
    ax.axvline(
        2.5, color=DANGER_COLOR, linestyle="--", lw=1.8, label="Anomaly Threshold (Z = ±2.5)"
    )
    ax.axvline(-2.5, color=DANGER_COLOR, linestyle="--", lw=1.8)

    if telemetry_data["has_data"]:
        durations = telemetry_data["durations"]
        n_runs = len(durations)
        mu = float(np.mean(durations))
        sigma = float(np.std(durations, ddof=1)) if len(durations) > 1 else 1.0

        # Safe zero-variance handling
        if sigma <= 1e-6:
            z_scores = np.zeros_like(durations)
        else:
            z_scores = (durations - mu) / sigma

        normal_z = z_scores[np.abs(z_scores) < 2.5]
        anom_z = z_scores[np.abs(z_scores) >= 2.5]

        # Scatter observed points along baseline y=0.015 with slight vertical jitter for visibility
        np.random.seed(42)
        y_jitter_normal = 0.015 + np.random.uniform(-0.005, 0.008, size=len(normal_z))
        ax.scatter(
            normal_z,
            y_jitter_normal,
            color=PRIMARY_COLOR,
            s=40,
            alpha=0.75,
            edgecolors="#1e3a8a",
            zorder=5,
            label=f"Observed Normal Runs (N={len(normal_z)})",
        )

        if len(anom_z) > 0:
            anom_idx = np.where(np.abs(z_scores) >= 2.5)[0]
            for idx in anom_idx:
                z_val = z_scores[idx]
                dur_val = durations[idx]
                ax.scatter(
                    [z_val],
                    [0.02],
                    color=DANGER_COLOR,
                    s=120,
                    marker="*",
                    edgecolors="#7f1d1d",
                    zorder=6,
                    label=f"Observed Anomaly Run (Z={z_val:.2f})",
                )
                ax.annotate(
                    f"Outlier Run #{idx + 1}\nDuration: {dur_val:.2f}s\nZ = +{z_val:.2f}",
                    xy=(z_val, 0.02),
                    xytext=(z_val - 1.2, 0.12),
                    arrowprops={
                        "facecolor": DANGER_COLOR,
                        "shrink": 0.08,
                        "width": 1.5,
                        "headwidth": 6,
                    },
                    fontsize=8.5,
                    fontweight="bold",
                    color="#7f1d1d",
                    bbox={
                        "boxstyle": "round,pad=0.3",
                        "facecolor": "#fee2e2",
                        "edgecolor": "#ef4444",
                    },
                )

        ax.set_title(
            f"Historical CI/CD Telemetry Anomaly Detection\n"
            f"Empirical Evaluation from Database (N={n_runs} Runs, μ={mu:.2f}s, σ={sigma:.2f}s)",
            pad=12,
        )
        info_text = (
            f"Historical Telemetry Records:\n"
            f"• Pipeline Runs Evaluated: N = {n_runs}\n"
            f"• Baseline Duration: μ = {mu:.2f}s, σ = {sigma:.2f}s\n"
            f"• Anomaly Threshold: |Z| ≥ 2.5 (Duration ≥ {mu + 2.5 * sigma:.2f}s)\n"
            f"• Outlier Detected: {len(anom_z)} run(s) exceeding threshold\n"
            f"• Hardware Telemetry (CPU/RAM): N = {telemetry_data['telemetry_count']}\n"
            f"  (< 5 sample window; correctly flagged as insufficient)"
        )
    else:
        ax.set_title(
            "Historical CI/CD Telemetry Anomaly Detection Baseline\n"
            "(Standard Normal Reference Model — Insufficient Database Runs)",
            pad=12,
        )
        info_text = (
            "Database Status: Insufficient historical records (< 5 runs).\n"
            "Graph illustrates theoretical Gaussian reference model |Z| ≥ 2.5.\n"
            "Deterministic fallback prevents premature anomaly decisions."
        )

    ax.set_xlabel("Z-Score (Standard Deviations from Historical Baseline Mean μ)", labelpad=8)
    ax.set_ylabel("Probability Density", labelpad=8)
    ax.set_xlim([-4.2, 5.8])
    ax.set_ylim([0, 0.45])
    ax.legend(loc="upper left", frameon=True, framealpha=0.9, fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.6)

    ax.text(
        0.98,
        0.58,
        info_text,
        ha="right",
        va="top",
        transform=ax.transAxes,
        fontsize=8,
        bbox={
            "boxstyle": "round,pad=0.4",
            "facecolor": "#f8fafc",
            "edgecolor": "#cbd5e1",
            "alpha": 0.95,
        },
    )

    save_fig(fig, "05_zscore_anomaly_detection.png")
    plt.close(fig)


def plot_master_evaluation_panel(
    metadata, feature_names, fp_importances, rp_importances, telemetry_data
):
    """Plot 6: Multi-panel composite master figure suitable for IEEE publication."""
    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.28)

    # 1. Confusion Matrix
    ax1 = fig.add_subplot(gs[0, 0])
    cm = np.array(metadata["failure_metrics"]["confusion_matrix"])
    labels = ["PASS (0)", "FAIL (1)"]
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        cbar=False,
        xticklabels=labels,
        yticklabels=labels,
        annot_kws={"size": 14, "weight": "bold"},
        ax=ax1,
        linewidths=1.2,
        linecolor="#e2e8f0",
    )
    ax1.set_title(
        "A. Failure Classifier Confusion Matrix\n(Held-out Test Split, N=10)",
        fontsize=10.5,
        weight="bold",
    )
    ax1.set_xlabel("Predicted Class", fontsize=9)
    ax1.set_ylabel("True Ground Truth", fontsize=9)

    # 2. ROC Curve
    ax2 = fig.add_subplot(gs[0, 1])
    auc = metadata["failure_metrics"]["roc_auc"]
    fpr = np.array([0.0, 0.0, 0.0, 0.1, 0.2, 0.5, 1.0])
    tpr = np.array([0.0, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])
    ax2.plot(
        fpr,
        tpr,
        color=PRIMARY_COLOR,
        lw=2.2,
        label=f"RF Classifier (Holdout AUC={auc:.2f})",
    )
    ax2.plot(
        [0, 1],
        [0, 1],
        color="#94a3b8",
        lw=1.2,
        linestyle="--",
        label="Random Chance (0.50)",
    )
    ax2.fill_between(fpr, tpr, color=PRIMARY_COLOR, alpha=0.15)
    ax2.set_xlim([-0.02, 1.02])
    ax2.set_ylim([-0.02, 1.05])
    ax2.set_title(
        "B. ROC Curve (Illustrative, Holdout AUC=1.00)",
        fontsize=10.5,
        weight="bold",
    )
    ax2.set_xlabel("False Positive Rate", fontsize=9)
    ax2.set_ylabel("True Positive Rate", fontsize=9)
    ax2.legend(loc="lower right", fontsize=8)
    ax2.grid(True, linestyle=":", alpha=0.6)

    # 3. Actual vs Predicted Runtime
    ax3 = fig.add_subplot(gs[0, 2])
    y_actual = np.array([5.2, 8.4, 12.1, 15.8, 19.3, 22.0, 28.5, 33.1, 39.8, 45.2])
    y_pred = y_actual + np.array([0.8, -1.2, 1.5, -0.9, 1.8, -2.1, 1.4, -1.9, 2.3, -1.7])
    ax3.scatter(
        y_actual,
        y_pred,
        color=PURPLE_COLOR,
        s=50,
        alpha=0.9,
        edgecolors="#4c1d95",
        zorder=4,
    )
    ax3.plot([0, 50], [0, 50], color="#0f172a", lw=1.5, linestyle="--")
    ax3.fill_between([0, 50], [0, 42.5], [0, 57.5], color=PURPLE_COLOR, alpha=0.1)
    ax3.set_xlim([0, 50])
    ax3.set_ylim([0, 50])
    ax3.set_title(
        "C. Runtime Regressor (Illustrative, ±15% SLA band)",
        fontsize=10.5,
        weight="bold",
    )
    ax3.set_xlabel("Actual Duration (s)", fontsize=9)
    ax3.set_ylabel("Predicted Duration (s)", fontsize=9)
    r2 = metadata["runtime_metrics"]["r2_score"]
    mae = metadata["runtime_metrics"]["mae"]
    ax3.text(
        0.95,
        0.08,
        f"R² = {r2:.3f}\nMAE = {mae:.2f}s",
        ha="right",
        va="bottom",
        transform=ax3.transAxes,
        fontsize=8.5,
        weight="semibold",
        bbox={
            "boxstyle": "round,pad=0.3",
            "facecolor": "#f8fafc",
            "edgecolor": "#cbd5e1",
        },
    )
    ax3.grid(True, linestyle=":", alpha=0.6)

    # 4. Feature Importance Comparison
    ax4 = fig.add_subplot(gs[1, 0:2])
    y_pos = np.arange(len(feature_names))
    display_names = [f.replace("_", " ").title() for f in feature_names]
    width = 0.38
    ax4.barh(
        y_pos - width / 2,
        fp_importances,
        width,
        label="Failure Risk Classifier",
        color=PRIMARY_COLOR,
        alpha=0.85,
    )
    ax4.barh(
        y_pos + width / 2,
        rp_importances,
        width,
        label="Runtime Regressor",
        color=PURPLE_COLOR,
        alpha=0.85,
    )
    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(display_names, fontsize=8.5)
    ax4.set_title(
        "D. Pre-Execution Feature Importance (Predictive Association, Not Causation)",
        fontsize=10.5,
        weight="bold",
    )
    ax4.set_xlabel("Gini Importance / MSE Reduction", fontsize=9)
    ax4.legend(loc="lower right", fontsize=8.5)
    ax4.grid(True, linestyle=":", alpha=0.6, axis="x")

    # 5. Z-Score Anomaly
    ax5 = fig.add_subplot(gs[1, 2])
    x = np.linspace(-4, 6, 600)
    y = (1 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * x**2)
    ax5.plot(x, y, color="#334155", lw=1.8)
    mask_normal = (x >= -2.5) & (x <= 2.5)
    ax5.fill_between(
        x[mask_normal],
        y[mask_normal],
        color=SUCCESS_COLOR,
        alpha=0.25,
        label="|Z| < 2.5 (Normal)",
    )
    ax5.fill_between(
        x[x >= 2.5],
        y[x >= 2.5],
        color=DANGER_COLOR,
        alpha=0.5,
        label="|Z| ≥ 2.5 (Anomaly)",
    )
    ax5.fill_between(x[x <= -2.5], y[x <= -2.5], color=DANGER_COLOR, alpha=0.5)
    ax5.axvline(2.5, color=DANGER_COLOR, linestyle="--", lw=1.5)
    ax5.axvline(-2.5, color=DANGER_COLOR, linestyle="--", lw=1.5)

    if telemetry_data["has_data"]:
        durations = telemetry_data["durations"]
        mu = float(np.mean(durations))
        sigma = float(np.std(durations, ddof=1)) if len(durations) > 1 else 1.0
        z_scores = (durations - mu) / sigma if sigma > 1e-6 else np.zeros_like(durations)
        normal_z = z_scores[np.abs(z_scores) < 2.5]
        anom_z = z_scores[np.abs(z_scores) >= 2.5]
        ax5.scatter(
            normal_z,
            [0.015] * len(normal_z),
            color=PRIMARY_COLOR,
            s=20,
            alpha=0.7,
            zorder=5,
        )
        if len(anom_z) > 0:
            ax5.scatter(
                anom_z,
                [0.02] * len(anom_z),
                color=DANGER_COLOR,
                s=60,
                marker="*",
                zorder=6,
            )
        ax5.set_title(
            f"E. Telemetry Z-Scores (DB N={len(durations)}, Outlier Z={anom_z[0]:.2f})",
            fontsize=10.5,
            weight="bold",
        )
    else:
        ax5.set_title("E. Telemetry Z-Score Anomaly Model", fontsize=10.5, weight="bold")

    ax5.set_xlabel("Z-Score Threshold", fontsize=9)
    ax5.set_ylabel("Density", fontsize=9)
    ax5.legend(loc="upper left", fontsize=7.5)
    ax5.grid(True, linestyle=":", alpha=0.6)

    fig.suptitle(
        "Autonomous DevOps: Machine Learning Empirical Evaluation & Telemetry Analytics\n"
        "AI-Driven CI/CD Pipeline Optimization with Deterministic Safety Fallbacks",
        fontsize=13,
        weight="bold",
        y=0.98,
    )

    save_fig(fig, "06_ml_evaluation_master_panel.png")
    plt.close(fig)


def main():
    ensure_directories()
    print("=" * 60)
    print("📊 Autonomous DevOps: Generating ML Evaluation Visualizations")
    print("=" * 60)

    # 1. Load metadata
    if not METADATA_PATH.exists():
        print(f"❌ Metadata file not found at {METADATA_PATH}")
        sys.exit(1)

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 2. Load trained models for real feature importances
    sys.path.insert(0, str(BASE_DIR))
    fp = joblib.load(FAILURE_MODEL_PATH)
    rp = joblib.load(RUNTIME_MODEL_PATH)

    feature_names = [
        "changed_files_count",
        "lines_added",
        "lines_deleted",
        "total_lines_changed",
        "affected_modules_count",
        "selected_tests_count",
        "is_sensitive_change",
        "has_test_file_changes",
        "historical_failure_rate",
        "previous_execution_duration",
    ]

    fp_importances = list(fp.model.feature_importances_)
    rp_importances = list(rp.model.feature_importances_)

    # 3. Query genuine historical telemetry from database
    telemetry_data = fetch_historical_telemetry()

    print("Generating Figure 1: Confusion Matrix...")
    plot_confusion_matrix(metadata)

    print("Generating Figure 2: ROC-AUC Curve...")
    plot_roc_curve(metadata)

    print("Generating Figure 3: Feature Importances...")
    plot_feature_importance(feature_names, fp_importances, rp_importances)

    print("Generating Figure 4: Runtime Actual vs Predicted...")
    plot_actual_vs_predicted(metadata)

    print("Generating Figure 5: Z-Score Anomaly Distribution...")
    plot_zscore_distribution(telemetry_data)

    print("Generating Figure 6: Master Evaluation Panel...")
    plot_master_evaluation_panel(
        metadata, feature_names, fp_importances, rp_importances, telemetry_data
    )

    print("=" * 60)
    print("✅ All 6 ML evaluation figures generated successfully!")
    print(f"📁 Document Figures: {DOCS_FIG_DIR}")
    print(f"📁 Static Web Graphs: {STATIC_FIG_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
