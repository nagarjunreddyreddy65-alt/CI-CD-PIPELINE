# Autonomous DevOps Workflow Demonstration (Windows PowerShell)

$BACKEND_URL = "http://127.0.0.1:8000"
$RUNNER_API_KEY = "autonomous_devops_runner_dev_api_key_2026"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Autonomous DevOps: Workflow Demonstration Script           ║" -ForegroundColor Cyan
Write-Host "║   AI-Driven CI/CD Pipeline Optimization                     ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Health Check
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 0: Health Check - Verify Backend is Running" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

try {
    $healthResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/health" -Method GET -UseBasicParsing
    $health = $healthResponse.Content | ConvertFrom-Json
    
    Write-Host "✅ Backend is HEALTHY" -ForegroundColor Green
    Write-Host "   Service: $($health.service)" -ForegroundColor Green
    Write-Host "   Version: $($health.version)" -ForegroundColor Green
    Write-Host "   Environment: $($health.environment)" -ForegroundColor Green
} catch {
    Write-Host "❌ Cannot connect to backend: $_" -ForegroundColor Red
    Write-Host "Run: docker compose up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Generate Execution Plan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 1: Generate Execution Plan" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$planRequest = @{
    repository_name = "AutonomousDevOps/CI-CD-PIPELINE"
    commit_hash = "c81a293f0b4d"
    branch = "main"
    author_name = "MCA Student"
    author_email = "student@example.edu"
    commit_message = "Fix floating point precision in division operator"
    changed_files = @(
        @{
            file_path = "sample_app/utils/math_ops.py"
            change_type = "MODIFIED"
            lines_added = 5
            lines_deleted = 2
        }
    )
    risk_threshold = 0.50
} | ConvertTo-Json

$headers = @{
    "X-Runner-Token" = $RUNNER_API_KEY
    "Content-Type" = "application/json"
}

Write-Host "Request: POST /api/v1/plans/generate" -ForegroundColor Yellow
Write-Host "Changed File: sample_app/utils/math_ops.py (5 lines added, 2 deleted)" -ForegroundColor Yellow
Write-Host ""

$planResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/plans/generate" `
    -Method POST `
    -Headers $headers `
    -Body $planRequest `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "Response:" -ForegroundColor Green
$planResponse | ConvertTo-Json -Depth 3 | Write-Host
Write-Host ""

$planId = $planResponse.plan_id
$runId = $planResponse.pipeline_run_id
$decision = $planResponse.decision
$testsReduction = $planResponse.tests_reduction_pct
$timeSaved = $planResponse.estimated_time_saved_sec

Write-Host "✅ Plan Generated:" -ForegroundColor Green
Write-Host "   Plan ID: $planId" -ForegroundColor Green
Write-Host "   Run ID: $runId" -ForegroundColor Green
Write-Host "   Decision: $decision" -ForegroundColor Green
Write-Host "   Test Reduction: $testsReduction%" -ForegroundColor Green
Write-Host "   Time Saved: $timeSaved seconds" -ForegroundColor Green
Write-Host ""

# Analyze Code Diff
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 2: Analyze Code Diff and Map Dependencies" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$diffRequest = @{
    repository_path = "."
    files = @(
        @{
            path = "sample_app/utils/math_ops.py"
            change_type = "MODIFIED"
            lines_added = 5
            lines_deleted = 2
        }
    )
} | ConvertTo-Json

Write-Host "Request: POST /api/v1/analysis/diff" -ForegroundColor Yellow
Write-Host ""

$diffResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/analysis/diff" `
    -Method POST `
    -Headers $headers `
    -Body $diffRequest `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "Affected Tests:" -ForegroundColor Green
$diffResponse.affected_test_identifiers | ForEach-Object { Write-Host "  • $_" -ForegroundColor Green }
Write-Host ""

# Record Telemetry
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 3: Record Pipeline Execution Telemetry" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$telemetryRequest = @{
    pipeline_run_id = $runId
    test_count = 3
    cpu_percent = 72.3
    memory_peak_mb = 256.8
    duration_sec = 14.2
    result_status = "SUCCESS"
    tests_passed = 3
    tests_failed = 0
} | ConvertTo-Json

Write-Host "Request: POST /api/v1/telemetry/record" -ForegroundColor Yellow
Write-Host "   Pipeline Run: $runId" -ForegroundColor Yellow
Write-Host "   Tests: 3 | CPU: 72.3% | Memory: 256.8 MB | Duration: 14.2s" -ForegroundColor Yellow
Write-Host ""

$telemetryResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/telemetry/record" `
    -Method POST `
    -Headers $headers `
    -Body $telemetryRequest `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "✅ Telemetry recorded successfully" -ForegroundColor Green
Write-Host ""

# Record Security Scan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 4: Record Security Scan Results" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$securityRequest = @{
    pipeline_run_id = $runId
    scanner_type = "BANDIT"
    scan_status = "PASSED"
    high_severity_count = 0
    medium_severity_count = 0
    low_severity_count = 0
    scan_summary = "SAST scan completed: 0 issues found"
    scan_details = '{"issues": [], "metrics": {"lines_analyzed": 1240}}'
} | ConvertTo-Json

Write-Host "Request: POST /api/v1/security/scan" -ForegroundColor Yellow
Write-Host "   Scanner: BANDIT (Static Application Security Testing)" -ForegroundColor Yellow
Write-Host "   Results: 0 High, 0 Medium, 0 Low severity" -ForegroundColor Yellow
Write-Host ""

$securityResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/security/scan" `
    -Method POST `
    -Headers $headers `
    -Body $securityRequest `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "✅ Security scan recorded successfully" -ForegroundColor Green
Write-Host ""

# Mark Pipeline Complete
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 5: Mark Pipeline Run as Complete" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$completionRequest = @{
    status = "SUCCESS"
    total_duration_sec = 45.8
    error_message = $null
} | ConvertTo-Json

Write-Host "Request: POST /api/v1/plans/runs/$runId/complete" -ForegroundColor Yellow
Write-Host "   Status: SUCCESS | Duration: 45.8s" -ForegroundColor Yellow
Write-Host ""

$completionResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/plans/runs/$runId/complete" `
    -Method POST `
    -Headers $headers `
    -Body $completionRequest `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "✅ Pipeline run marked as complete" -ForegroundColor Green
Write-Host ""

# Dashboard Metrics
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 6: Retrieve Dashboard Metrics" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "Request: GET /api/v1/dashboard/metrics" -ForegroundColor Yellow
Write-Host ""

$metricsResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/dashboard/metrics" `
    -Method GET `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "Dashboard Metrics:" -ForegroundColor Green
Write-Host "  Total Runs: $($metricsResponse.total_pipeline_runs)" -ForegroundColor Green
Write-Host "  Optimization Success Rate: $($metricsResponse.optimization_success_rate_pct)%" -ForegroundColor Green
Write-Host "  Cumulative Time Saved: $($metricsResponse.cumulative_time_saved_sec)s" -ForegroundColor Green
Write-Host "  Avg Test Reduction: $($metricsResponse.average_test_reduction_pct)%" -ForegroundColor Green
Write-Host "  ML Model Accuracy: $($metricsResponse.ml_model_accuracy)" -ForegroundColor Green
Write-Host ""

# ML Models
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 7: Retrieve ML Model Metadata" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "Request: GET /api/v1/predictions/models" -ForegroundColor Yellow
Write-Host ""

$modelsResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/predictions/models" `
    -Method GET `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "ML Models:" -ForegroundColor Green
$modelsResponse.models | ForEach-Object {
    Write-Host "  Model: $($_.model_name)" -ForegroundColor Green
    Write-Host "    Type: $($_.model_type)" -ForegroundColor Green
    Write-Host "    Version: $($_.version)" -ForegroundColor Green
    if ($_.training_accuracy) {
        Write-Host "    Accuracy: $($_.training_accuracy)" -ForegroundColor Green
    }
}
Write-Host ""

# Telemetry History
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "STEP 8: Retrieve Telemetry History" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "Request: GET /api/v1/telemetry/history" -ForegroundColor Yellow
Write-Host ""

$historyResponse = Invoke-WebRequest -Uri "$BACKEND_URL/api/v1/telemetry/history?limit=5" `
    -Method GET `
    -UseBasicParsing | Select-Object -ExpandProperty Content | ConvertFrom-Json

Write-Host "Recent Pipeline Runs:" -ForegroundColor Green
$historyResponse.telemetry_records | ForEach-Object {
    Write-Host "  Run: $($_.pipeline_run_id)" -ForegroundColor Green
    Write-Host "    Status: $($_.result_status) | Duration: $($_.duration_sec)s | CPU: $($_.cpu_percent)%" -ForegroundColor Green
}
Write-Host ""

# Summary
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "WORKFLOW DEMONSTRATION COMPLETE" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "✅ All Steps Executed Successfully" -ForegroundColor Green
Write-Host ""
Write-Host "Workflow Results:" -ForegroundColor Cyan
Write-Host "  Plan ID: $planId" -ForegroundColor Green
Write-Host "  Run ID: $runId" -ForegroundColor Green
Write-Host "  Decision: $decision" -ForegroundColor Green
Write-Host "  Test Reduction: $testsReduction%" -ForegroundColor Green
Write-Host "  Time Saved: $timeSaved seconds" -ForegroundColor Green
Write-Host ""

Write-Host "Access Points:" -ForegroundColor Cyan
Write-Host "  Dashboard: $BACKEND_URL/dashboard" -ForegroundColor Yellow
Write-Host "  API Docs: $BACKEND_URL/docs" -ForegroundColor Yellow
Write-Host "  ReDoc: $BACKEND_URL/redoc" -ForegroundColor Yellow
Write-Host ""

Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Autonomous DevOps: Where AI Predicts, Deterministic Safety Rules Decide" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
