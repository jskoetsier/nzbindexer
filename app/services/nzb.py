"""
NZB service for generating and managing NZB files
"""

import hashlib
import logging
import os
import random
import string
import time
import xml.dom.minidom
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Union

from app.core.config import settings
from app.db.models.release import Release
from app.db.session import AsyncSession
from app.services.nntp import NNTPService

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NZBService:
    """
    Service for generating and managing NZB files
    """

    def __init__(self, nntp_service: Optional[NNTPService] = None):
        """
        Initialize the NZB service
        """
        self.nntp_service = nntp_service or NNTPService()

        # Ensure NZB directory exists
        self.nzb_dir = os.path.join(settings.DATA_DIR, "nzb")
        os.makedirs(self.nzb_dir, exist_ok=True)

    async def generate_nzb(self, db: AsyncSession, release_id: int) -> Optional[str]:
        """
        Generate an NZB file for a release
        Returns the path to the generated NZB file
        """
        try:
            # Get release
            query = select(Release).filter(Release.id == release_id)
            result = await db.execute(query)
            release = result.scalars().first()

            if not release:
                logger.error(f"Release with ID {release_id} not found")
                return None

            # Generate NZB GUID if not exists
            if not release.nzb_guid:
                release.nzb_guid = self._generate_nzb_guid(release)
                db.add(release)
                await db.commit()

            # Check if NZB file already exists
            nzb_path = self._get_nzb_path(release.nzb_guid)
            if os.path.exists(nzb_path):
                return nzb_path

            # TODO: Implement actual NZB generation
            # This would involve:
            # 1. Getting all article message IDs for the release
            # 2. Creating an XML file with the article information
            # 3. Saving the XML file

            # For now, we'll create a placeholder NZB file
            await self._create_placeholder_nzb(release, nzb_path)

            return nzb_path

        except Exception as e:
            logger.error(f"Error generating NZB for release {release_id}: {str(e)}")
            return None

    def _generate_nzb_guid(self, release: Release) -> str:
        """
        Generate a unique GUID for an NZB file
        """
        # Create a unique string from release info
        unique_str = f"{release.guid}:{int(time.time())}"

        # Create MD5 hash
        md5 = hashlib.md5(unique_str.encode()).hexdigest()

        return md5

    def _get_nzb_path(self, nzb_guid: str) -> str:
        """
        Get the path to an NZB file
        """
        return os.path.join(self.nzb_dir, f"{nzb_guid}.nzb")

    def _generate_random_string(self, length: int = 10) -> str:
        """
        Generate a random string of specified length
        """
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def _obfuscate_subject(self, subject: str) -> Tuple[str, str]:
        """
        Obfuscate a subject line
        Returns a tuple of (obfuscated_subject, original_subject)
        """
        # Generate a random string for the obfuscated subject
        obfuscated = self._generate_random_string(20)

        # Return both the obfuscated subject and the original
        return obfuscated, subject

    async def _create_placeholder_nzb(self, release: Release, nzb_path: str) -> None:
        """
        Create a placeholder NZB file for a release with obfuscation
        This is a temporary solution until we implement actual NZB generation
        """
        # Create root element
        root = ET.Element("nzb", xmlns="http://www.newzbin.com/DTD/2003/nzb")

        # Add head element
        head = ET.SubElement(root, "head")

        # Add metadata
        meta_category = ET.SubElement(head, "meta", type="category")
        meta_category.text = "Placeholder"

        meta_name = ET.SubElement(head, "meta", type="name")
        meta_name.text = release.name

        meta_size = ET.SubElement(head, "meta", type="size")
        meta_size.text = str(release.size)

        # Add obfuscation metadata
        meta_obfuscated = ET.SubElement(head, "meta", type="obfuscated")
        meta_obfuscated.text = "yes"

        # Obfuscate the subject
        obfuscated_subject, original_subject = self._obfuscate_subject(release.name)

        # Store the original subject in metadata (encrypted or encoded in a real implementation)
        meta_original_subject = ET.SubElement(head, "meta", type="originalSubject")
        meta_original_subject.text = original_subject

        # Add file element with obfuscated subject
        file_elem = ET.SubElement(
            root, "file", poster="nzbindexer@example.com", date=str(int(time.time()))
        )
        file_elem.set("subject", obfuscated_subject)

        # Add groups
        groups = ET.SubElement(file_elem, "groups")
        group = ET.SubElement(groups, "group")

        # Get group name
        from app.db.models.group import Group

        query = select(Group).filter(Group.id == release.group_id)
        result = await db.execute(query)
        group_obj = result.scalars().first()

        if group_obj:
            group.text = group_obj.name
        else:
            group.text = "alt.binaries.placeholder"

        # Add segments
        segments = ET.SubElement(file_elem, "segments")

        # Add a placeholder segment with obfuscated message ID
        segment = ET.SubElement(
            segments, "segment", bytes=str(release.size), number="1"
        )
        segment.text = f"<{self._generate_random_string(30)}@placeholder.nzb>"

        # Create XML string
        xml_str = ET.tostring(root, encoding="utf-8")

        # Pretty print XML
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")

        # Write to file
        with open(nzb_path, "w") as f:
            f.write(pretty_xml)


async def get_nzb_for_release(
    db: AsyncSession, release_id: int, create_if_missing: bool = True
) -> Optional[str]:
    """
    Get the NZB file path for a release
    If create_if_missing is True, generate the NZB file if it doesn't exist
    """
    # Get release
    query = select(Release).filter(Release.id == release_id)
    result = await db.execute(query)
    release = result.scalars().first()

    if not release:
        logger.error(f"Release with ID {release_id} not found")
        return None

    # Check if NZB GUID exists
    if not release.nzb_guid:
        if not create_if_missing:
            return None

        # Generate NZB file
        nzb_service = NZBService()
        return await nzb_service.generate_nzb(db, release_id)

    # Check if NZB file exists
    nzb_service = NZBService()
    nzb_path = nzb_service._get_nzb_path(release.nzb_guid)

    if not os.path.exists(nzb_path):
        if not create_if_missing:
            return None

        # Generate NZB file
        return await nzb_service.generate_nzb(db, release_id)

    return nzb_path
