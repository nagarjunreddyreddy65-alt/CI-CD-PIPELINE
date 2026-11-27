@echo off
REM Autonomous DevOps Workflow Demonstration (Windows Batch)
REM Interactive demonstration of the complete workflow

setlocal enabledelayedexpansion

set "BACKEND_URL=http://127.0.0.1:8000"
set "RUNNER_API_KEY=autonomous_devops_runner_dev_api_key_2026"

cls
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║   Autonomous DevOps: Workflow Demonstration Script           ║
echo ║   AI-Driven CI/CD Pipeline Optimization                     ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

REM Step 0: Health Check
echo ═══════════════════════════════════════════════════════════════
echo STEP 0: Health Check - Verify Backend is Running
echo ═══════════════════════════════════════════════════════════════
echo.

echo Checking backend health...
curl -s -X GET "%BACKEND_URL%/api/v1/health" > health_response.json
type health_response.json
echo.

REM Step 1: Generate Execution Plan
echo ═══════════════════════════════════════════════════════════════
echo STEP 1: Generate Execution Plan
echo ═══════════════════════════════════════════════════════════════
echo.

echo Generating execution plan for code change...

(
echo {
echo   "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
echo   "commit_hash": "c81a293f0b4d",
echo   "branch": "main",
echo   "author_name": "MCA Student",
echo   "author_email": "student@example.edu",
echo   "commit_message": "Fix floating point precision in division operator",
echo   "changed_files": [
echo     {
echo       "file_path": "sample_app/utils/math_ops.py",
echo       "change_type": "MODIFIED",
echo       "lines_added": 5,
echo       "lines_deleted": 2
echo     }
echo   ],
echo   "risk_threshold": 0.50
echo }
) > plan_request.json

curl -s -X POST "%BACKEND_URL%/api/v1/plans/generate" ^
  -H "X-Runner-Token: %RUNNER_API_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "@plan_request.json" > plan_response.json

echo Request: POST /api/v1/plans/generate
echo Response:
type plan_response.json
echo.

REM Step 2: Analyze Code Diff
echo ═══════════════════════════════════════════════════════════════
echo STEP 2: Analyze Code Diff
echo ═══════════════════════════════════════════════════════════════
echo.

(
echo {
echo   "repository_path": ".",
echo   "files": [
echo     {
echo       "path": "sample_app/utils/math_ops.py",
echo       "change_type": "MODIFIED",
echo       "lines_added": 5,
echo       "lines_deleted": 2
echo     }
echo   ]
echo }
) > diff_request.json

curl -s -X POST "%BACKEND_URL%/api/v1/analysis/diff" ^
  -H "X-Runner-Token: %RUNNER_API_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "@diff_request.json" > diff_response.json

echo Request: POST /api/v1/analysis/diff
echo Response:
type diff_response.json
echo.

REM Step 3: Get Plan ID from response (for telemetry)
for /f "tokens=*" %%a in ('type plan_response.json') do set "plan_data=%%a"
echo Plan data: !plan_data!
echo.

REM Step 4: Dashboard Metrics
echo ═══════════════════════════════════════════════════════════════
echo STEP 3: Retrieve Dashboard Metrics
echo ═══════════════════════════════════════════════════════════════
echo.

echo Retrieving aggregated dashboard metrics...
curl -s -X GET "%BACKEND_URL%/api/v1/dashboard/metrics" ^
  -H "Content-Type: application/json" > metrics_response.json

echo Response:
type metrics_response.json
echo.

REM Step 5: ML Models
echo ═══════════════════════════════════════════════════════════════
echo STEP 4: Retrieve ML Model Metadata
echo ═══════════════════════════════════════════════════════════════
echo.

echo Fetching ML model information...
curl -s -X GET "%BACKEND_URL%/api/v1/predictions/models" ^
  -H "Content-Type: application/json" > models_response.json

echo Response:
type models_response.json
echo.

REM Step 6: Telemetry History
echo ═══════════════════════════════════════════════════════════════
echo STEP 5: Retrieve Telemetry History
echo ═══════════════════════════════════════════════════════════════
echo.

echo Fetching recent pipeline telemetry...
curl -s -X GET "%BACKEND_URL%/api/v1/telemetry/history?limit=5" ^
  -H "Content-Type: application/json" > history_response.json

echo Response:
type history_response.json
echo.

REM Summary
echo ═══════════════════════════════════════════════════════════════
echo WORKFLOW DEMONSTRATION COMPLETE
echo ═══════════════════════════════════════════════════════════════
echo.

echo All API endpoints have been successfully demonstrated.
echo.
echo Response files saved:
echo   - health_response.json
echo   - plan_response.json
echo   - diff_response.json
echo   - metrics_response.json
echo   - models_response.json
echo   - history_response.json
echo.

echo Next Steps:
echo   Dashboard: %BACKEND_URL%/dashboard
echo   API Docs: %BACKEND_URL%/docs
echo   ReDoc: %BACKEND_URL%/redoc
echo.

echo ════════════════════════════════════════════════════════════════
echo Autonomous DevOps: Where AI Predicts, Deterministic Safety Rules Decide
echo ════════════════════════════════════════════════════════════════

REM Clean up temporary files
del /q plan_request.json diff_request.json 2>nul

endlocal
pause
