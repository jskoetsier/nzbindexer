#!/usr/bin/env python3
"""
Seed Release Regex Patterns

Seeds the database with common regex patterns for release name extraction.
Based on NNTmux's proven patterns that achieve 15-25% improvement.

This includes patterns for:
- TV Shows (S01E01, 1x01, etc.)
- Movies (2024, 1080p, BluRay, etc.)
- Games, Software, Music, eBooks
- Various obfuscation patterns
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models.release_regex import ReleaseRegex
from app.db.session import AsyncSessionLocal
from sqlalchemy import select, text


# Common regex patterns organized by priority
# Lower ordinal = higher priority (more specific patterns first)
REGEX_PATTERNS = [
    # === TV SHOWS (High Priority, ordinal 10-30) ===
    {
        "group_pattern": "alt\\.binaries\\.(teevee|tv|hdtv).*",
        "regex": r"(?P<name>.*?S\d{2}E\d{2}.*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "TV: Standard S01E01 format",
        "ordinal": 10,
    },
    {
        "group_pattern": "alt\\.binaries\\.(teevee|tv|hdtv).*",
        "regex": r"(?P<name>.*?\d{1,2}x\d{2}.*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "TV: 1x01 format",
        "ordinal": 11,
    },
    {
        "group_pattern": "alt\\.binaries\\.(teevee|tv|hdtv).*",
        "regex": r"(?P<name>.*?(?:HDTV|WEB-DL|WEBRip|BluRay).*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "TV: Quality-based (HDTV, WEB-DL, etc.)",
        "ordinal": 12,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>[A-Za-z0-9 ]+\.S\d{2}(?:E\d{2})?\..*?)(?:\s*-\s*)?[\[\(]?\d+[/\\]\d+",
        "description": "TV: Dotted S01E01 format (universal)",
        "ordinal": 15,
    },
    # === MOVIES (ordinal 20-40) ===
    {
        "group_pattern": "alt\\.binaries\\.(movies?|moovee|dvdr).*",
        "regex": r"(?P<name>.*?(?:19|20)\d{2}.*?(?:1080p|720p|2160p).*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Movies: Year + Quality",
        "ordinal": 20,
    },
    {
        "group_pattern": "alt\\.binaries\\.(movies?|moovee|dvdr).*",
        "regex": r"(?P<name>.*?(?:BluRay|BRRip|DVDRip|WEB-DL).*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Movies: Source quality",
        "ordinal": 21,
    },
    {
        "group_pattern": "alt\\.binaries\\.(movies?|moovee|dvdr).*",
        "regex": r"(?P<name>.*?(?:x264|x265|XviD|HEVC).*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Movies: Codec-based",
        "ordinal": 22,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>[A-Za-z0-9 ]+\.(?:19|20)\d{2}\..*?)(?:\s*-\s*)?[\[\(]?\d+[/\\]\d+",
        "description": "Movies: Dotted format with year (universal)",
        "ordinal": 25,
    },
    # === GROUP TAGS (ordinal 30-50) ===
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.*?)-[A-Z0-9]{3,}(?:\s*[\[\(]?\d+[/\\]\d+|\s*yEnc)",
        "description": "Scene release with group tag",
        "ordinal": 30,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.*?)\.REPACK\..*?(?:\s*[\[\(]?\d+[/\\]\d+|\s*yEnc)",
        "description": "REPACK releases",
        "ordinal": 31,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.*?)\.PROPER\..*?(?:\s*[\[\(]?\d+[/\\]\d+|\s*yEnc)",
        "description": "PROPER releases",
        "ordinal": 32,
    },
    # === GAMES (ordinal 50-70) ===
    {
        "group_pattern": "alt\\.binaries\\.(games?|console).*",
        "regex": r"(?P<name>.*?(?:XBOX|PS[345]|NSW|PC).*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Games: Console/platform based",
        "ordinal": 50,
    },
    {
        "group_pattern": "alt\\.binaries\\.(games?|console).*",
        "regex": r"(?P<name>.*?-CODEX|-RELOADED|-SKIDROW.*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Games: Crackgroup based",
        "ordinal": 51,
    },
    # === SOFTWARE (ordinal 70-90) ===
    {
        "group_pattern": "alt\\.binaries\\.apps.*",
        "regex": r"(?P<name>.*?v?\d+\.\d+.*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Software: Version number",
        "ordinal": 70,
    },
    # === MUSIC (ordinal 90-100) ===
    {
        "group_pattern": "alt\\.binaries\\.sounds.*",
        "regex": r"(?P<name>.*?-\d{4}-[A-Z0-9]+.*?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Music: Year-Group format",
        "ordinal": 90,
    },
    # === GENERIC PATTERNS (ordinal 100-200, lower priority) ===
    {
        "group_pattern": "*",
        "regex": r'yEnc.*?"([^"]+(?:\.mkv|\.mp4|\.avi|\.m4v))"',
        "description": "Generic: yEnc with video extension",
        "ordinal": 100,
    },
    {
        "group_pattern": "*",
        "regex": r'yEnc.*?"([^"]+(?:\.rar|\.r\d+))".*?"([^"]+)"',
        "description": "Generic: yEnc with RAR and potential release name",
        "ordinal": 101,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.*?)\s*-\s*[\[\(]?\d+[/\\]\d+[\]\)]?\s*-\s*yEnc",
        "description": "Generic: Part numbers with yEnc",
        "ordinal": 110,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.*?)\s*[\[\(]?\d+[/\\]\d+[\]\)]?",
        "description": "Generic: Basic part numbers",
        "ordinal": 120,
    },
    {
        "group_pattern": "*",
        "regex": r'"([^"]+\.(?:mkv|mp4|avi|m4v|rar|nfo|sfv))"',
        "description": "Generic: Quoted filename with extension",
        "ordinal": 130,
    },
    # === OBFUSCATION PATTERNS (ordinal 200-300) ===
    {
        "group_pattern": "*",
        "regex": r"(?P<name>[^[\]]+)\s*-\s*\[FULL\]",
        "description": "Obfuscated: [FULL] tag",
        "ordinal": 200,
    },
    {
        "group_pattern": "*",
        "regex": r"\[REQ\]\s*(?P<name>.+?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Obfuscated: [REQ] requests",
        "ordinal": 201,
    },
    {
        "group_pattern": "*",
        "regex": r"\[\d+\]\s*-\s*(?P<name>.+?)\s*[\[\(]?\d+[/\\]\d+",
        "description": "Obfuscated: [12345] - Release pattern",
        "ordinal": 202,
    },
    # === FILE-BASED PATTERNS (ordinal 300-400) ===
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.+?)\.part\d+\.rar",
        "description": "File: .partXX.rar format",
        "ordinal": 300,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.+?)\.r\d{2,3}",
        "description": "File: .r01 .r02 format",
        "ordinal": 301,
    },
    {
        "group_pattern": "*",
        "regex": r"(?P<name>.+?)\.vol\d+\+\d+\.par2",
        "description": "File: PAR2 volume format",
        "ordinal": 302,
    },
]


async def seed_patterns():
    """Seed the database with regex patterns"""

    async with AsyncSessionLocal() as db:
        added_count = 0
        skipped_count = 0
        error_count = 0

        print(f"\nSeeding {len(REGEX_PATTERNS)} regex patterns...")
        print("=" * 60)

        for pattern_data in REGEX_PATTERNS:
            try:
                # Check if pattern already exists (by regex and group_pattern)
                query = select(ReleaseRegex).filter(
                    ReleaseRegex.regex == pattern_data["regex"],
                    ReleaseRegex.group_pattern == pattern_data["group_pattern"],
                )
                result = await db.execute(query)
                existing = result.scalars().first()

                if existing:
                    skipped_count += 1
                    print(f"⊘ Skipped (exists): {pattern_data['description']}")
                    continue

                # Create new pattern
                pattern = ReleaseRegex(
                    group_pattern=pattern_data["group_pattern"],
                    regex=pattern_data["regex"],
                    description=pattern_data["description"],
                    ordinal=pattern_data["ordinal"],
                    active=True,
                    match_count=0,
                )

                db.add(pattern)
                await db.commit()

                added_count += 1
                print(
                    f"✓ Added: {pattern_data['description']} (ordinal={pattern_data['ordinal']})"
                )

            except Exception as e:
                error_count += 1
                print(f"✗ Error: {pattern_data['description']} - {e}")
                await db.rollback()

        print("=" * 60)
        print(f"\n✓ Seeding completed:")
        print(f"  Added:   {added_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Errors:  {error_count}")
        print()


async def show_pattern_summary():
    """Show summary of patterns in database"""

    async with AsyncSessionLocal() as db:
        # Count total patterns
        count_query = select(ReleaseRegex)
        result = await db.execute(count_query)
        total = len(result.scalars().all())

        # Count by group pattern
        group_query = text(
            """
            SELECT group_pattern, COUNT(*) as count
            FROM release_regexes
            GROUP BY group_pattern
            ORDER BY count DESC
        """
        )
        result = await db.execute(group_query)
        groups = result.fetchall()

        print("\n" + "=" * 60)
        print("Regex Pattern Database Summary")
        print("=" * 60)
        print(f"\nTotal Patterns: {total}")
        print(f"\nBreakdown by Group:")
        for group_pattern, count in groups:
            print(f"  {group_pattern:<40} {count:>3} patterns")
        print()


async def main():
    print("=" * 60)
    print("Seed Release Regex Patterns")
    print("=" * 60)

    # Seed patterns
    await seed_patterns()

    # Show summary
    await show_pattern_summary()

    print("Next steps:")
    print("1. Restart the application (podman-compose restart app)")
    print("2. Monitor logs for '✓ REGEX MATCH' messages")
    print("3. Check pattern statistics via API or database")
    print()


if __name__ == "__main__":
    asyncio.run(main())
