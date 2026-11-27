#!/bin/bash
# Autonomous DevOps Workflow Demonstration Script
# Interactive cURL examples for testing the complete API workflow

set -e

# Configuration
BACKEND_URL="http://127.0.0.1:8000"
RUNNER_API_KEY="autonomous_devops_runner_dev_api_key_2026"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Autonomous DevOps: Workflow Demonstration Script           ║${NC}"
echo -e "${BLUE}║   AI-Driven CI/CD Pipeline Optimization                     ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo

# Function to print section headers
print_section() {
    echo
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo
}

# Function to execute cURL with error handling
execute_api_call() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4

    echo -e "${YELLOW}📡 $description${NC}"
    echo -e "${YELLOW}Request:${NC} $method $endpoint"
    if [ -n "$data" ]; then
        echo -e "${YELLOW}Payload:${NC} (see below)"
    fi
    echo

    if [ "$method" = "POST" ]; then
        response=$(curl -s -X POST "$BACKEND_URL$endpoint" \
            -H "X-Runner-Token: $RUNNER_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$data")
    else
        response=$(curl -s -X GET "$BACKEND_URL$endpoint" \
            -H "Content-Type: application/json")
    fi

    echo -e "${GREEN}Response:${NC}"
    echo "$response" | jq '.' 2>/dev/null || echo "$response"
    echo
}

# Function to extract value from JSON response
extract_json_value() {
    echo "$1" | jq -r "$2"
}

# ============================================================================
# Step 0: Health Check
# ============================================================================

print_section "STEP 0: Health Check - Verify Backend is Running"

response=$(curl -s -X GET "$BACKEND_URL/api/v1/health")
status=$(echo "$response" | jq -r '.status' 2>/dev/null)

if [ "$status" = "HEALTHY" ]; then
    echo -e "${GREEN}✅ Backend is HEALTHY and responding${NC}"
    echo -e "${GREEN}Service: $(echo $response | jq -r '.service')${NC}"
    echo -e "${GREEN}Version: $(echo $response | jq -r '.version')${NC}"
    echo -e "${GREEN}Environment: $(echo $response | jq -r '.environment')${NC}"
else
    echo -e "${RED}❌ Backend health check failed${NC}"
    echo -e "${RED}Response: $response${NC}"
    exit 1
fi

# ============================================================================
# Step 1: Generate Execution Plan (Simple Optimization)
# ============================================================================

print_section "STEP 1: Generate Execution Plan - Utility Module Change (Safe to Optimize)"

PLAN_REQUEST=$(cat <<'EOF'
{
  "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
  "commit_hash": "c81a293f0b4d",
  "branch": "main",
  "author_name": "MCA Student",
  "author_email": "student@example.edu",
  "commit_message": "Fix floating point precision in division operator",
  "changed_files": [
    {
      "file_path": "sample_app/utils/math_ops.py",
      "change_type": "MODIFIED",
      "lines_added": 5,
      "lines_deleted": 2
    }
  ],
  "risk_threshold": 0.50
}
EOF
)

PLAN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/plans/generate" \
    -H "X-Runner-Token: $RUNNER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$PLAN_REQUEST")

echo -e "${YELLOW}Request: POST /api/v1/plans/generate${NC}"
echo -e "${YELLOW}Commit: Fix floating point precision in division operator${NC}"
echo -e "${YELLOW}Changed File: sample_app/utils/math_ops.py${NC}"
echo
echo -e "${GREEN}Response:${NC}"
echo "$PLAN_RESPONSE" | jq '.'
echo

# Extract plan_id and run_id for later use
PLAN_ID=$(echo "$PLAN_RESPONSE" | jq -r '.plan_id')
RUN_ID=$(echo "$PLAN_RESPONSE" | jq -r '.pipeline_run_id')
DECISION=$(echo "$PLAN_RESPONSE" | jq -r '.decision')
TESTS_REDUCTION=$(echo "$PLAN_RESPONSE" | jq -r '.tests_reduction_pct')
TIME_SAVED=$(echo "$PLAN_RESPONSE" | jq -r '.estimated_time_saved_sec')

if [ "$DECISION" = "OPTIMIZED" ]; then
    echo -e "${GREEN}✅ OPTIMIZED PLAN GENERATED${NC}"
    echo -e "${GREEN}   Plan ID: $PLAN_ID${NC}"
    echo -e "${GREEN}   Run ID: $RUN_ID${NC}"
    echo -e "${GREEN}   Test Reduction: ${TESTS_REDUCTION}%${NC}"
    echo -e "${GREEN}   Estimated Time Saved: ${TIME_SAVED}s${NC}"
