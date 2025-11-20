#!/usr/bin/env python3
"""
Database Migration: Add release_regexes table

Creates the release_regexes table for regex pattern-based release name extraction.
Based on NNTmux's proven approach with 1000+ patterns.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from sqlalchemy import text


async def create_release_regexes_table():
    """Create the release_regexes table"""
    
    # Split SQL into separate statements for asyncpg
    sql_statements = [
        """
        CREATE TABLE IF NOT EXISTS release_regexes (
            id SERIAL PRIMARY KEY,
            group_pattern VARCHAR(255) NOT NULL,
            regex TEXT NOT NULL,
            description VARCHAR(500),
            ordinal INTEGER NOT NULL DEFAULT 100,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            match_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_release_regexes_group_pattern 
            ON release_regexes(group_pattern)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_release_regexes_ordinal 
            ON release_regexes(ordinal)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_release_regexes_active 
            ON release_regexes(active)
        """
    ]
    
    async with AsyncSessionLocal() as db:
        try:
            # Execute each SQL statement separately
            for sql in sql_statements:
                await db.execute(text(sql))
            await db.commit()
            
            print("✓ Successfully created release_regexes table and indexes")
            return True
            
        except Exception as e:
            print(f"✗ Error creating table: {e}")
            await db.rollback()
            return False


async def check_table_exists():
    """Check if release_regexes table exists"""

    check_sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'release_regexes'
    );
    """

    async with AsyncSessionLocal() as db:
        result = await db.execute(text(check_sql))
        exists = result.scalar()
        return exists


async def main():
    print("=" * 60)
    print("Database Migration: Create release_regexes table")
    print("=" * 60)

    # Check if table already exists
    exists = await check_table_exists()

    if exists:
        print("⚠ Table 'release_regexes' already exists")
        response = input("Do you want to continue anyway? (y/N): ")
        if response.lower() != "y":
            print("Migration cancelled")
            return

    # Create the table
    success = await create_release_regexes_table()

    if success:
        print("\n✓ Migration completed successfully")
        print("\nNext steps:")
        print("1. Run: python scripts/seed_release_regexes.py")
        print("2. Restart the application")
    else:
        print("\n✗ Migration failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
