#!/usr/bin/env python
"""
Script to add default categories to the database
Based on nzedb categories
"""

import asyncio
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application modules
from app.db.session import AsyncSessionLocal
from app.db.models.category import Category
from sqlalchemy import select


async def add_category(db, name, description, parent_id=None, newznab_category=None, sort_order=0):
    """Add a category to the database if it doesn't exist"""
    # Check if category already exists
    query = select(Category).filter(Category.name == name)
    result = await db.execute(query)
    category = result.scalars().first()

    if category:
        logger.info(f"Category '{name}' already exists")
        return category

    # Create category
    category = Category(
        name=name,
        description=description,
        parent_id=parent_id,
        newznab_category=newznab_category,
        sort_order=sort_order,
        active=True,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    logger.info(f"Added category '{name}'")
    return category


async def add_default_categories():
    """Add default categories to the database"""
    async with AsyncSessionLocal() as db:
        # Main categories
        console = await add_category(
            db, "Console", "Console games and related content", newznab_category=1000, sort_order=10
        )
        movies = await add_category(
            db, "Movies", "Movies and related content", newznab_category=2000, sort_order=20
        )
        audio = await add_category(
            db, "Audio", "Music and audio content", newznab_category=3000, sort_order=30
        )
        pc = await add_category(
            db, "PC", "PC software and games", newznab_category=4000, sort_order=40
        )
        tv = await add_category(
            db, "TV", "TV shows and related content", newznab_category=5000, sort_order=50
        )
        xxx = await add_category(
            db, "XXX", "Adult content", newznab_category=6000, sort_order=60
        )
        books = await add_category(
            db, "Books", "Books and related content", newznab_category=7000, sort_order=70
        )
        other = await add_category(
            db, "Other", "Uncategorized content", newznab_category=8000, sort_order=80
        )

        # Console subcategories
        await add_category(
            db, "NDS", "Nintendo DS games", console.id, newznab_category=1010, sort_order=11
        )
        await add_category(
            db, "PSP", "PlayStation Portable games", console.id, newznab_category=1020, sort_order=12
        )
        await add_category(
            db, "Wii", "Nintendo Wii games", console.id, newznab_category=1030, sort_order=13
        )
        await add_category(
            db, "Xbox", "Xbox games", console.id, newznab_category=1040, sort_order=14
        )
        await add_category(
            db, "Xbox 360", "Xbox 360 games", console.id, newznab_category=1050, sort_order=15
        )
        await add_category(
            db, "PS3", "PlayStation 3 games", console.id, newznab_category=1080, sort_order=16
        )

        # Movie subcategories
        await add_category(
            db, "Foreign", "Foreign movies", movies.id, newznab_category=2010, sort_order=21
        )
        await add_category(
            db, "HD", "High-definition movies", movies.id, newznab_category=2040, sort_order=22
        )
        await add_category(
            db, "SD", "Standard-definition movies", movies.id, newznab_category=2030, sort_order=23
        )
        await add_category(
            db, "BluRay", "Blu-ray movies", movies.id, newznab_category=2050, sort_order=24
        )
        await add_category(
            db, "3D", "3D movies", movies.id, newznab_category=2060, sort_order=25
        )

        # Audio subcategories
        await add_category(
            db, "MP3", "MP3 audio", audio.id, newznab_category=3010, sort_order=31
        )
        await add_category(
            db, "Video", "Music videos", audio.id, newznab_category=3020, sort_order=32
        )
        await add_category(
            db, "Audiobook", "Audiobooks", audio.id, newznab_category=3030, sort_order=33
        )
        await add_category(
            db, "Lossless", "Lossless audio", audio.id, newznab_category=3040, sort_order=34
        )

        # PC subcategories
        await add_category(
            db, "0day", "0-day releases", pc.id, newznab_category=4010, sort_order=41
        )
        await add_category(
            db, "ISO", "PC ISO images", pc.id, newznab_category=4020, sort_order=42
        )
        await add_category(
            db, "Mac", "Mac software", pc.id, newznab_category=4030, sort_order=43
        )
        await add_category(
            db, "Phone", "Mobile phone apps", pc.id, newznab_category=4040, sort_order=44
        )
        await add_category(
            db, "Games", "PC games", pc.id, newznab_category=4050, sort_order=45
        )

        # TV subcategories
        await add_category(
            db, "Foreign", "Foreign TV shows", tv.id, newznab_category=5020, sort_order=51
        )
        await add_category(
            db, "HD", "High-definition TV shows", tv.id, newznab_category=5040, sort_order=52
        )
        await add_category(
            db, "SD", "Standard-definition TV shows", tv.id, newznab_category=5030, sort_order=53
        )
        await add_category(
            db, "Sport", "Sports TV", tv.id, newznab_category=5060, sort_order=54
        )
        await add_category(
            db, "Documentary", "TV documentaries", tv.id, newznab_category=5070, sort_order=55
        )

        # XXX subcategories
        await add_category(
            db, "DVD", "Adult DVDs", xxx.id, newznab_category=6010, sort_order=61
        )
        await add_category(
            db, "WMV", "Adult WMV videos", xxx.id, newznab_category=6020, sort_order=62
        )
        await add_category(
            db, "XviD", "Adult XviD videos", xxx.id, newznab_category=6030, sort_order=63
        )
        await add_category(
            db, "x264", "Adult x264 videos", xxx.id, newznab_category=6040, sort_order=64
        )

        # Books subcategories
        await add_category(
            db, "Ebook", "E-books", books.id, newznab_category=7020, sort_order=71
        )
        await add_category(
            db, "Comics", "Comic books", books.id, newznab_category=7030, sort_order=72
        )
        await add_category(
            db, "Magazines", "Magazines", books.id, newznab_category=7010, sort_order=73
        )
        await add_category(
            db, "Technical", "Technical books", books.id, newznab_category=7040, sort_order=74
        )

        # Other subcategories
        await add_category(
            db, "Misc", "Miscellaneous content", other.id, newznab_category=8010, sort_order=81
        )
        await add_category(
            db, "Hashed", "Hashed content", other.id, newznab_category=8020, sort_order=82
        )


if __name__ == "__main__":
    asyncio.run(add_default_categories())
    print("Default categories added successfully!")
