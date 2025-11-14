#!/bin/bash

#########################################
# NZB Indexer - Utility Scripts
# Version: 0.9.0
#########################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect compose command
detect_compose() {
    if command -v podman-compose >/dev/null 2>&1; then
        echo "podman-compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo "ERROR: Neither podman-compose nor docker-compose found" >&2
        exit 1
    fi
}

COMPOSE_CMD=$(detect_compose)

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
show_usage() {
    echo "NZB Indexer - Utility Scripts"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  start                 Start all containers"
    echo "  stop                  Stop all containers"
    echo "  restart               Restart all containers"
    echo "  logs [service]        View logs (app, db, redis, or all)"
    echo "  status                Show container status"
    echo "  shell                 Open shell in app container"
    echo "  db-shell              Open PostgreSQL shell"
    echo "  backup                Backup database"
    echo "  restore <file>        Restore database from backup"
    echo "  update                Pull latest changes and rebuild"
    echo "  clean                 Remove all containers and volumes (DANGEROUS!)"
    echo "  add-categories        Add default categories"
    echo "  test-nntp             Test NNTP connection"
    echo "  reset-admin           Reset admin password"
    echo ""
}

# Start containers
cmd_start() {
    print_info "Starting containers..."
    $COMPOSE_CMD up -d
    print_success "Containers started"
}

# Stop containers
cmd_stop() {
    print_info "Stopping containers..."
    $COMPOSE_CMD down
    print_success "Containers stopped"
}

# Restart containers
cmd_restart() {
    print_info "Restarting containers..."
    $COMPOSE_CMD restart
    print_success "Containers restarted"
}

# View logs
cmd_logs() {
    local service=${1:-}
    if [ -z "$service" ]; then
        print_info "Showing logs for all services (Ctrl+C to exit)..."
        $COMPOSE_CMD logs -f
    else
        print_info "Showing logs for $service (Ctrl+C to exit)..."
        $COMPOSE_CMD logs -f "$service"
    fi
}

# Show status
cmd_status() {
    print_info "Container status:"
    $COMPOSE_CMD ps
}

# Open shell
cmd_shell() {
    print_info "Opening shell in app container..."
    $COMPOSE_CMD exec app /bin/bash
}

# Open database shell
cmd_db_shell() {
    print_info "Opening PostgreSQL shell..."
    $COMPOSE_CMD exec db psql -U nzbindexer -d nzbindexer
}

# Backup database
cmd_backup() {
    local backup_file="backup_$(date +%Y%m%d_%H%M%S).sql"
    print_info "Creating database backup: $backup_file"
    $COMPOSE_CMD exec -T db pg_dump -U nzbindexer nzbindexer > "$backup_file"
    print_success "Database backed up to $backup_file"
}

# Restore database
cmd_restore() {
    local backup_file=$1
    if [ -z "$backup_file" ]; then
        print_error "Please specify backup file to restore"
        echo "Usage: $0 restore <backup_file>"
        exit 1
    fi

    if [ ! -f "$backup_file" ]; then
        print_error "Backup file not found: $backup_file"
        exit 1
    fi

    print_info "Restoring database from $backup_file..."
    cat "$backup_file" | $COMPOSE_CMD exec -T db psql -U nzbindexer nzbindexer
    print_success "Database restored"
}

# Update application
cmd_update() {
    print_info "Pulling latest changes..."
    git pull

    print_info "Rebuilding containers..."
    $COMPOSE_CMD build

    print_info "Restarting containers..."
    $COMPOSE_CMD up -d

    print_success "Application updated"
}

# Clean everything
cmd_clean() {
    echo -e "${RED}WARNING: This will remove all containers and volumes!${NC}"
    echo "All data will be lost!"
    read -p "Are you sure? Type 'yes' to confirm: " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Operation cancelled"
        exit 0
    fi

    print_info "Stopping containers..."
    $COMPOSE_CMD down -v

    print_success "All containers and volumes removed"
}

