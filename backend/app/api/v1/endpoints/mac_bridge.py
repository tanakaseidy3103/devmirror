"""
DevMirror - Mac Bridge Endpoint（Mac接続管理）

コマンド文字列を受け取るエンドポイントは存在しない。
接続テストはサーバ側に固定された調査スクリプトだけを実行する。
"""
from datetime import datetime
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import MacHostModel
from app.services import mac_bridge
from app.services.mac_bridge import HostKeyMismatchError, MacBridgeError

router = APIRouter()
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
