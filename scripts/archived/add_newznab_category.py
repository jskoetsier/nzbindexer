#!/usr/bin/env python
"""
Script to add the newznab_category column to the category table
"""

import asyncio
import logging
import os
import sqlite3
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.path.join(os.getcwd(), "app.db")


def add_newznab_category_column():
    """
    Add the newznab_category column to the category table
    """
    try:
        # Check if database file exists
        if not Path(DB_PATH).exists():
            logger.error(f"Database file not found: {DB_PATH}")
            return False

        # Connect to the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if the column already exists
        cursor.execute("PRAGMA table_info(category)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "newznab_category" in column_names:
            logger.info(
                "Column 'newznab_category' already exists in the category table"
            )
            conn.close()
            return True

        # Add the column
        logger.info("Adding 'newznab_category' column to the category table")
        cursor.execute("ALTER TABLE category ADD COLUMN newznab_category INTEGER")
        conn.commit()
        conn.close()

        logger.info("Column 'newznab_category' added successfully")
        return True

    except Exception as e:
        logger.error(f"Error adding column: {str(e)}")
        return False


if __name__ == "__main__":
    success = add_newznab_category_column()
    if success:
        print("Column 'newznab_category' added successfully to the category table")
    else:
        print("Failed to add column 'newznab_category' to the category table")
