# NZB Indexer

A modern, intelligent Usenet indexer built with FastAPI, featuring advanced deobfuscation capabilities, NZBHydra2 integration, and a responsive web interface.

## Version 0.9.0 - Major Update (Nov 17, 2025)

**🎉 Major Features:**
- ✅ **NZBHydra2 Integration** - Query millions of hash mappings from aggregated indexers
- ✅ **Multi-Source Deobfuscation Pipeline** - PreDB, NZBHydra2, Newznab, hash decoding, archives, NFO extraction
- ✅ **Obfuscated Release Indexing** - Creates releases even when deobfuscation fails, enabling retroactive matching
- ✅ **ORN (Obfuscated Release Names) Cache** - Community-shareable hash database with import/export
- ✅ **Comprehensive Deobfuscation Guide** - 10+ solutions for building your hash database

## Features

### Core Functionality
- **Responsive Web Interface**: Built with Bootstrap 5 for optimal viewing on any device
- **User Authentication**: Secure login and registration system
- **Group Management**: View and manage Usenet newsgroups
- **Admin Panel**: Configure groups, manage users, and monitor system status
- **API Access**: Complete RESTful API with OpenAPI documentation
- **Smart Backfill System**: Day-based backfilling with automatic target calculation
  - Configure backfill by number of days (0-365)
  - Automatic article target calculation based on group activity
  - Progress tracking and visualization
  - Runs automatically every 5 minutes

### Advanced Deobfuscation (NEW in v0.9.0)
- **Multi-Source Deobfuscation Pipeline**:
  1. yEnc Header Extraction - Get real filenames from article content
  2. PreDB Lookup - Query 4 PreDB APIs (predb.ovh, predb.me, srrDB, abgx360)
  3. **NZBHydra2 Integration** - Access aggregated indexer databases
  4. Newznab Cross-Indexer Lookup - Query other indexers
  5. Hash Decoding - Base64, hex, and pattern decoding
  6. TMDB/IMDB Metadata Matching - Size + date matching
  7. Archive Header Extraction - RAR/ZIP/7-Zip/Par2 headers
  8. NFO File Extraction - Parse NFO files for release names
  9. Obfuscated Release Creation - Index with pending deobfuscation

- **ORN (Obfuscated Release Names) Management**:
  - Local hash-to-name mapping cache
  - Source attribution (PreDB, NZBHydra2, community, etc.)
  - Confidence scoring
  - JSON/CSV import/export
  - Public sharing API for community collaboration
  - Automatic retry with cache updates

### Robust Article Processing
- **Binary Post Detection**:
  - NNTP OVER dictionary format parsing
  - Safe int conversion with comprehensive error handling
  - Binary post detection and grouping
  - Part tracking and completion percentage calculation
  - **Obfuscated Binary Support**: Process modern binary posts with obfuscated subjects
  - **Multiple Completion Criteria**: 100%, ≥25% with ≥2 parts, or ≥5 parts

### Release Management
- **Automatic Release Creation**: Convert complete binaries into releases
- **Metadata Extraction**: Category, quality, year, resolution detection
- **Size Tracking**: Accurate byte count across all parts
- **NZB Generation**: Create downloadable NZB files with proper formatting
- **Search Functionality**: Find releases by name, category, hash, and more
- **Sonarr/Radarr Integration**: Compatible with automation tools via Newznab API

### System Tools
- **Batch Processing**: Efficient group discovery with progress tracking
- **Job Control**: Cancel long-running tasks when needed
- **Diagnostic Tools**: Analyze NNTP connections and article processing
- **Comprehensive Error Logging**: Detailed tracebacks for debugging and monitoring

## Screenshots

(Screenshots to be added)

## Requirements

- Python 3.9 or higher
- PostgreSQL, MySQL, or SQLite
- Usenet server access

## Installation

### Quick Start with Podman (Recommended)

The fastest way to get NZB Indexer running:

```bash
git clone https://github.com/yourusername/nzbindexer.git
cd nzbindexer
chmod +x install-podman.sh
./install-podman.sh
```

The installer will:
- ✓ Check for podman-compose or docker-compose
- ✓ Create and configure `.env` file with secure defaults
- ✓ Build and start all containers
- ✓ Initialize the database
- ✓ Create an admin user
- ✓ Provide access URLs and useful commands

