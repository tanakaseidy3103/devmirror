"""
DevMirror - Mac Bridge Endpoint（Mac接続管理）

コマンド文字列を受け取るエンドポイントは存在しない。
接続テストはサーバ側に固定された調査スクリプトだけを実行する。
"""
import ipaddress
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.db.models import MacBuildModel, MacHostModel
from app.services import mac_bridge, mac_build
from app.services.mac_bridge import HostKeyMismatchError, MacBridgeError

def require_local_client(request: Request) -> None:
    """
    API に認証が無いため、Mac Bridge は同じ PC（loopback）からの要求だけを受け付ける。
    バックエンドを 0.0.0.0 で起動しても、他の端末からは Mac を操作できない。
    """
    host = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host in ("localhost", "testclient")
    if not local:
        raise HTTPException(403, "Mac Bridge はこの PC（localhost）からのみ利用できます")


def get_session_factory():
    """バックグラウンドのビルドジョブが使う DB セッション（テストで差し替える）。"""
    return AsyncSessionLocal


router = APIRouter(dependencies=[Depends(require_local_client)])
logger = structlog.get_logger(__name__)


class RegisterMacRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    hostname: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str
    key_path: str
    host_key_fingerprint: str


def _to_dict(h: MacHostModel) -> Dict[str, Any]:
    probe = h.probe or {}
    return {
        "id": h.id,
        "name": h.name,
        "hostname": h.hostname,
        "port": h.port,
        "username": h.username,
        "host_key_fingerprint": h.host_key_fingerprint,
        "enabled": h.enabled,
        "status": h.status,
        "last_error": h.last_error,
        "last_checked_at": h.last_checked_at.isoformat() if h.last_checked_at else None,
        "last_connected_at": h.last_connected_at.isoformat() if h.last_connected_at else None,
        "macos_version": h.macos_version,
        "xcode_version": h.xcode_version,
        "xcode_build": probe.get("xcode_build"),
        "arch": probe.get("arch"),
        "disk_free_gb": probe.get("disk_free_gb"),
        "tools": probe.get("tools", []),
        "simulators": probe.get("simulators", []),
        "issues": probe.get("issues", []),
    }


async def _get(db: AsyncSession, host_id: int) -> MacHostModel:
    host = await db.get(MacHostModel, host_id)
    if host is None:
        raise HTTPException(404, "Mac が見つかりません")
    return host


@router.get("/hosts", response_model=List[Dict[str, Any]])
async def list_hosts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MacHostModel).order_by(MacHostModel.created_at))
    return [_to_dict(h) for h in result.scalars()]


@router.post("/hosts", response_model=Dict[str, Any], status_code=201)
async def register_host(req: RegisterMacRequest, db: AsyncSession = Depends(get_db)):
    """Mac を登録する。ホスト鍵がユーザー確認済みのフィンガープリントと一致した場合のみ。"""
    try:
        hostname = mac_bridge.validate_hostname(req.hostname)
        username = mac_bridge.validate_username(req.username)
        fp = mac_bridge.validate_fingerprint(req.host_key_fingerprint)
        key_path = mac_bridge.validate_key_path(req.key_path)
    except MacBridgeError as e:
        raise HTTPException(400, str(e))

    exists = await db.execute(select(MacHostModel).where(MacHostModel.name == req.name))
    if exists.scalar_one_or_none():
        raise HTTPException(409, "同じ名前の Mac が既に登録されています")

    try:
        line = await mac_bridge.verify_host_key(hostname, req.port, fp)
    except HostKeyMismatchError as e:
        raise HTTPException(409, str(e))
    except MacBridgeError as e:
        raise HTTPException(502, str(e))

    host = MacHostModel(
        name=req.name, hostname=hostname, port=req.port, username=username,
        key_path=key_path, host_key_fingerprint=fp, known_hosts_line=line,
    )
    db.add(host)
    await db.flush()
    logger.info("Mac を登録しました", host_id=host.id, hostname=hostname)
    return _to_dict(host)


@router.post("/hosts/{host_id}/test", response_model=Dict[str, Any])
async def test_host(host_id: int, db: AsyncSession = Depends(get_db)):
    """接続テストと環境調査（macOS / Xcode / シミュレータ / 空き容量）。"""
    host = await _get(db, host_id)
    lock = mac_bridge.host_lock(host_id)
    if lock.locked():
        raise HTTPException(409, "この Mac は接続テスト中です")
    async with lock:
        result = await mac_bridge.probe_host(host)

    host.status = result.status
    host.last_checked_at = datetime.utcnow()
    if result.status == "online":
        host.enabled = True
        host.last_error = None
        host.last_connected_at = host.last_checked_at
        host.macos_version = result.macos_version
        host.xcode_version = result.xcode_version
        host.probe = result.to_dict()
    else:
        host.last_error = result.message
    await db.flush()
    return _to_dict(host)


