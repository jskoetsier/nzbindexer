#!/bin/bash

#########################################
# NZB Indexer - Podman Installation Script
# Version: 0.9.0
#########################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for podman or docker
check_container_runtime() {
    print_header "Checking Container Runtime"

    if command_exists podman-compose; then
        COMPOSE_CMD="podman-compose"
        print_success "podman-compose found"
    elif command_exists podman && command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
        print_warning "podman found but podman-compose not installed, using docker-compose"
    elif command_exists docker && command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
        print_warning "Using docker-compose (podman recommended)"
    else
        print_error "Neither podman-compose nor docker-compose found!"
        echo ""
        echo "Please install podman and podman-compose:"
        echo ""
        echo "macOS:"
        echo "  brew install podman podman-compose"
        echo ""
        echo "Fedora/RHEL:"
        echo "  sudo dnf install podman podman-compose"
        echo ""
        echo "Ubuntu/Debian:"
        echo "  sudo apt install podman podman-compose"
        echo ""
        exit 1
    fi

    print_info "Using: $COMPOSE_CMD"
}

# Generate secure random string
generate_secret() {
    if command_exists openssl; then
        openssl rand -base64 32
    else
        date +%s | sha256sum | base64 | head -c 32
    fi
}

# Setup environment file
setup_env() {
    print_header "Setting Up Environment Configuration"

    if [ -f .env ]; then
        print_warning ".env file already exists"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env file"
            return
        fi
    fi

    print_info "Creating .env file from template..."
    cp .env.example .env

    # Generate secure secret key
    SECRET_KEY=$(generate_secret)

    # Update .env with secure values
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
    else
        # Linux
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
    fi

    print_success ".env file created with secure random secret key"

    # Prompt for database password
    read -sp "Enter PostgreSQL password (or press Enter for default): " DB_PASSWORD
    echo
    if [ -n "$DB_PASSWORD" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_PASSWORD}|" .env
        else
            sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_PASSWORD}|" .env
        fi
        print_success "Database password updated"
    fi

    echo ""
    print_info "You can customize other settings in .env file"
}

# Build and start containers
start_containers() {
    print_header "Building and Starting Containers"

    print_info "Building application container..."
    $COMPOSE_CMD build

    print_info "Starting all services..."
    $COMPOSE_CMD up -d

    print_success "Containers started successfully"
}

# Wait for database to be ready
wait_for_db() {
    print_header "Waiting for Database"

    print_info "Waiting for PostgreSQL to be ready..."

    MAX_RETRIES=30
    RETRY=0

    while [ $RETRY -lt $MAX_RETRIES ]; do
        if $COMPOSE_CMD exec -T db pg_isready -U nzbindexer >/dev/null 2>&1; then
            print_success "Database is ready"
            return 0
        fi
        RETRY=$((RETRY + 1))
        echo -n "."
        sleep 1
    done

    echo ""
    print_error "Database failed to start within ${MAX_RETRIES} seconds"
    return 1
}

# Initialize database
init_database() {
    print_header "Initializing Database"

    print_info "Running database migrations..."
    $COMPOSE_CMD exec -T app python -m app.db.init_db

    print_success "Database initialized successfully"
}

# Create admin user
create_admin_user() {
    print_header "Creating Admin User"

    echo ""
    read -p "Enter admin username (default: admin): " ADMIN_USER
    ADMIN_USER=${ADMIN_USER:-admin}

    read -p "Enter admin email (default: admin@example.com): " ADMIN_EMAIL
    ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.com}

    read -sp "Enter admin password: " ADMIN_PASSWORD
    echo

    if [ -z "$ADMIN_PASSWORD" ]; then
        print_error "Password cannot be empty"
        return 1
    fi

    read -sp "Confirm admin password: " ADMIN_PASSWORD_CONFIRM
    echo

    if [ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD_CONFIRM" ]; then
        print_error "Passwords do not match"
        return 1
    fi

    # Create admin user using Python script in container
    $COMPOSE_CMD exec -T app python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.models.user import User
from app.core.security import get_password_hash
from datetime import datetime, timezone

async def create_admin():
    async with AsyncSessionLocal() as db:
        admin = User(
            email='${ADMIN_EMAIL}',
            username='${ADMIN_USER}',
            hashed_password=get_password_hash('${ADMIN_PASSWORD}'),
            is_active=True,
            is_admin=True,
            last_login=datetime.now(timezone.utc)
        )
        db.add(admin)
        await db.commit()
        print('Admin user created successfully')

asyncio.run(create_admin())
"

    print_success "Admin user '${ADMIN_USER}' created successfully"
}

# Show summary
show_summary() {
    print_header "Installation Complete!"

    echo ""
    echo -e "${GREEN}✓${NC} NZB Indexer is now running in containers"
    echo ""
    echo "Access the application:"
    echo -e "  ${BLUE}Web Interface:${NC}     http://localhost:8000"
    echo -e "  ${BLUE}API Documentation:${NC} http://localhost:8000/api/v1/docs"
    echo ""
    echo "Useful commands:"
    echo -e "  ${BLUE}View logs:${NC}         $COMPOSE_CMD logs -f app"
    echo -e "  ${BLUE}Stop services:${NC}     $COMPOSE_CMD down"
    echo -e "  ${BLUE}Restart services:${NC}  $COMPOSE_CMD restart"
    echo -e "  ${BLUE}View status:${NC}       $COMPOSE_CMD ps"
    echo ""
    echo "Utilities:"
    echo -e "  ${BLUE}./scripts/utils.sh${NC} - Common management tasks"
    echo ""
}

# Main installation flow
main() {
    clear
    print_header "NZB Indexer - Podman Installation"

    echo "This script will:"
    echo "  1. Check for podman/docker and compose tools"
    echo "  2. Set up environment configuration"
    echo "  3. Build and start containers"
    echo "  4. Initialize the database"
    echo "  5. Create an admin user"
    echo ""
    read -p "Continue with installation? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_info "Installation cancelled"
        exit 0
    fi

    # Run installation steps
    check_container_runtime
    setup_env
    start_containers

    if wait_for_db; then
        init_database
        create_admin_user
        show_summary
    else
        print_error "Installation failed: Database did not start"
        echo ""
        echo "Check logs with: $COMPOSE_CMD logs db"
        exit 1
    fi
}

# Run main installation
main
