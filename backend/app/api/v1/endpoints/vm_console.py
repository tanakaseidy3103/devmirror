"""
DevMirror - VM コンソール / ライフサイクル API

ブラウザから VM に「入る」ための API。

  GET  /vm/console/list              : 環境の一覧
  POST /vm/console/{name}/create     : overlay を作る
  POST /vm/console/{name}/start      : 起動する
  POST /vm/console/{name}/stop       : 停止する
  POST /vm/console/{name}/reset      : 初期状態に戻す
  POST /vm/console/{name}/delete     : 消す
  GET  /vm/console/{name}/screenshot : 画面を取得
  WS   /vm/console/{name}/vnc        : VNC を WebSocket に中継（noVNC 用）
"""
import asyncio
from pathlib import Path
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services.qemu_provider import QemuError
from app.services.vm_factory import get_qemu_provider

router = APIRouter()
logger = structlog.get_logger(__name__)

SCREENSHOT_DIR = Path.home() / ".devmirror" / "screenshots"


def _provider():
    provider = get_qemu_provider()
    # QEMU は WSL 前提なので、Windows 上の起動はここで明確に落とす
    provider.check_host()
    return provider


def _bad_request(exc: QemuError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/console/list", response_model=List[Dict[str, Any]])
async def list_console_vms() -> List[Dict[str, Any]]:
    """3 環境それぞれの状態（作成済みか・起動中か・VNC ポート）を返す。"""
    try:
        provider = _provider()
        return await provider.list_vms()
    except QemuError as exc:
        raise _bad_request(exc) from exc


@router.post("/console/{name}/create", response_model=Dict[str, Any])
async def create_console_vm(name: str) -> Dict[str, Any]:
    try:
        provider = _provider()
        created = await provider.create(name)
    except QemuError as exc:
        raise _bad_request(exc) from exc
    return {"name": name, "created": created, **await provider.status(name)}


@router.post("/console/{name}/start", response_model=Dict[str, Any])
async def start_console_vm(name: str) -> Dict[str, Any]:
    try:
        provider = _provider()
        started = await provider.start(name)
    except QemuError as exc:
        raise _bad_request(exc) from exc
    return {"name": name, "started": started, **await provider.status(name)}


@router.post("/console/{name}/stop", response_model=Dict[str, Any])
async def stop_console_vm(name: str) -> Dict[str, Any]:
    try:
        provider = _provider()
        stopped = await provider.stop(name)
    except QemuError as exc:
        raise _bad_request(exc) from exc
    return {"name": name, "stopped": stopped, **await provider.status(name)}


@router.post("/console/{name}/reset", response_model=Dict[str, Any])
async def reset_console_vm(name: str) -> Dict[str, Any]:
    try:
        provider = _provider()
        await provider.reset(name)
    except QemuError as exc:
        raise _bad_request(exc) from exc
    return {"name": name, "reset": True, **await provider.status(name)}


@router.post("/console/{name}/delete", response_model=Dict[str, Any])
async def delete_console_vm(name: str) -> Dict[str, Any]:
    try:
        provider = _provider()
        deleted = await provider.delete(name)
    except QemuError as exc:
        raise _bad_request(exc) from exc
    return {"name": name, "deleted": deleted}


@router.get("/console/{name}/screenshot")
async def console_screenshot(name: str) -> FileResponse:
    """VM の現在の画面を PNG で返す。"""
    dest = SCREENSHOT_DIR / f"{name}.png"
    try:
        provider = _provider()
        await provider.screenshot(name, dest)
    except QemuError as exc:
        raise _bad_request(exc) from exc
    return FileResponse(dest, media_type="image/png")


@router.websocket("/console/{name}/vnc")
async def vnc_console(websocket: WebSocket, name: str) -> None:
    """
    VNC の TCP 接続を WebSocket に中継する。

    noVNC は WebSocket 越しに RFB プロトコルを話すので、
    そのままバイナリを流すだけでブラウザに VM の画面が出る。
    """
    await websocket.accept(subprotocol="binary")

    try:
        provider = _provider()
        port = provider.vnc_port(name)
    except QemuError as exc:
        await websocket.send_text(str(exc))
        await websocket.close()
        return

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        await websocket.send_text(
            f"{name} に接続できません。VM が起動しているか確認してください。"
        )
        await websocket.close()
        return

    async def pump_to_browser() -> None:
        """VNC -> ブラウザ"""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("VNC 送信ループが終了", vm=name, error=str(exc))

    async def pump_to_vnc() -> None:
        """ブラウザ -> VNC"""
        try:
            while True:
                data = await websocket.receive_bytes()
                writer.write(data)
                await writer.drain()
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("VNC 受信ループが終了", vm=name, error=str(exc))

    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(pump_to_browser()), asyncio.create_task(pump_to_vnc())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["router", "settings"]
