#!/bin/bash

#########################################
# NZB Indexer - Validation Script
# Version: 0.9.0
#########################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Detect compose command
detect_compose() {
    if command -v podman-compose >/dev/null 2>&1; then
        echo "podman-compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

COMPOSE_CMD=$(detect_compose)

# Print functions
print_test_header() {
    echo -e "\n${BLUE}▶${NC} Testing: $1"
}

print_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_fail() {
    echo -e "  ${RED}✗${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_info() {
    echo -e "  ${BLUE}ℹ${NC} $1"
}

# Run a test
run_test() {
    TESTS_RUN=$((TESTS_RUN + 1))
}

# Test file existence
test_file_exists() {
    run_test
    if [ -f "$1" ]; then
        print_pass "File exists: $1"
        return 0
    else
        print_fail "File missing: $1"
        return 1
    fi
}

# Test file executable
test_file_executable() {
    run_test
    if [ -x "$1" ]; then
        print_pass "File executable: $1"
        return 0
    else
        print_fail "File not executable: $1"
        return 1
    fi
}

# Test container health
test_container_health() {
    run_test
    local container=$1
    local status=$($COMPOSE_CMD ps --format json | grep -o "\"Service\":\"$container\"" -A5 | grep -o "\"Health\":\"[^\"]*\"" | cut -d'"' -f4)

    if [ "$status" = "healthy" ] || [ -z "$status" ]; then
        print_pass "Container healthy: $container"
        return 0
    else
        print_fail "Container unhealthy: $container (status: $status)"
        return 1
    fi
}

# Test HTTP endpoint
test_http_endpoint() {
    run_test
    local url=$1
    local expected_code=${2:-200}

    local response_code=$(curl -s -o /dev/null -w "%{http_code}" "$url")

    if [ "$response_code" = "$expected_code" ]; then
        print_pass "HTTP endpoint: $url (got $response_code)"
        return 0
    else
        print_fail "HTTP endpoint: $url (expected $expected_code, got $response_code)"
        return 1
    fi
}

# Main validation
main() {
    echo "========================================="
    echo " NZB Indexer - Validation Script"
    echo "========================================="
    echo ""

    # Test 1: Required files
    print_test_header "Required Files"
    test_file_exists "docker-compose.yml"
    test_file_exists ".env.example"
    test_file_exists "Dockerfile"
    test_file_exists ".dockerignore"
    test_file_exists "requirements.txt"
    test_file_exists "install-podman.sh"
    test_file_executable "install-podman.sh"
    test_file_exists "scripts/utils.sh"
    test_file_executable "scripts/utils.sh"

    # Test 2: Docker/Podman availability
    print_test_header "Container Runtime"
    run_test
    if [ -n "$COMPOSE_CMD" ]; then
        print_pass "Container runtime found: $COMPOSE_CMD"
    else
        print_fail "No container runtime found (podman-compose or docker-compose required)"
        echo ""
        echo "Please install podman-compose or docker-compose to continue"
        exit 1
    fi

    # Test 3: Containers running
    print_test_header "Container Status"
    run_test
    if $COMPOSE_CMD ps | grep -q "nzbindexer"; then
        print_pass "Containers are running"

        # Test individual containers
        test_container_health "app"
        test_container_health "db"
        test_container_health "redis"
    else
        print_info "Containers not running - skipping container tests"
        print_info "Run './install-podman.sh' or '$COMPOSE_CMD up -d' to start containers"
    fi

    # Test 4: HTTP endpoints (only if containers are running)
    if $COMPOSE_CMD ps | grep -q "nzbindexer"; then
        print_test_header "HTTP Endpoints"

        # Wait a moment for services to be ready
        sleep 2

        test_http_endpoint "http://localhost:8000/health"
        test_http_endpoint "http://localhost:8000/" 307  # Should redirect
        test_http_endpoint "http://localhost:8000/api/v1/docs"
    fi

    # Test 5: Environment configuration
    print_test_header "Configuration"
    run_test
    if [ -f ".env" ]; then
        print_pass ".env file exists"

        # Check for required environment variables
        run_test
        if grep -q "SECRET_KEY" .env && ! grep -q "SECRET_KEY=your-secret-key" .env; then
            print_pass "SECRET_KEY is configured"
        else
            print_fail "SECRET_KEY not properly configured"
        fi

        run_test
        if grep -q "POSTGRES_PASSWORD" .env; then
            print_pass "POSTGRES_PASSWORD is set"
        else
            print_fail "POSTGRES_PASSWORD not set"
        fi
    else
        print_info ".env file not found - use .env.example as template"
    fi

    # Test 6: Python application structure
    print_test_header "Application Structure"
    test_file_exists "app/main.py"
    test_file_exists "app/core/config.py"
    test_file_exists "app/db/session.py"
    test_file_exists "app/services/nntp.py"
    test_file_exists "app/services/article.py"
    test_file_exists "app/web/templates/base.html"

    # Summary
    echo ""
    echo "========================================="
    echo " Test Summary"
    echo "========================================="
    echo ""
    echo "Total tests run:    $TESTS_RUN"
    echo -e "${GREEN}Tests passed:${NC}       $TESTS_PASSED"
    echo -e "${RED}Tests failed:${NC}       $TESTS_FAILED"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        echo ""
        exit 0
    else
        echo -e "${RED}✗ Some tests failed${NC}"
        echo ""
        exit 1
    fi
}

# Run validation
main
