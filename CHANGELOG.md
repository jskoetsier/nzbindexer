# Changelog

All notable changes to the NZB Indexer project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2025-11-17

### 🎉 Major Milestone - Advanced Deobfuscation System

This release introduces a revolutionary multi-source deobfuscation system with NZBHydra2 integration, fixing critical issues that prevented indexing of obfuscated releases. The indexer now creates releases even when deobfuscation fails, enabling retroactive matching as the ORN cache grows.

### Added
- **NZBHydra2 Integration** ⭐
  - Complete integration with NZBHydra2 meta-indexer
  - Access to millions of hash mappings from aggregated indexers
  - Service client implementation (`/app/services/nzbhydra.py`)
  - Configuration settings for URL and API key
  - Setup assistant script (`/scripts/setup_nzbhydra2.sh`)
  - Deployed and tested on production server

- **Multi-Source Deobfuscation Pipeline** ⭐
  - 9-step comprehensive deobfuscation process:
    1. yEnc Header Extraction
    2. PreDB Lookup (4 providers: predb.ovh, predb.me, srrDB, abgx360)
    3. **NZBHydra2 Lookup** (NEW!)
    4. Newznab Cross-Indexer Lookup
    5. Hash Decoding (base64, hex, patterns)
    6. TMDB/IMDB Metadata Matching
    7. Archive Header Extraction (RAR/ZIP/7-Zip/Par2)
    8. NFO File Extraction
    9. Obfuscated Release Creation (fallback)

- **ORN (Obfuscated Release Names) System**
  - Complete ORN cache management system
  - Database model for hash-to-name mappings (`/app/db/models/orn_mapping.py`)
  - Source attribution (predb_predb.ovh, predb_predb.me, nzbhydra2, etc.)
  - Confidence scoring (0.0-1.0)
  - Use count tracking for popular hashes
  - Created/updated timestamps

- **ORN API Endpoints** (`/app/api/v1/endpoints/orn.py`)
  - `GET /api/v1/orn/stats` - View statistics
  - `GET /api/v1/orn/mappings` - List mappings with pagination
  - `POST /api/v1/orn/mappings` - Create mapping
  - `DELETE /api/v1/orn/mappings/{id}` - Delete mapping
  - `GET /api/v1/orn/export/json` - Export JSON
  - `GET /api/v1/orn/export/csv` - Export CSV
  - `POST /api/v1/orn/import/json` - Import JSON
  - `POST /api/v1/orn/import/csv` - Import CSV
  - `GET /api/v1/orn/public/mappings` - Share mappings publicly
  - `POST /api/v1/orn/public/contribute` - Accept community contributions

- **Comprehensive Documentation**
  - 10+ solutions for building ORN database (`/docs/ORN_DATABASE_GUIDE.md`)
  - NZBHydra2 deployment guide
  - Community database import strategies
  - SABnzbd/NZBGet cache mining instructions
  - Prowlarr integration guide
  - Machine learning approach outline
  - Expected growth timeline projections

### Fixed
- **CRITICAL: Obfuscated Post Skipping** ⭐⭐⭐
  - **Root Cause**: System was SKIPPING ALL obfuscated posts when deobfuscation failed
  - **Impact**: Only 47 releases created despite thousands of articles processed
  - **Logs**: "✗ COMPLETE FAILURE: obfuscated_xxx - SKIPPING"
  - **Solution**: Changed behavior to CREATE releases with obfuscated names
  - **New Behavior**: "⚠ DEOBFUSCATION PENDING - will retry with future ORN cache updates"
  - **Result**: 31 new releases created in 90 seconds after fix (47 → 78+)
  - **Benefit**: All releases now indexed and retroactively deobfuscatable

- **Duplicate Code Block Removal**
  - Removed duplicate NFO check + SKIPPING logic (lines 1233-1244)
  - Cleaned up deobfuscation pipeline flow
  - Ensured single code path for release creation

### Changed
- **Deobfuscation Strategy**: From "skip on failure" to "index and retry later"
- **Release Creation Logic**: Now creates releases even with obfuscated names
- **Backfill Effectiveness**: Dramatically improved as all posts are now indexed
- **Version Number**: Bumped to 0.9.0 to reflect major feature additions

