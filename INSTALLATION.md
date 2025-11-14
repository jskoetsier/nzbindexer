# NZB Indexer - Installation & Management Guide

## Quick Start

Get NZB Indexer running in 3 easy steps:

```bash
# 1. Clone and enter directory
git clone https://github.com/yourusername/nzbindexer.git
cd nzbindexer

# 2. Run installer
./install-podman.sh

# 3. Access the application
# Web: http://localhost:8000
# API Docs: http://localhost:8000/api/v1/docs
```

## Requirements

- **Container Runtime**: podman-compose (recommended) or docker-compose
- **Operating System**: Linux, macOS, or Windows with WSL2
- **NNTP Access**: Valid Usenet server credentials

### Installing Podman

**macOS:**
```bash
brew install podman podman-compose
```

**Fedora/RHEL:**
```bash
sudo dnf install podman podman-compose
```

**Ubuntu/Debian:**
```bash
sudo apt install podman podman-compose
```

## Management Commands

All management is done through the `scripts/utils.sh` utility:

### Container Operations
```bash
./scripts/utils.sh start          # Start all containers
./scripts/utils.sh stop           # Stop all containers
./scripts/utils.sh restart        # Restart containers
./scripts/utils.sh status         # View container status
./scripts/utils.sh logs [service] # View logs (app, db, redis, or all)
```

### Container Access
```bash
./scripts/utils.sh shell          # Open bash shell in app container
./scripts/utils.sh db-shell       # Open PostgreSQL database shell
```

### Database Operations
```bash
./scripts/utils.sh backup                # Create database backup
./scripts/utils.sh restore <file>        # Restore from backup
```

### Application Management
```bash
./scripts/utils.sh add-categories        # Add default release categories
./scripts/utils.sh test-nntp             # Test NNTP server connection
./scripts/utils.sh reset-admin           # Reset admin user password
./scripts/utils.sh update                # Update application from git
```

### Cleanup
```bash
./scripts/utils.sh clean          # Remove all containers and volumes (DANGEROUS!)
```

## Configuration

### Initial Setup

The installer creates a `.env` file with secure defaults. You can customize:

```bash
# Edit environment configuration
nano .env
```

Key settings:
- `POSTGRES_PASSWORD` - Database password
- `SECRET_KEY` - Application secret (auto-generated)
- `NNTP_*` - Usenet server settings (optional, can configure via web UI)

### NNTP Server Setup

Configure your Usenet provider via the web interface:

1. Login as admin
2. Navigate to Admin → Settings
3. Enter NNTP server details:
   - Server address
   - Port (usually 119 or 563 for SSL)
   - SSL enabled/disabled
   - Username and password

Test the connection with:
```bash
./scripts/utils.sh test-nntp
```

## First Time Setup

After installation:

1. **Add Categories** (optional but recommended):
   ```bash
   ./scripts/utils.sh add-categories
   ```

2. **Configure NNTP** via web interface at:
   http://localhost:8000/admin/settings

3. **Discover Groups** via web interface:
   - Navigate to Admin → Groups
   - Click "Discover Groups"
   - Enter search pattern (e.g., `alt.binaries.*`)

## Troubleshooting

### View Logs
```bash
# All services
./scripts/utils.sh logs

# Specific service
./scripts/utils.sh logs app
./scripts/utils.sh logs db
```

### Container Not Starting
```bash
# Check status
./scripts/utils.sh status

# View detailed logs
podman-compose logs db
podman-compose logs app
```

### Database Issues
```bash
# Access database directly
./scripts/utils.sh db-shell

# Create backup before troubleshooting
./scripts/utils.sh backup
```

### Reset Everything
```bash
# WARNING: Destroys all data!
./scripts/utils.sh clean

# Then reinstall
./install-podman.sh
```

## Validation

Test your installation at any time:

```bash
./scripts/validate.sh
```

This checks:
- Required files exist
- Container runtime available
- Containers running and healthy
- HTTP endpoints accessible
- Configuration properly set

## Upgrading

To upgrade to the latest version:

```bash
./scripts/utils.sh update
```

This will:
1. Pull latest code from git
2. Rebuild containers
3. Restart services

**Note**: Always backup your database before upgrading!

## Data Persistence

All data is stored in named volumes:

- `postgres_data` - Database
- `redis_data` - Cache
- `nzb_data` - Generated NZB files
- `app_data` - Application data
- `app_logs` - Log files

These persist even if containers are removed.

## Security Best Practices

1. **Change Default Passwords**: Always set secure passwords in `.env`
2. **Use SSL**: Enable NNTP SSL if your provider supports it
3. **Regular Backups**: Use `./scripts/utils.sh backup` regularly
4. **Keep Updated**: Run `./scripts/utils.sh update` periodically
5. **Firewall**: Only expose necessary ports (typically just 8000)

## Getting Help

- **Documentation**: See README.md
- **Logs**: Use `./scripts/utils.sh logs`
- **Validation**: Run `./scripts/validate.sh`
- **GitHub Issues**: Report bugs and request features

## Advanced Usage

### Custom Port
Edit `.env` and change `APP_PORT`:
```bash
APP_PORT=9000
```

Then restart:
```bash
./scripts/utils.sh restart
```

### Multiple Instances
To run multiple instances, create separate directories and use different ports in each `.env` file.

### Production Deployment
For production use:
1. Set strong passwords in `.env`
2. Configure reverse proxy (nginx/apache)
3. Enable SSL/TLS
4. Set up automated backups
5. Monitor logs regularly

## Support

For issues or questions:
1. Check logs: `./scripts/utils.sh logs`
2. Run validation: `./scripts/validate.sh`
3. Review documentation
4. Open GitHub issue with details
