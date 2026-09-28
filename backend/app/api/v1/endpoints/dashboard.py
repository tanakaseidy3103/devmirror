"""
DevMirror - Dashboard Endpoint
"""
from datetime import datetime, timedelta
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import FingerprintModel, IncidentModel, ProjectModel
from app.domain.models import IncidentStatus, TestResult

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/stats", response_model=Dict[str, Any])
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """ダッシュボード統計情報を返す"""

    # プロジェクト数
    proj_count = (await db.execute(select(func.count(ProjectModel.id)))).scalar() or 0

    # 環境数（Fingerprint数）
    env_count = (await db.execute(select(func.count(FingerprintModel.id)))).scalar() or 0

    # インシデント統計
    total_incidents = (await db.execute(select(func.count(IncidentModel.id)))).scalar() or 0

    reproduced = (await db.execute(
        select(func.count(IncidentModel.id)).where(
            IncidentModel.status == IncidentStatus.REPRODUCED
        )
    )).scalar() or 0

    failed_tests = (await db.execute(
        select(func.count(IncidentModel.id)).where(
            IncidentModel.test_result == TestResult.FAIL
        )
    )).scalar() or 0

    # 最近のインシデント（5件）
    recent_result = await db.execute(
        select(IncidentModel)
        .order_by(IncidentModel.created_at.desc())
        .limit(5)
    )
    recent_incidents = recent_result.scalars().all()

    return {
        "projects": proj_count,
        "environments": env_count,
        "incidents": {
            "total": total_incidents,
            "reproduced": reproduced,
            "failed_tests": failed_tests,
            "open": total_incidents - reproduced,
        },
        "recent_incidents": [
            {
                "incident_id": inc.incident_id,
                "project_name": inc.project_name,
                "environment_name": inc.environment_name,
                "status": inc.status.value if inc.status else "OPEN",
                "test_result": inc.test_result.value if inc.test_result else "UNKNOWN",
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
            }
            for inc in recent_incidents
        ],
    }
