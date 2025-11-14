# NZB Indexer

A modern Usenet indexer built with FastAPI, featuring a responsive web interface and comprehensive API.

## Features

- **Responsive Web Interface**: Built with Bootstrap 5 for optimal viewing on any device
- **User Authentication**: Secure login and registration system
- **Group Management**: View and manage Usenet newsgroups
- **Admin Panel**: Configure groups, manage users, and monitor system status
- **API Access**: Complete RESTful API with OpenAPI documentation
- **Backfill Support**: Track and manage article backfilling
- **Article Processing**: Convert Usenet articles into releases
- **Obfuscated Binary Support**: Process modern binary posts with obfuscated subjects
- **yEnc Header Detection**: Extract filenames from yEnc headers in article content
- **Release Management**: Extract metadata and categorize releases
- **NZB Generation**: Create NZB files for downloads with obfuscation
- **Search Functionality**: Find releases by name, category, and more
- **Sonarr/Radarr Integration**: Compatible with automation tools via Newznab API
- **Batch Processing**: Efficient group discovery with progress tracking
- **Job Control**: Cancel long-running tasks when needed
- **Diagnostic Tools**: Analyze NNTP connections and article processing

## Screenshots

(Screenshots to be added)

## Requirements

- Python 3.9 or higher
- PostgreSQL, MySQL, or SQLite
- Usenet server access

## Installation

### Quick Install

The easiest way to install NZB Indexer is to use the provided installation script:

```bash
git clone https://github.com/yourusername/nzbindexer.git
cd nzbindexer
chmod +x install.sh
./install.sh
```

The script will:
1. Check for Python 3.8+
2. Create a virtual environment
3. Install dependencies
4. Initialize the database
5. Create an admin user
6. Generate a systemd service file

### Manual Installation

If you prefer to install manually:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/nzbindexer.git
   cd nzbindexer
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Initialize the database:
   ```bash
   python -m app.db.init_db
   ```

5. Create an admin user:
   ```python
   from app.db.session import SessionLocal
   from app.db.models.user import User
   from app.core.security import get_password_hash
   import datetime

   db = SessionLocal()
   admin = User(
       email='admin@example.com',
       username='admin',
       hashed_password=get_password_hash('your_password'),
       is_active=True,
       is_admin=True,
       is_confirmed=True,
       last_login=datetime.datetime.utcnow()
   )
   db.add(admin)
   db.commit()
   db.close()
   ```

6. Run the application:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

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
