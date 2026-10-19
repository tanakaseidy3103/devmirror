"""
Mac Bridge（Mac接続管理）のテスト

実機 Mac が無くても動くよう、run_process（ssh / ssh-keyscan の起動）だけを差し替える。
実機での確認は docs/mac-bridge/TEST_PLAN.md の手順で行う。
"""
import json
import shutil
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.services import mac_bridge
from app.services.mac_bridge import HostKeyMismatchError, MacBridgeError

KEY_B64 = "AAAAC3NzaC1lZDI1NTE5AAAAIBn0Qp3ZtYbVxP0p7wq3c8m9Yb1n2lJ0kQx7a5c6d7e8"
KEY_FP = mac_bridge.fingerprint_of(KEY_B64)
OTHER_FP = "SHA256:" + "A" * 43

SIMS = {"devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
        {"name": "iPhone 15", "udid": "U1", "state": "Shutdown", "isAvailable": True},
    ],
}}
PROBE_OK = "\n".join([
    "@@macos", "14.5", "@@arch", "arm64",
    "@@xcode", "Xcode 15.4", "Build version 15F31d",
    "@@devdir", "/Applications/Xcode.app/Contents/Developer",
    "@@sims", json.dumps(SIMS),
    "@@disk", "/dev/disk3s5 488245288 300000000 104857600 75% /System/Volumes/Data",
    "@@tools", "git", "swift", "xcodebuild", "xcrun",
    "@@end",
])
PROBE_NO_XCODE = "\n".join([
    "@@macos", "14.5", "@@arch", "arm64",
    "@@xcode", "xcode-select: error: tool 'xcodebuild' requires Xcode",
    "@@devdir", "/Library/Developer/CommandLineTools",
    "@@sims", "@@disk", "/dev/disk3s5 1 1 1048576 1% /", "@@tools", "git", "@@end",
])


@pytest.fixture
def fake_proc(monkeypatch, tmp_path):
    """run_process を差し替え、呼ばれた argv を記録する。"""
    monkeypatch.setattr(settings, "MAC_BRIDGE_DATA_DIR", str(tmp_path / "mb"))
    calls = []
    responses = {"keyscan": (0, f"mac.local ssh-ed25519 {KEY_B64}\n", ""), "ssh": (0, PROBE_OK, "")}

    async def fake(argv, timeout):
        calls.append(argv)
        r = responses["keyscan" if "keyscan" in argv[0] else "ssh"]
        if isinstance(r, Exception):
            raise r
        return r

    async def resolve(hostname):
        mac_bridge.validate_hostname(hostname)
        return "192.168.1.20"

    monkeypatch.setattr(mac_bridge, "run_process", fake)
    monkeypatch.setattr(mac_bridge, "resolve_private_address", resolve)
    return calls, responses


@pytest.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override():
        async with Session() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def key_file(tmp_path):
    p = tmp_path / "id_ed25519"
    p.write_text("dummy")
    return str(p)


def payload(key_file, **kw):
    return {"name": "My Mac", "hostname": "mac.local", "username": "eduardo",
            "key_path": key_file, "host_key_fingerprint": KEY_FP, **kw}


# ─── 入力検証 ───

@pytest.mark.parametrize("bad", ["-oProxyCommand=calc", "mac;rm", "a b", "", "$(id)"])
def test_hostname_rejects_option_and_shell_injection(bad):
    with pytest.raises(MacBridgeError):
        mac_bridge.validate_hostname(bad)


def test_hostname_rejects_public_ip_but_allows_lan_and_tailscale():
    with pytest.raises(MacBridgeError):
        mac_bridge.validate_hostname("8.8.8.8")
    assert mac_bridge.validate_hostname("192.168.1.20")
    assert mac_bridge.validate_hostname("100.101.102.103")  # Tailscale CGNAT


@pytest.mark.parametrize("bad", ["-l", "root;x", "a b", ""])
def test_username_validation(bad):
    with pytest.raises(MacBridgeError):
        mac_bridge.validate_username(bad)


def test_fingerprint_validation():
    with pytest.raises(MacBridgeError):
        mac_bridge.validate_fingerprint("MD5:aa:bb")
    assert mac_bridge.validate_fingerprint(f"  {KEY_FP} ") == KEY_FP