### Manual Podman/Docker Compose Installation

If you prefer manual installation:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/nzbindexer.git
   cd nzbindexer
   ```

2. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set your configuration:
   - Change `POSTGRES_PASSWORD` to a secure password
   - Change `SECRET_KEY` to a long random string
   - Optionally configure NNTP settings (can also be done via web interface)

3. Build and start the containers:

   **Using podman-compose:**
   ```bash
   podman-compose up -d
   ```

   **Using docker-compose:**
   ```bash
   docker-compose up -d
   ```

4. Initialize the database and create an admin user:
   ```bash
   # For podman-compose:
   podman-compose exec app python -m app.db.init_db

   # For docker-compose:
   docker-compose exec app python -m app.db.init_db
   ```

5. Access the application:
   - Web Interface: http://localhost:8000
   - API Documentation: http://localhost:8000/api/v1/docs
   - Default admin credentials will be created during initialization

6. To view logs:
   ```bash
   # For podman-compose:
   podman-compose logs -f app

   # For docker-compose:
   docker-compose logs -f app
   ```

7. To stop the application:
   ```bash
   # For podman-compose:
   podman-compose down

   # For docker-compose:
   docker-compose down
   ```

### Container Management

The compose file includes three services:
- **app**: The main NZB Indexer application
- **db**: PostgreSQL database
- **redis**: Redis cache (for future features)

All data is persisted in Docker/Podman volumes:
- `postgres_data`: Database files
- `redis_data`: Redis persistence
- `nzb_data`: NZB files
- `app_data`: Application data
- `app_logs`: Application logs

## Management & Utilities

### Utility Script

The `scripts/utils.sh` script provides common management tasks:

```bash
# Start containers
./scripts/utils.sh start

# Stop containers
./scripts/utils.sh stop

# View logs
./scripts/utils.sh logs [service]

# Access container shell
./scripts/utils.sh shell

# Database operations
./scripts/utils.sh backup
./scripts/utils.sh restore <backup-file>
./scripts/utils.sh db-shell

# Application management
./scripts/utils.sh add-categories
./scripts/utils.sh test-nntp
./scripts/utils.sh reset-admin

# Update application
./scripts/utils.sh update

# View all available commands
./scripts/utils.sh
```

### Validation

Test your installation:

```bash
./scripts/validate.sh
```

This will check:
- Required files are present
- Container runtime is available
- Containers are running and healthy
- HTTP endpoints are accessible
- Configuration is properly set
- Application structure is intact

## Configuration

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```
DATABASE_URL=sqlite:///./app.db
SECRET_KEY=your-secret-key
API_V1_STR=/api/v1
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

For production, it's recommended to use PostgreSQL or MySQL:

```
DATABASE_URL=postgresql://user:password@localhost/nzbindexer
```

### Web Server Configuration

Example configurations for Nginx and Apache are provided in the `config/` directory.

#### Nginx

```bash
sudo cp config/nginx.conf /etc/nginx/sites-available/nzbindexer
sudo ln -s /etc/nginx/sites-available/nzbindexer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Apache

```bash
sudo cp config/apache.conf /etc/apache2/sites-available/nzbindexer.conf
sudo a2ensite nzbindexer.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## Usage

### Web Interface

Access the web interface at `http://localhost:8000` (or your configured domain).

- **Browse**: View and search releases
- **Groups**: View available Usenet newsgroups
- **Admin**: Manage groups, users, and system settings (admin only)

### API

Access the API documentation at `http://localhost:8000/api/v1/docs`.

The API provides endpoints for:
- Authentication
- User management
- Group management
- Release management
- Category management

## Development

### Project Structure

```
nzbindexer/
├── app/
│   ├── api/            # API endpoints
│   ├── core/           # Core functionality
│   ├── db/             # Database models and session
│   ├── schemas/        # Pydantic schemas
│   ├── services/       # Business logic
│   ├── web/            # Web interface
│   │   ├── static/     # Static files (CSS, JS)
│   │   └── templates/  # Jinja2 templates
│   └── main.py         # Application entry point
├── config/             # Configuration examples
├── tests/              # Test suite
├── .env                # Environment variables
├── install.sh          # Installation script
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

### Running Tests

```bash
pytest
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- FastAPI
- SQLAlchemy
- Bootstrap
- Jinja2
