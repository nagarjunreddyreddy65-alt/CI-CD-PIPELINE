# Autonomous DevOps
## An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Ruff](https://img.shields.io/badge/Code%20Style-Ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Bandit](https://img.shields.io/badge/Security-Bandit%20Clean-success.svg)](https://github.com/PyCQA/bandit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📌 Executive Summary

Modern Continuous Integration and Continuous Delivery (CI/CD) pipelines often expend extensive compute resources and developer time repeatedly executing non-impacted regression tests. Conversely, naive test-skipping approaches introduce unacceptable risk of escaped production defects.

**Autonomous DevOps** provides a balanced, secure, hybrid optimization framework combining:
1. **Python AST Dependency Analysis:** Traces exact module import hierarchies and maps altered code directly to affected unit/integration tests using directed graph algorithms (`NetworkX`).
2. **Machine Learning Predictive Intelligence:** Employs a **Random Forest Classifier** to assess pipeline failure risk and a **Random Forest Regressor** to forecast execution duration before tests run.
3. **Deterministic Safety Policy Engine:** Governed by the foundational law:
   > **"AI predicts. Deterministic safety rules decide."**  
   The AI model **never** unilaterally authorizes test skipping. If any of the **21 strict safety fallback conditions** are met (database schema migrations, authentication changes, lock-file modifications, unresolved dynamic imports, or low ML confidence), the engine deterministically forces a **Full Test Suite Fallback**.

---

## 🏗️ System Architecture

```text
DEVELOPER
    │
    ▼
GITHUB REPOSITORY
    │
    ▼
GITHUB ACTIONS RUNNER (Isolated test execution + security scans)
    │
    ├── 1. Extract Changed Files & Commit Metadata
    │
    ├── 2. Request Plan (Authenticated via X-Runner-Token)
    │                            │
    │                            ▼
    │                 FASTAPI BACKEND
    │                 ├── AST & NetworkX Dependency Analyzer
    │                 ├── ML Failure Risk & Runtime Predictors
    │                 ├── Deterministic Safety Policy (21 Fallback Rules)
    │                 └── PostgreSQL Store (with SQLite Fallback)
    │
    ◄── 3. Return Plan (OPTIMIZED Subset OR FULL_SUITE Fallback)
    │
    └── 4. Execute Tests & Report Telemetry ──► FASTAPI ──► WEB DASHBOARD (Chart.js)
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- **Python 3.11+** installed
- **Docker & Docker Compose** (optional for PostgreSQL containerization)
- **Git**

### 2. Clone and Setup Environment
```bash
git clone https://github.com/nagarjunreddyreddy65-alt/CI-CD-PIPELINE.git
cd CI-CD-PIPELINE

# Copy example environment configuration
cp .env.example .env
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run with Docker Compose (FastAPI + PostgreSQL 16)
```bash
docker-compose up -d
```
Once started, the services will be accessible at:
- **FastAPI Web Service:** `http://localhost:8000`
- **Interactive Swagger API Docs:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **PostgreSQL Database:** `localhost:5432` (`autonomous_devops_db`)
- **Web Dashboard:** `http://localhost:8000/dashboard`

### 5. Run on Kubernetes
Kubernetes manifests are provided in `k8s/` and validated for production deployment:
```bash
# 1. Create secret from production configuration (see k8s/secrets.example.yaml)
kubectl apply -f k8s/secrets.example.yaml

# 2. Deploy infrastructure and application services
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```
> [!NOTE]
> All Kubernetes manifests are syntactically and structurally validated. Database credentials and API keys are strictly decoupled from manifest source files using `secretKeyRef` referencing `autonomous-devops-secrets`. Full cluster deployment requires an active Kubernetes cluster with secrets applied.

### 6. Run Locally Without Docker (Automatic SQLite Fallback)
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🔒 Security & API Access Control

All runner-facing write endpoints and sensitive operational read endpoints require constant-time pre-shared token comparison via `hmac.compare_digest` with the `X-Runner-Token` header:
- `POST /api/v1/plans/generate` — Generates execution plans (historical runs verified server-side).
- `GET /api/v1/plans/{plan_id}` & `GET /api/v1/plans` — Retrieves operational plan audit history.
- `POST /api/v1/analysis/diff` — Evaluates commit diff and maps test dependencies.
- `POST /api/v1/telemetry/record` — Records CPU, memory, and duration telemetry.
- `POST /api/v1/telemetry/detect-anomalies` — Z-score performance anomaly detection.
- `POST /api/v1/telemetry/correlate-failures` — Groups failures by normalized error signature.
- `GET /api/v1/telemetry/history` — Retrieves pipeline telemetry history.
- `POST /api/v1/security/scan` & `GET /api/v1/security/scans/{pipeline_run_id}` — Audits security reports.
- `POST /api/v1/predictions/predict` & `POST /api/v1/predictions/train` — ML model inference and training.

