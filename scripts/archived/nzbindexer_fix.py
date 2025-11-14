#!/usr/bin/env python
"""
NZB Indexer Fix - Comprehensive fix script for NZB Indexer
This script consolidates all fixes and functionality from various scripts
"""

import asyncio
import logging
import os
import sys
import re
import uuid
import shutil
import argparse
from typing import Dict, List, Optional, Set, Tuple, Union
from datetime import datetime
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger("nzbindexer_fix")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.db.models.release import Release
from app.db.models.category import Category
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from app.services.article import ArticleService
from app.services.nzb import NZBService
from app.services.release import create_release, create_release_guid
from app.schemas.release import ReleaseCreate
from sqlalchemy import select, update, func, text


# ===== DATABASE FIXES =====

async def fix_database_issues():
    """Fix database issues"""
    logger.info("Fixing database issues")

    async with AsyncSessionLocal() as db:
        try:
            # Execute PRAGMA statements to optimize SQLite for concurrent access
            await db.execute(text("PRAGMA journal_mode = WAL"))
            await db.execute(text("PRAGMA synchronous = NORMAL"))
            await db.execute(text("PRAGMA temp_store = MEMORY"))
            await db.execute(text("PRAGMA cache_size = 10000"))

            # Vacuum the database to reclaim space and optimize
            await db.execute(text("VACUUM"))

            # Analyze the database to optimize query planning
            await db.execute(text("ANALYZE"))

            logger.info("Applied SQLite optimizations to reduce database locking")

            # Commit the changes
            await db.commit()
            return True

        except Exception as e:
            logger.error(f"Error optimizing database: {str(e)}")
            await db.rollback()
            return False


# ===== DIRECTORY FIXES =====