@router.post("/hosts/{host_id}/disconnect", response_model=Dict[str, Any])
async def disconnect_host(host_id: int, db: AsyncSession = Depends(get_db)):
    """常駐セッションは持たないため、無効化して以降のタスクに使わせない。"""
    host = await _get(db, host_id)
    host.enabled = False
    host.status = "disconnected"
    await db.flush()
    return _to_dict(host)


@router.delete("/hosts/{host_id}", status_code=204)
async def delete_host(host_id: int, db: AsyncSession = Depends(get_db)):
    host = await _get(db, host_id)
    await db.delete(host)
    (mac_bridge.data_dir() / f"known_hosts_{host_id}").unlink(missing_ok=True)


# ─────────────────────────────────────────────
# Xcode Remote Build Engine（MVP2）
# ─────────────────────────────────────────────

class InspectProjectRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=1024)


class PrepareBuildRequest(BaseModel):
    host_id: int
    source_path: str = Field(min_length=1, max_length=1024)
    container: str = Field(min_length=1, max_length=512)


class StartBuildRequest(BaseModel):
    scheme: str = Field(min_length=1, max_length=255)
    configuration: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _build_dict(job: MacBuildModel, host: Optional[MacHostModel] = None) -> Dict[str, Any]:
    return {
        "id": job.id,
        "host_id": job.host_id,
        "host_name": job.host_name,
        "source_path": job.source_path,
        "container": job.container,
        "container_type": job.container_type,
        "schemes": job.schemes or [],
        "configurations": job.configurations or [],
        "destinations": mac_build.destination_options(host) if host else [],
        "scheme": job.scheme,
        "configuration": job.configuration,
        "destination": job.destination,
        "destination_label": job.destination_label,
        "status": job.status,
        "exit_code": job.exit_code,
        "error_message": job.error_message,
        "errors": job.errors or [],
        "warning_count": job.warning_count or 0,
        "macos_version": job.macos_version,
        "xcode_version": job.xcode_version,
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "duration_sec": job.duration_sec,
        "workspace_cleaned": job.workspace_cleaned,
    }


def _mark_orphan(job: MacBuildModel) -> None:
    """バックエンド再起動で実行中タスクが消えたジョブを interrupted にする。"""
    if job.status in mac_build.ACTIVE_STATUSES and not mac_build.is_running(job.id):
        job.status = "interrupted"
        job.error_message = "バックエンドの再起動により中断されました"


async def _get_build(db: AsyncSession, build_id: str) -> MacBuildModel:
    job = await db.get(MacBuildModel, build_id) if mac_build.JOB_ID_RE.match(build_id) else None
    if job is None:
        raise HTTPException(404, "ビルドが見つかりません")
    _mark_orphan(job)
    return job


async def _host_busy(db: AsyncSession, host_id: int) -> bool:
    result = await db.execute(
        select(MacBuildModel).where(
            MacBuildModel.host_id == host_id, MacBuildModel.status.in_(mac_build.ACTIVE_STATUSES)
        )
    )
    return any(mac_build.is_running(j.id) for j in result.scalars())


@router.post("/projects/inspect", response_model=Dict[str, Any])
async def inspect_project(req: InspectProjectRequest):
    """Windows 側のフォルダから Xcode プロジェクト / ワークスペースを検出する。"""
    try:
        root = mac_build.resolve_source(req.source_path)
    except MacBridgeError as e:
        raise HTTPException(400, str(e))
    containers = mac_build.find_containers(root)
    if not containers:
        raise HTTPException(404, ".xcodeproj / .xcworkspace が見つかりません")
    return {"source_path": str(root), "containers": containers}


