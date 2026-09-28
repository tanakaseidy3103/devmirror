"""
DevMirror - VM Provider Factory
"""
import structlog

from app.core.config import settings
from app.domain.providers import VMProvider
from app.services.qemu_provider import QemuError, QemuProvider
from app.services.vm_provider import MockVMProvider
from app.services.virtualbox_provider import VirtualBoxError, VirtualBoxProvider

logger = structlog.get_logger(__name__)


def get_qemu_provider() -> QemuProvider:
    """設定から QemuProvider を組み立てる（コンソール機能で使う）。"""
    return QemuProvider(
        binary=settings.QEMU_BINARY,
        img_binary=settings.QEMU_IMG_BINARY,
        base_image=settings.QEMU_BASE_IMAGE,
        boot_iso=settings.QEMU_BOOT_ISO,
        vm_dir=settings.QEMU_VM_DIR,
        vnc_base_port=settings.QEMU_VNC_BASE_PORT,
        memory_mb=settings.QEMU_MEMORY_MB,
        cpus=settings.QEMU_CPUS,
        accel=settings.QEMU_ACCEL,
        boot_timeout=settings.QEMU_BOOT_TIMEOUT,
        stop_timeout=settings.QEMU_STOP_TIMEOUT,
    )


def uses_qemu_console() -> bool:
    """ブラウザから VM に入れる方式（QEMU）が選択されているか。"""
    return (settings.VM_PROVIDER or "mock").strip().lower() == "qemu"


def get_vm_provider() -> VMProvider:
    """
    設定 (VM_PROVIDER) に応じた VMProvider を返す。

    "mock"       : モック（デモ用・実際の VM は使わない）
    "virtualbox" : VBoxManage を使う実機
    "qemu"       : QEMU + KVM を使う実機（コンソール付き）
    """
    provider = (settings.VM_PROVIDER or "mock").strip().lower()

    if provider == "virtualbox":
        logger.info("[VM] VirtualBoxProvider を使用します")
        return VirtualBoxProvider()
    if provider == "qemu":
        logger.info("[VM] QemuProvider を使用します")
        return get_qemu_provider()
    if provider == "mock":
        logger.info("[VM] MockVMProvider を使用します")
        return MockVMProvider()

    logger.warning(
        "[VM] 不明な VM_PROVIDER です。Mock にフォールバックします", value=provider
    )
    return MockVMProvider()


def is_real_provider() -> bool:
    """実機のプロバイダーを使う設定かどうか"""
    return (settings.VM_PROVIDER or "mock").strip().lower() in {"virtualbox", "qemu"}


__all__ = [
    "get_vm_provider",
    "get_qemu_provider",
    "is_real_provider",
    "uses_qemu_console",
    "VirtualBoxError",
    "QemuError",
]
