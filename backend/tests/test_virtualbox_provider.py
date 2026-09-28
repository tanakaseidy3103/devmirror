"""
VirtualBoxProvider のテスト

本物の VirtualBox が無い環境でも検証できるよう、tests/fake_vboxmanage.py
を VBoxManage として起動するラッパーを使う（conftest.py の fixture）。
"""
import pytest

from app.domain.providers import VMProvider
from app.services.virtualbox_provider import VirtualBoxError, VirtualBoxProvider


@pytest.fixture
def provider(vboxmanage_path):
    return VirtualBoxProvider(
        vboxmanage_path=vboxmanage_path,
        base_vm="DevMirror-Base",
        clone_mode="linked",
        clone_prefix="DevMirror",
        guest_username="dmuser",
        guest_password="dmpass",
        boot_timeout=2,
        guest_ready_timeout=1,
    )


# --------------------------------------------------------------------- 契約

def test_抽象インターフェースを満たしている():
    assert issubclass(VirtualBoxProvider, VMProvider)
    # ABC の抽象メソッドが残っていないこと
    assert VirtualBoxProvider.__abstractmethods__ == frozenset()


# ------------------------------------------------------------------- create

@pytest.mark.asyncio
async def test_create_は基準VMをクローンして登録する(provider, vbox_env):
    vm = await provider.create("envA", {})

    assert vm == "DevMirror-envA"
    calls = vbox_env()
    assert any(c.startswith("clonevm DevMirror-Base --name DevMirror-envA") for c in calls)
    assert any("--mode linked" in c for c in calls)
    assert any(c.startswith("modifyvm DevMirror-envA") for c in calls)


@pytest.mark.asyncio
async def test_3つの環境がそれぞれ別のVMになる(provider):
    """「環境A（動作する）」と「環境A（失敗する）」を区別できること"""
    names = {provider._vm_name(n) for n in ("envA", "envB", "envC")}
    assert len(names) == 3

    jp = {provider._vm_name(n) for n in ("環境A（動作する）", "環境A（失敗する）")}
    assert len(jp) == 2, "日本語の近い環境名が衝突している"

    # 同じ名前からは常に同じ VM 名（冪等）
    assert provider._vm_name("環境B") == provider._vm_name("環境B")


@pytest.mark.asyncio
async def test_create_は基準VMが無ければVirtualBoxError(provider):
    with pytest.raises(VirtualBoxError):
        await provider.create("envA", {"base_vm": "NoSuchBase"})


@pytest.mark.asyncio
async def test_create_は既存VMを作り直す(provider, vbox_env):
    await provider.create("envA", {})
    vbox_env()  # 履歴をいったん消す
    await provider.create("envA", {})
    calls = vbox_env()
    assert any(c.startswith("unregistervm DevMirror-envA --delete") for c in calls)
    assert any(c.startswith("clonevm") for c in calls)


# ------------------------------------------------------------- start / stop

@pytest.mark.asyncio
async def test_start_はヘッドレス起動しGuest_Additionsを待つ(provider, vbox_env):
    assert await provider.start("DevMirror-envA") is True
    assert any("startvm DevMirror-envA --type headless" in c for c in vbox_env())
    assert any("guestcontrol DevMirror-envA getenv" in c for c in vbox_env())


@pytest.mark.asyncio
async def test_start_はGuest_Additionsが無応答ならエラー(vboxmanage_path, monkeypatch):
    monkeypatch.setenv("FAKE_VBOX_NOT_READY", "1")
    p = VirtualBoxProvider(
        vboxmanage_path=vboxmanage_path,
        guest_username="dmuser",
        guest_ready_timeout=0,
        boot_timeout=2,
    )
    with pytest.raises(VirtualBoxError, match="Guest Additions"):
        await p.start("DevMirror-envA")


@pytest.mark.asyncio
async def test_stop_はacpiで停止する(provider, vbox_env):
    assert await provider.stop("DevMirror-envA") is True
    assert any("controlvm DevMirror-envA acpipowerbutton" in c for c in vbox_env())


@pytest.mark.asyncio
async def test_destroy_はpoweroffして削除する(provider, vbox_env):
    assert await provider.destroy("DevMirror-envA") is True
    calls = vbox_env()
    assert any("controlvm DevMirror-envA poweroff" in c for c in calls)
    assert any("unregistervm DevMirror-envA --delete" in c for c in calls)


# ------------------------------------------------------------ copy_project

