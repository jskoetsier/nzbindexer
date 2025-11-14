#!/bin/bash

#########################################
# NZB Indexer - Non-Interactive Deployment
# Version: 0.9.0
#########################################

set -e

# Configuration (can be overridden via environment variables)
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme123}
ADMIN_USER=${ADMIN_USER:-admin}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.com}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-Admin123!}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect compose command
if command -v podman-compose >/dev/null 2>&1; then
    COMPOSE_CMD="podman-compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    print_error "Neither podman-compose nor docker-compose found!"
    exit 1
fi

print_info "Using container runtime: $COMPOSE_CMD"

# Generate secret key (limit to reasonable length for bcrypt)
SECRET_KEY=$(openssl rand -base64 32 2>/dev/null || date +%s | sha256sum | base64 | head -c 32 | head -c 50)

# Create .env file
print_info "Creating .env configuration..."
cat > .env << EOF
# Database Configuration
POSTGRES_DB=nzbindexer
POSTGRES_USER=nzbindexer
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# Application Port
APP_PORT=8000

# Application Settings
SECRET_KEY=${SECRET_KEY}
API_V1_STR=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=60
PROJECT_NAME=NZB Indexer

# NNTP Server Configuration (configure via web interface)
NNTP_SERVER=
NNTP_PORT=119
NNTP_SSL=false
NNTP_SSL_PORT=563
NNTP_USERNAME=
NNTP_PASSWORD=
EOF

print_success ".env file created"

# Build and start containers
print_info "Building containers..."
$COMPOSE_CMD build

print_info "Starting containers..."
$COMPOSE_CMD up -d

# Wait for database
print_info "Waiting for database to be ready..."
sleep 5
MAX_RETRIES=30
RETRY=0

while [ $RETRY -lt $MAX_RETRIES ]; do
    if $COMPOSE_CMD exec -T db pg_isready -U nzbindexer >/dev/null 2>&1; then
        print_success "Database is ready"
        break
    fi
    RETRY=$((RETRY + 1))
    echo -n "."
    sleep 1
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    print_error "Database failed to start"
    exit 1
fi

# Initialize database
print_info "Initializing database..."
$COMPOSE_CMD exec -T app python -m app.db.init_db

# Create admin user
print_info "Creating admin user..."
$COMPOSE_CMD exec -T app python << PYEOF
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
PYEOF

print_success "Installation complete!"
echo ""
echo "========================================="
echo " NZB Indexer - Deployment Complete"
echo "========================================="
echo ""
echo "Access the application:"
echo "  Web Interface:     http://localhost:8000"
echo "  API Documentation: http://localhost:8000/api/v1/docs"
echo ""
echo "Admin credentials:"
echo "  Username: ${ADMIN_USER}"
echo "  Email:    ${ADMIN_EMAIL}"
echo "  Password: ${ADMIN_PASSWORD}"
echo ""
echo "Management:"
echo "  View logs:    $COMPOSE_CMD logs -f app"
echo "  Stop:         $COMPOSE_CMD down"
echo "  Restart:      $COMPOSE_CMD restart"
echo ""
