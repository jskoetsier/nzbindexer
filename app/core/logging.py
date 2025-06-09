"""
Logging configuration for the application
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from app.core.config import settings


def setup_logging():
    """
    Set up logging for the application
    """
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "nzbindexer.log"),
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    # Set up loggers for specific modules
    loggers = [
        "app",
        "app.api",
        "app.core",
        "app.db",
        "app.services",
        "app.web",
        "uvicorn",
        "sqlalchemy",
    ]

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = True

    # Set SQLAlchemy logger to WARNING to reduce noise
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # Log startup message
    logging.getLogger("app").info("Logging configured")
