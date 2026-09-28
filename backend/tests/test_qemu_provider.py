"""
QemuProvider のテスト

本物の QEMU / KVM が無い環境でも、argv の組み立てとエラー処理、
ライフサイクルを検証する（tests/fake_qemu.py を使う）。
"""
import asyncio

from pathlib import Path

import pytest

from app.services.qemu_provider import QemuError, QemuProvider


@pytest.fixture
def provider(tmp_path, qemu_binaries):
    binary, img = qemu_binaries
    base = tmp_path / "base.qcow2"
    base.write_bytes(b"QFI\xfb" + b"\0" * 100)
    iso = tmp_path / "boot.iso"
    iso.write_bytes(b"iso")

    vm_dir = tmp_path / "vms"
    vm_dir.mkdir()

    return QemuProvider(
        binary=binary,
        img_binary=img,
        base_image=str(base),
        boot_iso=str(iso),
        vm_dir=str(vm_dir),
        vnc_base_port=5901,
        memory_mb=1024,
        cpus=2,
        accel="kvm",
        boot_timeout=2,
        stop_timeout=2,
    )


@pytest.fixture
def alive(monkeypatch):
    """
    プロセスが生きている状態にする。

    os.kill(pid, 0) は POSIX 専用で、Windows では TerminateProcess に
    なるため-os を触らずに判定だけを差し替える。
    """
    monkeypatch.setattr(QemuProvider, "_pid_alive", staticmethod(lambda pid: True))


@pytest.fixture
def dead(monkeypatch):
    """プロセスが止まっている状態にする。"""
    monkeypatch.setattr(QemuProvider, "_pid_alive", staticmethod(lambda pid: False))


@pytest.fixture
def running(provider, alive):
    """指定した名前の VM を「起動中」にする。"""
    def _running(name: str) -> None:
        provider.pid_path(name).write_text("4242")
    return _running


@pytest.fixture
def no_qmp():
    """QMP を何もしないダミーにする（ソケットが無い状況を避ける）。"""
    async def _no_qmp(name, command, arguments=None):
        return {}
    return _no_qmp


# ----------------------------------------------------------------------
# パスとポート
# ----------------------------------------------------------------------
def test_vncポートは環境ごとに違う(provider):
    assert provider.vnc_port("envA") == 5901
    assert provider.vnc_port("envB") == 5902
    assert provider.vnc_port("envC") == 5903


def test_未知の環境名はQemuError(provider):
    with pytest.raises(QemuError, match="未知の環境名"):
        provider.vnc_port("envZ")


def test_実行ファイル解決は設定値を優先する(provider):
    assert provider.resolve_binary() == "qemu-system-x86_64"
    assert provider.resolve_img_binary() == "qemu-img"


def test_基準ディスクが無ければQemuError(tmp_path, qemu_binaries):
    binary, img = qemu_binaries
    p = QemuProvider(binary=binary, img_binary=img, base_image="", vm_dir=str(tmp_path))
    with pytest.raises(QemuError, match="QEMU_BASE_IMAGE"):
        p.resolve_base_image()


def test_基準ディスクが実在しなければQemuError(tmp_path, qemu_binaries):
    binary, img = qemu_binaries
    p = QemuProvider(
        binary=binary, img_binary=img,
        base_image=str(tmp_path / "nope.qcow2"), vm_dir=str(tmp_path),
    )
    with pytest.raises(QemuError, match="存在しません"):
        p.resolve_base_image()


# ----------------------------------------------------------------------
# ライフサイクル
# ----------------------------------------------------------------------
async def test_create_はoverlayを作る(provider, qemu_env):
    created = await provider.create("envA")
    assert created is True
    assert provider.overlay_path("envA").exists()

    # 基準ディスクを親に指定している
    assert any("qemu-img create" in c and "-b" in c for c in qemu_env())


async def test_create_は2回目は何もしない(provider, qemu_env):
    await provider.create("envA")
    provider.overlay_path("envA").write_bytes(b"already")
    assert await provider.create("envA") is False


async def test_create_は未知の名前を拒否する(provider):
    with pytest.raises(QemuError):
        await provider.create("envZ")


async def test_start_はoverlayが無いと失敗する(provider):
    with pytest.raises(QemuError, match="overlay がありません"):
        await provider.start("envA")


@pytest.fixture
def no_wait():
    """VNC 待ちを飛ばす（ポートを実際に開けないため）。"""
    async def _no_wait(name, port, timeout):
        return None
    return _no_wait


async def test_start_はkvmとvncとdaemonizeを渡す(provider, qemu_env, monkeypatch, no_wait):
    await provider.create("envA")
    monkeypatch.setattr(provider, "_wait_for_port", no_wait)

    assert await provider.start("envA") is True
    cmd = " ".join(qemu_env())

    assert "-accel kvm" in cmd
    assert "-vnc 127.0.0.1:1" in cmd          # 5901 - 5900
    assert "-daemonize" in cmd
    assert f"file={provider.overlay_path('envA')}" in cmd
    assert f"file={provider.boot_iso},media=cdrom" in cmd
    assert "-boot d" in cmd


