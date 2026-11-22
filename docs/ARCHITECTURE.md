# System Architecture Document
## Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization

---

## 1. Architectural Philosophy

The core architectural tenet of **Autonomous DevOps** is:

> **"AI predicts. Deterministic safety rules decide."**

Machine learning models provide probabilistic insights (failure likelihood and expected duration), but the decision to execute an optimized test subset versus triggering a full-suite fallback is governed by an unyielding, deterministic rule engine.

---

## 2. Component Diagram

```text
+--------------------------------------------------------------------------+
|                        Tier 1: Developer & GitHub                        |
+--------------------------------------------------------------------------+
       │ Push / Pull Request
       ▼
+--------------------------------------------------------------------------+
|                  Tier 2: GitHub Actions Runner Environment               |
|  - Clones repository in isolated, ephemeral sandbox                      |
|  - Extracts commit SHA, branch, and changed files git diff               |
|  - Queries FastAPI Optimization API for execution plan                  |
|  - Executes selected tests (or full suite fallback)                      |
|  - Runs security scanners: Bandit, pip-audit, Gitleaks                   |
|  - Sends execution telemetry & test results back to FastAPI API          |
+--------------------------------------------------------------------------+
       │ HTTPS / REST API with X-Runner-Token Auth
       ▼
+--------------------------------------------------------------------------+
|                     Tier 3: Autonomous DevOps FastAPI Backend            |
|  ┌────────────────────────────────────────────────────────────────────┐  |
|  │ Change & AST Dependency Analyzer (Python AST + NetworkX)           │  |
|  ├────────────────────────────────────────────────────────────────────┤  |
|  │ Machine Learning Engine:                                           │  |
|  │ - Random Forest Classifier (Failure Risk Prediction)               │  |
|  │ - Random Forest Regressor (Runtime Duration Prediction)            │  |
|  ├────────────────────────────────────────────────────────────────────┤  |
|  │ Deterministic Safety Policy Engine (21 Fallback Scenarios)         │  |
|  ├────────────────────────────────────────────────────────────────────┤  |
|  │ Telemetry Processing & Anomaly Detection                           │  |
|  └────────────────────────────────────────────────────────────────────┘  |
+--------------------------------------------------------------------------+
       │ SQLAlchemy 2.0 ORM
       ▼
+--------------------------------------------------------------------------+
|                     Tier 4: PostgreSQL Relational Database                |
|  - Repositories, Commits, Pipeline Runs, Execution Plans                 |
|  - Test Cases, Test Results, Predictions, Telemetry, Audit Logs          |
+--------------------------------------------------------------------------+
       ▲
       │ Query & Analytics
+--------------------------------------------------------------------------+
|                     Tier 5: Web Dashboard (HTML5 + Chart.js)             |
|  - Pipeline History, AI Insights, Test Reduction Analytics, Health        |
+--------------------------------------------------------------------------+
```

---

## 3. Data Flow

1. **Trigger:** A commit or PR occurs on GitHub.
2. **Metadata Extraction:** The GitHub Actions workflow inspects `git diff` to identify added, modified, and deleted files.
3. **Plan Request:** The runner sends changed files and commit metadata to `POST /api/v1/plans/generate`.
4. **AST Dependency Mapping:** The backend parses relevant Python files into ASTs and traverses the NetworkX dependency graph to find all affected test functions.
5. **ML Model Loading & Prediction:** The `DecisionEngine` automatically loads trained model artifacts at initialization (`load_models()`). Pre-execution features are extracted; if model artifacts are missing or untrained, Safety Rule 14 triggers `FULL_SUITE`. Out-of-sample holdout test splits (20%) validate real telemetry before production model deployment.
6. **Safety Evaluation:** The backend evaluates the **21 Safety Fallback Rules**. Historical runs ($\ge 15$) are validated server-side against genuine completed database records (caller-supplied counts are discarded). If any rule triggers (e.g., database schema change, untrained model), the plan enforces `decision = "FULL_SUITE"`. Otherwise, `decision = "OPTIMIZED"`.
7. **Database Audit & Fail-Closed Persistence:** The plan is persisted to the database. If a database error occurs during persistence, Safety Rule 21 immediately triggers: the transaction rolls back, and the plan mutates to `decision = "FULL_SUITE"` with `is_optimized = False` and `fallback_triggered = True` (fail-closed).
8. **Test Execution:** The isolated runner receives the plan, runs the exact test subset (or full suite), and records timing.
9. **Result & Telemetry Reporting:** Test results and CPU/RAM metrics are posted back to `POST /api/v1/telemetry/record` for long-term analytics and anomaly detection.
10. **Access Control & Health Probes:** Runner write endpoints and sensitive operational read endpoints (`/plans`, `/security/scans/{id}`, `/telemetry/history`) require constant-time pre-shared key validation (`X-Runner-Token`) using `hmac.compare_digest`. All file input paths are strictly validated against directory traversal attacks. Production mode enforces fail-fast database startup, and `/ready` returns HTTP 503 if the database is disconnected.