Public read-only endpoints:
- `GET /api/v1/health` — Liveness health check.
- `GET /api/v1/ready` — Readiness check (returns HTTP 503 if database disconnected).
- `GET /dashboard/*`, `GET /api/v1/dashboard/metrics` — Visual dashboard views and chart metrics.
- `GET /api/v1/analysis/graph`, `GET /api/v1/predictions/models` — Public system status and model metadata.

In production (`ENVIRONMENT=production`):
- Startup configuration validation strictly enforces that default secrets (`SECRET_KEY`, `RUNNER_API_KEY`) and default database passwords are overridden.
- Database connection failure at application startup raises an immediate fatal exception (fail-fast).
- Path traversal protection is strictly enforced across all file input payloads.
- Database persistence failure during plan generation triggers Safety Rule 21 fail-closed fallback to `FULL_SUITE`.

---

## 🧪 Verification & Automated Testing

All core components, API endpoints, sample application modules, safety rules, ML model loading, and authentication layers are strictly verified:

### 1. Run Complete Test Suite (280 tests, 100% pass rate)
```bash
python -m pytest tests/ tests_sample_app/ -v
```

### 2. Code Quality & Linting (Ruff)
```bash
ruff check .
ruff format --check .
```
*(0 violations across all repository files; 100% formatted)*

### 3. Security Auditing (Bandit SAST, pip-audit SCA, Gitleaks)
```bash
bandit -r app sample_app -ll -ii
pip-audit -r requirements.txt --desc on
```
*(0 High/Medium security issues; 0 dependency vulnerabilities; Gitleaks clean)*

### 4. End-to-End Benchmarking & Controlled Defect Injection
```bash
python scripts/benchmark_e2e.py
```
*(Executes 15 benchmark scenarios, controlled defect injection, dynamically calculates safety compliance, and exports `data/e2e_benchmark_report.json`)*

### 5. Train Machine Learning Models on Genuine TravisTorrent Dataset
```bash
python scripts/train_travistorrent_models.py
```
*(Trains Balanced Random Forest Classifier and Regressor on 3,808 genuine builds from TravisTorrent DSpace repository; produces serialized models and updates `model_metadata.json`)*

### 6. Reproduce Empirical ML Evaluation Figures
```bash
python scripts/generate_ml_evaluation_graphs.py
```
*(Generates all 6 publication-quality ML and telemetry evaluation figures in `docs/figures/ml_evaluation/` and `app/static/graphs/`)*

---

## 📚 Project Documentation

- [TravisTorrent ML Integration & Audit Report](TRAVISTORRENT_ML_INTEGRATION_REPORT.md) — Comprehensive dataset provenance, holdout metrics, model limitations, and verification.
- [System Architecture](docs/ARCHITECTURE.md) — 5-tier architecture, security boundaries, and data flows.
- [Project Plan & Roadmap](docs/PROJECT_PLAN.md) — Complete milestone records and deliverables.
- [Deterministic Safety Policy (21 Rules)](docs/SAFETY_POLICY.md) — Exhaustive specification of all 21 fallback conditions.
- [Machine Learning Empirical Evaluation](docs/ML_EVALUATION_RESULTS.md) — Empirical ML benchmarks, ROC curve, feature importances, and telemetry Z-scores.
- [Testing, Benchmarking & Evaluation](docs/TESTING_AND_EVALUATION.md) — Empirical benchmark reports, test matrices, and defect analysis.
- [Development Log](docs/DEVELOPMENT_LOG.md) — Chronological record of engineering decisions and audit resolutions.
- [IEEE Research Paper Structure](docs/IEEE_PAPER_STRUCTURE.md) — Academic publication draft with mathematical modeling and empirical limitations.
- [Viva Voce Defense Guide](docs/VIVA_DEFENSE_GUIDE.md) — Comprehensive 7-section viva exam preparation and architectural defenses.

---

## 📄 License
This project is developed for academic evaluation, research, and open-source contribution under the **MIT License**.
