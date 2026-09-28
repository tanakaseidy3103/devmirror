"""
DevMirror - Projects Endpoint
"""
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import ProjectModel

router = APIRouter()
logger = structlog.get_logger(__name__)


class CreateProjectRequest(BaseModel):
    name: str
    language: Optional[str] = None
    description: Optional[str] = None
    git_url: Optional[str] = None


@router.post("/", response_model=Dict[str, Any])
async def create_project(
    req: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
):
    """プロジェクトを作成する"""
    model = ProjectModel(
        name=req.name,
        language=req.language,
        description=req.description,
        git_url=req.git_url,
    )
    db.add(model)
    await db.flush()
    return {"id": model.id, "name": model.name, "language": model.language}


@router.get("/", response_model=List[Dict[str, Any]])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """プロジェクト一覧を取得"""
    result = await db.execute(
        select(ProjectModel).order_by(ProjectModel.created_at.desc())
    )
    return [
        {
            "id": m.id,
            "name": m.name,
            "language": m.language,
            "description": m.description,
            "git_url": m.git_url,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in result.scalars().all()
    ]


@router.get("/{project_id}", response_model=Dict[str, Any])
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """プロジェクトを取得"""
    result = await db.execute(
        select(ProjectModel).where(ProjectModel.id == project_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
    return {
        "id": model.id,
        "name": model.name,
        "language": model.language,
        "description": model.description,
        "git_url": model.git_url,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }
