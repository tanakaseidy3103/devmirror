"""
DevMirror - Incidents Endpoint
"""
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.db.models import DiffModel, IncidentModel
from app.domain.models import IncidentStatus, TestResult
from app.services.incident_manager import IncidentManager
from app.services.test_runner import CommandTestRunner
from app.services.vm_factory import get_vm_provider, is_real_provider
from app.services.virtualbox_provider import VirtualBoxError

router = APIRouter()
logger = structlog.get_logger(__name__)


class CreateIncidentRequest(BaseModel):
    project_name: str
    environment_name: str
    test_result: TestResult
    logs: str = ""
    error_messages: List[str] = Field(default_factory=list)
    stack_traces: List[str] = Field(default_factory=list)
    command_executed: Optional[str] = None
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    project_language: Optional[str] = None
    fingerprint_id: Optional[str] = None
    diff_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class UpdateStatusRequest(BaseModel):
    status: IncidentStatus
    note: Optional[str] = None


def _model_to_dict(m: IncidentModel) -> Dict[str, Any]:
    return {
        "incident_id": m.incident_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        "project_name": m.project_name,
        "project_language": m.project_language,
        "environment_name": m.environment_name,
        "git_commit": m.git_commit,
        "git_branch": m.git_branch,
        "test_result": m.test_result.value if m.test_result else None,
        "command_executed": m.command_executed,
        "logs": m.logs,
        "error_messages": m.error_messages or [],
        "stack_traces": m.stack_traces or [],
        "screenshots": m.screenshots or [],
        "fingerprint_id": m.fingerprint_id,
        "diff_id": m.diff_id,
        "ai_diagnosis": m.ai_diagnosis,
        "status": m.status.value if m.status else None,
        "timeline": m.timeline or [],
        "tags": m.tags or [],
        "notes": m.notes,
    }


@router.post("/", response_model=Dict[str, Any])
async def create_incident(
    req: CreateIncidentRequest,
    db: AsyncSession = Depends(get_db),
):
    """新しいIncident Capsuleを作成する"""
    if req.fingerprint_id:
        from app.db.models import FingerprintModel
        fingerprint = await db.execute(
            select(FingerprintModel).where(FingerprintModel.fingerprint_id == req.fingerprint_id)
        )
        if fingerprint.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail="Environment Fingerprint が見つかりません")
    if req.diff_id:
        diff = await db.execute(select(DiffModel).where(DiffModel.diff_id == req.diff_id))
        if diff.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail="環境差分が見つかりません")

    manager = IncidentManager(db)
    model = await manager.create(
        project_name=req.project_name,
        environment_name=req.environment_name,
        test_result=req.test_result,
        logs=req.logs,
        error_messages=req.error_messages,
        stack_traces=req.stack_traces,
        command_executed=req.command_executed,
        git_commit=req.git_commit,
        git_branch=req.git_branch,
        project_language=req.project_language,
        fingerprint_id=req.fingerprint_id,
        diff_id=req.diff_id,
        tags=req.tags,
    )
    return _model_to_dict(model)


@router.get("/", response_model=List[Dict[str, Any]])
async def list_incidents(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    project_name: Optional[str] = None,
    status: Optional[IncidentStatus] = None,
):
    """インシデント一覧を取得"""
    manager = IncidentManager(db)
    models = await manager.list_all(limit=limit, offset=offset, project_name=project_name, status=status)
    return [_model_to_dict(m) for m in models]


@router.get("/{incident_id}", response_model=Dict[str, Any])
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """特定のIncidentを取得"""
    manager = IncidentManager(db)
    model = await manager.get(incident_id)
    if not model:
        raise HTTPException(status_code=404, detail="インシデントが見つかりません")
    return _model_to_dict(model)


