# Deterministic Safety Policy: The 21 Fallback Scenarios
## Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization

---

## 1. Guiding Axiom

> **"The AI predicts probability; deterministic safety rules decide execution."**  
> Under NO circumstance is an AI model permitted to bypass safety rules or independently authorize skipping tests.

---

## 2. The 21 Mandatory Fallback Scenarios

Whenever any of the following 21 scenarios is detected, the decision engine **must immediately force full test suite execution** (`FULL_SUITE`):

1. **Database Migration Changes:** Schema alterations, Alembic migration scripts, SQL scripts, or ORM model definitions.
2. **Authentication / Authorization Changes:** Modifications in security, token handling, JWT, RBAC, or user permission logic.
3. **Payment & Billing Changes:** Code paths touching transactions, payment gateways, currencies, or invoicing.
4. **Cryptographic & Sensitive Code:** Encryption, hashing, key generation, or certificate management modifications.
5. **Dependency Manifest Changes:** Modifications to `requirements.txt`, `pyproject.toml`, `setup.py`, or `Pipfile`.
6. **Lock-File Changes:** Changes to `uv.lock`, `poetry.lock`, or `Pipfile.lock`.
7. **CI/CD Workflow Configuration Changes:** Alterations in `.github/workflows/`, Dockerfiles, or build scripts.
8. **Unknown or Unsupported File Types:** Files modified that AST analyzers cannot parse (e.g. C extensions, binary files, shell scripts).
9. **AST Parsing Failures:** Syntax errors, invalid Python code, or encoding failures during AST generation.
10. **Unresolved Dynamic Imports:** Use of `__import__()`, `importlib.import_module()`, `eval()`, or `exec()`.
11. **Incomplete Dependency Graph:** Disconnected components or circular dependencies preventing confident topological sorting.
12. **Missing Test Mapping:** Changed code has no identified or mapped test cases.
13. **Empty Selected-Test List:** The optimization algorithm yielded zero tests for a non-empty commit.
14. **Missing or Untrained ML Model Artifact:** Machine learning model file is missing, corrupted, unreadable on disk, or not yet trained on pipeline telemetry (`is_trained == False`). Untrained heuristic models can never authorize test skipping.
15. **Stale or Incompatible Model:** Model version mismatch, feature dimension mismatch, or model expired.
16. **Invalid Prediction Output:** ML model returns NaN, infinite values, or probabilities outside $[0.0, 1.0]$.
17. **Insufficient Historical Training Data:** Pipeline runs for this repository $< 15$ runs. Historical count is verified server-side against genuine completed database records; caller-supplied historical counts are rejected and discarded.
18. **Low Prediction Confidence:** Model confidence score below configured threshold ($< 0.70$) or failure probability elevated.
19. **Optimization API Unreachable:** GitHub Actions runner cannot connect to backend or receives HTTP 5xx. Runner deterministically executes full suite.
20. **GitHub API Failure After Retry:** Inability to retrieve git diff or commit metadata after bounded retries.
21. **Database Persistence Failure / Unverifiable Safety:** Audit record cannot be stored in database, transaction failure, or any edge case where safety cannot be proven conclusively (fail-closed to `FULL_SUITE`).
