/**
 * Autonomous DevOps - Chart.js & Dashboard Interactivity
 * High-performance, zero-dependency interactive dashboard engine
 */

document.addEventListener("DOMContentLoaded", () => {
  // Global Chart.js 4+ dark theme defaults
  if (typeof Chart !== "undefined") {
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.borderColor = "#1e293b";
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif';
    Chart.defaults.plugins.tooltip.backgroundColor = "#0f172a";
    Chart.defaults.plugins.tooltip.borderColor = "#334155";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.titleFont = { weight: "600", size: 12 };
    Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
  }

  // Initialize interactive features
  initMobileNav();
  initCopyableElements();
  initAutoTableSearch();
});

/**
 * Mobile Navigation Drawer Toggle
 */
function initMobileNav() {
  const toggleBtn = document.getElementById("mobileNavToggle");
  const backdrop = document.getElementById("sidebarBackdrop");

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      document.body.classList.toggle("sidebar-open");
    });
  }

  if (backdrop) {
    backdrop.addEventListener("click", () => {
      document.body.classList.remove("sidebar-open");
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("sidebar-open")) {
      document.body.classList.remove("sidebar-open");
    }
  });
}

/**
 * Copy to Clipboard with temporary Toast Notification
 */
function initCopyableElements() {
  document.querySelectorAll(".copyable").forEach((el) => {
    el.addEventListener("click", async (e) => {
      e.preventDefault();
      const text = el.getAttribute("data-copy") || el.innerText.trim();
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        showToast(`Copied to clipboard: ${text.slice(0, 16)}${text.length > 16 ? "..." : ""}`);
      } catch (err) {
        // Fallback for older browsers
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        showToast("Copied to clipboard!");
      }
    });
  });
}

