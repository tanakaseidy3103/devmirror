"""
DevMirror - Diffs Endpoint
"""
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import DiffModel, FingerprintModel
from app.domain.models import EnvironmentFingerprint
from app.services.diff_engine import DiffEngine

router = APIRouter()
logger = structlog.get_logger(__name__)


class DiffRequest(BaseModel):
    fingerprint_a_id: str
    fingerprint_b_id: str


def _fp_model_to_domain(m: FingerprintModel) -> EnvironmentFingerprint:
    """FingerprintModelをドメインモデルに変換"""
    from app.domain.models import (
        ArchitectureInfo, CompilerInfo, DependencyInfo,
        OSInfo, ProjectInfo, RuntimeInfo,
    )

    fp = EnvironmentFingerprint(
        fingerprint_id=m.fingerprint_id,
        environment_name=m.environment_name,
        schema_version=m.schema_version or "1.0",
        collected_at=m.collected_at,
    )

    if m.os_info:
        fp.os = OSInfo(**m.os_info)
    if m.architecture_info:
        fp.architecture = ArchitectureInfo(**m.architecture_info)
    if m.runtime_info:
        fp.runtime = RuntimeInfo(**m.runtime_info)
    if m.compiler_info:
        fp.compiler = CompilerInfo(**m.compiler_info)
    if m.dependencies:
        fp.dependencies = [DependencyInfo(**d) for d in m.dependencies]
    if m.project_info:
        fp.project = ProjectInfo(**m.project_info)
    fp.path_entries = m.path_entries or []

    return fp


@router.post("/compare", response_model=Dict[str, Any])
async def compare_fingerprints(
    req: DiffRequest,
    db: AsyncSession = Depends(get_db),
):
    """2つのEnvironment Fingerprintを比較してDiffを生成・保存する"""

    result_a = await db.execute(
        select(FingerprintModel).where(FingerprintModel.fingerprint_id == req.fingerprint_a_id)
    )
    model_a = result_a.scalar_one_or_none()
    if not model_a:
        raise HTTPException(status_code=404, detail=f"Fingerprint A not found: {req.fingerprint_a_id}")

    result_b = await db.execute(
        select(FingerprintModel).where(FingerprintModel.fingerprint_id == req.fingerprint_b_id)
    )
    model_b = result_b.scalar_one_or_none()
    if not model_b:
        raise HTTPException(status_code=404, detail=f"Fingerprint B not found: {req.fingerprint_b_id}")

    fp_a = _fp_model_to_domain(model_a)
    fp_b = _fp_model_to_domain(model_b)

    engine = DiffEngine()
    diff = engine.compare(fp_a, fp_b)

    # DB保存
    diff_model = DiffModel(
        diff_id=diff.diff_id,
        fingerprint_a_id=diff.fingerprint_a_id,
        fingerprint_b_id=diff.fingerprint_b_id,
        environment_a_name=diff.environment_a_name,
        environment_b_name=diff.environment_b_name,
        entries=[e.model_dump() for e in diff.entries],
        high_severity_count=diff.high_severity_count,
        medium_severity_count=diff.medium_severity_count,
        low_severity_count=diff.low_severity_count,
    )
    db.add(diff_model)
    await db.flush()

    return diff.model_dump()


@router.get("/", response_model=List[Dict[str, Any]])
async def list_diffs(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Diff一覧を取得"""
    result = await db.execute(
        select(DiffModel).order_by(DiffModel.created_at.desc()).limit(limit).offset(offset)
    )
    models = result.scalars().all()
    return [
        {
            "diff_id": m.diff_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "environment_a_name": m.environment_a_name,
            "environment_b_name": m.environment_b_name,
            "high_severity_count": m.high_severity_count,
            "medium_severity_count": m.medium_severity_count,
            "low_severity_count": m.low_severity_count,
            "entries": m.entries,
        }
        for m in models
    ]


@router.get("/{diff_id}", response_model=Dict[str, Any])
async def get_diff(diff_id: str, db: AsyncSession = Depends(get_db)):
    """特定のDiffを取得"""
    result = await db.execute(
        select(DiffModel).where(DiffModel.diff_id == diff_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="環境差分が見つかりません")
    return {
        "diff_id": model.diff_id,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "environment_a_name": model.environment_a_name,
        "environment_b_name": model.environment_b_name,
        "fingerprint_a_id": model.fingerprint_a_id,
        "fingerprint_b_id": model.fingerprint_b_id,
        "high_severity_count": model.high_severity_count,
        "medium_severity_count": model.medium_severity_count,
        "low_severity_count": model.low_severity_count,
        "entries": model.entries,
    }