@pytest.mark.skipif(not shutil.which("ssh-keygen"), reason="ssh-keygen が無い")
def test_fingerprint_matches_openssh(tmp_path):
    key = tmp_path / "k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    pub = (tmp_path / "k.pub").read_text().split()[1]
    expected = subprocess.run(["ssh-keygen", "-lf", str(tmp_path / "k.pub")],
                              capture_output=True, text=True, check=True).stdout.split()[1]
    assert mac_bridge.fingerprint_of(pub) == expected


# ─── ホスト鍵 ───

async def test_verify_host_key_accepts_matching(fake_proc):
    line = await mac_bridge.verify_host_key("mac.local", 22, KEY_FP)
    assert line == f"mac.local ssh-ed25519 {KEY_B64}"


async def test_verify_host_key_nonstandard_port(fake_proc):
    # ssh は HostKeyAlias=<hostname> で照合するため、ポートは付けない
    line = await mac_bridge.verify_host_key("mac.local", 2222, KEY_FP)
    assert line.startswith("mac.local ssh-ed25519 ")
    assert fake_proc[0][-1][-1] == "192.168.1.20"  # keyscan は検査済み IP へ


async def test_verify_host_key_rejects_unknown(fake_proc):
    with pytest.raises(HostKeyMismatchError):
        await mac_bridge.verify_host_key("mac.local", 22, OTHER_FP)


async def test_verify_host_key_unreachable(fake_proc):
    fake_proc[1]["keyscan"] = (1, "", "")
    with pytest.raises(MacBridgeError):
        await mac_bridge.verify_host_key("mac.local", 22, KEY_FP)


# ─── 調査結果の解析 ───

def test_parse_probe_ok():
    r = mac_bridge.parse_probe(PROBE_OK)
    assert r.status == "online"
    assert (r.macos_version, r.xcode_version, r.xcode_build) == ("14.5", "15.4", "15F31d")
    assert r.simulators[0]["runtime"] == "iOS 17.5"
    assert r.disk_free_gb == 100.0
    assert r.issues == []


def test_parse_probe_without_xcode():
    r = mac_bridge.parse_probe(PROBE_NO_XCODE)
    assert r.xcode_version is None and r.developer_dir == "/Library/Developer/CommandLineTools"
    assert any("Xcode" in i for i in r.issues)
    assert any("シミュレータ" in i for i in r.issues)
    assert any("空き容量" in i for i in r.issues)


def test_parse_probe_truncated_is_error():
    assert mac_bridge.parse_probe("@@macos\n14.5\n").status == "error"


@pytest.mark.parametrize("stderr,status", [
    ("@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@", "host_key_mismatch"),
    ("Host key verification failed.", "host_key_mismatch"),
    ("eduardo@mac.local: Permission denied (publickey).", "auth_failed"),
    ("ssh: connect to host mac.local port 22: Connection timed out", "offline"),
    ("Connection closed by 192.168.1.20 port 22", "offline"),
])
def test_classify_ssh_failure(stderr, status):
    assert mac_bridge.classify_ssh_failure(stderr).status == status


# ─── プロセス実行（実プロセス） ───

async def test_run_process_timeout_kills():
    with pytest.raises(MacBridgeError, match="タイムアウト"):
        await mac_bridge.run_process([sys.executable, "-c", "import time; time.sleep(30)"], 0.5)


async def test_run_process_captures_output():
    rc, out, err = await mac_bridge.run_process(
        [sys.executable, "-c", "import sys; print('o'); print('e', file=sys.stderr); sys.exit(3)"], 10)
    assert (rc, out.strip(), err.strip()) == (3, "o", "e")


# ─── API ───

async def test_register_and_test_connection(client, fake_proc, key_file):
    calls, _ = fake_proc
    res = await client.post("/api/v1/mac-bridge/hosts", json=payload(key_file))
    assert res.status_code == 201, res.text
    host = res.json()
    assert host["status"] == "unknown"
    assert "known_hosts_line" not in host and "key_path" not in host

    res = await client.post(f"/api/v1/mac-bridge/hosts/{host['id']}/test")
    body = res.json()
    assert body["status"] == "online"
    assert body["macos_version"] == "14.5" and body["xcode_version"] == "15.4"
    assert body["last_connected_at"]

    argv = calls[-1]
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=no" not in " ".join(argv)
    assert argv[-1] == mac_bridge.PROBE_SCRIPT  # 固定スクリプトのみ
    assert argv[-2] == "eduardo@192.168.1.20" and argv[-3] == "--"  # 検査済み IP へ接続
    assert "HostKeyAlias=mac.local" in argv


