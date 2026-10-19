"""
Xcode Remote Build Engine（MVP2）のテスト

ssh の代わりに tests/fake_mac.py を実プロセスとして起動する。
転送（tar.gz の生成・stdin 経由の送信・展開）、ログの逐次取得、キャンセル、
タイムアウトは本物のプロセスで動く。Mac・xcodebuild の出力だけが偽物。
**ここで成功してもビルドが実機で通ったことにはならない**（docs/mac-bridge/TEST_PLAN.md）。
"""
import asyncio
import json
import os
import shlex
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import mac_bridge as ep
from app.core.config import settings
from app.core.database import Base, get_db
from app.db.models import MacBuildModel, MacHostModel
from app.main import app
from app.services import mac_bridge, mac_build
from app.services.mac_bridge import MacBridgeError

FAKE_MAC = str(Path(__file__).parent / "fake_mac.py")
UDID = "8C1B6F4E-1D2A-4B3C-9E8F-0A1B2C3D4E5F"
LIST_JSON = json.dumps({"workspace": {"name": "App", "schemes": ["App", "AppTests"]}})
API = "/api/v1/mac-bridge"


# ─── フィクスチャ ───

@pytest.fixture
def project(tmp_path):
    root = tmp_path / "projects" / "MyApp"
    (root / "App.xcodeproj" / "project.xcworkspace").mkdir(parents=True)
    (root / "App.xcodeproj" / "project.pbxproj").write_text("// pbx")
    (root / "App.xcworkspace").mkdir()
    (root / "App.xcworkspace" / "contents.xcworkspacedata").write_text("<Workspace/>")
    (root / "Pods" / "Pods.xcodeproj").mkdir(parents=True)
    (root / "App" / "ContentView.swift").parent.mkdir()
    (root / "App" / "ContentView.swift").write_text("import SwiftUI // 日本語コメント\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("secret-ish")
    (root / "DerivedData").mkdir()
    (root / "DerivedData" / "big.o").write_text("x")
    return root


@pytest.fixture
def fake_mac(tmp_path, monkeypatch, project):
    mac_dir = tmp_path / "mac"
    monkeypatch.setattr(settings, "MAC_BRIDGE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(settings, "MAC_BRIDGE_PROJECT_ROOTS", [str(tmp_path / "projects")])
    monkeypatch.setenv("FAKE_MAC_DIR", str(mac_dir))
    monkeypatch.setenv("FAKE_MAC_LIST", LIST_JSON)
    monkeypatch.setenv("FAKE_MAC_BUILD_OUT", "CompileSwift normal arm64\\n** BUILD SUCCEEDED **")
    monkeypatch.setenv("FAKE_MAC_BUILD_RC", "0")
    monkeypatch.setenv("FAKE_MAC_SLEEP", "0")

    async def argv_for(host, remote_command):
        return [sys.executable, FAKE_MAC, remote_command]

    monkeypatch.setattr(mac_bridge, "ssh_argv_for", argv_for)

    def commands():
        p = mac_dir / "commands.log"
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    return mac_dir, commands


@pytest.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with Session() as s:
        s.add(MacHostModel(
            id=1, name="Mac", hostname="mac.local", username="u", key_path="k",
            host_key_fingerprint="SHA256:x", known_hosts_line="mac.local ssh-ed25519 AAAA",
            status="online", macos_version="14.5", xcode_version="15.4",
            probe={"simulators": [{"name": "iPhone 15", "udid": UDID, "runtime": "iOS 17.5", "state": "Shutdown"}]},
        ))
        await s.commit()

    async def override():
        async with Session() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[ep.get_session_factory] = lambda: Session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.Session = Session
        yield ac
    for t in list(mac_build._tasks.values()):
        t.cancel()
    await asyncio.sleep(0.1)
    app.dependency_overrides.clear()
    await engine.dispose()


async def wait_status(client, build_id, statuses, timeout=20):
    for _ in range(int(timeout / 0.1)):
        body = (await client.get(f"{API}/builds/{build_id}")).json()
        if body["status"] in statuses:
            return body
        await asyncio.sleep(0.1)
    raise AssertionError(f"status が {statuses} になりません: {body['status']}")


async def prepare(client, project):
    res = await client.post(f"{API}/builds", json={
        "host_id": 1, "source_path": str(project), "container": "App.xcworkspace"})
    assert res.status_code == 202, res.text
    return await wait_status(client, res.json()["id"], {"ready", "error"})


async def start(client, build_id, **kw):
    body = {"scheme": "App", "configuration": "Debug", "destination": UDID, **kw}
    return await client.post(f"{API}/builds/{build_id}/start", json=body)


# ─── プロジェクト検出 ───

def test_find_containers_prefers_workspace_and_skips_internal(project):
    found = mac_build.find_containers(project)
    paths = [c["path"] for c in found]
    assert paths[0] == "App.xcworkspace"
    assert "App.xcodeproj" in paths and "Pods/Pods.xcodeproj" in paths
    assert not any("project.xcworkspace" in p for p in paths)


async def test_inspect_rejects_outside_roots_and_traversal(client, fake_mac, project, tmp_path):
    ok = await client.post(f"{API}/projects/inspect", json={"source_path": str(project)})
    assert ok.status_code == 200 and ok.json()["containers"][0]["type"] == "workspace"
    outside = await client.post(f"{API}/projects/inspect", json={"source_path": str(tmp_path)})
    assert outside.status_code == 400
    traversal = await client.post(f"{API}/projects/inspect",
                                  json={"source_path": str(project / ".." / ".." / "..")})
    assert traversal.status_code == 400
    missing = await client.post(f"{API}/projects/inspect", json={"source_path": str(project / "nope")})
    assert missing.status_code == 400


def test_archive_excludes_vcs_and_build_outputs(project, tmp_path):
    import tarfile
    dest = tmp_path / "a.tar.gz"
    mac_build.create_archive(project, dest)
    names = tarfile.open(dest).getnames()
    assert "App/ContentView.swift" in names
    assert not any(n.startswith((".git", "DerivedData")) for n in names)
    assert all(not n.startswith("/") and ".." not in n.split("/") for n in names)


def test_archive_size_limit(project, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MAC_BRIDGE_MAX_UPLOAD_MB", 0)
    with pytest.raises(MacBridgeError, match="大きすぎ"):
        mac_build.create_archive(project, tmp_path / "a.tar.gz")


# ─── コマンド組み立て ───

def test_build_command_quotes_hostile_values():
    jid = "a" * 32
    cmd = mac_build.build_command(jid, "My App.xcworkspace", "workspace",
                                  'x"; rm -rf ~; echo "', "Debug", "generic/platform=iOS Simulator")
    tail = cmd.split("exec ", 1)[1]
    argv = shlex.split(tail)
    assert argv[argv.index("-scheme") + 1] == 'x"; rm -rf ~; echo "'
    assert argv[argv.index("-workspace") + 1] == "My App.xcworkspace"
    assert "CODE_SIGNING_ALLOWED=NO" in argv and argv[-1] == "build"


@pytest.mark.parametrize("bad", ["../etc", "A" * 32, "a" * 31, "a" * 32 + "; rm -rf ~"])
def test_workspace_dir_rejects_bad_ids(bad):
    with pytest.raises(MacBridgeError):
        mac_build.workspace_dir(bad)


def test_cleanup_only_targets_job_directory():
    assert mac_build.cleanup_command("b" * 32) == 'rm -rf "$HOME/DevMirrorWorkspaces/' + "b" * 32 + '"'


def test_parse_list_variants():
    assert mac_build.parse_list(LIST_JSON) == (["App", "AppTests"], ["Debug", "Release"])
    proj = 'warning: noise\n{"project": {"schemes": ["A"], "configurations": ["Debug", "Staging"]}}'
    assert mac_build.parse_list(proj) == (["A"], ["Debug", "Staging"])
    with pytest.raises(MacBridgeError):
        mac_build.parse_list("xcodebuild: error: no project")


def test_read_log_does_not_split_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MAC_BRIDGE_DATA_DIR", str(tmp_path))
    jid = "c" * 32
    mac_build.append_log(jid, "ビルド")
    text, off = mac_build.read_log(jid, 0, limit=4)  # 「ビ」は 3 バイト
    assert text == "ビ" and off == 3
    rest, off2 = mac_build.read_log(jid, off)
    assert rest == "ルド\n"


# ─── API フロー ───

async def test_full_build_flow(client, fake_mac, project):
    mac_dir, commands = fake_mac
    job = await prepare(client, project)
    assert job["status"] == "ready", job
    assert job["schemes"] == ["App", "AppTests"]
    assert {d["id"] for d in job["destinations"]} == {"generic", UDID}
    # 転送された内容（.git / DerivedData は送らない）
    assert (mac_dir / "src" / "App" / "ContentView.swift").read_text(encoding="utf-8").startswith("import SwiftUI")
    assert not (mac_dir / "src" / ".git").exists()

    assert (await start(client, job["id"])).status_code == 202
    done = await wait_status(client, job["id"], {"succeeded", "failed", "error"})
    assert done["status"] == "succeeded" and done["exit_code"] == 0
    assert done["duration_sec"] is not None
    assert done["destination"] == f"platform=iOS Simulator,id={UDID}"

    log = (await client.get(f"{API}/builds/{job['id']}/log")).json()
    assert "** BUILD SUCCEEDED **" in log["text"]
    later = (await client.get(f"{API}/builds/{job['id']}/log", params={"offset": log["offset"]})).json()
    assert later["text"] == ""

    build_cmd = [c for c in commands() if "exec xcodebuild" in c][0]
    assert f'DevMirrorWorkspaces/{job["id"]}' in build_cmd
    history = (await client.get(f"{API}/builds")).json()
    assert history[0]["id"] == job["id"]


async def test_build_failure_collects_errors(client, fake_mac, project, monkeypatch):
    monkeypatch.setenv("FAKE_MAC_BUILD_OUT",
                       "/src/App/ContentView.swift:3:5: error: cannot find 'Foo' in scope\\n"
                       "/src/App/A.swift:1:1: warning: unused\\n** BUILD FAILED **")
    monkeypatch.setenv("FAKE_MAC_BUILD_RC", "65")
    job = await prepare(client, project)
    await start(client, job["id"])
    done = await wait_status(client, job["id"], {"succeeded", "failed", "error"})
    assert done["status"] == "failed" and done["exit_code"] == 65
    assert "cannot find 'Foo'" in done["errors"][0]
    assert done["warning_count"] == 1


async def test_ssh_disconnect_is_not_reported_as_build_failure(client, fake_mac, project, monkeypatch):
    monkeypatch.setenv("FAKE_MAC_BUILD_RC", "255")
    job = await prepare(client, project)
    await start(client, job["id"])
    done = await wait_status(client, job["id"], {"succeeded", "failed", "error"})
    assert done["status"] == "error" and "切断" in done["error_message"]


async def test_invalid_parameters_rejected(client, fake_mac, project):
    job = await prepare(client, project)
    assert (await start(client, job["id"], scheme="Evil; rm -rf ~")).status_code == 400
    assert (await start(client, job["id"], configuration="Hacked")).status_code == 400
    assert (await start(client, job["id"], destination="00000000-0000-0000-0000-000000000000")).status_code == 400
    assert (await client.get(f"{API}/builds/{job['id']}")).json()["status"] == "ready"


async def test_prepare_rejects_container_not_in_folder(client, fake_mac, project):
    res = await client.post(f"{API}/builds", json={
        "host_id": 1, "source_path": str(project), "container": "../other/X.xcodeproj"})
    assert res.status_code == 400


async def test_prepare_error_when_no_schemes(client, fake_mac, project, monkeypatch):
    monkeypatch.setenv("FAKE_MAC_LIST", json.dumps({"project": {"schemes": []}}))
    job = await prepare(client, project)
    assert job["status"] == "error" and "scheme" in job["error_message"]


async def test_cancel_stops_build_and_remote_process(client, fake_mac, project, monkeypatch):
    _, commands = fake_mac
    monkeypatch.setenv("FAKE_MAC_SLEEP", "30")
    job = await prepare(client, project)
    await start(client, job["id"])
    await asyncio.sleep(1.0)
    res = await client.post(f"{API}/builds/{job['id']}/cancel")
    assert res.status_code == 200
    done = await wait_status(client, job["id"], {"cancelled"}, timeout=10)
    assert done["duration_sec"] < 30
    assert any("kill -TERM" in c and job["id"] in c for c in commands())


async def test_timeout(client, fake_mac, project, monkeypatch):
    _, commands = fake_mac
    monkeypatch.setenv("FAKE_MAC_SLEEP", "30")
    monkeypatch.setattr(settings, "MAC_BRIDGE_BUILD_TIMEOUT", 1)
    job = await prepare(client, project)
    await start(client, job["id"])
    done = await wait_status(client, job["id"], {"timeout"}, timeout=15)
    assert "タイムアウト" in done["error_message"]
    assert any("kill -TERM" in c for c in commands())


async def test_one_active_job_per_host(client, fake_mac, project, monkeypatch):
    monkeypatch.setenv("FAKE_MAC_SLEEP", "30")
    job = await prepare(client, project)
    await start(client, job["id"])
    res = await client.post(f"{API}/builds", json={
        "host_id": 1, "source_path": str(project), "container": "App.xcworkspace"})
    assert res.status_code == 409
    await client.post(f"{API}/builds/{job['id']}/cancel")
    await wait_status(client, job["id"], {"cancelled"})


async def test_jobs_use_separate_workspaces(client, fake_mac, project):
    _, commands = fake_mac
    a = await prepare(client, project)
    b = await prepare(client, project)
    assert a["id"] != b["id"]
    uploads = [c for c in commands() if "tar -xzf" in c]
    assert a["id"] in uploads[0] and b["id"] in uploads[1]


async def test_cleanup(client, fake_mac, project):
    _, commands = fake_mac
    job = await prepare(client, project)
    res = await client.post(f"{API}/builds/{job['id']}/cleanup")
    assert res.status_code == 200 and res.json()["workspace_cleaned"]
    assert commands()[-1] == mac_build.cleanup_command(job["id"])
    assert (await start(client, job["id"])).status_code == 409


async def test_orphaned_running_job_marked_interrupted(client, fake_mac):
    async with client.Session() as s:
        s.add(MacBuildModel(id="d" * 32, host_id=1, host_name="Mac", source_path="x",
                            container="A.xcodeproj", container_type="project", status="running"))
        await s.commit()
    body = (await client.get(f"{API}/builds/{'d' * 32}")).json()
    assert body["status"] == "interrupted"


async def test_bad_build_id_is_404(client, fake_mac):
    assert (await client.get(f"{API}/builds/..%2F..%2Fetc")).status_code == 404
    assert (await client.get(f"{API}/builds/{'e' * 32}")).status_code == 404
