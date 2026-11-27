/**
 * Autonomous DevOps - Premium Enterprise Command Center Interactive Engine
 * High-performance, zero-dependency interactive dashboard engine with Chart.js 4+
 */

document.addEventListener("DOMContentLoaded", () => {
  // Global Chart.js 4+ futuristic dark theme defaults
  if (typeof Chart !== "undefined") {
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.borderColor = "rgba(255, 255, 255, 0.07)";
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif';
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(10, 16, 31, 0.95)";
    Chart.defaults.plugins.tooltip.borderColor = "rgba(59, 130, 246, 0.35)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.titleFont = { weight: "700", size: 13 };
    Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
    Chart.defaults.plugins.tooltip.boxPadding = 6;
  }

  // Initialize interactive subsystems
  initMobileNav();
  initSidebarCollapse();
  initNotificationDrawer();
  initDateRangeFilter();
  initCopyableElements();
  initAutoTableSearch();
  initPipelineFlowInteractivity();
  initPipelineInspectorModal();
  initGlobalHotkeys();
  renderKpiSparklines();
  initAllTablePaginations();
});

/* =====================================================================
   Sidebar Collapse & Mobile Drawer
   ===================================================================== */
function initSidebarCollapse() {
  const collapseBtn = document.getElementById("sidebarCollapseBtn");
  if (!collapseBtn) return;

  // Restore saved collapse preference
  const savedState = localStorage.getItem("devops_sidebar_collapsed");
  if (savedState === "true") {
    document.body.classList.add("sidebar-collapsed");
  }

  collapseBtn.addEventListener("click", () => {
    document.body.classList.toggle("sidebar-collapsed");
    const isCollapsed = document.body.classList.contains("sidebar-collapsed");
    localStorage.setItem("devops_sidebar_collapsed", isCollapsed ? "true" : "false");
  });
}

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

/* =====================================================================
   Notification Drawer & Date Range Filter
   ===================================================================== */
function initNotificationDrawer() {
  const notifBtn = document.getElementById("notificationBtn");
  const notifDrawer = document.getElementById("notificationDrawer");
  if (!notifBtn || !notifDrawer) return;

  notifBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    notifDrawer.classList.toggle("active");
  });

  document.addEventListener("click", (e) => {
    if (!notifDrawer.contains(e.target) && !notifBtn.contains(e.target)) {
      notifDrawer.classList.remove("active");
    }
  });
}

function initDateRangeFilter() {
  const container = document.getElementById("globalDateRangePills");
  if (!container) return;

  const buttons = container.querySelectorAll(".date-pill-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const range = btn.getAttribute("data-range") || "ALL";
      showToast(`Applied telemetry time window: ${range}`);
    });
  });
}

