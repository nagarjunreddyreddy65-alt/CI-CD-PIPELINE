# Database Design Document
## Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization

---

## 1. Overview
The persistence layer utilizes **PostgreSQL 16** with **SQLAlchemy 2.0 ORM** and **Alembic** migrations. For offline test environments and local development, an automated fallback to SQLite is provided.

---

## 2. Entity Relationship Diagram (ERD)

```text
                  +--------------------+
                  |       users        |
                  +--------------------+
                            │
                            │
+--------------------+      │       +--------------------+
|    repositories    |◄─────┴───────┤     audit_logs     |
+--------------------+              +--------------------+
          │ 1
          │
          │ N
+--------------------+ 1          N +--------------------+
|      commits       |◄─────────────┤   changed_files    |
+--------------------+              +--------------------+
          │ 1
          │
          │ N
+--------------------+ 1          1 +--------------------+
|   pipeline_runs    |──────────────┤  execution_plans   |
+--------------------+              +--------------------+
  │ 1        │ 1       │ 1      │ 1
  │          │         │        │
  │ N        │ 1       │ N      │ N
  ▼          ▼         ▼        ▼
+----------+ +-------+ +------+ +----------------+
|test_cases| |tele-  | |pred- | | security_scans |
| & results| |metry  | |ictions| +----------------+
+----------+ +-------+ +------+
```

---

## 3. Entity Dictionary

1. **`users`**: Administrative and developer accounts for platform access.
2. **`repositories`**: Monitored GitHub code repositories.
3. **`commits`**: Individual Git revisions triggering pipeline workflows.
4. **`pipeline_runs`**: End-to-end execution records of GitHub Actions runs.
5. **`changed_files`**: Granular file diffs per commit (paths, lines added, lines deleted).
6. **`test_cases`**: Catalog of discoverable tests across the repository.
7. **`test_results`**: Individual test case pass/fail/skip outcome, duration, and stack traces.
8. **`execution_plans`**: Exact decision record (`OPTIMIZED` vs `FULL_SUITE`), test reduction percentages, and triggered safety rules.
9. **`predictions`**: AI model inference records (failure probability, expected duration, model version, features).
10. **`telemetry`**: Runner hardware metrics (average CPU, peak memory, runner OS).
11. **`model_versions`**: Registered ML models with evaluation metrics (F1-score, accuracy, MAE).
12. **`security_scans`**: Findings summary from Bandit, pip-audit, and Gitleaks.
13. **`deployments`**: Deployment event records with environment, approval, and status.
14. **`audit_logs`**: Immutable security and safety event logs.