@router.patch("/{incident_id}/status", response_model=Dict[str, Any])
async def update_incident_status(
    incident_id: str,
    req: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """インシデントのステータスを更新"""
    manager = IncidentManager(db)
    model = await manager.update_status(incident_id, req.status, req.note)
    if not model:
        raise HTTPException(status_code=404, detail="インシデントが見つかりません")
    return _model_to_dict(model)


@router.post("/{incident_id}/diagnose", response_model=Dict[str, Any])
async def run_ai_diagnosis(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    """AI診断を実行してインシデントに追加する"""
    manager = IncidentManager(db)

    # インシデントのDiffを取得
    incident = await manager.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="インシデントが見つかりません")

    diff = None
    if incident.diff_id:
        from app.api.v1.endpoints.diffs import _fp_model_to_domain
        from app.db.models import DiffModel, FingerprintModel
        from app.domain.models import EnvironmentDiff, DiffEntry

        diff_result = await db.execute(
            select(DiffModel).where(DiffModel.diff_id == incident.diff_id)
        )
        diff_model = diff_result.scalar_one_or_none()
        if diff_model:
            from app.domain.models import DiffEntry, DiffSeverity, DiffStatus
            diff = EnvironmentDiff(
                diff_id=diff_model.diff_id,
                fingerprint_a_id=diff_model.fingerprint_a_id,
                fingerprint_b_id=diff_model.fingerprint_b_id,
                environment_a_name=diff_model.environment_a_name,
                environment_b_name=diff_model.environment_b_name,
                entries=[DiffEntry(**e) for e in (diff_model.entries or [])],
                high_severity_count=diff_model.high_severity_count or 0,
                medium_severity_count=diff_model.medium_severity_count or 0,
                low_severity_count=diff_model.low_severity_count or 0,
            )

    model = await manager.add_ai_diagnosis(incident_id, diff=diff)
    if not model:
        raise HTTPException(status_code=404, detail="インシデントが見つかりません")
    return _model_to_dict(model)


@router.post("/{incident_id}/replay", response_model=Dict[str, Any])
async def replay_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    """インシデントを再実行（Replay）して結果を比較する"""
    manager = IncidentManager(db)
    incident = await manager.get(incident_id)

    if not incident:
        raise HTTPException(status_code=404, detail="インシデントが見つかりません")

    # Mock の場合はシミュレーションであり、実環境の再現として扱ってはならない。
    real = is_real_provider()
    vm_provider = get_vm_provider()
    provider_name = type(vm_provider).__name__
    test_runner = CommandTestRunner(vm_provider)

    # 1. Create environment
    try:
        instance_id = await vm_provider.create(incident.environment_name, {})
    except VirtualBoxError as exc:
        raise HTTPException(status_code=503, detail=f"VM を作成できません: {exc}") from exc

    try:
        await vm_provider.start(instance_id)

        # 実機の場合はプロジェクトを VM へ配置してから実行する
        if real and settings.VBOX_PROJECT_PATH:
            await vm_provider.copy_project(
                instance_id, settings.VBOX_PROJECT_PATH, settings.VBOX_GUEST_PATH
            )

        await vm_provider.install_dependencies(instance_id, [])
        cmd = incident.command_executed or "make test"
        result, logs, err = await test_runner.run(
            instance_id, settings.VBOX_GUEST_PATH, cmd
        )
        collected_logs = await vm_provider.collect_logs(instance_id, r"C:\DevMirror\app\error.log")
    except VirtualBoxError as exc:
        raise HTTPException(status_code=502, detail=f"VM での再実行に失敗しました: {exc}") from exc
    finally:
        if not (real and settings.VBOX_KEEP_VM):
            await vm_provider.destroy(instance_id)

    # 実機で同じ結果が出てはじめて「再現」と呼べる
    verified = real and result == incident.test_result

    if real:
        if verified:
            note = (
                f"実VMでの再実行結果: {result.value}（元の結果: {incident.test_result.value}）。"
                "実機環境で同じ結果を確認できました。"
            )
        else:
            note = (
                f"実VMでの再実行結果: {result.value}（元の結果: {incident.test_result.value}）。"
                "実機環境では元の結果と一致しませんでした。"
            )
    else:
        note = (
            f"Mock再実行のシミュレーション結果: {result.value}"
            f"（元の結果: {incident.test_result.value}）。"
            "実プロジェクトの環境を実行していないため、再現は未検証です。"
        )

    updated_model = await manager.update_status(
        incident_id, IncidentStatus.INVESTIGATING, note=note
    )

    return {
        "replay_result": result.value,
        "logs": collected_logs,
        "provider": provider_name,
        "simulated": not real,
        "reproduction_verified": verified,
        "runner_output": logs,
        "runner_error": err,
        "incident": _model_to_dict(updated_model) if updated_model else None
    }