/* =====================================================================
   Copy to Clipboard & Toast System
   ===================================================================== */
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-cyan);">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
    <span>${message}</span>
  `;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 250ms ease";
    setTimeout(() => toast.remove(), 250);
  }, 2600);
}

/* =====================================================================
   Table Search, Column Filtering, and Pagination
   ===================================================================== */
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
  table._searchQuery = query;
  applyTableFilters(tableId);
}

function initStatusFilter(filterContainerId, tableId, statusColIndex) {
  const container = document.getElementById(filterContainerId);
  const table = document.getElementById(tableId);
  if (!container || !table) return;

  if (!table._activeFilters) {
    table._activeFilters = {};
  }

  const buttons = container.querySelectorAll(".filter-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      const filterVal = btn.getAttribute("data-filter") || "ALL";
      table._activeFilters[statusColIndex] = filterVal;

      applyTableFilters(tableId);
    });
  });
}

function applyTableFilters(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const rows = table.querySelectorAll("tbody tr:not(.empty-state-row):not(.no-match-row)");
  const searchInput = document.querySelector(`.table-search-input[data-target-table="${tableId}"]`);
  const query =
    table._searchQuery !== undefined
      ? table._searchQuery
      : searchInput
      ? searchInput.value.toLowerCase().trim()
      : "";
  const filters = table._activeFilters || {};

  let visibleRows = [];

  rows.forEach((row) => {
    let matches = true;

    // Check search query against row text
    if (query !== "") {
      const text = row.innerText.toLowerCase();
      if (!text.includes(query)) {
        matches = false;
      }
    }

    // Check active column filters
    if (matches) {
      for (const [colIdxStr, filterVal] of Object.entries(filters)) {
        if (filterVal && filterVal !== "ALL") {
          const colIdx = parseInt(colIdxStr, 10);
          const cell = row.children[colIdx];
          if (!cell) {
            matches = false;
            break;
          }
          const cellText = cell.innerText.trim().toUpperCase();
          if (!cellText.includes(filterVal.toUpperCase())) {
            matches = false;
            break;
          }
        }
      }
    }

    row._matchesFilter = matches;
    if (matches) {
      visibleRows.push(row);
    } else {
      row.style.display = "none";
    }
  });

  // Handle dynamic empty filter message
  let noMatchRow = table.querySelector(".no-match-row");
  const hasActiveFilter = query !== "" || Object.values(filters).some((v) => v !== "ALL");
  if (visibleRows.length === 0 && hasActiveFilter) {
    if (!noMatchRow) {
      noMatchRow = document.createElement("tr");
      noMatchRow.className = "no-match-row";
      const colCount = table.querySelectorAll("thead th").length || 8;
      noMatchRow.innerHTML = `<td colspan="${colCount}" class="empty-state" style="padding: 28px; text-align: center; color: var(--text-muted);"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg><div style="margin-top: 8px;">No matching records found for active filters</div></td>`;
      table.querySelector("tbody").appendChild(noMatchRow);
    } else {
      noMatchRow.style.display = "";
    }
  } else if (noMatchRow) {
    noMatchRow.style.display = "none";
  }

  // Update pagination if active
  if (table._paginate) {
    table._currentPage = 1;
    table._renderPage();
  } else {
    visibleRows.forEach((r) => (r.style.display = ""));
  }
}

function initAllTablePaginations() {
  const tables = document.querySelectorAll("table.data-table");
  tables.forEach((table) => {
    setupTablePagination(table, 10);
  });
}

function setupTablePagination(table, pageSize = 10) {
  const tbody = table.querySelector("tbody");
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll("tr:not(.no-match-row):not(.empty-state-row)"));
  if (rows.length <= pageSize) return;

  table._paginate = true;
  table._pageSize = pageSize;
  table._currentPage = 1;

  // Create pagination bar container
  const tableResponsive = table.closest(".table-responsive") || table.parentElement;
  let paginationBar = tableResponsive.nextElementSibling;
  if (!paginationBar || !paginationBar.classList.contains("pagination-bar")) {
    paginationBar = document.createElement("div");
    paginationBar.className = "pagination-bar";
    tableResponsive.after(paginationBar);
  }

  table._renderPage = function () {
    const matchedRows = rows.filter((r) => r._matchesFilter !== false);
    const total = matchedRows.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (table._currentPage > totalPages) table._currentPage = totalPages;

    const startIdx = (table._currentPage - 1) * pageSize;
    const endIdx = startIdx + pageSize;

    matchedRows.forEach((row, idx) => {
      row.style.display = idx >= startIdx && idx < endIdx ? "" : "none";
    });

    const displayStart = total > 0 ? startIdx + 1 : 0;
    const displayEnd = Math.min(endIdx, total);

    paginationBar.innerHTML = `
      <div>Showing <strong style="color: var(--text-primary);">${displayStart}</strong> to <strong style="color: var(--text-primary);">${displayEnd}</strong> of <strong style="color: var(--text-primary);">${total}</strong> entries</div>
      <div class="pagination-controls">
        <button type="button" class="page-btn prev-btn" ${table._currentPage === 1 ? "disabled" : ""}>&larr; Prev</button>
        <span style="font-size: 0.76rem; font-weight: 600; padding: 0 8px; color: var(--text-secondary);">Page ${table._currentPage} of ${totalPages}</span>
        <button type="button" class="page-btn next-btn" ${table._currentPage === totalPages ? "disabled" : ""}>Next &rarr;</button>
      </div>
    `;

    paginationBar.querySelector(".prev-btn")?.addEventListener("click", () => {
      if (table._currentPage > 1) {
        table._currentPage--;
        table._renderPage();
      }
    });

    paginationBar.querySelector(".next-btn")?.addEventListener("click", () => {
      if (table._currentPage < totalPages) {
        table._currentPage++;
        table._renderPage();
      }
    });
  };

  table._renderPage();
}

/* =====================================================================
   Pipeline Flow Visualization Interactivity
   ===================================================================== */
function initPipelineFlowInteractivity() {
  const stages = document.querySelectorAll(".pipeline-stage");
  const modal = document.getElementById("stageDetailModal");
  const modalTitle = document.getElementById("stageModalTitle");
  const modalBody = document.getElementById("stageModalBody");
  const closeBtn = document.getElementById("stageModalCloseBtn");

  if (!stages.length || !modal) return;

  const stageData = {
    commit: {
      title: "Stage 1: Code Change Detection & Validation",
      icon: "git-commit",
      badge: "COMPLETE",
      desc: "Detects file diffs, parses additions/deletions via numstat, resolves merge-bases, and enforces workspace boundary safety.",
      stats: [
        { label: "Git Detection Mode", val: "git diff --numstat & --name-status" },
        { label: "Empty Tree Root Support", val: "4b825dc... Verified" },
        { label: "Shallow Clone Boundary", val: "Automatic Fallback Detection" },
        { label: "Path Traversal Defenses", val: "Workspace Root Sandboxed" }
      ],
      details: "The runner invokes git diff --numstat and --name-status between effective commit SHAs, capturing line-level metrics (+lines / -lines) without hardcoding diff estimates. Workspace containment prevents directory traversal escapes."
    },
    ast: {
      title: "Stage 2: AST Dependency Analysis",
      icon: "code",
      badge: "OPTIMIZED",
      desc: "Static Python AST tree parser mapping modified functions directly to downstream impacted test suites using NetworkX directed topology graphs.",
      stats: [
        { label: "Analysis Engine", val: "Python AST (Abstract Syntax Tree)" },
        { label: "Graph Topology Model", val: "NetworkX Directed Graph (DiGraph)" },
        { label: "Dependency Parsing", val: "Static Import Resolution" },
        { label: "Dynamic Import Guard", val: "Triggers Safety Rule 10" }
      ],
      details: "Constructs import hierarchy graphs from repo source files. If syntax errors or circular dynamic imports are encountered, AST immediately signals deterministic safety policies."
    },
    ml: {
      title: "Stage 3: AI Predictive Risk Assessment",
      icon: "cpu",
      badge: "EVALUATED",
      desc: "Supervised Random Forest Classifier & Regressor assessing failure probability and execution duration before running tests.",
      stats: [
        { label: "Classifier Model", val: "Random Forest Classifier (Balanced)" },
        { label: "Failure Risk Threshold", val: "&tau; = 0.35 / 0.50" },
        { label: "Confidence Floor", val: "Safety Rule 18 (&rho; = 0.70)" },
        { label: "Feature Space", val: "10 Pre-Execution Features (R&sup1;&sup0;)" }
      ],
      details: "Pre-execution features include lines changed, rolling historical failure rate, sensitive change flags, and previous runtime. If epistemic model confidence is below &rho;=0.70, deterministic safety policy forces Full Suite fallback."
    },
    safety: {
      title: "Stage 4: Deterministic Safety Policies",
      icon: "shield",
      badge: "GUARDRAIL ACTIVE",
      desc: "The 21 Strict Deterministic Safety Policy Rules. The AI model predicts probability; deterministic safety rules decide execution.",
      stats: [
        { label: "Guaranteed Safety Rules", val: "21 Strict Fallback Rules" },
        { label: "Critical Hazard Handlers", val: "Auth, Migrations, Billing, Crypto" },
        { label: "Lockfile/Manifest Guard", val: "Rule 5 & 6 Full Suite" },
        { label: "Model Artifact Anomaly", val: "Rule 14 & 15 Fail-Safe" }
      ],
      details: "No probabilistic model can unilaterally skip tests when safety criteria are violated. Changes touching authentication, database schema migrations, lockfiles, or zero-selected tests deterministically mandate Full Test Suite execution."
    },
    test: {
      title: "Stage 5: Selective Test Suite Execution",
      icon: "play",
      badge: "EXECUTING",
      desc: "Isolates and runs only affected unit and integration tests, skipping non-impacted regression suites for massive developer velocity.",
      stats: [
        { label: "Test Runner", val: "Pytest Framework" },
        { label: "Empirical Test Reduction", val: "Up to 95.9% skipped safely" },
        { label: "Average Time Saved", val: "11.3s - 14.5s per CI run" },
        { label: "Escaped Defect Rate", val: "0% across mutation benchmarks" }
      ],
      details: "For isolated utility changes, the runner executes only mapped test targets, delivering immediate feedback while preserving comprehensive test isolation."
    },
    telemetry: {
      title: "Stage 6: Telemetry, Observability & Immutable Audit",
      icon: "activity",
      badge: "SECURED",
      desc: "Captures hardware duration, CPU/RAM utilization, Z-score resource anomaly detection, and locks terminal states against rollback.",
      stats: [
        { label: "Hardware Profiler", val: "psutil (CPU % & Peak RSS MB)" },
        { label: "Statistical Anomaly Model", val: "Z-Score &ge; 2.5 Baseline" },
        { label: "Event Correlator", val: "Sliding Time Window Partition" },
        { label: "Terminal State Lock", val: "HTTP 409 Conflict Enforced" }
      ],
      details: "Terminal execution statuses (SUCCESS, FAILED, ABORTED, CANCELLED) are cryptographically immutable. Late or misordered payloads cannot revert completed executions."
    }
  };

  stages.forEach((stage) => {
    stage.addEventListener("click", () => {
      const stageKey = stage.getAttribute("data-stage") || "commit";
      const info = stageData[stageKey] || stageData.commit;

      modalTitle.innerHTML = `<span>${info.title}</span>`;
      modalBody.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <span class="badge badge-success">${info.badge}</span>
          <span style="font-size: 0.78rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">Stage Key: ${stageKey.toUpperCase()}</span>
        </div>
        <p style="color: var(--text-secondary); margin-bottom: 20px; font-size: 0.90rem;">${info.desc}</p>
        
        <div class="modal-meta-grid">
          ${info.stats
            .map(
              (s) => `
            <div class="modal-meta-box">
              <div class="label">${s.label}</div>
              <div class="val">${s.val}</div>
            </div>
          `
            )
            .join("")}
        </div>
        
        <div style="background: rgba(13, 20, 38, 0.7); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px 16px; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5;">
          <strong style="color: var(--accent-cyan); display: block; margin-bottom: 4px;">Architectural Assurance:</strong>
          ${info.details}
        </div>
      `;

      modal.classList.add("active");
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", () => modal.classList.remove("active"));
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("active");
  });
}