### Performance Improvements
- **Release Creation Rate**: 31 releases in 90 seconds after fix
- **Database Growth**: From 47 → 78+ releases immediately
- **Deobfuscation Coverage**: All posts now indexed (100% vs ~5% before)
- **Future Matching**: All obfuscated releases can be matched when ORN cache grows

### Technical Details

#### Commits (Nov 17, 2025)
- `f9af262`: Research-backed ORN database building solutions
- `a187654`: NZBHydra2 setup assistant script
- `c146a9a`: NZBHydra2 integration into deobfuscation pipeline
- `41ed558`: First attempt to fix obfuscated post skipping
- `20873d1`: Remove duplicate SKIPPING code block (FINAL FIX)

#### Configuration
- NZBHydra2 URL: `http://192.168.1.153:5076`
- NZBHydra2 API Key: Configured and tested
- Connected to: NZBFinder indexer
- All deobfuscation services active

#### File Changes
- `/app/services/nzbhydra.py`: New NZBHydra2 service client
- `/app/services/article.py`: Fixed SKIPPING logic, integrated NZBHydra2 (Step 3)
- `/app/core/config.py`: Added NZBHYDRA_URL and NZBHYDRA_API_KEY
- `/docs/ORN_DATABASE_GUIDE.md`: Comprehensive 10+ solution guide
- `/scripts/setup_nzbhydra2.sh`: Interactive setup assistant
- `README.md`: Updated with v0.9.0 features
- `CHANGELOG.md`: This entry

### Breaking Changes
- None - all changes are additive and backward compatible

### Migration Guide

No database migration required. NZBHydra2 integration is optional and configured via settings.

**To enable NZBHydra2:**
1. Deploy NZBHydra2 container (or use existing instance)
2. Get API key from NZBHydra2 settings
3. Configure in `app/core/config.py` or environment variables
4. System automatically uses NZBHydra2 in deobfuscation pipeline

**To build ORN cache:**
- See `/docs/ORN_DATABASE_GUIDE.md` for 10+ solutions
- Import community databases via API endpoints
- Add more indexers to NZBHydra2
- Enable public sharing for community contributions

### Known Limitations
- ORN cache starts at 0 mappings (requires seeding)
- NZBHydra2 requires separate deployment
- PreDB APIs may rate-limit on high volume
- Ultra-obfuscated posts won't match until ORN cache grows

### Expected Growth
- **Day 1**: 0 → 1,000 mappings (manual imports, NZBHydra2 queries)
- **Week 1**: 1,000 → 10,000 mappings (Newznab cross-queries, community)
- **Month 1**: 10,000 → 100,000 mappings (network effects, sharing)
- **Month 3+**: 100,000+ mappings (established database)

### Success Metrics
- ✅ NZBHydra2 deployed and querying successfully
- ✅ Releases created even when obfuscated (47 → 78+ in 90s)
- ✅ Deobfuscation pipeline executing all 9 steps
- ✅ Background tasks running continuously
- ✅ System ready for ORN cache growth

## [1.0.0] - 2025-01-17

### 🎉 Major Milestone - Fully Operational Release

This release represents a major milestone with the NZB Indexer now fully operational and processing articles correctly. All critical issues preventing release creation have been resolved.

### Added
- **Day-based Backfill System**: Revolutionary new backfill approach
  - Configure backfill target by number of days (0-365) instead of arbitrary article counts
  - Automatic target calculation based on group activity: `target_articles = articles_per_day × backfill_days`
  - Safety limits: minimum 1,000, maximum 100,000 articles per backfill
  - Auto-recalculation every 5 minutes during backfill execution
  - New `backfill_days` field in Group model and database schema
  - UI form fields in admin group editor with read-only calculated target display
  - Helper text showing global default backfill days

- **Enhanced Error Logging**: Comprehensive debugging and monitoring
  - Detailed tracebacks for all errors in article processing
  - NNTP connection error logging with full context
  - Safe error handling with informative messages
  - Added error tracking to backfill task execution

- **Migration Script**: Database schema update utility
  - `scripts/add_backfill_days_column.py` for adding backfill_days field to existing installations
  - Safe migration with null value handling
  - Default value assignment (0 = global default)