else
    echo -e "${YELLOW}⚠️  FULL_SUITE FALLBACK${NC}"
    echo -e "${YELLOW}   Reason: $(echo $PLAN_RESPONSE | jq -r '.fallback_reason')${NC}"
fi

# ============================================================================
# Step 2: Analyze Code Diff Dependencies
# ============================================================================

print_section "STEP 2: Analyze Code Diff and Map Test Dependencies"

DIFF_REQUEST=$(cat <<'EOF'
{
  "repository_path": ".",
  "files": [
    {
      "path": "sample_app/utils/math_ops.py",
      "change_type": "MODIFIED",
      "lines_added": 5,
      "lines_deleted": 2
    }
  ]
}
EOF
)

DIFF_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/analysis/diff" \
    -H "X-Runner-Token: $RUNNER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$DIFF_REQUEST")

echo -e "${YELLOW}Request: POST /api/v1/analysis/diff${NC}"
echo -e "${YELLOW}File: sample_app/utils/math_ops.py${NC}"
echo
echo -e "${GREEN}Response (Dependencies Mapped):${NC}"
echo "$DIFF_RESPONSE" | jq '.affected_test_identifiers'
echo

# Extract affected tests
AFFECTED_TESTS=$(echo "$DIFF_RESPONSE" | jq -r '.affected_test_identifiers | length')
echo -e "${GREEN}Affected Tests: $AFFECTED_TESTS${NC}"
echo

# ============================================================================
# Step 3: Record Execution Telemetry
# ============================================================================

print_section "STEP 3: Record Pipeline Execution Telemetry"

TELEMETRY_REQUEST=$(cat <<EOF
{
  "pipeline_run_id": "$RUN_ID",
  "test_count": 3,
  "cpu_percent": 72.3,
  "memory_peak_mb": 256.8,
  "duration_sec": 14.2,
  "result_status": "SUCCESS",
  "tests_passed": 3,
  "tests_failed": 0
}
EOF
)

TELEMETRY_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/telemetry/record" \
    -H "X-Runner-Token: $RUNNER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$TELEMETRY_REQUEST")

echo -e "${YELLOW}Request: POST /api/v1/telemetry/record${NC}"
echo -e "${YELLOW}Pipeline Run: $RUN_ID${NC}"
echo -e "${YELLOW}Tests Executed: 3 | CPU: 72.3% | Memory Peak: 256.8 MB | Duration: 14.2s${NC}"
echo
echo -e "${GREEN}Response:${NC}"
echo "$TELEMETRY_RESPONSE" | jq '.'
echo

if echo "$TELEMETRY_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Telemetry recorded successfully${NC}"
else
    echo -e "${YELLOW}⚠️  Telemetry recording may have issues${NC}"
fi

# ============================================================================
# Step 4: Record Security Scan Results
# ============================================================================

print_section "STEP 4: Record Security Scan Results"

SECURITY_REQUEST=$(cat <<EOF
{
  "pipeline_run_id": "$RUN_ID",
  "scanner_type": "BANDIT",
  "scan_status": "PASSED",
  "high_severity_count": 0,
  "medium_severity_count": 0,
  "low_severity_count": 0,
  "scan_summary": "SAST scan completed: 0 issues found",
  "scan_details": "{\\"issues\\": [], \\"metrics\\": {\\"lines_analyzed\\": 1240}}"
}
EOF
)

SECURITY_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/security/scan" \
    -H "X-Runner-Token: $RUNNER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$SECURITY_REQUEST")

echo -e "${YELLOW}Request: POST /api/v1/security/scan${NC}"
echo -e "${YELLOW}Scanner: BANDIT (Static Application Security Testing)${NC}"
echo -e "${YELLOW}Results: 0 High, 0 Medium, 0 Low severity findings${NC}"
echo
echo -e "${GREEN}Response:${NC}"
echo "$SECURITY_RESPONSE" | jq '.'
echo

if echo "$SECURITY_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Security scan recorded successfully${NC}"
fi

# ============================================================================
# Step 5: Mark Pipeline Run as Complete
# ============================================================================

print_section "STEP 5: Mark Pipeline Run as Complete"

COMPLETION_REQUEST=$(cat <<'EOF'
{
  "status": "SUCCESS",
  "total_duration_sec": 45.8,
  "error_message": null
}
EOF
)

COMPLETION_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/plans/runs/$RUN_ID/complete" \
    -H "X-Runner-Token: $RUNNER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$COMPLETION_REQUEST")

