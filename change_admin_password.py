#!/usr/bin/env python3
"""
Script to change the admin password from the command line
"""

import argparse
import asyncio
import getpass
import sys
from typing import Optional

from app.core.security import get_password_hash
from app.db.models.user import User
from app.db.session import AsyncSessionLocal

from sqlalchemy import select


async def get_admin_user(username: Optional[str] = None) -> Optional[User]:
    """
    Get an admin user by username or the first admin user if no username is provided
    """
    async with AsyncSessionLocal() as db:
        if username:
            # Get admin user by username
            query = select(User).filter(
                User.username == username, User.is_admin == True
            )
        else:
            # Get first admin user
            query = select(User).filter(User.is_admin == True)

        result = await db.execute(query)
        return result.scalars().first()


async def change_password(user: User, new_password: str) -> None:
    """
    Change the user's password
    """
    async with AsyncSessionLocal() as db:
        # Get user from database
        db_user = await db.get(User, user.id)
        if not db_user:
            print(f"Error: User {user.username} not found")
            return

        # Update password
        db_user.hashed_password = get_password_hash(new_password)
        db.add(db_user)
        await db.commit()

        print(f"Password for {db_user.username} updated successfully")


async def main() -> None:
    """
    Main entry point
    """
    parser = argparse.ArgumentParser(description="Change admin password")
    parser.add_argument("--username", "-u", help="Admin username (optional)")
    args = parser.parse_args()

    # Get admin user
    admin = await get_admin_user(args.username)
    if not admin:
        if args.username:
            print(f"Error: Admin user '{args.username}' not found")
        else:
            print("Error: No admin users found")
        sys.exit(1)

    print(f"Changing password for admin user: {admin.username}")

    # Get new password
    while True:
        new_password = getpass.getpass("New password: ")
        if not new_password:
            print("Password cannot be empty")
            continue

        confirm_password = getpass.getpass("Confirm password: ")
        if new_password != confirm_password:
            print("Passwords do not match")
            continue

        break

    # Change password
    await change_password(admin, new_password)


if __name__ == "__main__":
    asyncio.run(main())