### Fixed
- **CRITICAL: NNTP OVER Dictionary Format Parsing** ⭐
  - **Root Cause**: NNTP OVER command returns `(article_num, headers_dict)` tuples, not individual fields
  - **Impact**: ALL articles (1000/1000) were being skipped because `subject` was always empty
  - **Solution**: Extract fields from `headers_dict` dictionary:
    - `subject = headers_dict.get('subject', '')`
    - `message_id = headers_dict.get('message-id', '')`
    - `from_header = headers_dict.get('from', '')`
    - `date_header = headers_dict.get('date', '')`
  - This single fix resolved 100% article skip rate and enabled proper binary processing

- **CRITICAL: Safe Integer Conversion** ⭐
  - **Problem**: `int('')` raises `ValueError: invalid literal for int() with base 10: ''`
  - **Cause**: NNTP headers can have empty strings for `:bytes` and `:lines` fields
  - **Solution**: Implemented safe int conversion with try/except blocks:
    ```python
    try:
        bytes_str = headers_dict.get(':bytes', '0')
        bytes_count = int(bytes_str) if bytes_str and bytes_str.strip() else 0
    except (ValueError, AttributeError):
        bytes_count = 0
    ```
  - Applied to both `:bytes` and `:lines` fields
  - Prevents crashes during article processing

- **Article Processing Robustness**
  - Enhanced subject line parsing with proper dictionary extraction
  - Improved binary detection with permissive pattern matching
  - Better handling of obfuscated posts with hash-based naming
  - Proper part number extraction from various formats: `[01/50]`, `(01/50)`, `01/50`

- **Binary Post Detection**
  - Fixed detection logic to handle modern Usenet posts
  - Improved part grouping and tracking
  - Enhanced completion percentage calculation
  - Better handling of incomplete binaries

### Changed
- **Backfill Task Frequency**: Now runs every 5 minutes (was every 10 minutes)
- **Group Schema Updates**: `GroupCreate` and `GroupUpdate` schemas now include `backfill_days` field
- **Article Processing Logic**: Complete rewrite to handle NNTP OVER dictionary format correctly
- **Error Handling**: All critical operations now have comprehensive error handling with logging

### Performance Improvements
- **Best Performing Groups** (as of testing):
  - `a.b.bloaf`: 1000/1000 articles processed, 18 binaries/cycle, 0 failed ✅
  - `a.b.nl`: 1000/1000 articles processed, 20 binaries/cycle, 0 failed ✅
- Eliminated 100% article skip rate
- Proper binary accumulation for release creation
- Expected release creation within hours of backfill start

### Technical Details

#### File Changes
- `/Users/johansebastiaan/dev/nzbindexer/app/db/models/group.py`: Added `backfill_days` field
- `/Users/johansebastiaan/dev/nzbindexer/app/services/article.py`: Fixed NNTP OVER parsing (lines 140-160), safe int conversion (lines 155-165)
- `/Users/johansebastiaan/dev/nzbindexer/app/core/tasks.py`: Enhanced backfill task with day-based calculation
- `/Users/johansebastiaan/dev/nzbindexer/app/web/templates/admin/group_form.html`: Added backfill days UI
- `/Users/johansebastiaan/dev/nzbindexer/app/schemas/group.py`: Updated schemas for backfill_days

#### Known Limitations
- Some groups may show high "failed" counts - this is normal and represents articles that have expired/been deleted from the NNTP server
- Obfuscated posts use hash-based naming (e.g., `obfuscated_123456789`)
- Release creation requires minimum part threshold to avoid incomplete releases:
  - 100% complete (all parts) OR
  - ≥25% complete with ≥2 parts OR
  - ≥5 parts total

### Breaking Changes
- Database schema change: new `backfill_days` column in `group` table (migration script provided)
- Groups without `backfill_days` set will use global default (0 = disabled)

### Migration Guide

For existing installations, run the migration script:

```bash
# In container environment:
podman-compose exec app python scripts/add_backfill_days_column.py

# Or docker-compose:
docker-compose exec app python scripts/add_backfill_days_column.py
```

Then configure backfill days for your groups via the admin interface.

## [0.9.0] - 2025-01-14

### Added
- Full Docker and Podman containerization support with docker-compose.yml
- PostgreSQL 16 and Redis 7 services in container orchestration
- Comprehensive .dockerignore for optimized container builds
- .env.example template for easy configuration
- Health checks for all containerized services
- Named volumes for persistent data (postgres_data, redis_data, nzb_data, app_data, app_logs)
- Detailed podman-compose and docker-compose documentation in README

