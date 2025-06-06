#!/bin/bash

# NZB Indexer Installation Script
# Version: 0.2.0

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}NZB Indexer Installation Script${NC}"
echo -e "${GREEN}=============================${NC}"
echo ""

# Check if Python 3.8+ is installed
echo -e "${YELLOW}Checking Python version...${NC}"
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
        echo -e "${GREEN}Python $PYTHON_VERSION detected. Continuing...${NC}"
        PYTHON_CMD="python3"
    else
        echo -e "${RED}Python 3.8+ is required. Found Python $PYTHON_VERSION${NC}"
        exit 1
    fi
else
    echo -e "${RED}Python 3 not found. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

# Create virtual environment first to avoid externally-managed-environment issues
echo -e "${YELLOW}Setting up virtual environment...${NC}"

# Check if venv exists and is valid
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    echo -e "${GREEN}Valid virtual environment found.${NC}"
else
    # Remove any existing invalid venv directory
    if [ -d "venv" ]; then
        echo -e "${YELLOW}Found invalid virtual environment. Removing it...${NC}"
        rm -rf venv
    fi

    echo -e "${YELLOW}Creating new virtual environment...${NC}"

    # Check if venv module is available
    if $PYTHON_CMD -c "import venv" &>/dev/null; then
        echo -e "${GREEN}Using built-in venv module...${NC}"
        $PYTHON_CMD -m venv venv
    else
        echo -e "${YELLOW}venv module not available. Trying alternative methods...${NC}"

        # Try to use virtualenv directly if it's installed
        if command -v virtualenv &>/dev/null; then
            echo -e "${GREEN}Using system virtualenv...${NC}"
            virtualenv venv
        else
            # Try to install virtualenv
            echo -e "${YELLOW}Installing virtualenv...${NC}"

            # Try with --break-system-packages flag for Python 3.12+
            $PYTHON_CMD -m pip install --user --break-system-packages virtualenv 2>/dev/null || \
            $PYTHON_CMD -m pip install --user virtualenv 2>/dev/null || \
            echo -e "${RED}Failed to install virtualenv. Please install it manually with: pip install --user virtualenv${NC}"

            # Check if virtualenv was installed successfully
            if $PYTHON_CMD -m virtualenv --version &>/dev/null; then
                echo -e "${GREEN}Successfully installed virtualenv. Creating environment...${NC}"
                $PYTHON_CMD -m virtualenv venv
            else
                echo -e "${RED}Could not create virtual environment. Please create it manually with: python -m venv venv${NC}"
                exit 1
            fi
        fi
    fi

    # Verify the virtual environment was created successfully
    if [ ! -f "venv/bin/activate" ]; then
        echo -e "${RED}Failed to create a valid virtual environment. Please check your Python installation.${NC}"
        exit 1
    fi

    echo -e "${GREEN}Virtual environment created successfully.${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate || { echo -e "${RED}Failed to activate virtual environment.${NC}"; exit 1; }

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -r requirements.txt

# Check if database exists and initialize if needed
echo -e "${YELLOW}Checking database...${NC}"
if [ ! -f "app.db" ]; then
    echo -e "${YELLOW}Database not found. Initializing database...${NC}"
    $PYTHON_CMD -m app.db.init_db
    echo -e "${GREEN}Database initialized.${NC}"
else
    echo -e "${GREEN}Database found. Skipping initialization.${NC}"
fi

# Create initial admin user if needed
echo -e "${YELLOW}Checking for admin user...${NC}"
if $PYTHON_CMD -c "from app.db.session import SessionLocal; from app.db.models.user import User; db = SessionLocal(); print(db.query(User).filter(User.is_admin == True).count() == 0)" | grep -q "True"; then
    echo -e "${YELLOW}No admin user found. Creating admin user...${NC}"
    read -p "Enter admin email: " ADMIN_EMAIL
    read -p "Enter admin username: " ADMIN_USERNAME
    read -s -p "Enter admin password: " ADMIN_PASSWORD
    echo ""

    $PYTHON_CMD -c "
from app.db.session import SessionLocal
from app.db.models.user import User
from app.core.security import get_password_hash
import datetime

db = SessionLocal()
admin = User(
    email='$ADMIN_EMAIL',
    username='$ADMIN_USERNAME',
    hashed_password=get_password_hash('$ADMIN_PASSWORD'),
    is_active=True,
    is_admin=True,
    is_confirmed=True,
    last_login=datetime.datetime.utcnow()
)
db.add(admin)
db.commit()
db.close()
"
    echo -e "${GREEN}Admin user created.${NC}"
else
    echo -e "${GREEN}Admin user already exists. Skipping creation.${NC}"
fi

# Create systemd service file
echo -e "${YELLOW}Creating systemd service file...${NC}"
SERVICE_FILE="nzbindexer.service"
cat > $SERVICE_FILE << EOL
[Unit]
Description=NZB Indexer
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=nzbindexer

[Install]
WantedBy=multi-user.target
EOL

echo -e "${GREEN}Service file created: $SERVICE_FILE${NC}"
echo -e "${YELLOW}To install the service system-wide, run:${NC}"
echo -e "  sudo cp $SERVICE_FILE /etc/systemd/system/"
echo -e "  sudo systemctl daemon-reload"
echo -e "  sudo systemctl enable nzbindexer"
echo -e "  sudo systemctl start nzbindexer"

echo ""
echo -e "${GREEN}Installation completed successfully!${NC}"
echo -e "${YELLOW}To start the application manually, run:${NC}"
echo -e "  source venv/bin/activate"
echo -e "  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo -e "${YELLOW}Access the web interface at:${NC} http://localhost:8000"
echo -e "${YELLOW}Access the API documentation at:${NC} http://localhost:8000/api/v1/docs"
echo ""
echo -e "${GREEN}Thank you for installing NZB Indexer!${NC}"