async def test_register_rejects_wrong_fingerprint(client, fake_proc, key_file):
    res = await client.post("/api/v1/mac-bridge/hosts",
                            json=payload(key_file, host_key_fingerprint=OTHER_FP))
    assert res.status_code == 409
    assert (await client.get("/api/v1/mac-bridge/hosts")).json() == []


async def test_register_validation_errors(client, fake_proc, key_file):
    assert (await client.post("/api/v1/mac-bridge/hosts",
                              json=payload(key_file, hostname="-oProxyCommand=x"))).status_code == 400
    assert (await client.post("/api/v1/mac-bridge/hosts",
                              json=payload("C:/no/such/key"))).status_code == 400
    assert fake_proc[0] == []  # 検証失敗時は ssh を起動しない


async def test_changed_host_key_marks_mismatch_and_keeps_last_good(client, fake_proc, key_file):
    _, responses = fake_proc
    host = (await client.post("/api/v1/mac-bridge/hosts", json=payload(key_file))).json()
    await client.post(f"/api/v1/mac-bridge/hosts/{host['id']}/test")

    responses["ssh"] = (255, "", "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!")
    body = (await client.post(f"/api/v1/mac-bridge/hosts/{host['id']}/test")).json()
    assert body["status"] == "host_key_mismatch"
    assert body["last_error"]
    assert body["xcode_version"] == "15.4"  # 最後に成功した情報は残す


async def test_offline_and_timeout(client, fake_proc, key_file):
    _, responses = fake_proc
    host = (await client.post("/api/v1/mac-bridge/hosts", json=payload(key_file))).json()
    responses["ssh"] = MacBridgeError("Mac からの応答がタイムアウトしました（60 秒）")
    body = (await client.post(f"/api/v1/mac-bridge/hosts/{host['id']}/test")).json()
    assert body["status"] == "offline" and "タイムアウト" in body["last_error"]
    assert body["last_connected_at"] is None


async def test_disconnect_and_delete(client, fake_proc, key_file):
    host = (await client.post("/api/v1/mac-bridge/hosts", json=payload(key_file))).json()
    body = (await client.post(f"/api/v1/mac-bridge/hosts/{host['id']}/disconnect")).json()
    assert body["status"] == "disconnected" and body["enabled"] is False
    assert (await client.delete(f"/api/v1/mac-bridge/hosts/{host['id']}")).status_code == 204
    assert (await client.post(f"/api/v1/mac-bridge/hosts/{host['id']}/test")).status_code == 404


async def test_duplicate_name_rejected(client, fake_proc, key_file):
    assert (await client.post("/api/v1/mac-bridge/hosts", json=payload(key_file))).status_code == 201
    assert (await client.post("/api/v1/mac-bridge/hosts", json=payload(key_file))).status_code == 409


# ─── DNS 解決後の公開 IP 拒否 ───

def _fake_dns(monkeypatch, *addresses):
    import socket

    def getaddrinfo(host, *a, **kw):
        if not addresses:
            raise socket.gaierror("not found")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in addresses]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


async def test_dns_name_resolving_to_public_ip_is_rejected(monkeypatch):
    _fake_dns(monkeypatch, "93.184.216.34")
    with pytest.raises(MacBridgeError, match="グローバル IP"):
        await mac_bridge.resolve_private_address("evil.example.com")


async def test_dns_name_with_any_public_address_is_rejected(monkeypatch):
    _fake_dns(monkeypatch, "192.168.1.20", "93.184.216.34")
    with pytest.raises(MacBridgeError):
        await mac_bridge.resolve_private_address("mixed.example.com")


async def test_dns_name_resolving_to_lan_returns_ip(monkeypatch):
    _fake_dns(monkeypatch, "192.168.1.20")
    assert await mac_bridge.resolve_private_address("my-mac.local") == "192.168.1.20"


async def test_dns_unresolvable(monkeypatch):
    _fake_dns(monkeypatch)
    with pytest.raises(MacBridgeError, match="解決できません"):
        await mac_bridge.resolve_private_address("nowhere.local")


async def test_api_rejects_non_local_client(tmp_path):
    transport = ASGITransport(app=app, client=("192.168.1.50", 5555))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        assert (await ac.get("/api/v1/mac-bridge/hosts")).status_code == 403