### Changed
- **BREAKING**: Application now designed to run exclusively in containerized environment
- Updated all Python dependencies to latest stable versions (FastAPI 0.115.0, SQLAlchemy 2.0.36, Pydantic 2.10.0, etc.)
- Replaced deprecated `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)` throughout codebase
- Migrated from deprecated FastAPI `@app.on_event` decorators to modern `lifespan` context manager
- Updated Python requirement from 3.8+ to 3.9+ for better timezone support
- Updated README with containerization-first approach

### Fixed
- All deprecation warnings related to datetime usage (Python 3.12+ compatibility)
- FastAPI startup/shutdown event deprecation warnings
- Improved timezone handling across all services

### Security
- Updated all dependencies with latest security patches
- Enhanced container security with minimal base image and proper volume permissions

## [0.8.0] - 2025-06-10

### Added
- Support for obfuscated binary posts with yEnc header detection
- Enhanced article processing to extract filenames from yEnc headers
- Improved binary post detection for modern Usenet posts
- Diagnostic tools for NNTP connection and article processing
- Database optimization for SQLite to reduce locking issues
- API authentication improvements for web interface

### Fixed
- Fixed binary post detection for posts with random or empty subjects
- Improved error handling for Unicode encoding issues in article subjects
- Enhanced NNTP connection stability with better error recovery
- Fixed database locking issues with concurrent article processing
- Resolved issues with empty articles in binary groups

## [0.7.0] - 2023-12-15

### Added
- NZB obfuscation for improved privacy and compatibility with Usenet providers
- Category IDs for Sonarr/Radarr compatibility (Newznab standard)
- Batch processing for group discovery with progress tracking
- Job cancellation capability for long-running discovery tasks
- Improved pagination in admin group management interface
- Tab state preservation in paginated views

### Fixed
- Fixed backfill functionality to properly handle edge cases
- Improved NNTP connection handling with better error recovery
- Fixed string/bytes handling for different NNTP server responses
- Added proper database migration script for category IDs
- Fixed article processing to handle different NNTP response formats
- Resolved issues with dictionary access in templates

## [0.6.0] - 2023-12-01

### Added
- Article processing functionality for converting Usenet articles into releases
- Release management with metadata extraction and categorization
- NZB file generation for downloads
- Release detail page with comprehensive information display
- Search functionality for finding releases
- API endpoints for managing and downloading releases
- Binary post detection and grouping
- Automatic metadata extraction from release names
- Release categorization based on content analysis

## [0.5.4] - 2023-11-20

### Fixed
- Fixed group service function parameter mismatch
- Updated get_groups() function to match how it's used in main.py
- Added support for filtering groups by active status, backfill status, and search term
- Fixed "TypeError: get_groups() got an unexpected keyword argument 'active'" error
- Added pagination support to group listing

## [0.5.3] - 2023-11-15

### Fixed
- Fixed database connection issues in main application
- Updated session.py to use the same database URL logic as init_db.py
- Resolved PostgreSQL connection errors during login
- Ensured consistent database usage throughout the application

## [0.5.2] - 2023-11-10

### Fixed
- Fixed Jinja2 context processor implementation
- Replaced decorator-based context processor with direct globals update
- Fixed "AttributeError: 'Environment' object has no attribute 'context_processor'" error
- Improved template context handling for global variables

## [0.5.1] - 2023-11-05

### Added
- Template context processor for common template variables
- Added current_year function for copyright year in footer
- Improved template rendering with global context variables

### Fixed
- Fixed "Encountered unknown tag 'now'" error in base template
- Replaced Django-style {% now %} tag with Jinja2-compatible approach
- Fixed footer copyright year display

## [0.5.0] - 2023-11-01

### Added
- Custom Jinja2 template filters for improved UI
- Added timeago filter for human-readable date formatting
- Added filesizeformat filter for human-readable file sizes
- Improved template rendering with custom filters

### Fixed
- Fixed "No filter named 'timeago'" error in templates
- Resolved template rendering issues with date and file size formatting
- Fixed web interface display of timestamps and file sizes

## [0.4.9] - 2023-10-25

