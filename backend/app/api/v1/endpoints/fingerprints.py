"""
DevMirror - Fingerprints Endpoint
"""
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import FingerprintModel

router = APIRouter()
logger = structlog.get_logger(__name__)


def _model_to_dict(m: FingerprintModel) -> Dict[str, Any]:
    return {
        "fingerprint_id": m.fingerprint_id,
        "environment_name": m.environment_name,
        "schema_version": m.schema_version,
        "collected_at": m.collected_at.isoformat() if m.collected_at else None,
        "os": m.os_info,
        "architecture": m.architecture_info,
        "runtime": m.runtime_info,
        "compiler": m.compiler_info,
        "dependencies": m.dependencies,
        "project": m.project_info,
        "path_entries": m.path_entries,
    }


@router.get("/", response_model=List[Dict[str, Any]])
async def list_fingerprints(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Environment Fingerprint一覧を取得"""
    result = await db.execute(
        select(FingerprintModel)
        .order_by(FingerprintModel.collected_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_model_to_dict(m) for m in result.scalars().all()]


@router.get("/{fingerprint_id}", response_model=Dict[str, Any])
async def get_fingerprint(
    fingerprint_id: str,
    db: AsyncSession = Depends(get_db),
):
    """特定のEnvironment Fingerprintを取得"""
    result = await db.execute(
        select(FingerprintModel).where(FingerprintModel.fingerprint_id == fingerprint_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Environment Fingerprint が見つかりません")
    return _model_to_dict(model)
