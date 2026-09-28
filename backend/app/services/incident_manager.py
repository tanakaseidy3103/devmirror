"""
DevMirror - Incident Manager Service

Incident Capsuleの作成・管理・検索を担当する。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IncidentModel, ProjectModel
from app.domain.models import (
    AIDiagnosis,
    EnvironmentDiff,
    EnvironmentFingerprint,
    IncidentCapsule,
    IncidentStatus,
    TestResult,
)
from app.services.ai_analyzer import get_ai_analyzer
from app.services.diff_engine import DiffEngine
from app.services.scanner import EnvironmentScanner

logger = structlog.get_logger(__name__)

# UI表示用の日本語ステータス名（タイムラインに記録するため）
INCIDENT_STATUS_LABELS: Dict[str, str] = {
    IncidentStatus.OPEN.value: "オープン",
    IncidentStatus.INVESTIGATING.value: "調査中",
    IncidentStatus.REPRODUCED.value: "再現済み",
    IncidentStatus.RESOLVED.value: "解決済み",
    IncidentStatus.ARCHIVED.value: "アーカイブ",
}


async def _next_incident_id(session: AsyncSession) -> str:
    """次のIncident IDを生成 (INC-XXXX形式)"""
    result = await session.execute(select(func.count(IncidentModel.id)))
    count = result.scalar() or 0
    return f"INC-{(count + 1):04d}"


class IncidentManager:
    """
    Incident Capsuleのライフサイクルを管理する

    - 作成 (create)
    - 取得 (get, list)
    - 検索 (search)
    - AI診断の追加 (add_diagnosis)
    - ステータス更新 (update_status)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._diff_engine = DiffEngine()

    async def create(
        self,
        project_name: str,
        environment_name: str,
        test_result: TestResult,
        logs: str = "",
        error_messages: Optional[List[str]] = None,
        stack_traces: Optional[List[str]] = None,
        command_executed: Optional[str] = None,
        git_commit: Optional[str] = None,
        git_branch: Optional[str] = None,
        project_language: Optional[str] = None,
        fingerprint_id: Optional[str] = None,
        diff_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> IncidentModel:
        """新しいIncident Capsuleを作成する"""

        incident_id = await _next_incident_id(self.session)

        timeline = [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "event": "Incident Capsule 作成",
                "detail": f"プロジェクト: {project_name}",
            }
        ]

        if test_result == TestResult.FAIL:
            timeline.append({
                "timestamp": datetime.utcnow().isoformat(),
                "event": "テスト失敗を検出",
                "detail": command_executed or "",
            })

        model = IncidentModel(
            incident_id=incident_id,
            project_name=project_name,
            project_language=project_language,
            environment_name=environment_name,
            git_commit=git_commit,
            git_branch=git_branch,
            test_result=test_result,
            command_executed=command_executed,
            logs=logs,
            error_messages=error_messages or [],
            stack_traces=stack_traces or [],
            fingerprint_id=fingerprint_id,
            diff_id=diff_id,
            status=IncidentStatus.OPEN,
            timeline=timeline,
            tags=tags or [],
        )

        self.session.add(model)
        await self.session.flush()

        logger.info(
            "Incident Capsule を作成しました",
            incident_id=incident_id,
            project=project_name,
            result=test_result.value,
        )
        return model

    async def get(self, incident_id: str) -> Optional[IncidentModel]:
        """IDでインシデントを取得"""
        result = await self.session.execute(
            select(IncidentModel).where(IncidentModel.incident_id == incident_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        project_name: Optional[str] = None,
        status: Optional[IncidentStatus] = None,
    ) -> List[IncidentModel]:
        """インシデント一覧を取得"""
        query = select(IncidentModel).order_by(IncidentModel.created_at.desc())

        if project_name:
            query = query.where(IncidentModel.project_name.ilike(f"%{project_name}%"))
        if status:
            query = query.where(IncidentModel.status == status)

        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        incident_id: str,
        status: IncidentStatus,
        note: Optional[str] = None,
    ) -> Optional[IncidentModel]:
        """インシデントのステータスを更新"""
        model = await self.get(incident_id)
        if not model:
            return None

        model.status = status
        model.updated_at = datetime.utcnow()

        timeline = model.timeline or []
        timeline.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": f"ステータス変更: {INCIDENT_STATUS_LABELS.get(status.value, status.value)}",
            "detail": note or "",
        })
        model.timeline = timeline

        await self.session.flush()
        logger.info("ステータス更新", incident_id=incident_id, status=status.value)
        return model

    async def add_ai_diagnosis(
        self,
        incident_id: str,
        diff: Optional[EnvironmentDiff] = None,
    ) -> Optional[IncidentModel]:
        """AI診断を実行してインシデントに追加する"""
        model = await self.get(incident_id)
        if not model:
            return None

        analyzer = get_ai_analyzer()
        diagnosis = await analyzer.analyze(
            environment_diff=diff,
            logs=model.logs or "",
            test_results={"result": model.test_result.value if model.test_result else "UNKNOWN"},
            project_info={
                "name": model.project_name,
                "language": model.project_language,
                "commit": model.git_commit,
            },
        )

        # JSONカラムへ保存するため mode="json"（created_at を文字列化）
        model.ai_diagnosis = diagnosis.model_dump(mode="json")
        model.updated_at = datetime.utcnow()

        timeline = model.timeline or []
        timeline.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "AI診断を実行",
            "detail": f"信頼度: {diagnosis.confidence:.0%}",
        })
        model.timeline = timeline

        await self.session.flush()
        logger.info("AI診断を追加", incident_id=incident_id, confidence=diagnosis.confidence)
        return model

    async def get_dashboard_stats(self) -> dict:
        """ダッシュボード用の統計情報を返す"""
        total_result = await self.session.execute(select(func.count(IncidentModel.id)))
        total = total_result.scalar() or 0

        reproduced_result = await self.session.execute(
            select(func.count(IncidentModel.id)).where(
                IncidentModel.status == IncidentStatus.REPRODUCED
            )
        )
        reproduced = reproduced_result.scalar() or 0

        failed_result = await self.session.execute(
            select(func.count(IncidentModel.id)).where(
                IncidentModel.test_result == TestResult.FAIL
            )
        )
        failed = failed_result.scalar() or 0

        return {
            "total_incidents": total,
            "reproduced_incidents": reproduced,
            "failed_tests": failed,
            "open_incidents": total - reproduced,
        }