function showToast(message) {
  const existing = document.querySelector(".toast-notice");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = "toast-notice";
  toast.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #10b981;">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
  `;
  const toastMessage = document.createElement("span");
  toastMessage.textContent = message;
  toast.appendChild(toastMessage);
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 300ms ease";
    setTimeout(() => toast.remove(), 300);
  }, 2400);
}

/**
 * Interactive Client-Side Table Filtering & Search
 */
function initAutoTableSearch() {
  const searchInputs = document.querySelectorAll(".table-search-input");
  searchInputs.forEach((input) => {
    const targetTableId = input.getAttribute("data-target-table");
    if (!targetTableId) return;

    input.addEventListener("input", () => {
      filterTable(targetTableId, input.value.toLowerCase().trim());
    });
  });
}

function filterTable(tableId, query) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const rows = table.querySelectorAll("tbody tr");
  let visibleCount = 0;

  rows.forEach((row) => {
    // Ignore designated empty state rows
    if (row.classList.contains("empty-state-row")) return;

    const text = row.innerText.toLowerCase();
    const matches = query === "" || text.includes(query);
    row.style.display = matches ? "" : "none";
    if (matches) visibleCount++;
  });

  // Handle dynamic empty filter message
  let noMatchRow = table.querySelector(".no-match-row");
  if (visibleCount === 0 && query !== "") {
    if (!noMatchRow) {
      noMatchRow = document.createElement("tr");
      noMatchRow.className = "no-match-row";
      const colCount = table.querySelectorAll("thead th").length || 7;
      const td = document.createElement("td");
      td.colSpan = colCount;
      td.className = "empty-state";
      td.style.padding = "24px";
      td.style.textAlign = "center";
      td.style.color = "var(--text-muted)";
      td.textContent = `No matching records found for query "${query}"`;
      noMatchRow.appendChild(td);
      table.querySelector("tbody").appendChild(noMatchRow);
    } else {
      noMatchRow.style.display = "";
    }
  } else if (noMatchRow) {
    noMatchRow.style.display = "none";
  }
}

/**
 * Status Button Pills Filter
 */
function initStatusFilter(filterContainerId, tableId, statusColIndex) {
  const container = document.getElementById(filterContainerId);
  const table = document.getElementById(tableId);
  if (!container || !table) return;

  const buttons = container.querySelectorAll(".filter-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      const filterVal = btn.getAttribute("data-filter") || "ALL";
      const rows = table.querySelectorAll("tbody tr:not(.empty-state-row):not(.no-match-row)");

      rows.forEach((row) => {
        if (filterVal === "ALL") {
          row.style.display = "";
          return;
        }

        const cell = row.children[statusColIndex];
        if (!cell) return;
        const cellText = cell.innerText.trim().toUpperCase();
        row.style.display = cellText.includes(filterVal.toUpperCase()) ? "" : "none";
      });
    });
  });
}

/**
 * Header Refresh Button Trigger
 */
function refreshDashboard() {
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    const icon = refreshBtn.querySelector("svg");
    if (icon) icon.style.animation = "spin 1s linear infinite";
  }

  showToast("Refreshing pipeline metrics...");
  setTimeout(() => {
    window.location.reload();
  }, 400);
}

// Spin animation for refresh icon
const style = document.createElement("style");
style.innerHTML = `@keyframes spin { 100% { transform: rotate(360deg); } }`;
document.head.appendChild(style);

/* =====================================================================
   Chart.js Visualization Initialization Routines
   ===================================================================== */

/**
 * Overview View: Duration Trend Line Chart & Decision Doughnut
 */
function initOverviewCharts(trendLabels, durationData, optimizedCount, fallbackCount) {
  const trendCtx = document.getElementById("durationTrendChart");
  if (trendCtx && typeof Chart !== "undefined") {
    const labels = trendLabels && trendLabels.length ? trendLabels : [];
    const data = durationData && durationData.length ? durationData : [];

    new Chart(trendCtx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Pipeline Duration (seconds)",
          data: data,
          borderColor: "#6366f1",
          backgroundColor: "rgba(99, 102, 241, 0.12)",
          fill: true,
          tension: 0.35,
          borderWidth: 2.5,
          pointBackgroundColor: "#6366f1",
          pointBorderColor: "#ffffff",
          pointHoverRadius: 6,
          pointRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#64748b" }
          },
          y: {
            beginAtZero: true,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b" },
            title: { display: true, text: "Seconds", color: "#64748b" }
          }
        }
      }
    });
  }

  const decisionCtx = document.getElementById("decisionDoughnutChart");
  if (decisionCtx && typeof Chart !== "undefined") {
    const opt = Number(optimizedCount) || 0;
    const fall = Number(fallbackCount) || 0;
    const total = opt + fall;

    new Chart(decisionCtx, {
      type: "doughnut",
      data: {
        labels: total > 0 ? ["Optimized AST Execution", "Full-Suite Fallback"] : ["No Executions Yet"],
        datasets: [{
          data: total > 0 ? [opt, fall] : [1],
          backgroundColor: total > 0 ? ["#10b981", "#f59e0b"] : ["#1e293b"],
          borderColor: "#0f172a",
          borderWidth: 3,
          hoverOffset: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              boxWidth: 12,
              padding: 16,
              color: "#94a3b8",
              font: { size: 12 }
            }
          }
        },
        cutout: "72%"
      }
    });
  }
}

/**
 * Observability View: Dual-Axis CPU & Memory Line Chart
 */
function initObservabilityCharts(labels, cpuData, memData) {
  const ctx = document.getElementById("telemetryChart");
  if (ctx && typeof Chart !== "undefined") {
    const chartLabels = labels && labels.length ? labels : [];
    const cpu = cpuData && cpuData.length ? cpuData : [];
    const mem = memData && memData.length ? memData : [];

    new Chart(ctx, {
      type: "line",
      data: {
        labels: chartLabels,
        datasets: [
          {
            label: "Avg CPU Utilization (%)",
            data: cpu,
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6, 182, 212, 0.1)",
            fill: true,
            tension: 0.3,
            borderWidth: 2,
            pointRadius: 3,
            yAxisID: "yCpu",
          },
          {
            label: "Peak Memory (MB)",
            data: mem,
            borderColor: "#8b5cf6",
            backgroundColor: "rgba(139, 92, 246, 0.1)",
            fill: true,
            tension: 0.3,
            borderWidth: 2,
            pointRadius: 3,
            yAxisID: "yMem",
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            labels: { boxWidth: 12, color: "#94a3b8" }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#64748b" }
          },
          yCpu: {
            type: "linear",
            position: "left",
            beginAtZero: true,
            max: 100,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            title: { display: true, text: "CPU %", color: "#06b6d4" },
            ticks: { color: "#06b6d4" }
          },
          yMem: {
            type: "linear",
            position: "right",
            beginAtZero: true,
            title: { display: true, text: "Memory (MB)", color: "#8b5cf6" },
            ticks: { color: "#8b5cf6" },
            grid: { drawOnChartArea: false }
          }
        }
      }
    });
  }
}

/**
 * AI Insights View: Failure Probability Risk Distribution Chart
 */
function initAIInsightsCharts(riskLabels, riskValues) {
  const ctx = document.getElementById("failureRiskChart");
  if (ctx && typeof Chart !== "undefined") {
    const labels = riskLabels && riskLabels.length ? riskLabels : [];
    const values = riskValues && riskValues.length ? riskValues : [];

    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "Predicted Failure Probability",
          data: values,
          backgroundColor: values.map((v) => (v >= 0.40 ? "rgba(239, 68, 68, 0.75)" : "rgba(99, 102, 241, 0.75)")),
          borderColor: values.map((v) => (v >= 0.40 ? "#ef4444" : "#6366f1")),
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#64748b" }
          },
          y: {
            beginAtZero: true,
            max: 1.0,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b" },
            title: { display: true, text: "Risk Probability (0.00 - 1.00)", color: "#64748b" }
          }
        }
      }
    });
  }
}