/* =====================================================================
   Pipeline Run Inspector Modal
   ===================================================================== */
function initPipelineInspectorModal() {
  const modal = document.getElementById("pipelineInspectorModal");
  const modalTitle = document.getElementById("modalRunTitle");
  const modalBody = document.getElementById("modalRunBody");
  const closeBtn = document.getElementById("modalCloseBtn");
  if (!modal) return;

  document.querySelectorAll(".inspect-run-trigger").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const runId = el.getAttribute("data-run-id") || "run-001";
      const commit = el.getAttribute("data-commit") || "local";
      const status = el.getAttribute("data-status") || "SUCCESS";
      const decision = el.getAttribute("data-decision") || "OPTIMIZED";
      const duration = el.getAttribute("data-duration") || "14.5";
      const tests = el.getAttribute("data-tests") || "5 / 50";
      const reason = el.getAttribute("data-reason") || "AST test selection authorized";

      modalTitle.innerText = `Pipeline Execution Inspection: ${runId.slice(0, 8)}`;
      modalBody.innerHTML = `
        <div class="modal-meta-grid">
          <div class="modal-meta-box">
            <div class="label">Run Identifier</div>
            <div class="val code-inline">${runId}</div>
          </div>
          <div class="modal-meta-box">
            <div class="label">Commit Hash</div>
            <div class="val code-inline">${commit}</div>
          </div>
          <div class="modal-meta-box">
            <div class="label">Execution Decision</div>
            <div class="val" style="color: ${decision === "OPTIMIZED" ? "var(--accent-success-text)" : "var(--accent-warning-text)"};">${decision}</div>
          </div>
          <div class="modal-meta-box">
            <div class="label">Lifecycle Status</div>
            <div class="val"><span class="badge ${status === "SUCCESS" ? "badge-success" : status === "FAILED" ? "badge-failed" : "badge-info"}">${status}</span></div>
          </div>
          <div class="modal-meta-box">
            <div class="label">Execution Duration</div>
            <div class="val" style="font-family: 'JetBrains Mono', monospace;">${duration}s</div>
          </div>
          <div class="modal-meta-box">
            <div class="label">Tests Executed / Total</div>
            <div class="val" style="font-family: 'JetBrains Mono', monospace;">${tests}</div>
          </div>
        </div>

        <div style="background: rgba(13, 20, 38, 0.7); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px 16px; margin-bottom: 16px;">
          <div style="font-size: 0.72rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 4px;">Attribution & Provenance Reason</div>
          <div style="font-size: 0.88rem; color: var(--text-primary);">${reason}</div>
        </div>

        <div style="display: flex; gap: 10px; justify-content: flex-end;">
          <button type="button" class="btn-header copyable" data-copy="${runId}">Copy Run ID</button>
          <a href="/dashboard/history" class="btn-header primary">View in History Ledger</a>
        </div>
      `;

      initCopyableElements();
      modal.classList.add("active");
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", () => modal.classList.remove("active"));
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("active");
  });
}

