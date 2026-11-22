An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📌 Executive Summary

Modern Continuous Integration and Continuous Delivery (CI/CD) pipelines often waste substantial developer time and cloud compute resources executing extensive, redundant regression test suites on minor or non-impactful code changes. Conversely, naively skipping tests risks escaping severe bugs to production.

**Autonomous DevOps** solves this dilemma through an intelligent, hybrid optimization framework combining:
1. **Python AST Dependency Analysis:** Traces exact module import hierarchies and maps altered code directly to affected unit/integration tests using directed graph algorithms (`NetworkX`).
2. **Machine Learning Predictive Intelligence:** Employs a **Random Forest Classifier** to assess pipeline failure probability and a **Random Forest Regressor** to predict expected execution duration before tests run.
3. **Deterministic Safety Policy Engine:** Governed by the foundational law:
   > **"AI predicts. Deterministic safety rules decide."**  
   The AI model **never** unilaterally authorizes skipping a test. If any of the **21 strict safety fallback conditions** are met (e.g. database migration changes, auth changes, lock-file modifications, unresolved imports, or low ML confidence), the engine deterministically forces a **Full Test Suite Fallback**.

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
    ├── 2. Request Plan ──► FASTAPI BACKEND (Analysis + ML + Safety Policy Engine)
    │                            │
    │                            ├── Change & AST Dependency Analyzer
    │                            ├── ML Failure Risk & Runtime Predictors
    │                            ├── Deterministic Safety Policy (21 Fallback Rules)
    │                            └── PostgreSQL Persistence & Telemetry Store
    │
    ◄── 3. Return Plan (Optimized Subset OR Full-Suite Fallback)
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

### 4. Run with Docker Compose (FastAPI + PostgreSQL)
```bash
docker-compose up -d
```
Once started, the services will be accessible at:
- **FastAPI Web Service:** `http://localhost:8000`
- **Interactive Swagger API Docs:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **PostgreSQL Database:** `localhost:5432` (`autonomous_devops_db`)

### 5. Run Locally Without Docker (SQLite Fallback)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 Running Automated Tests

All modules adhere to strict test verification:
```bash
python -m pytest tests/ -v
```

---

## 📚 Project Documentation

- [System Architecture](docs/ARCHITECTURE.md)
- [Project Plan & 8-Phase Roadmap](docs/PROJECT_PLAN.md)
- [Deterministic Safety Policy (21 Rules)](docs/SAFETY_POLICY.md)

---

## 📄 License
This project is developed for academic evaluation, research, and open-source contribution under the **MIT License**.