async def test_start_は既に起動中なら何もしない(provider, qemu_env, running):
    running("envA")
    assert await provider.start("envA") is False
    assert qemu_env() == []


async def test_is_running_は死んだpidでFalse(provider, dead):
    provider.pid_path("envA").write_text("12345")
    assert provider.is_running("envA") is False


async def test_is_running_は生きているpidでTrue(provider, alive):
    provider.pid_path("envA").write_text("12345")
    assert provider.is_running("envA") is True


async def test_is_running_はpidファイル無しでFalse(provider):
    assert provider.is_running("envA") is False


async def test_is_running_は不正なpidでFalse(provider):
    provider.pid_path("envA").write_text("not-a-number")
    assert provider.is_running("envA") is False


async def test_stop_は未起動ならFalse(provider):
    assert await provider.stop("envA") is False


async def test_stop_はpidとソケットを片付ける(provider, running, no_qmp, monkeypatch):
    running("envA")
    provider.qmp_path("envA").write_text("")
    monkeypatch.setattr(provider, "_qmp", no_qmp)

    assert await provider.stop("envA") is True
    assert not provider.pid_path("envA").exists()
    assert not provider.qmp_path("envA").exists()


async def test_reset_はoverlayを作り直す(provider, dead, no_qmp, monkeypatch):
    await provider.create("envA")
    provider.overlay_path("envA").write_bytes(b"dirty-state")

    monkeypatch.setattr(provider, "_qmp", no_qmp)

    assert await provider.reset("envA") is True
    assert provider.overlay_path("envA").exists()


async def test_delete_はoverlayを消す(provider):
    await provider.create("envA")
    assert await provider.delete("envA") is True
    assert not provider.overlay_path("envA").exists()


# ----------------------------------------------------------------------
# 状態と一覧
# ----------------------------------------------------------------------
async def test_status_は作成と起動状態を返す(provider):
    st = await provider.status("envA")
    assert st["name"] == "envA"
    assert st["created"] is False
    assert st["running"] is False
    assert st["vnc_port"] == 5901

    await provider.create("envA")
    assert (await provider.status("envA"))["created"] is True


async def test_list_は3環境を返す(provider):
    vms = await provider.list_vms()
    assert [v["name"] for v in vms] == ["envA", "envB", "envC"]


# ----------------------------------------------------------------------
# エラー処理
# ----------------------------------------------------------------------
async def test_実行ファイルが無い場合はQemuError(tmp_path, monkeypatch):
    from app.services import qemu_provider as mod

    p = QemuProvider(binary="qemu-does-not-exist", vm_dir=str(tmp_path))

    async def boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", boom)
    with pytest.raises(QemuError, match="実行ファイルが見つかりません"):
        await p._run(["qemu-does-not-exist"])


async def test_qemu_imgが失敗したらQemuError(provider, qemu_env, monkeypatch):
    monkeypatch.setenv("FAKE_QEMU_EXITCODE", "1")
    with pytest.raises(QemuError, match="overlay を作成できません"):
        await provider.create("envA")


async def test_スクリーンショットは未起動なら失敗(provider):
    with pytest.raises(QemuError, match="起動していない"):
        await provider.screenshot("envA", Path("/tmp/x.png"))


async def test_スクリーンショットはQMPで撮る(provider, tmp_path, monkeypatch, running, no_qmp):
    calls = []
    dest = tmp_path / "shot.png"

    async def fake_qmp(name, command, arguments=None):
        calls.append((name, command, arguments))
        Path((arguments or {})["filename"]).write_bytes(b"\x89PNG fake")
        return {}

    running("envA")
    monkeypatch.setattr(provider, "_qmp", fake_qmp)

    assert await provider.screenshot("envA", dest) is True
    assert calls[0][1] == "screendump"
    assert dest.read_bytes().startswith(b"\x89PNG")


async def test_vncポートが開かなければtimeout(provider, monkeypatch, alive, no_qmp):
    await provider.create("envA")
    monkeypatch.setattr(provider, "_qmp", no_qmp)
    # プロセスは生きているが VNC はずっと開かない
    monkeypatch.setattr(QemuProvider, "_port_open", staticmethod(_never_open))

    with pytest.raises(QemuError, match="開きません"):
        await provider.start("envA")


async def test_起動直後に落ちたらエラー(provider, monkeypatch, dead, no_qmp):
    await provider.create("envA")
    monkeypatch.setattr(provider, "_qmp", no_qmp)

    with pytest.raises(QemuError, match="起動直後に停止"):
        await provider.start("envA")


# ----------------------------------------------------------------------
# ヘルパー
# ----------------------------------------------------------------------
async def _never_open(port, host="127.0.0.1"):
    return False
