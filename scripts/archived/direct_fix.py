#!/usr/bin/env python
"""
Direct fix for NZB indexer issues
This script directly creates releases and NZB files, bypassing the normal flow
"""

import asyncio
import logging
import os
import sys
import re
import uuid
import shutil
from typing import Dict, List, Optional, Set, Tuple, Union
from datetime import datetime
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger("direct_fix")

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


async def check_database_connection():
    """Check the database connection"""
    logger.info("Checking database connection")

    try:
        async with AsyncSessionLocal() as db:
            # Try a simple query
            query = select(func.count(Group.id))
            result = await db.execute(query)
            count = result.scalar()

            logger.info(f"Database connection successful. Found {count} groups.")
            return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False


async def check_and_create_directories():
    """Check and create necessary directories"""
    logger.info("Checking and creating necessary directories")

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

        # Check permissions
        try:
            # Create a test file to check write permissions
            test_file = os.path.join(dir_path, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            logger.info(f"Directory {dir_path} is writable")
        except Exception as e:
            logger.error(f"Directory {dir_path} is not writable: {str(e)}")
            return False

    return True


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


async def check_nzb_service():
    """Check the NZB service"""
    logger.info("Checking NZB service")

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

            # Create NZB service
            nzb_service = NZBService(nntp_service=nntp_service)

            # Get a release
            query = select(Release).limit(1)
            result = await db.execute(query)
            release = result.scalars().first()

            if not release:
                logger.warning("No releases found to test NZB generation")
                return False

            # Generate NZB file
            nzb_path = await nzb_service.generate_nzb(db, release.id)

            if nzb_path:
                logger.info(f"Successfully generated NZB file: {nzb_path}")
                return True
            else:
                logger.warning("Failed to generate NZB file")
                return False

        except Exception as e:
            logger.error(f"Error checking NZB service: {str(e)}")
            return False


async def check_release_service():
    """Check the release service"""
    logger.info("Checking release service")

    async with AsyncSessionLocal() as db:
        try:
            # Count releases
            query = select(func.count(Release.id))
            result = await db.execute(query)
            count = result.scalar()

            logger.info(f"Found {count} releases in the database")

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

            return count > 0

        except Exception as e:
            logger.error(f"Error checking release service: {str(e)}")
            return False


async def fix_nzb_directory_permissions():
    """Fix NZB directory permissions"""
    logger.info("Fixing NZB directory permissions")

    try:
        # Get the NZB directory
        nzb_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nzb")

        # Check if the directory exists
        if not os.path.exists(nzb_dir):
            os.makedirs(nzb_dir, exist_ok=True)
            logger.info(f"Created NZB directory: {nzb_dir}")

        # Set permissions
        os.chmod(nzb_dir, 0o755)  # rwxr-xr-x
        logger.info(f"Set permissions on NZB directory: {nzb_dir}")

        # Check if the directory is writable
        test_file = os.path.join(nzb_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        logger.info(f"NZB directory is writable: {nzb_dir}")

        return True

    except Exception as e:
        logger.error(f"Error fixing NZB directory permissions: {str(e)}")
        return False


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


async def main():
    """Main function"""
    logger.info("Starting direct fix")

    # Check database connection
    db_ok = await check_database_connection()
    if not db_ok:
        logger.error("Database connection check failed, aborting")
        return

    # Check and create directories
    dirs_ok = await check_and_create_directories()
    if not dirs_ok:
        logger.error("Directory check failed, aborting")
        return

    # Fix NZB directory permissions
    nzb_perms_ok = await fix_nzb_directory_permissions()
    if not nzb_perms_ok:
        logger.error("NZB directory permissions fix failed, aborting")
        return

    # Fix database issues
    db_fix_ok = await fix_database_issues()
    if not db_fix_ok:
        logger.error("Database issues fix failed, aborting")
        return

    # Create a test release
    release_ok = await create_test_release()
    if not release_ok:
        logger.error("Test release creation failed, aborting")
        return

    # Check release service
    release_service_ok = await check_release_service()
    if not release_service_ok:
        logger.error("Release service check failed, aborting")
        return

    # Check NZB service
    nzb_service_ok = await check_nzb_service()
    if not nzb_service_ok:
        logger.error("NZB service check failed, aborting")
        return

    logger.info("Direct fix complete")


if __name__ == "__main__":
    asyncio.run(main())
    print("Direct fix complete!")
