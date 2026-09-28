"""
DevMirror - Scanner Endpoint
"""
from typing import Any, Dict, Optional
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import FingerprintModel, ProjectModel
from app.services.scanner import EnvironmentScanner

router = APIRouter()
logger = structlog.get_logger(__name__)


class ScanRequest(BaseModel):
    environment_name: str
    project_path: Optional[str] = None


@router.post("/scan")
async def scan_environment(
    req: ScanRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    現在の環境をスキャンしてEnvironment Fingerprintを生成・保存する
    """
    logger.info("スキャンリクエスト受信", environment=req.environment_name)

    if not req.environment_name.strip():
        raise HTTPException(status_code=422, detail="環境名は必須です")
    if req.project_path:
        project_path = Path(req.project_path).expanduser()
        if not project_path.exists() or not project_path.is_dir():
            raise HTTPException(status_code=422, detail="プロジェクトパスは既存のディレクトリである必要があります")
        req.project_path = str(project_path.resolve())

    scanner = EnvironmentScanner(
        environment_name=req.environment_name,
        project_path=req.project_path,
    )
    fp = scanner.scan()

    project_id = None
    if fp.project and fp.project.name:
        project_result = await db.execute(
            select(ProjectModel).where(ProjectModel.name == fp.project.name)
        )
        project = project_result.scalar_one_or_none()
        if project is None:
            project = ProjectModel(name=fp.project.name, language=fp.project.language)
            db.add(project)
            await db.flush()
        elif fp.project.language and not project.language:
            project.language = fp.project.language
        project_id = project.id

    # DBに保存
    model = FingerprintModel(
        fingerprint_id=fp.fingerprint_id,
        environment_name=fp.environment_name,
        schema_version=fp.schema_version,
        collected_at=fp.collected_at,
        os_info=fp.os.model_dump() if fp.os else None,
        architecture_info=fp.architecture.model_dump() if fp.architecture else None,
        runtime_info=fp.runtime.model_dump() if fp.runtime else None,
        compiler_info=fp.compiler.model_dump() if fp.compiler else None,
        dependencies=[d.model_dump() for d in fp.dependencies],
        project_info=fp.project.model_dump() if fp.project else None,
        path_entries=fp.path_entries,
        project_id=project_id,
    )
    db.add(model)
    await db.flush()

    return fp.model_dump()