# Add default categories
cmd_add_categories() {
    print_info "Adding default categories..."
    $COMPOSE_CMD exec -T app python << 'EOF'
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.models.category import Category

async def add_categories():
    async with AsyncSessionLocal() as db:
        # Define categories
        categories = [
            {"name": "Movies", "description": "Movie releases", "active": True, "sort_order": 1},
            {"name": "TV", "description": "TV show releases", "active": True, "sort_order": 2},
            {"name": "Music", "description": "Music releases", "active": True, "sort_order": 3},
            {"name": "Games", "description": "Game releases", "active": True, "sort_order": 4},
            {"name": "Apps", "description": "Application releases", "active": True, "sort_order": 5},
            {"name": "Books", "description": "Book releases", "active": True, "sort_order": 6},
            {"name": "Other", "description": "Other releases", "active": True, "sort_order": 99},
        ]

        for cat_data in categories:
            # Check if category exists
            from sqlalchemy import select
            result = await db.execute(select(Category).filter(Category.name == cat_data["name"]))
            existing = result.scalars().first()

            if not existing:
                category = Category(**cat_data)
                db.add(category)
                print(f"Added category: {cat_data['name']}")
            else:
                print(f"Category already exists: {cat_data['name']}")

        await db.commit()
        print("Categories setup complete")

asyncio.run(add_categories())
EOF
    print_success "Default categories added"
}

# Test NNTP connection
cmd_test_nntp() {
    print_info "Testing NNTP connection..."
    $COMPOSE_CMD exec -T app python -c "
from app.services.nntp import NNTPService
from app.db.session import AsyncSessionLocal
from app.services.setting import get_app_settings
import asyncio

async def test_connection():
    async with AsyncSessionLocal() as db:
        settings = await get_app_settings(db)

        if not settings.nntp_server:
            print('ERROR: NNTP server not configured')
            print('Configure NNTP settings in the web interface at http://localhost:8000/admin/settings')
            return

        try:
            nntp_service = NNTPService(
                server=settings.nntp_server,
                port=settings.nntp_ssl_port if settings.nntp_ssl else settings.nntp_port,
                use_ssl=settings.nntp_ssl,
                username=settings.nntp_username,
                password=settings.nntp_password,
            )

            conn = nntp_service.connect()
            welcome = conn.welcome
            conn.quit()

            print('SUCCESS: Connected to NNTP server')
            print(f'Server welcome: {welcome}')
        except Exception as e:
            print(f'ERROR: Failed to connect to NNTP server: {str(e)}')

asyncio.run(test_connection())
"
}

# Reset admin password
cmd_reset_admin() {
    print_info "Reset Admin Password"
    echo ""
    read -p "Enter admin username: " admin_user

    if [ -z "$admin_user" ]; then
        print_error "Username cannot be empty"
        exit 1
    fi

    read -sp "Enter new password: " new_password
    echo

    if [ -z "$new_password" ]; then
        print_error "Password cannot be empty"
        exit 1
    fi

    read -sp "Confirm new password: " confirm_password
    echo

    if [ "$new_password" != "$confirm_password" ]; then
        print_error "Passwords do not match"
        exit 1
    fi

    $COMPOSE_CMD exec -T app python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.models.user import User
from app.core.security import get_password_hash
from sqlalchemy import select

async def reset_password():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).filter(User.username == '${admin_user}'))
        user = result.scalars().first()

        if not user:
            print('ERROR: User not found')
            return

        user.hashed_password = get_password_hash('${new_password}')
        await db.commit()
        print('SUCCESS: Password updated for user ${admin_user}')

asyncio.run(reset_password())
"
}

# Main command dispatcher
case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs "${2:-}"
        ;;
    status)
        cmd_status
        ;;
    shell)
        cmd_shell
        ;;
    db-shell)
        cmd_db_shell
        ;;
    backup)
        cmd_backup
        ;;
    restore)
        cmd_restore "$2"
        ;;
    update)
        cmd_update
        ;;
    clean)
        cmd_clean
        ;;
    add-categories)
        cmd_add_categories
        ;;
    test-nntp)
        cmd_test_nntp
        ;;
    reset-admin)
        cmd_reset_admin
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
