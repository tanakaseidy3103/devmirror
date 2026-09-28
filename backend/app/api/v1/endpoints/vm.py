"""
DevMirror - VM Status Endpoint

VirtualBox が使える状態かを、切らずに確認するための情報。
"""
from typing import Any, Dict

import os
import structlog
from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings
from app.services.qemu_provider import QemuError, QemuProvider
from app.services.vm_factory import get_vm_provider, is_real_provider, uses_qemu_console
from app.services.virtualbox_provider import VirtualBoxError, VirtualBoxProvider

router = APIRouter()
logger = structlog.get_logger(__name__)


async def _qemu_status(provider: Any) -> Dict[str, Any]:
    """QEMU 選択時の状態。実行ファイルと基準ディスクの実在を確認する。"""
    info: Dict[str, Any] = {
        "provider": type(provider).__name__,
        "simulated": False,
        "console": True,
        "memory_mb": settings.QEMU_MEMORY_MB,
        "cpus": settings.QEMU_CPUS,
        "accel": settings.QEMU_ACCEL,
        "vm_names": settings.QEMU_VM_NAMES,
        "base_image": settings.QEMU_BASE_IMAGE,
        "vm_dir": settings.QEMU_VM_DIR or str(provider.vm_dir),
    }

    problems = []

    try:
        info["resolved_qemu_binary"] = provider.resolve_binary()
    except QemuError as exc:
        problems.append(str(exc))

    try:
        info["resolved_qemu_img_binary"] = provider.resolve_img_binary()
    except QemuError as exc:
        problems.append(str(exc))

    try:
        provider.resolve_base_image()
        info["base_image_found"] = True
    except QemuError as exc:
        info["base_image_found"] = False
        problems.append(str(exc))

    # 起動可能な-accel か（kvm が使えるか）を確認する
    if settings.QEMU_ACCEL == "kvm" and not Path("/dev/kvm").exists():
        problems.append(
            "/dev/kvm が見つかりません。WSL で "
            "`sudo usermod -aG kvm $USER` を実行し、ターミナルを開き直してください。"
        )
    elif settings.QEMU_ACCEL == "kvm" and not os.access("/dev/kvm", os.R_OK | os.W_OK):
        problems.append(
            "/dev/kvm への権限がありません。"
            "`sudo usermod -aG kvm $USER` の後にターミナルを開き直してください。"
        )

    try:
        info["vms"] = await provider.list_vms()
    except QemuError:
        info["vms"] = []

    if problems:
        info.update({"available": False, "detail": " / ".join(problems)})
    else:
        info.update({"available": True, "detail": "QEMU を使用できます。ブラウザから VM に入れます。"})

    return info


@router.get("/status", response_model=Dict[str, Any])
async def vm_status() -> Dict[str, Any]:
    """
    現在の VM Provider と、その実行可否を返す。

    実機 (virtualbox) の場合は VBoxManage と基準 VM の有無を実際に確認する。
    """
    provider = get_vm_provider()
    is_real = is_real_provider()

    if uses_qemu_console():
        return await _qemu_status(provider)

    info: Dict[str, Any] = {
        "provider": type(provider).__name__,
        "simulated": not is_real,
        "base_vm": settings.VBOX_BASE_VM,
        "clone_mode": settings.VBOX_CLONE_MODE,
        "clone_prefix": settings.VBOX_CLONE_PREFIX,
        "memory_mb": settings.VBOX_MEMORY_MB,
        "cpus": settings.VBOX_CPUS,
        "project_path": settings.VBOX_PROJECT_PATH,
        "guest_path": settings.VBOX_GUEST_PATH,
        "vboxmanage_path": settings.VBOXMANAGE_PATH,
        "guest_username": settings.VBOX_GUEST_USERNAME,
    }

    if not is_real:
        info.update({"available": True, "detail": "モックモードです。実 VM は使用しません。"})
        return info

    if not isinstance(provider, VirtualBoxProvider):
        info.update({"available": False, "detail": "VirtualBoxProvider ではありません。"})
        return info

    # VBoxManage に到達できるか
    try:
        exe = provider.resolve_executable()
    except VirtualBoxError as exc:
        info.update({"available": False, "detail": str(exc)})
        return info

    info["resolved_vboxmanage_path"] = exe

    try:
        rc, out, _ = await provider._vbox("list", "vms", timeout=30)
    except VirtualBoxError as exc:
        info.update({"available": False, "detail": f"VBoxManage の実行に失敗しました: {exc}"})
        return info

    if rc != 0:
        info.update({"available": False, "detail": f"VBoxManage がエラーを返しました (rc={rc})"})
        return info

    registered = [
        line.split('"')[1]
        for line in out.splitlines()
        if line.strip().startswith('"') and '"' in line.strip()
    ]
    info["registered_vms"] = registered
    info["base_vm_found"] = settings.VBOX_BASE_VM in registered

    problems = []
    if not info["base_vm_found"]:
        problems.append(
            f"基準 VM「{settings.VBOX_BASE_VM}」が見つかりません。"
            "先に VM を作成して Guest Additions を入れてください。"
        )
    if not settings.VBOX_GUEST_USERNAME:
        problems.append("VBOX_GUEST_USERNAME が未設定です。guestcontrol を使えません。")
    if not settings.VBOX_PROJECT_PATH:
        problems.append("VBOX_PROJECT_PATH が未設定です。VM にゲームが配置されません。")

    if problems:
        info.update({"available": False, "detail": " / ".join(problems)})
    else:
        info.update({"available": True, "detail": "VirtualBox を使用できます。"})

    return info
