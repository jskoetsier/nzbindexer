#!/usr/bin/env python
"""
Script to fix binary post detection in article processing
"""

import asyncio
import logging
import os
import sys
import re
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("fix_binary")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.group import Group
from app.services.nntp import NNTPService
from app.services.setting import get_app_settings
from sqlalchemy import select


async def test_binary_detection(db, group_name: str, limit: int = 100):
    """Test binary post detection on a group"""
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

    logger.info(f"Testing binary detection on group: {group.name}")

    try:
        # Connect to NNTP server
        conn = nntp_service.connect()

        # Select the group
        resp, count, first, last, name = conn.group(group.name)

        # Get a sample of articles
        sample_start = max(first, last - limit)
        sample_end = last

        logger.info(f"Getting sample of {limit} articles from {sample_start} to {sample_end}")

        # Get article headers
        try:
            resp, articles = conn.over((sample_start, sample_end))
        except Exception as e:
            logger.error(f"Error getting articles with OVER command: {str(e)}")
            logger.info("Falling back to HEAD command for individual articles")

            articles = []
            for article_id in range(sample_start, sample_end + 1):
                try:
                    resp, article_info = conn.head(f"{article_id}")

                    # Extract basic info from headers
                    subject = None
                    message_id = None

                    # Parse headers
                    for line in article_info.lines:
                        line_str = line.decode() if isinstance(line, bytes) else line
                        if line_str.startswith("Subject:"):
                            subject = line_str[8:].strip()
                        elif line_str.startswith("Message-ID:"):
                            message_id = line_str[10:].strip()

                    if subject and message_id:
                        articles.append((article_id, subject, None, None, message_id, None, 0, 0, {}))
                except Exception as article_e:
                    logger.debug(f"Skipping article {article_id}: {str(article_e)}")
                    continue

        # Close connection
        conn.quit()

        # Test binary detection on each article
        binary_count = 0
        binary_examples = []

        for article in articles:
            try:
                # Extract article info
                if len(article) >= 9:
                    article_num, subject, from_addr, date, message_id, references, bytes_count, lines_count, other = article
                elif len(article) == 2:
                    article_num, message_id = article
                    subject = ""
                    bytes_count = 0
                else:
                    logger.warning(f"Unexpected article format: {article}")
                    continue

                # Decode bytes to strings with error handling
                try:
                    subject = subject.decode('utf-8', errors='replace') if isinstance(subject, bytes) else subject
                    subject = ''.join(c if ord(c) < 0xD800 or ord(c) > 0xDFFF else '?' for c in subject)
                except Exception:
                    subject = "Unknown Subject"

                # Test original binary detection
                binary_name, part_num, total_parts = parse_binary_subject_original(subject)

                if binary_name and part_num:
                    binary_count += 1
                    if len(binary_examples) < 5:
                        binary_examples.append({
                            "subject": subject,
                            "binary_name": binary_name,
                            "part_num": part_num,
                            "total_parts": total_parts
                        })

                # Test enhanced binary detection
                binary_name, part_num, total_parts = parse_binary_subject_enhanced(subject)

                if binary_name and part_num and not (binary_name and part_num):
                    logger.info(f"Enhanced detection found binary that original missed: {subject}")
                    binary_count += 1
                    if len(binary_examples) < 5:
                        binary_examples.append({
                            "subject": subject,
                            "binary_name": binary_name,
                            "part_num": part_num,
                            "total_parts": total_parts,
                            "enhanced": True
                        })

            except Exception as e:
                logger.error(f"Error testing binary detection on article: {str(e)}")

        logger.info(f"Found {binary_count} binary posts out of {len(articles)} articles")

        if binary_examples:
            logger.info("Examples of binary posts found:")
            for example in binary_examples:
                logger.info(f"  Subject: {example['subject']}")
                logger.info(f"  Binary Name: {example['binary_name']}")
                logger.info(f"  Part: {example['part_num']}/{example['total_parts']}")
                if example.get("enhanced"):
                    logger.info(f"  (Found by enhanced detection)")
                logger.info("")

        return binary_count

    except Exception as e:
        logger.error(f"Error testing binary detection: {str(e)}")
        return 0