echo -e "${YELLOW}Request: POST /api/v1/plans/runs/$RUN_ID/complete${NC}"
echo -e "${YELLOW}Status: SUCCESS${NC}"
echo -e "${YELLOW}Total Duration: 45.8s${NC}"
echo
echo -e "${GREEN}Response:${NC}"
echo "$COMPLETION_RESPONSE" | jq '.'
echo

if echo "$COMPLETION_RESPONSE" | jq -e '.success' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Pipeline run marked as complete${NC}"
fi

# ============================================================================
# Step 6: Retrieve Dashboard Metrics
# ============================================================================

print_section "STEP 6: Retrieve Dashboard Metrics"

METRICS_RESPONSE=$(curl -s -X GET "$BACKEND_URL/api/v1/dashboard/metrics" \
    -H "Content-Type: application/json")

echo -e "${YELLOW}Request: GET /api/v1/dashboard/metrics${NC}"
echo
echo -e "${GREEN}Response (Key Metrics):${NC}"
echo "$METRICS_RESPONSE" | jq '.
{
  total_runs: .total_pipeline_runs,
  success_rate: .optimization_success_rate_pct,
  time_saved: .cumulative_time_saved_sec,
  test_reduction: .average_test_reduction_pct,
  ml_accuracy: .ml_model_accuracy
}'
echo

# ============================================================================
# Step 7: Retrieve ML Model Metadata
# ============================================================================

print_section "STEP 7: Retrieve ML Model Metadata"

MODELS_RESPONSE=$(curl -s -X GET "$BACKEND_URL/api/v1/predictions/models" \
    -H "Content-Type: application/json")

echo -e "${YELLOW}Request: GET /api/v1/predictions/models${NC}"
echo
echo -e "${GREEN}Response (Model Information):${NC}"
echo "$MODELS_RESPONSE" | jq '.models[] | {
  name: .model_name,
  type: .model_type,
  version: .version,
  accuracy: (if has("training_accuracy") then .training_accuracy else "N/A" end)
}'
echo

# ============================================================================
# Step 8: Retrieve Telemetry History
# ============================================================================

print_section "STEP 8: Retrieve Telemetry History"

HISTORY_RESPONSE=$(curl -s -X GET "$BACKEND_URL/api/v1/telemetry/history?limit=5&offset=0" \
    -H "Content-Type: application/json")

echo -e "${YELLOW}Request: GET /api/v1/telemetry/history (limit=5)${NC}"
echo
echo -e "${GREEN}Response (Recent Pipeline Runs):${NC}"
echo "$HISTORY_RESPONSE" | jq '.telemetry_records[] | {
  run_id: .pipeline_run_id,
  status: .result_status,
  duration_sec: .duration_sec,
  cpu_percent: .cpu_percent,
  memory_mb: .memory_peak_mb
}'
echo

# ============================================================================
# Summary Report
# ============================================================================

print_section "WORKFLOW DEMONSTRATION COMPLETE - SUMMARY REPORT"

echo -e "${GREEN}✅ All API Endpoints Successfully Demonstrated${NC}"
echo
echo -e "${BLUE}Workflow Steps Executed:${NC}"
echo -e "  1. ✅ Health Check - Backend is running and healthy"
echo -e "  2. ✅ Generate Execution Plan - Utility module optimization"
echo -e "  3. ✅ Analyze Code Diff - Dependencies mapped"
echo -e "  4. ✅ Record Telemetry - CPU, memory, duration captured"
echo -e "  5. ✅ Record Security Scan - SAST results stored"
echo -e "  6. ✅ Mark Run Complete - Pipeline status updated"
echo -e "  7. ✅ Retrieve Metrics - Dashboard data aggregated"
echo -e "  8. ✅ Retrieve ML Models - Model metadata retrieved"
echo -e "  9. ✅ Retrieve History - Telemetry history displayed"
echo
echo -e "${BLUE}Key Outcomes:${NC}"
echo -e "  • Plan ID: $PLAN_ID"
echo -e "  • Run ID: $RUN_ID"
echo -e "  • Decision: $DECISION"
echo -e "  • Test Reduction: ${TESTS_REDUCTION}%"
echo -e "  • Time Saved: ${TIME_SAVED}s"
echo
echo -e "${BLUE}Next Steps:${NC}"
echo -e "  • View Dashboard: ${BACKEND_URL}/dashboard"
echo -e "  • API Documentation: ${BACKEND_URL}/docs"
echo -e "  • ReDoc Docs: ${BACKEND_URL}/redoc"
echo
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Autonomous DevOps: Where AI Predicts, Deterministic Safety Rules Decide${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
