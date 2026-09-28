"""
VM コンソール API のテスト

QEMU は WSL（Linux）前提なので、Windows 上の Python で動かそうとすると
check_host() が「WSL で起動して」というエラーを返す。ここでは

  1. Windows で動かしたときの明確なエラー
  2. overlay のライフサイクル（作成・削除・復元）
  3. WebSocket 中継（VM 停止中は案内メッセージ、未知の名前は 400）

を FakeQemuProvider（実際の QEMU/qemu-img を使わない）で検証する。
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import vm_console
from app.main import app
from app.services.qemu_provider import QemuError, QemuProvider


class FakeQemuProvider(QemuProvider):
    """実際の QEMU を起動せず、argv からファイルを模倣する。"""

    async def _run(self, argv, timeout: float = 120):
        tool = os.path.basename(argv[0])
        # qemu-img create → overlay ファイルを作る
        if tool.startswith("qemu-img") and argv[1:2] == ["create"]:
            target = argv[-1]
            Path(target).write_bytes(b"QFI\xfb" + b"\0" * 100)
            return 0, "ok", ""
        # qemu-system-x86_64 -daemonize → pidfile を作るだけで成功扱い
        if "-daemonize" in argv:
            if "-pidfile" in argv:
                pid_arg = argv[argv.index("-pidfile") + 1]
                Path(pid_arg).write_text("4242", encoding="utf-8")
        return 0, "", ""


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_provider(tmp_path, monkeypatch):
    base = tmp_path / "base.qcow2"
    base.write_bytes(b"QFI\xfb" + b"\0" * 100)
    vm_dir = tmp_path / "vms"
    vm_dir.mkdir()

    provider = FakeQemuProvider(
        binary="qemu-system-x86_64",
        img_binary="qemu-img",
        base_image=str(base),
        vm_dir=str(vm_dir),
    )
    # QEMU は WSL 前提だが、Windows でもこの fake では動かしてよい
    monkeypatch.setattr(provider, "check_host", lambda: None)
    monkeypatch.setattr(vm_console, "_provider", lambda: provider)
    return provider


# ----------------------------------------------------------------------
# 1) ホスト環境のチェック
# ----------------------------------------------------------------------
def test_check_hostはWindowsで明確なWSL案内を返す():
    """
    QEMU は WSL（Linux）前提なので、Windows 上の Python で動かそうとすると
    check_host() が「WSL で起動して」というエラーを出す。
    """
    provider = QemuProvider()
    if os.name == "nt":
        with pytest.raises(QemuError) as exc:
            provider.check_host()
        assert "WSL" in str(exc.value)
    else:
        # Linux（WSL2）なら何も出さないのが正しい
        provider.check_host()


def test_console_listはホストエラーを400で返す(client, monkeypatch):
    """check_host が失敗するホストでは、400 + 案内メッセージになる。"""

    def windows_provider():
        raise QemuError(
            "QEMU を使う場合、バックエンドは WSL 上の Python で起動してください。"
        )

    monkeypatch.setattr(vm_console, "_provider", windows_provider)
    res = client.get("/api/v1/vm/console/list")
    assert res.status_code == 400
    assert "WSL" in res.json()["detail"]


# ----------------------------------------------------------------------
# 2) 一覧とライフサイクル
# ----------------------------------------------------------------------
def test_listは3環境とVNCポートを返す(client, fake_provider):
    res = client.get("/api/v1/vm/console/list")
    assert res.status_code == 200
    vms = res.json()
    assert [v["name"] for v in vms] == ["envA", "envB", "envC"]
    assert [v["vnc_port"] for v in vms] == [5901, 5902, 5903]
    assert all(v["created"] is False for v in vms)


def test_createはoverlayを作る(client, fake_provider):
    res = client.post("/api/v1/vm/console/envA/create")
    assert res.status_code == 200
    assert res.json()["name"] == "envA"
    assert fake_provider.overlay_path("envA").exists()


def test_未知の環境名は400(client, fake_provider):
    res = client.post("/api/v1/vm/console/envZ/create")
    assert res.status_code == 400
    assert "未知の環境名" in res.json()["detail"]


def test_deleteはoverlayを消す(client, fake_provider):
    client.post("/api/v1/vm/console/envA/create")
    assert fake_provider.overlay_path("envA").exists()

    res = client.post("/api/v1/vm/console/envA/delete")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert not fake_provider.overlay_path("envA").exists()


def test_resetはoverlayを作り直す(client, fake_provider):
    client.post("/api/v1/vm/console/envA/create")
    fake_provider.overlay_path("envA").write_bytes(b"dirty")

    res = client.post("/api/v1/vm/console/envA/reset")
    assert res.status_code == 200
    assert fake_provider.overlay_path("envA").exists()


# ----------------------------------------------------------------------
# 3) WebSocket 中継
# ----------------------------------------------------------------------
def _refuse_connection(monkeypatch):
    """VNC への接続を「拒否」に固定して、どの環境でも実行できるようにする。"""

    async def fake_open(*args, **kwargs):
        raise OSError("127.0.0.1:port に接続できません")

    monkeypatch.setattr(vm_console.asyncio, "open_connection", fake_open)


def test_console_wsでvm停止中は案内を送って閉じる(client, fake_provider, monkeypatch):
    # VM が起動していなくても確実に「接続できません」の分岐を通す
    _refuse_connection(monkeypatch)
    with client.websocket_connect("/api/v1/vm/console/envA/vnc") as ws:
        msg = ws.receive_text()
        assert "接続できません" in msg
        with pytest.raises(Exception):
            ws.receive_text()


def test_console_wsで未知の名前は案内を送って閉じる(client, fake_provider, monkeypatch):
    _refuse_connection(monkeypatch)
    with client.websocket_connect("/api/v1/vm/console/envZ/vnc") as ws:
        msg = ws.receive_text()
        assert "未知の環境名" in msg
        with pytest.raises(Exception):
            ws.receive_text()