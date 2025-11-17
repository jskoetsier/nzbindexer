"""
ORN Management API Endpoints

Admin endpoints for managing ORN (Obfuscated Release Names) mappings,
import/export, and distributed sharing.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.api.deps import get_current_admin_user, get_db
from app.db.models.orn_mapping import ORNMapping
from app.db.models.user import User
from app.services.predb import PreDBService

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models
class ORNMappingCreate(BaseModel):
    obfuscated_hash: str
    real_name: str
    source: str = "manual"
    confidence: float = 1.0


class ORNMappingResponse(BaseModel):
    id: int
    obfuscated_hash: str
    real_name: str
    source: str
    confidence: float
    use_count: int
    created_at: datetime
    last_used: Optional[datetime]


class ORNStatsResponse(BaseModel):
    total_mappings: int
    by_source: dict
    most_used: List[dict]


@router.get("/stats", response_model=ORNStatsResponse)
async def get_orn_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get ORN cache statistics"""
    predb_service = PreDBService(db)
    try:
        stats = await predb_service.get_cache_stats()
        return stats
    finally:
        await predb_service.close()


@router.get("/mappings", response_model=List[ORNMappingResponse])
async def list_orn_mappings(
    skip: int = 0,
    limit: int = 100,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List ORN mappings with pagination"""
    query = select(ORNMapping).offset(skip).limit(limit).order_by(ORNMapping.id.desc())

    if source:
        query = query.filter(ORNMapping.source == source)

    result = await db.execute(query)
    mappings = result.scalars().all()

    return mappings


@router.post("/mappings", response_model=ORNMappingResponse)
async def create_orn_mapping(
    mapping: ORNMappingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Create a new ORN mapping"""
    predb_service = PreDBService(db)
    try:
        success = await predb_service.save_to_cache(
            mapping.obfuscated_hash,
            mapping.real_name,
            mapping.source,
            mapping.confidence,
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to create mapping")

        # Retrieve the created mapping
        query = select(ORNMapping).filter(
            ORNMapping.obfuscated_hash
            == predb_service._normalize_name(mapping.obfuscated_hash)
        )
        result = await db.execute(query)
        created = result.scalars().first()

        return created
    finally:
        await predb_service.close()


@router.delete("/mappings/{mapping_id}")
async def delete_orn_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete an ORN mapping"""
    query = select(ORNMapping).filter(ORNMapping.id == mapping_id)
    result = await db.execute(query)
    mapping = result.scalars().first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    await db.delete(mapping)
    await db.commit()

    return {"message": "Mapping deleted successfully"}


@router.get("/export/json")
async def export_orn_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Export all ORN mappings as JSON"""
    query = select(ORNMapping)
    result = await db.execute(query)
    mappings = result.scalars().all()

    data = [
        {
            "obfuscated_hash": m.obfuscated_hash,
            "real_name": m.real_name,
            "source": m.source,
            "confidence": m.confidence,
            "use_count": m.use_count,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mappings
    ]

    json_str = json.dumps(data, indent=2)

    return StreamingResponse(
        io.StringIO(json_str),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=orn_mappings_{datetime.now().strftime('%Y%m%d')}.json"
        },
    )


@router.get("/export/csv")
async def export_orn_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Export all ORN mappings as CSV"""
    query = select(ORNMapping)
    result = await db.execute(query)
    mappings = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["obfuscated_hash", "real_name", "source", "confidence", "use_count"]
    )

    for m in mappings:
        writer.writerow(
            [m.obfuscated_hash, m.real_name, m.source, m.confidence, m.use_count]
        )

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=orn_mappings_{datetime.now().strftime('%Y%m%d')}.csv"
        },
    )


@router.post("/import/json")
async def import_orn_json(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Import ORN mappings from JSON file"""
    try:
        content = await file.read()
        data = json.loads(content)

        predb_service = PreDBService(db)
        imported = 0

        for item in data:
            await predb_service.save_to_cache(
                item["obfuscated_hash"],
                item["real_name"],
                item.get("source", "imported"),
                item.get("confidence", 0.9),
            )
            imported += 1

        await predb_service.close()

        return {"message": f"Successfully imported {imported} mappings"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


@router.post("/import/csv")
async def import_orn_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Import ORN mappings from CSV file"""
    try:
        content = await file.read()
        content_str = content.decode("utf-8")

        reader = csv.DictReader(io.StringIO(content_str))

        predb_service = PreDBService(db)
        imported = 0

        for row in reader:
            await predb_service.save_to_cache(
                row["obfuscated_hash"],
                row["real_name"],
                row.get("source", "imported"),
                float(row.get("confidence", 0.9)),
            )
            imported += 1

        await predb_service.close()

        return {"message": f"Successfully imported {imported} mappings"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


# Distributed ORN Sharing Endpoints (Public API)
@router.get("/public/mappings", response_model=List[dict])
async def get_public_orn_mappings(
    skip: int = 0,
    limit: int = 1000,
    min_confidence: float = 0.8,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint for distributed ORN sharing
    Returns mappings with high confidence for community sharing
    """
    query = (
        select(ORNMapping)
        .filter(ORNMapping.confidence >= min_confidence)
        .offset(skip)
        .limit(limit)
        .order_by(ORNMapping.use_count.desc())
    )

    result = await db.execute(query)
    mappings = result.scalars().all()

    return [
        {
            "obfuscated_hash": m.obfuscated_hash,
            "real_name": m.real_name,
            "source": "community",
            "confidence": m.confidence,
        }
        for m in mappings
    ]


@router.post("/public/contribute")
async def contribute_orn_mapping(
    mapping: ORNMappingCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint for community contributions
    Accepts mappings from other indexers
    """
    # Set source to "community" and lower confidence
    predb_service = PreDBService(db)
    try:
        success = await predb_service.save_to_cache(
            mapping.obfuscated_hash,
            mapping.real_name,
            "community",
            min(mapping.confidence, 0.85),  # Cap community contributions at 0.85
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to save mapping")

        return {"message": "Contribution accepted", "status": "success"}
    finally:
        await predb_service.close()
