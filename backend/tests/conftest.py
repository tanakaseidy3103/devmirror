"""
pytest 共通フィクスチャ
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

FAKE_VBOXMANAGE = Path(__file__).parent / "fake_vboxmanage.py"
FAKE_QEMU = Path(__file__).parent / "fake_qemu.py"


@pytest.fixture
def vboxmanage_path(monkeypatch):
    """
    ダミーの VBoxManage を起動するためのプレースホルダパスを返す。

    本物の VirtualBox が無い環境でも argv の組み立てを検証するため、
    create_subprocess_exec を差し替えて fake_vboxmanage.py を
    venv の Python で直接起動する。

    シェルスクリプト（.sh / .cmd）を使わない理由:
    プロジェクトのパスに日本語（デスクトップ）が含まれており、
    cmd.exe は .cmd を OEM コードページで読むため UTF-8 のパスを
    正しく解釈できない。直接起動すればコードページに依存しない。
    """
    from app.services import virtualbox_provider

    fake = str(FAKE_VBOXMANAGE)
    real_exec = asyncio.create_subprocess_exec

    async def exec_fake(exe, *cmd, **kwargs):
        return await real_exec(sys.executable, fake, *cmd, **kwargs)

    monkeypatch.setattr(
        virtualbox_provider.asyncio, "create_subprocess_exec", exec_fake
    )
    return "VBoxManage.exe"


@pytest.fixture
def vbox_env(tmp_path, monkeypatch):
    """ダミー VBoxManage の環境変数と、呼び出し履歴の取得器を返す。"""
    log = tmp_path / "vbox.log"
    monkeypatch.setenv("FAKE_VBOX_LOG", str(log))
    monkeypatch.setenv("FAKE_VBOX_STDOUT", "")
    monkeypatch.setenv("FAKE_VBOX_STDERR", "")
    monkeypatch.setenv("FAKE_VBOX_EXITCODE", "0")
    monkeypatch.setenv("FAKE_VBOX_VMS", "")
    monkeypatch.delenv("FAKE_VBOX_NOT_READY", raising=False)
    monkeypatch.delenv("FAKE_VBOX_MISSING", raising=False)

    def calls():
        if not log.exists():
            return []
        return [x for x in log.read_text(encoding="utf-8").splitlines() if x]

    return calls


@pytest.fixture
def qemu_env(tmp_path, monkeypatch):
    """ダミー QEMU の環境変数と、呼び出し履歴の取得器を返す。"""
    log = tmp_path / "qemu.log"
    monkeypatch.setenv("FAKE_QEMU_LOG", str(log))
    monkeypatch.setenv("FAKE_QEMU_STDOUT", "")
    monkeypatch.setenv("FAKE_QEMU_STDERR", "")
    monkeypatch.setenv("FAKE_QEMU_EXITCODE", "0")
    monkeypatch.setenv("FAKE_QEMU_VMS", "")
    monkeypatch.delenv("FAKE_QEMU_MISSING", raising=False)

    def calls():
        if not log.exists():
            return []
        return [x for x in log.read_text(encoding="utf-8").splitlines() if x]

    return calls


@pytest.fixture
def qemu_binaries(monkeypatch):
    """
    QemuProvider が使う実行ファイル名をダミーに向ける。

    Windows の CreateProcess は .cmd / .bat を直接実行できないため、
    シェルスクリプトは使わず venv の Python で直接起動する。
    """
    from app.services import qemu_provider

    fake = str(FAKE_QEMU)
    real_exec = asyncio.create_subprocess_exec

    async def exec_fake(exe, *cmd, **kwargs):
        return await real_exec(sys.executable, fake, os.path.basename(exe), *cmd, **kwargs)

    monkeypatch.setattr(qemu_provider.asyncio, "create_subprocess_exec", exec_fake)
    return "qemu-system-x86_64", "qemu-img"