async def fix_directories():
    """Fix directory issues"""
    logger.info("Fixing directory issues")

    # Define directories to check
    directories = [
        "data",
        "data/nzb",
        "data/covers",
        "data/samples",
    ]

    # Check and create each directory
    for directory in directories:
        dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), directory)
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"Created directory: {dir_path}")
            except Exception as e:
                logger.error(f"Failed to create directory {dir_path}: {str(e)}")
                return False

        # Set permissions
        try:
            os.chmod(dir_path, 0o755)  # rwxr-xr-x
            logger.info(f"Set permissions on directory: {dir_path}")
        except Exception as e:
            logger.error(f"Failed to set permissions on directory {dir_path}: {str(e)}")
            return False

        # Check if the directory is writable
        try:
            test_file = os.path.join(dir_path, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            logger.info(f"Directory {dir_path} is writable")
        except Exception as e:
            logger.error(f"Directory {dir_path} is not writable: {str(e)}")
            return False

    return True


# ===== TEST RELEASE CREATION =====

async def create_test_release():
    """Create a test release directly in the database"""
    logger.info("Creating a test release")

    async with AsyncSessionLocal() as db:
        try:
            # Get a group
            query = select(Group).filter(Group.active == True).limit(1)
            result = await db.execute(query)
            group = result.scalars().first()

            if not group:
                logger.error("No active groups found")
                return False

            # Get or create a category
            query = select(Category).filter(Category.name == "Other")
            result = await db.execute(query)
            category = result.scalars().first()

            if not category:
                # Create default category
                category = Category(
                    name="Other",
                    description="Uncategorized releases",
                    active=True,
                    sort_order=999,
                )
                db.add(category)
                await db.commit()
                await db.refresh(category)
                logger.info("Created default 'Other' category")

            # Create a unique name for the test release
            release_name = f"Test Release {datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Create release data
            release_data = ReleaseCreate(
                name=release_name,
                search_name=release_name.lower(),
                guid=create_release_guid(release_name, group.name),
                size=1024 * 1024,  # 1 MB
                files=1,
                completion=100.0,
                posted_date=datetime.utcnow(),
                status=1,  # Active
                passworded=0,  # Unknown
                category_id=category.id,
                group_id=group.id,
            )

            # Create the release
            release = await create_release(db, release_data)
            logger.info(f"Created test release: {release.id} - {release.name}")

            # Create a test NZB file
            nzb_path = await create_test_nzb_file(release)

            if nzb_path:
                logger.info(f"Created test NZB file: {nzb_path}")

                # Update the release with the NZB GUID
                release.nzb_guid = os.path.basename(nzb_path).replace(".nzb", "")
                db.add(release)
                await db.commit()
                logger.info(f"Updated release {release.id} with NZB GUID: {release.nzb_guid}")

                return True
            else:
                logger.error("Failed to create test NZB file")
                return False

        except Exception as e:
            logger.error(f"Error creating test release: {str(e)}")
            await db.rollback()
            return False


async def create_test_nzb_file(release):
    """Create a test NZB file"""
    logger.info(f"Creating test NZB file for release {release.id}")

    try:
        # Create a simple NZB file structure
        root = ET.Element("nzb", xmlns="http://www.newzbin.com/DTD/2003/nzb")

        # Add a file element
        file_elem = ET.SubElement(root, "file",
                                 poster="test@example.com",
                                 date="1234567890",
                                 subject=f"Test File for {release.name}")

        # Add groups
        groups_elem = ET.SubElement(file_elem, "groups")
        group_elem = ET.SubElement(groups_elem, "group")
        group_elem.text = "alt.binaries.test"

        # Add segments
        segments_elem = ET.SubElement(file_elem, "segments")
        segment_elem = ET.SubElement(segments_elem, "segment", bytes="1024", number="1")
        segment_elem.text = f"<test-{uuid.uuid4()}@test.com>"

        # Create the XML string
        xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        # Create the NZB file
        nzb_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nzb")
        nzb_guid = str(uuid.uuid4())
        nzb_path = os.path.join(nzb_dir, f"{nzb_guid}.nzb")

        with open(nzb_path, "wb") as f:
            f.write(xml_str)

        return nzb_path

    except Exception as e:
        logger.error(f"Error creating test NZB file: {str(e)}")
        return None


# ===== GROUP PROCESSING =====

async def reset_group_article_ids(group_name=None):
    """Reset article IDs for groups"""
    logger.info("Resetting article IDs for groups")

    async with AsyncSessionLocal() as db:
        # Get app settings
        app_settings = await get_app_settings(db)

        # Create NNTP service
        nntp_service = NNTPService(
            server=app_settings.nntp_server,
            port=(
                app_settings.nntp_ssl_port
                if app_settings.nntp_ssl
                else app_settings.nntp_port
            ),
            use_ssl=app_settings.nntp_ssl,
            username=app_settings.nntp_username,
            password=app_settings.nntp_password,
        )

        # Get groups to reset
        if group_name:
            query = select(Group).filter(Group.name == group_name)
        else:
            query = select(Group).filter(Group.active == True)

        result = await db.execute(query)
        groups = result.scalars().all()

        logger.info(f"Resetting article IDs for {len(groups)} groups")

        # Reset each group
        for group in groups:
            try:
                # Connect to NNTP server
                conn = nntp_service.connect()

                # Select the group
                resp, count, first, last, name = conn.group(group.name)

                # Close connection
                conn.quit()

                # Handle both string and bytes for name
                name_str = name if isinstance(name, str) else name.decode()

                logger.info(f"Group {name_str}: {count} articles, {first}-{last}")

                # Calculate a reasonable backfill target (e.g., 1000 articles back from last)
                backfill_amount = min(10000, (last - first) // 2)
                backfill_target = max(first, last - backfill_amount)

                # Update group's article IDs
                old_first = group.first_article_id
                old_last = group.last_article_id
                old_current = group.current_article_id
                old_backfill = group.backfill_target

                # Set current_article_id to a value less than last_article_id
                # This ensures there are articles to process
                current_article_id = last - 1000  # Set current to 1000 articles before last

                group.first_article_id = first
                group.last_article_id = last
                group.current_article_id = current_article_id
                group.backfill_target = backfill_target

                # Save changes
                db.add(group)
                await db.commit()

                logger.info(f"Updated group {group.name}:")
                logger.info(f"  First: {old_first} -> {first}")
                logger.info(f"  Last: {old_last} -> {last}")
                logger.info(f"  Current: {old_current} -> {current_article_id}")
                logger.info(f"  Backfill Target: {old_backfill} -> {backfill_target}")

            except Exception as e:
                logger.error(f"Error resetting group {group.name}: {str(e)}")
                await db.rollback()

        logger.info("Group article IDs reset complete")
        return True


async def process_group(group_name: str, limit: int = 50):
    """Process a group"""
    logger.info(f"Processing group {group_name}")

    async with AsyncSessionLocal() as db:
        try:
            # Get app settings
            app_settings = await get_app_settings(db)

            # Create NNTP service
            nntp_service = NNTPService(
                server=app_settings.nntp_server,
                port=(
                    app_settings.nntp_ssl_port
                    if app_settings.nntp_ssl
                    else app_settings.nntp_port
                ),
                use_ssl=app_settings.nntp_ssl,
                username=app_settings.nntp_username,
                password=app_settings.nntp_password,
            )

            # Get group
            query = select(Group).filter(Group.name == group_name)
            result = await db.execute(query)
            group = result.scalars().first()

            if not group:
                logger.error(f"Group {group_name} not found")
                return

            # Create article service
            article_service = ArticleService(nntp_service=nntp_service)

            # Connect to NNTP server
            conn = nntp_service.connect()

            # Select the group
            resp, count, first, last, name = conn.group(group.name)
            # Handle both string and bytes for name
            name_str = name if isinstance(name, str) else name.decode()
            logger.info(f"Selected group {name_str}: {count} articles, {first}-{last}")

            # Close connection
            conn.quit()

            # Calculate range to process - use the most recent articles
            process_start = last - limit
            process_end = last

            logger.info(f"Processing articles {process_start} to {process_end} for group {group.name}")

            # Process articles
            stats = await article_service.process_articles(
                db, group, process_start, process_end, limit
            )

            logger.info(f"Article processing stats: {stats}")

            # Check if any releases were created
            query = select(func.count(Release.id))
            result = await db.execute(query)
            release_count = result.scalar()

            logger.info(f"Total releases in database: {release_count}")

            # Get a sample of releases
            query = select(Release).limit(5)
            result = await db.execute(query)
            releases = result.scalars().all()

            if releases:
                logger.info("Sample releases:")
                for release in releases:
                    logger.info(f"  ID: {release.id}, Name: {release.name}, Files: {release.files}, Size: {release.size}")

                    # Check if NZB file exists
                    if release.nzb_guid:
                        nzb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nzb", f"{release.nzb_guid}.nzb")
                        if os.path.exists(nzb_path):
                            logger.info(f"  NZB file exists: {nzb_path}")
                        else:
                            logger.warning(f"  NZB file does not exist: {nzb_path}")
                    else:
                        logger.warning(f"  Release {release.id} has no NZB GUID")
            else:
                logger.info("No releases found in database")

            return stats

        except Exception as e:
            logger.error(f"Error processing group {group_name}: {str(e)}")
            await db.rollback()
            return None


# ===== MAIN FUNCTIONS =====

async def fix_all():
    """Fix all issues"""
    logger.info("Starting comprehensive fix")

    # Fix database issues
    db_fix_ok = await fix_database_issues()
    if not db_fix_ok:
        logger.error("Database issues fix failed")
        return False

    # Fix directory issues
    dirs_ok = await fix_directories()
    if not dirs_ok:
        logger.error("Directory fix failed")
        return False

    # Create a test release
    release_ok = await create_test_release()
    if not release_ok:
        logger.error("Test release creation failed")
        return False

    logger.info("Comprehensive fix complete")
    return True


async def process_binary_groups(limit=50):
    """Process binary groups"""
    logger.info("Processing binary groups")

    # List of binary groups to test
    binary_groups = [
        "alt.binaries.teevee",
        "alt.binaries.moovee",
        "alt.binaries.movies",
        "alt.binaries.hdtv",
        "alt.binaries.hdtv.x264",
        "alt.binaries.tv",
        "alt.binaries.multimedia",
    ]

    # Process each group
    for group_name in binary_groups:
        await process_group(group_name, limit)
        print("\n" + "-" * 80 + "\n")

    return True


# ===== COMMAND LINE INTERFACE =====

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="NZB Indexer Fix")
    parser.add_argument("--fix-all", action="store_true", help="Fix all issues")
    parser.add_argument("--fix-db", action="store_true", help="Fix database issues")
    parser.add_argument("--fix-dirs", action="store_true", help="Fix directory issues")
    parser.add_argument("--test-release", action="store_true", help="Create a test release")
    parser.add_argument("--reset-groups", action="store_true", help="Reset group article IDs")
    parser.add_argument("--reset-group", type=str, help="Reset article IDs for a specific group")
    parser.add_argument("--process-groups", action="store_true", help="Process binary groups")
    parser.add_argument("--process-group", type=str, help="Process a specific group")
    parser.add_argument("--limit", type=int, default=50, help="Limit the number of articles to process")

    args = parser.parse_args()

    # If no arguments are provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        return

    # Fix all issues
    if args.fix_all:
        await fix_all()

    # Fix database issues
    if args.fix_db:
        await fix_database_issues()

    # Fix directory issues
    if args.fix_dirs:
        await fix_directories()

    # Create a test release
    if args.test_release:
        await create_test_release()

    # Reset group article IDs
    if args.reset_groups:
        await reset_group_article_ids()

    # Reset article IDs for a specific group
    if args.reset_group:
        await reset_group_article_ids(args.reset_group)

    # Process binary groups
    if args.process_groups:
        await process_binary_groups(args.limit)

    # Process a specific group
    if args.process_group:
        await process_group(args.process_group, args.limit)


if __name__ == "__main__":
    asyncio.run(main())
    print("NZB Indexer Fix complete!")
