"""公式デモ投入 API"""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.demo_seed import seed_dx_library_demo

router = APIRouter()


@router.post("/dx-library")
async def seed_dx_library(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """C++ + DX Library の公式デモデータを投入する。"""
    return await seed_dx_library_demo(db)
