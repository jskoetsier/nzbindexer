# Changelog

All notable changes to the NZB Indexer project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