@router.post("/builds", response_model=Dict[str, Any], status_code=202)
async def prepare_build(
    req: PrepareBuildRequest,
    db: AsyncSession = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    """プロジェクトを Mac の隔離ディレクトリへ転送し、scheme を取得する（非同期）。"""
    host = await _get(db, req.host_id)
    if not host.enabled or host.status == "host_key_mismatch":
        raise HTTPException(409, "この Mac は利用できません（接続テストで状態を確認してください）")
    try:
        root = mac_build.resolve_source(req.source_path)
    except MacBridgeError as e:
        raise HTTPException(400, str(e))
    container = next((c for c in mac_build.find_containers(root) if c["path"] == req.container), None)
    if container is None:
        raise HTTPException(400, "選択したプロジェクトがフォルダ内にありません")
    if await _host_busy(db, host.id):
        raise HTTPException(409, "この Mac では別のビルドが実行中です")

    job = MacBuildModel(
        id=mac_build.new_job_id(), host_id=host.id, host_name=host.name,
        source_path=str(root), container=container["path"], container_type=container["type"],
        macos_version=host.macos_version, xcode_version=host.xcode_version, status="preparing",
    )
    db.add(job)
    await db.commit()  # バックグラウンドタスクが別セッションで読むため先に確定する
    mac_build.spawn(job.id, mac_build.prepare_job(job.id, session_factory))
    return _build_dict(job, host)


@router.get("/builds", response_model=List[Dict[str, Any]])
async def list_builds(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MacBuildModel).order_by(MacBuildModel.created_at.desc()).limit(100))
    jobs = list(result.scalars())
    for j in jobs:
        _mark_orphan(j)
    return [_build_dict(j) for j in jobs]


@router.get("/builds/{build_id}", response_model=Dict[str, Any])
async def get_build(build_id: str, db: AsyncSession = Depends(get_db)):
    job = await _get_build(db, build_id)
    host = await db.get(MacHostModel, job.host_id) if job.host_id else None
    return _build_dict(job, host)


@router.get("/builds/{build_id}/log", response_model=Dict[str, Any])
async def get_build_log(build_id: str, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """ログを offset から差分で返す（フロントエンドがポーリングする）。"""
    job = await _get_build(db, build_id)
    text, next_offset = mac_build.read_log(job.id, offset)
    return {"text": text, "offset": next_offset, "status": job.status}


@router.post("/builds/{build_id}/start", response_model=Dict[str, Any], status_code=202)
async def start_build(
    build_id: str,
    req: StartBuildRequest,
    db: AsyncSession = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    """検証済みのパラメータで xcodebuild を実行する。"""
    job = await _get_build(db, build_id)
    if job.status != "ready" or job.workspace_cleaned:
        raise HTTPException(409, "このビルドは開始できる状態ではありません")
    host = await _get(db, job.host_id)
    if not host.enabled:
        raise HTTPException(409, "この Mac は切断されています")
    if req.scheme not in (job.schemes or []):
        raise HTTPException(400, "scheme が候補にありません")
    if req.configuration not in (job.configurations or []):
        raise HTTPException(400, "configuration が候補にありません")
    try:
        destination, label = mac_build.resolve_destination(host, req.destination)
    except MacBridgeError as e:
        raise HTTPException(400, str(e))
    if await _host_busy(db, host.id):
        raise HTTPException(409, "この Mac では別のビルドが実行中です")

    job.scheme, job.configuration = req.scheme, req.configuration
    job.destination, job.destination_label = destination, label
    job.status, job.started_at = "running", datetime.utcnow()
    await db.commit()
    mac_build.spawn(job.id, mac_build.run_build(job.id, session_factory))
    return _build_dict(job, host)


@router.post("/builds/{build_id}/cancel", response_model=Dict[str, Any])
async def cancel_build(build_id: str, db: AsyncSession = Depends(get_db)):
    job = await _get_build(db, build_id)
    if not mac_build.cancel(job.id):
        raise HTTPException(409, "実行中ではありません")
    return {"id": job.id, "status": "cancelling"}


@router.post("/builds/{build_id}/cleanup", response_model=Dict[str, Any])
async def cleanup_build(build_id: str, db: AsyncSession = Depends(get_db)):
    """Mac 上の作業ディレクトリ（~/DevMirrorWorkspaces/<id>）を削除する。ログは残す。"""
    job = await _get_build(db, build_id)
    if mac_build.is_running(job.id):
        raise HTTPException(409, "実行中のビルドは削除できません。先にキャンセルしてください")
    host = await _get(db, job.host_id)
    try:
        await mac_build.cleanup_workspace(host, job.id)
    except MacBridgeError as e:
        raise HTTPException(502, str(e))
    job.workspace_cleaned = True
    if job.status == "ready":
        job.status = "cancelled"
    await db.flush()
    return _build_dict(job, host)