@pytest.mark.asyncio
async def test_copy_project_は親ディレクトリをWindows形式で作る(
    provider, vbox_env, tmp_path
):
    src = tmp_path / "app"
    src.mkdir()
    (src / "DXGame.exe").write_bytes(b"MZ")

    ok = await provider.copy_project(
        "DevMirror-envA", str(src), r"C:\DevMirror\app"
    )

    assert ok is True
    calls = vbox_env()
    # os.path ではなく ntpath を使うため、"C:\DevMirror" が親として出る
    assert any(
        "guestcontrol DevMirror-envA mkdir C:\\DevMirror --parents" in c for c in calls
    )
    assert any(
        "copyto C:\\DevMirror\\app" in c and "--recursive" in c for c in calls
    )


@pytest.mark.asyncio
async def test_copy_project_はコピー元が無ければエラー(provider, tmp_path):
    with pytest.raises(VirtualBoxError, match="コピー元"):
        await provider.copy_project("DevMirror-envA", str(tmp_path / "nope"), r"C:\a")


# ------------------------------------------------------------- run_command

@pytest.mark.asyncio
async def test_run_command_はpidを待ち標準出力を返す(provider, vbox_env, monkeypatch):
    monkeypatch.setenv("FAKE_VBOX_STDOUT", "テスト開始\n完了")
    rc, stdout, stderr = await provider.run_command("DevMirror-envA", "DXGame.exe")

    assert rc == 0
    assert "完了" in stdout
    calls = vbox_env()
    assert any("run cmd.exe /c" in c for c in calls)
    assert any("wait 4242" in c for c in calls)
    assert any("readcat 4242" in c for c in calls)


@pytest.mark.asyncio
async def test_run_command_は終了コードを返す(provider, vbox_env, monkeypatch):
    monkeypatch.setenv("FAKE_VBOX_EXITCODE", "3")
    rc, _, _ = await provider.run_command("DevMirror-envA", "DXGame.exe")
    assert rc == 3


@pytest.mark.asyncio
async def test_run_command_は終了コード取得失敗を0にする(provider, monkeypatch):
    monkeypatch.setenv("FAKE_VBOX_EXITCODE", "no-digits-here")
    rc, _, _ = await provider.run_command("DevMirror-envA", "DXGame.exe")
    assert rc == 0


@pytest.mark.asyncio
async def test_run_command_は存在しないVMでエラー(provider):
    with pytest.raises(VirtualBoxError):
        await provider.run_command("GhostVM", "DXGame.exe")


# ------------------------------------------------------ install_dependencies

@pytest.mark.asyncio
async def test_install_dependencies_はinstall_commandを実行する(provider, vbox_env):
    ok = await provider.install_dependencies(
        "DevMirror-envA", [{"name": "DX Library", "install_command": "setup.exe /S"}]
    )
    assert ok is True
    assert any("setup.exe /S" in c for c in vbox_env())


@pytest.mark.asyncio
async def test_install_dependencies_はinstall_command無しなら何もしない(
    provider, vbox_env
):
    assert await provider.install_dependencies("DevMirror-envA", [{"name": "git"}]) is True
    assert vbox_env() == []


# ----------------------------------------------------------- logs / 画像

@pytest.mark.asyncio
async def test_collect_logs_はファイルの中身を返す(provider, vbox_env, monkeypatch):
    monkeypatch.setenv("FAKE_VBOX_EXITCODE", "DxLib.dll が見つかりません")
    logs = await provider.collect_logs("DevMirror-envA", r"C:\DevMirror\app\error.log")
    assert "DxLib.dll" in logs


@pytest.mark.asyncio
async def test_take_screenshot_はpngを返す(provider, vbox_env):
    png = await provider.take_screenshot("DevMirror-envA")
    assert png is not None
    assert png.startswith(b"\x89PNG")


# ---------------------------------------------------------- 実行ファイル探索

def test_resolve_executable_は未設定かつ未発見ならエラー(monkeypatch):
    p = VirtualBoxProvider(vboxmanage_path="")
    monkeypatch.setattr(
        "app.services.virtualbox_provider._CANDIDATE_PATHS", ["/nope/vboxmanage"]
    )
    monkeypatch.setattr(
        "app.services.virtualbox_provider.shutil.which", lambda name: None
    )
    with pytest.raises(VirtualBoxError, match="VBoxManage が見つかりません"):
        p.resolve_executable()


def test_resolve_executable_は設定値を優先する(vboxmanage_path):
    assert VirtualBoxProvider(vboxmanage_path=vboxmanage_path).resolve_executable() == (
        vboxmanage_path
    )