def parse_binary_subject_original(subject: str):
    """
    Original binary subject parsing function from article.py
    """
    # Remove common prefixes
    subject = re.sub(r"^Re: ", "", subject)

    # Try to match common binary post patterns

    # Pattern: "name [01/10] - description"
    match = re.search(r"^(.*?)\s*\[(\d+)/(\d+)\]", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name (01/10) - description"
    match = re.search(r"^(.*?)\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - 01/10 - description"
    match = re.search(r"^(.*?)\s*-\s*(\d+)/(\d+)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - Part 01 of 10 - description"
    match = re.search(r"^(.*?)\s*-\s*[Pp]art\s*(\d+)\s*of\s*(\d+)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - File 01 of 10 - description"
    match = re.search(r"^(.*?)\s*-\s*[Ff]ile\s*(\d+)\s*of\s*(\d+)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - yEnc (01/10) - description"
    match = re.search(r"^(.*?)\s*-\s*yEnc\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - yEnc - (01/10) - description"
    match = re.search(r"^(.*?)\s*-\s*yEnc\s*-\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name (yEnc 01/10) - description"
    match = re.search(r"^(.*?)\s*\(yEnc\s*(\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - yEnc (01/10)"
    match = re.search(r"^(.*?)\s*-\s*yEnc\s*\((\d+)/(\d+)\)\s*$", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name [01/10]"
    match = re.search(r"^(.*?)\s*\[(\d+)/(\d+)\]\s*$", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name (01/10)"
    match = re.search(r"^(.*?)\s*\((\d+)/(\d+)\)\s*$", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Single file pattern: "name - yEnc"
    match = re.search(r"^(.*?)\s*-\s*yEnc\s*$", subject)
    if match:
        name = match.group(1).strip()
        return name, 1, 1  # Treat as a single part

    # No pattern matched
    return None, None, None


def parse_binary_subject_enhanced(subject: str):
    """
    Enhanced binary subject parsing function with more patterns
    """
    # Remove common prefixes
    subject = re.sub(r"^Re: ", "", subject)

    # Check for yEnc indicator anywhere in the subject
    has_yenc = "yenc" in subject.lower() or "yEnc" in subject

    # Try to match common binary post patterns

    # Pattern: "name [01/10] - description"
    match = re.search(r"(.*?)\s*\[(\d+)/(\d+)\]", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name (01/10) - description"
    match = re.search(r"(.*?)\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - 01/10 - description"
    match = re.search(r"(.*?)\s*-\s*(\d+)/(\d+)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - Part 01 of 10 - description"
    match = re.search(r"(.*?)\s*-\s*[Pp]art\s*(\d+)\s*of\s*(\d+)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - File 01 of 10 - description"
    match = re.search(r"(.*?)\s*-\s*[Ff]ile\s*(\d+)\s*of\s*(\d+)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - yEnc (01/10) - description"
    match = re.search(r"(.*?)\s*-\s*yEnc\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - yEnc - (01/10) - description"
    match = re.search(r"(.*?)\s*-\s*yEnc\s*-\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name (yEnc 01/10) - description"
    match = re.search(r"(.*?)\s*\(yEnc\s*(\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name - yEnc (01/10)"
    match = re.search(r"(.*?)\s*-\s*yEnc\s*\((\d+)/(\d+)\)\s*$", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name [01/10]"
    match = re.search(r"(.*?)\s*\[(\d+)/(\d+)\]\s*$", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "name (01/10)"
    match = re.search(r"(.*?)\s*\((\d+)/(\d+)\)\s*$", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Single file pattern: "name - yEnc"
    match = re.search(r"(.*?)\s*-\s*yEnc\s*$", subject)
    if match:
        name = match.group(1).strip()
        return name, 1, 1  # Treat as a single part

    # Additional patterns for enhanced detection

    # Pattern: "description - filename.ext (01/10)"
    match = re.search(r".*?-\s*([\w\.-]+\.\w+)\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "description - filename.ext [01/10]"
    match = re.search(r".*?-\s*([\w\.-]+\.\w+)\s*\[(\d+)/(\d+)\]", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "filename.ext (01/10)"
    match = re.search(r"([\w\.-]+\.\w+)\s*\((\d+)/(\d+)\)", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "filename.ext [01/10]"
    match = re.search(r"([\w\.-]+\.\w+)\s*\[(\d+)/(\d+)\]", subject)
    if match:
        name = match.group(1).strip()
        part = int(match.group(2))
        total = int(match.group(3))
        return name, part, total

    # Pattern: "01/10 - filename.ext"
    match = re.search(r"(\d+)/(\d+)\s*-\s*([\w\.-]+\.\w+)", subject)
    if match:
        part = int(match.group(1))
        total = int(match.group(2))
        name = match.group(3).strip()
        return name, part, total

    # Pattern: "[01/10] - filename.ext"
    match = re.search(r"\[(\d+)/(\d+)\]\s*-\s*([\w\.-]+\.\w+)", subject)
    if match:
        part = int(match.group(1))
        total = int(match.group(2))
        name = match.group(3).strip()
        return name, part, total

    # Pattern: "(01/10) - filename.ext"
    match = re.search(r"\((\d+)/(\d+)\)\s*-\s*([\w\.-]+\.\w+)", subject)
    if match:
        part = int(match.group(1))
        total = int(match.group(2))
        name = match.group(3).strip()
        return name, part, total

    # If we have yEnc in the subject, try to extract a filename
    if has_yenc:
        # Look for common file extensions
        match = re.search(r"([\w\.-]+\.(mkv|avi|mp4|mov|wmv|iso|zip|rar|7z|tar|gz|mp3|flac|wav|epub|pdf|mobi|azw|doc|docx|xls|xlsx|ppt|pptx))", subject, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            return name, 1, 1  # Assume it's a single part if we can't determine

    # No pattern matched
    return None, None, None


async def update_article_processing_code(db):
    """Update the article processing code to use the enhanced binary detection"""
    try:
        # Path to the article.py file
        article_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "app", "services", "article.py")

        # Check if the file exists
        if not os.path.exists(article_py_path):
            logger.error(f"Article processing code not found at {article_py_path}")
            return False

        # Read the current content
        with open(article_py_path, "r") as f:
            content = f.read()

        # Check if the file contains the _parse_binary_subject method
        if "_parse_binary_subject" not in content:
            logger.error("Could not find _parse_binary_subject method in article.py")
            return False

        # Replace the _parse_binary_subject method with the enhanced version
        new_content = re.sub(
            r"def _parse_binary_subject\(.*?\):\s+\"\"\".*?\"\"\".*?return None, None, None",
            inspect.getsource(parse_binary_subject_enhanced).replace("parse_binary_subject_enhanced", "_parse_binary_subject"),
            content,
            flags=re.DOTALL
        )

        # Write the updated content back to the file
        with open(article_py_path, "w") as f:
            f.write(new_content)

        logger.info(f"Updated article processing code with enhanced binary detection")
        return True
    except Exception as e:
        logger.error(f"Error updating article processing code: {str(e)}")
        return False


async def test_binary_groups(db):
    """Test binary detection on common binary groups"""
    # List of common binary groups to test
    binary_groups = [
        "alt.binaries.teevee",
        "alt.binaries.moovee",
        "alt.binaries.movies",
        "alt.binaries.hdtv",
        "alt.binaries.hdtv.x264",
        "alt.binaries.tv",
    ]

    results = {}

    for group_name in binary_groups:
        logger.info(f"Testing binary detection on group: {group_name}")
        binary_count = await test_binary_detection(db, group_name, limit=100)
        results[group_name] = binary_count

    logger.info("Binary detection test results:")
    for group_name, count in results.items():
        logger.info(f"  {group_name}: {count} binary posts found")

    return results


async def main():
    """Main function"""
    import inspect

    logger.info("Starting binary detection fix")

    async with AsyncSessionLocal() as db:
        # Test binary detection on common binary groups
        results = await test_binary_groups(db)

        # Update article processing code if any binary posts were found
        if any(count > 0 for count in results.values()):
            await update_article_processing_code(db)
            logger.info("Binary detection fix applied successfully")
        else:
            logger.warning("No binary posts found in any of the tested groups")
            logger.warning("Please check your NNTP server configuration and group selection")


if __name__ == "__main__":
    import inspect
    asyncio.run(main())
    print("Binary detection fix complete!")