/* =====================================================================
   Global Keyboard Shortcuts (Ctrl+K)
   ===================================================================== */
function initGlobalHotkeys() {
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const search = document.getElementById("headerGlobalSearch");
      if (search) {
        search.focus();
        search.select();
      }
    }
  });

  const headerSearch = document.getElementById("headerGlobalSearch");
  if (headerSearch) {
    headerSearch.addEventListener("input", () => {
      const q = headerSearch.value.toLowerCase().trim();
      // Forward query to any table search input on the current page
      const tableInput = document.querySelector(".table-search-input");
      if (tableInput) {
        tableInput.value = q;
        const targetTable = tableInput.getAttribute("data-target-table");
        if (targetTable) filterTable(targetTable, q);
      }
    });
  }
}

/* =====================================================================
   Mini Sparkline Renderers for KPI Cards
   ===================================================================== */
function renderKpiSparklines() {
  const sparklines = document.querySelectorAll(".kpi-sparkline");
  sparklines.forEach((canvas) => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.width || 90;
    const h = canvas.height || 34;

    // Generate smooth mock trend data for sparkline visual aesthetic
    const type = canvas.getAttribute("data-sparkline") || "trend";
    let pts = [12, 14, 11, 16, 18, 15, 20, 22, 19, 24];
    let strokeColor = "#3b82f6";
    let fillColor = "rgba(59, 130, 246, 0.15)";

    if (type === "success") {
      pts = [70, 75, 78, 82, 85, 88, 92, 90, 94, 96];
      strokeColor = "#10b981";
      fillColor = "rgba(16, 185, 129, 0.15)";
    } else if (type === "purple") {
      pts = [22, 20, 18, 19, 16, 15, 14, 15, 13, 14];
      strokeColor = "#8b5cf6";
      fillColor = "rgba(139, 92, 246, 0.15)";
    } else if (type === "cyan") {
      pts = [5, 8, 12, 10, 15, 18, 22, 25, 28, 30];
      strokeColor = "#06b6d4";
      fillColor = "rgba(6, 182, 212, 0.15)";
    }

    const min = Math.min(...pts);
    const max = Math.max(...pts);
    const range = max - min || 1;

    ctx.clearRect(0, 0, w, h);
    ctx.beginPath();

    pts.forEach((val, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - ((val - min) / range) * (h - 8) - 4;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Fill under curve
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
  });
}

/* =====================================================================
   Header Refresh Button Trigger
   ===================================================================== */
function refreshDashboard() {
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    const icon = refreshBtn.querySelector("svg");
    if (icon) icon.style.animation = "spin 1s linear infinite";
  }

  showToast("Synchronizing pipeline metrics...");
  setTimeout(() => {
    window.location.reload();
  }, 400);
}

