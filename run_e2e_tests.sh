#!/bin/bash
# =============================================================================
# PSAN Radar - Orchestrated E2E Test Runner
# =============================================================================
# This script:
# 1. Verifies backend and frontend ports are open
# 2. Runs backend E2E tests (pytest)
# 3. Runs frontend E2E tests (pytest + Playwright)
# 4. Prints a clean summary table
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
# Use Windows host IP from WSL (default gateway)
WSL_HOST_IP="${WSL_HOST_IP:-172.28.192.1}"
FRONTEND_URL="${FRONTEND_URL:-http://${WSL_HOST_IP}:5173}"
BACKEND_PORT=8000
FRONTEND_PORT=5173
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tests"

# Test result tracking
BACKEND_RESULT=0
FRONTEND_RESULT=0
BACKEND_OUTPUT=""
FRONTEND_OUTPUT=""

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

print_header() {
    echo -e "\n${BLUE}==============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==============================================================================${NC}\n"
}

print_step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_port() {
    local host=$1
    local port=$2
    local service=$3
    
    print_step "Checking $service on $host:$port..."
    
    if command -v nc >/dev/null 2>&1; then
        if nc -z "$host" "$port" 2>/dev/null; then
            print_success "$service is reachable on port $port"
            return 0
        fi
    elif command -v timeout >/dev/null 2>&1; then
        if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
            print_success "$service is reachable on port $port"
            return 0
        fi
    elif command -v python3 >/dev/null 2>&1; then
        if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('$host', $port)); s.close()" 2>/dev/null; then
            print_success "$service is reachable on port $port"
            return 0
        fi
    fi
    
    print_error "$service is NOT reachable on port $port"
    return 1
}

wait_for_service() {
    local url=$1
    local service=$2
    local max_attempts=30
    local attempt=1
    
    print_step "Waiting for $service at $url..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f -o /dev/null --max-time 5 "$url" 2>/dev/null; then
            print_success "$service is ready"
            return 0
        fi
        
        if [ $((attempt % 5)) -eq 0 ]; then
            print_info "Attempt $attempt/$max_attempts - still waiting..."
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "$service did not become ready after $max_attempts attempts"
    return 1
}

run_backend_tests() {
    print_header "RUNNING BACKEND E2E TESTS"
    
    cd "$TEST_DIR"
    
    print_step "Executing: pytest test_backend_e2e.py -v --tb=short"
    
    if python -m pytest test_backend_e2e.py -v --tb=short 2>&1; then
        BACKEND_RESULT=0
        print_success "Backend tests PASSED"
    else
        BACKEND_RESULT=$?
        print_error "Backend tests FAILED (exit code: $BACKEND_RESULT)"
    fi
}

run_frontend_tests() {
    print_header "RUNNING FRONTEND E2E TESTS"
    
    cd "$TEST_DIR"
    
    print_step "Executing: pytest test_frontend_e2e.py -v --tb=short"
    
    if python -m pytest test_frontend_e2e.py -v --tb=short 2>&1; then
        FRONTEND_RESULT=0
        print_success "Frontend tests PASSED"
    else
        FRONTEND_RESULT=$?
        print_error "Frontend tests FAILED (exit code: $FRONTEND_RESULT)"
    fi
}

print_summary() {
    print_header "TEST SUMMARY"
    
    echo -e "${BLUE}┌────────────────────────┬──────────┬────────────────────────────────┐${NC}"
    echo -e "${BLUE}│ Test Suite             │ Status   │ Details                        │${NC}"
    echo -e "${BLUE}├────────────────────────┼──────────┼────────────────────────────────┤${NC}"
    
    if [ $BACKEND_RESULT -eq 0 ]; then
        echo -e "${BLUE}│${NC} Backend E2E Tests      │ ${GREEN}PASS${NC}    │ All API, BOM, WebSocket tests  │${NC}"
    else
        echo -e "${BLUE}│${NC} Backend E2E Tests      │ ${RED}FAIL${NC}    │ Exit code: $BACKEND_RESULT                        │${NC}"
    fi
    
    if [ $FRONTEND_RESULT -eq 0 ]; then
        echo -e "${BLUE}│${NC} Frontend E2E Tests     │ ${GREEN}PASS${NC}    │ All Playwright UI tests        │${NC}"
    else
        echo -e "${BLUE}│${NC} Frontend E2E Tests     │ ${RED}FAIL${NC}    │ Exit code: $FRONTEND_RESULT                        │${NC}"
    fi
    
    echo -e "${BLUE}└────────────────────────┴──────────┴────────────────────────────────┘${NC}"
    
    echo ""
    
    if [ $BACKEND_RESULT -eq 0 ] && [ $FRONTEND_RESULT -eq 0 ]; then
        print_success "ALL TESTS PASSED ✓"
        return 0
    else
        print_error "SOME TESTS FAILED ✗"
        return 1
    fi
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    print_header "PSAN RADAR - E2E TEST RUNNER"
    print_info "Backend:  $BACKEND_URL"
    print_info "Frontend: $FRONTEND_URL"
    print_info "Test Dir: $TEST_DIR"
    
    # Step 1: Check ports
    print_header "SERVICE AVAILABILITY CHECK"
    
    check_port "localhost" $BACKEND_PORT "Backend API" || true
    check_port "localhost" $FRONTEND_PORT "Frontend" || true
    
    # Step 2: Wait for services to be fully ready
    wait_for_service "$BACKEND_URL/api/v1/health" "Backend API" || {
        print_error "Backend health check failed. Is the server running?"
        exit 1
    }
    
    wait_for_service "$FRONTEND_URL" "Frontend" || {
        print_error "Frontend not accessible. Is Vite dev server running?"
        exit 1
    }
    
    # Step 3: Install Playwright browsers if needed
    print_header "PLAYWRIGHT SETUP"
    print_step "Ensuring Playwright Chromium is installed..."
    if python -m playwright install chromium 2>&1 | tail -5; then
        print_success "Playwright Chromium ready"
    else
        print_error "Failed to install Playwright Chromium"
        exit 1
    fi
    
    # Step 4: Run backend tests
    run_backend_tests
    
    # Step 5: Run frontend tests
    run_frontend_tests
    
    # Step 6: Print summary
    print_summary
    
    # Exit with appropriate code
    if [ $BACKEND_RESULT -eq 0 ] && [ $FRONTEND_RESULT -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"