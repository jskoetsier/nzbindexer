# Changelog

All notable changes to the NZB Indexer project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