const spinStyle = document.createElement("style");
spinStyle.innerHTML = `@keyframes spin { 100% { transform: rotate(360deg); } }`;
document.head.appendChild(spinStyle);

/* =====================================================================
   Chart.js Visualization Initialization Routines (Enhanced with Gradients)
   ===================================================================== */

/**
 * Overview View: Duration Trend Line Chart & Decision Doughnut
 */
function initOverviewCharts(trendLabels, durationData, optimizedCount, fallbackCount, unplannedCount) {
  const trendCtx = document.getElementById("durationTrendChart");
  if (trendCtx && typeof Chart !== "undefined") {
    const labels = trendLabels && trendLabels.length ? trendLabels : [];
    const data = durationData && durationData.length ? durationData : [];

    const gradient = trendCtx.getContext("2d").createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, "rgba(59, 130, 246, 0.28)");
    gradient.addColorStop(1, "rgba(59, 130, 246, 0.0)");

    new Chart(trendCtx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Pipeline Duration (seconds)",
          data: data,
          borderColor: "#3b82f6",
          backgroundColor: gradient,
          fill: true,
          tension: 0.35,
          borderWidth: 2.5,
          pointBackgroundColor: "#06b6d4",
          pointBorderColor: "#ffffff",
          pointBorderWidth: 1.5,
          pointHoverRadius: 7,
          pointRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => ` Duration: ${context.parsed.y}s`
            }
          }
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
            title: { display: true, text: "Duration (Seconds)", color: "#64748b" }
          }
        }
      }
    });
  }

  const decisionCtx = document.getElementById("decisionDoughnutChart");
  if (decisionCtx && typeof Chart !== "undefined") {
    const opt = Number(optimizedCount) || 0;
    const fall = Number(fallbackCount) || 0;
    const unpl = Number(unplannedCount) || 0;
    const total = opt + fall + unpl;

    new Chart(decisionCtx, {
      type: "doughnut",
      data: {
        labels: total > 0
          ? ["Planned Optimized", "Deterministic Fallback", "Direct / Baseline"]
          : ["No Executions Yet"],
        datasets: [{
          data: total > 0 ? [opt, fall, unpl] : [1],
          backgroundColor: total > 0 ? ["#10b981", "#8b5cf6", "#64748b"] : ["#1e293b"],
          borderColor: "#0a101f",
          borderWidth: 3,
          hoverOffset: 6,
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
              font: { size: 12, weight: "600" }
            }
          }
        },
        cutout: "70%"
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

    const gradientCpu = ctx.getContext("2d").createLinearGradient(0, 0, 0, 260);
    gradientCpu.addColorStop(0, "rgba(6, 182, 212, 0.22)");
    gradientCpu.addColorStop(1, "rgba(6, 182, 212, 0.0)");

    const gradientMem = ctx.getContext("2d").createLinearGradient(0, 0, 0, 260);
    gradientMem.addColorStop(0, "rgba(139, 92, 246, 0.22)");
    gradientMem.addColorStop(1, "rgba(139, 92, 246, 0.0)");

    new Chart(ctx, {
      type: "line",
      data: {
        labels: chartLabels,
        datasets: [
          {
            label: "Avg CPU Utilization (%)",
            data: cpu,
            borderColor: "#06b6d4",
            backgroundColor: gradientCpu,
            fill: true,
            tension: 0.35,
            borderWidth: 2.2,
            pointRadius: 3.5,
            pointBackgroundColor: "#06b6d4",
            yAxisID: "yCpu",
          },
          {
            label: "Peak Memory (MB)",
            data: mem,
            borderColor: "#8b5cf6",
            backgroundColor: gradientMem,
            fill: true,
            tension: 0.35,
            borderWidth: 2.2,
            pointRadius: 3.5,
            pointBackgroundColor: "#8b5cf6",
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
            labels: { boxWidth: 12, color: "#94a3b8", font: { weight: "600" } }
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
          backgroundColor: values.map((v) => (v >= 0.35 ? "rgba(244, 63, 94, 0.78)" : "rgba(59, 130, 246, 0.78)")),
          borderColor: values.map((v) => (v >= 0.35 ? "#f43f5e" : "#3b82f6")),
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => ` Risk Probability: ${(context.parsed.y * 100).toFixed(1)}%`
            }
          }
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
