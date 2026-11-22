/**
 * Autonomous DevOps - Chart.js & Dashboard Interactivity
 */

document.addEventListener("DOMContentLoaded", () => {
  // Chart defaults for dark theme
  if (typeof Chart !== "undefined") {
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.borderColor = "#334155";
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  }
});

function initOverviewCharts(trendLabels, durationData, optimizedCount, fallbackCount) {
  // 1. Duration Trend Line Chart
  const trendCtx = document.getElementById("durationTrendChart");
  if (trendCtx) {
    new Chart(trendCtx, {
      type: "line",
      data: {
        labels: trendLabels && trendLabels.length ? trendLabels : ["Run 1", "Run 2", "Run 3", "Run 4", "Run 5"],
        datasets: [{
          label: "Execution Duration (s)",
          data: durationData && durationData.length ? durationData : [25, 22, 18, 15, 12],
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.1)",
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointBackgroundColor: "#3b82f6",
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: "Seconds" }
          }
        }
      }
    });
  }

  // 2. Decision Doughnut Chart
  const decisionCtx = document.getElementById("decisionDoughnutChart");
  if (decisionCtx) {
    const opt = optimizedCount || 0;
    const fall = fallbackCount || 0;
    const hasData = (opt + fall) > 0;

    new Chart(decisionCtx, {
      type: "doughnut",
      data: {
        labels: ["Optimized Plans", "Full-Suite Fallbacks"],
        datasets: [{
          data: hasData ? [opt, fall] : [1, 0],
          backgroundColor: ["#10b981", "#f59e0b"],
          borderColor: "#1e293b",
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 12, padding: 14 }
          }
        },
        cutout: "70%"
      }
    });
  }
}

function initObservabilityCharts(labels, cpuData, memData) {
  const ctx = document.getElementById("telemetryChart");
  if (ctx) {
    new Chart(ctx, {
      type: "line",
      data: {
        labels: labels && labels.length ? labels : ["Run 1", "Run 2", "Run 3", "Run 4", "Run 5"],
        datasets: [
          {
            label: "Avg CPU Utilization (%)",
            data: cpuData && cpuData.length ? cpuData : [35, 42, 38, 40, 37],
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6, 182, 212, 0.08)",
            tension: 0.3,
            yAxisID: "yCpu",
          },
          {
            label: "Peak Memory (MB)",
            data: memData && memData.length ? memData : [110, 115, 125, 118, 120],
            borderColor: "#8b5cf6",
            backgroundColor: "rgba(139, 92, 246, 0.08)",
            tension: 0.3,
            yAxisID: "yMem",
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          yCpu: {
            type: "linear",
            position: "left",
            beginAtZero: true,
            max: 100,
            title: { display: true, text: "CPU %" }
          },
          yMem: {
            type: "linear",
            position: "right",
            beginAtZero: true,
            title: { display: true, text: "Memory (MB)" },
            grid: { drawOnChartArea: false }
          }
        }
      }
    });
  }
}

function initAIInsightsCharts(riskLabels, riskValues) {
  const ctx = document.getElementById("failureRiskChart");
  if (ctx) {
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: riskLabels && riskLabels.length ? riskLabels : ["Run 1", "Run 2", "Run 3", "Run 4", "Run 5"],
        datasets: [{
          label: "Predicted Failure Probability",
          data: riskValues && riskValues.length ? riskValues : [0.08, 0.12, 0.05, 0.45, 0.10],
          backgroundColor: riskValues.map(v => v >= 0.40 ? "rgba(239, 68, 68, 0.7)" : "rgba(59, 130, 246, 0.7)"),
          borderColor: riskValues.map(v => v >= 0.40 ? "#ef4444" : "#3b82f6"),
          borderWidth: 1,
          borderRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            max: 1.0,
            title: { display: true, text: "Probability (0.0 - 1.0)" }
          }
        }
      }
    });
  }
}
