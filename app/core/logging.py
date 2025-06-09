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

    # Detailed log format for all handlers
    detailed_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_format)
    root_logger.addHandler(console_handler)

    # Main application log file
    main_file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "nzbindexer.log"),
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )
    main_file_handler.setLevel(logging.INFO)
    main_file_handler.setFormatter(detailed_format)
    root_logger.addHandler(main_file_handler)

    # Core application log file (app.core.*)
    core_file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "core.log"),
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )
    core_file_handler.setLevel(logging.DEBUG)
    core_file_handler.setFormatter(detailed_format)
    core_logger = logging.getLogger("app.core")
    core_logger.setLevel(logging.DEBUG)
    core_logger.addHandler(core_file_handler)

    # Processing log file (app.services.article.*)
    processing_file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "processing.log"),
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )
    processing_file_handler.setLevel(logging.DEBUG)
    processing_file_handler.setFormatter(detailed_format)
    processing_logger = logging.getLogger("app.services.article")
    processing_logger.setLevel(logging.DEBUG)
    processing_logger.addHandler(processing_file_handler)

    # Tasks log file (app.core.tasks.*)
    tasks_file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "tasks.log"),
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )
    tasks_file_handler.setLevel(logging.DEBUG)
    tasks_file_handler.setFormatter(detailed_format)
    tasks_logger = logging.getLogger("app.core.tasks")
    tasks_logger.setLevel(logging.DEBUG)
    tasks_logger.addHandler(tasks_file_handler)

    # NNTP connections log file (app.services.nntp.*)
    nntp_file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "nntp.log"),
        maxBytes=10485760,  # 10MB
        backupCount=5,
    )
    nntp_file_handler.setLevel(logging.DEBUG)
    nntp_file_handler.setFormatter(detailed_format)
    nntp_logger = logging.getLogger("app.services.nntp")
    nntp_logger.setLevel(logging.DEBUG)
    nntp_logger.addHandler(nntp_file_handler)

    # Set up loggers for other specific modules
    loggers = [
        "app",
        "app.api",
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
    logging.getLogger("app").info("Logging configured with verbose logs for core, processing, tasks, and NNTP")