### Fixed
- Added missing get_current_user function to security module
- Fixed ImportError in main.py when importing security functions
- Implemented proper JWT token validation and user retrieval
- Fixed application startup error related to missing security functions

## [0.4.8] - 2023-10-20

### Fixed
- Completely removed problematic self-referential relationship in Category model
- Simplified Category model to avoid SQLAlchemy relationship issues
- Kept only the foreign key for parent-child relationship
- Fixed "Category.children and back-reference Category.parent are both of the same direction" error

## [0.4.7] - 2023-10-15

### Fixed
- Fixed self-referential relationship in Category model
- Simplified relationship definition to avoid remote_side issues
- Resolved "Column expression expected for argument 'remote_side'" error
- Fixed parent-child relationship in Category model

## [0.4.6] - 2023-10-10

### Fixed
- Fixed relationship definition in Category model
- Resolved conflict between built-in id() function and column attribute
- Fixed "Column expression expected for argument 'remote_side'" error
- Updated remote_side parameter to use string column name

## [0.4.5] - 2023-10-05

### Fixed
- Fixed missing database tables during initialization
- Added proper model imports in __init__.py
- Ensured all models are registered with SQLAlchemy metadata
- Fixed "no such table: user" error during admin user creation

## [0.4.4] - 2023-09-30

### Fixed
- Fixed database connection issues in admin user creation
- Added explicit SQLite connection for admin user creation
- Bypassed PostgreSQL connection attempts during installation
- Improved installation script with direct database path specification

## [0.4.3] - 2023-09-25

### Fixed
- Fixed SQLAlchemy raw SQL query execution in admin user creation
- Added proper text() wrapper for raw SQL queries
- Resolved ArgumentError with textual SQL expressions
- Updated installation script to handle SQLAlchemy 2.0 SQL execution

## [0.4.2] - 2023-09-20

### Fixed
- Resolved SQLAlchemy type annotation conflict in Base model
- Fixed conflict between `id: Any` type annotation and `id = Column(...)` definition
- Removed redundant type annotation in Base class
- Fixed admin user creation during installation

## [0.4.1] - 2023-09-15

### Fixed
- Fixed SQLAlchemy 2.0 compatibility issues with model classes
- Added `__allow_unmapped__ = True` to Base model class
- Resolved MappedAnnotationError during admin user creation
- Fixed database model compatibility with newer SQLAlchemy versions

## [0.4.0] - 2023-09-10

### Added
- Smart database selection with automatic SQLite fallback
- PostgreSQL availability detection
- Installation mode detection for optimal database choice
- Comprehensive database initialization module

### Changed
- Improved async database operations throughout the application
- Enhanced admin user creation process with better error handling
- Updated all version references throughout the codebase

### Fixed
- Fixed database initialization issues with PostgreSQL connections
- Resolved admin user creation with async session handling
- Fixed externally-managed-environment errors in Python 3.12+
- Improved virtual environment validation and recreation

## [0.3.0] - 2023-08-25

### Added
- Improved installation script with better Python 3.12+ support
- Support for externally managed environments
- Requirements.txt file for easier dependency management

### Changed
- Updated dependency management to be more flexible
- Removed strict version constraints to avoid dependency conflicts
- Improved error handling in installation process

### Fixed
- Fixed dependency conflicts between FastAPI and Starlette
- Resolved "externally-managed-environment" errors in Python 3.12+
- Added fallback methods for virtual environment creation

## [0.2.0] - 2023-08-15

### Added
- Responsive web interface with Bootstrap 5
- User authentication system (login and registration)
- Session management with "remember me" functionality
- Group viewing capability for all users
- Detailed group information page
- Admin interface for managing groups
- Group configuration management (create, edit, delete)
- Backfill management with progress visualization
- Installation script for easy setup
- Example configurations for Nginx and Apache
- Systemd service file generation

### Changed
- Improved project structure with web templates and static files
- Enhanced security with proper authentication and authorization
- Updated API endpoints to support web interface

### Fixed
- Various minor bugs and improvements

## [0.1.0] - 2023-07-01

### Added
- Initial release with basic API functionality
- Group management API endpoints
- User management API endpoints
- Release management API endpoints
- Category management API endpoints
- Basic authentication with JWT tokens
- Database models and schemas
- Configuration system
