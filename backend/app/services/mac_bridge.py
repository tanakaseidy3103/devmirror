"""
DevMirror - Mac Bridge Connection Manager（Mac接続管理）

Windows 上の DevMirror から、ユーザーが許可した実機 Mac に SSH で接続し、
macOS / Xcode / シミュレータ / 空き容量を調べる。

Mac は VM ではないため VMProvider は使わない（起動・停止・スナップショットの
概念が無い）。リモートビルドホストとして独立して扱う。

セキュリティ方針:
- 秘密鍵・パスワードは保存しない。鍵ファイルのパスだけを ssh に渡す。
- ホスト鍵は「ユーザーが Mac 上で確認したフィンガープリント」と一致した場合だけ
  登録する（TOFU 禁止）。以降は StrictHostKeyChecking=yes で検証する。
- リモートで実行するのは本モジュールに固定された PROBE_SCRIPT のみ。
  フロントエンドや LLM からのコマンド文字列は一切受け付けない。
- シェルを経由せず argv で ssh を起動する（ローカル側のコマンドインジェクション防止）。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import re
import shlex
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,252})$")
USERNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,31}$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")

# リモートで実行する唯一のスクリプト（読み取り専用の調査コマンドのみ）
PROBE_SCRIPT = "; ".join([
    "echo @@macos", "sw_vers -productVersion 2>&1",
    "echo @@arch", "uname -m",
    "echo @@xcode", "xcodebuild -version 2>&1",
    "echo @@devdir", "xcode-select -p 2>&1",
    "echo @@sims", "xcrun simctl list devices available -j 2>/dev/null",
    "echo @@disk", 'df -k "$HOME" | tail -1',
    "echo @@tools",
    "for t in git swift xcodebuild xcrun pod; do command -v $t >/dev/null 2>&1 && echo $t; done",
    "echo @@end",
])


class MacBridgeError(Exception):
    """Mac Bridge の利用者向けエラー（メッセージは日本語）"""


class HostKeyMismatchError(MacBridgeError):
    pass


@dataclass
class ProbeResult:
    status: str  # online / offline / auth_failed / host_key_mismatch / error
    message: str = ""
    macos_version: Optional[str] = None
    arch: Optional[str] = None
    xcode_version: Optional[str] = None
    xcode_build: Optional[str] = None
    developer_dir: Optional[str] = None
    simulators: list[dict[str, Any]] = field(default_factory=list)
    disk_free_gb: Optional[float] = None
    tools: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ─────────────────────────────────────────────
# 入力検証
# ─────────────────────────────────────────────

def validate_hostname(hostname: str) -> str:
    # 先頭 "-" を禁止して ssh のオプションとして解釈されるのを防ぐ
    if not HOSTNAME_RE.match(hostname or ""):
        raise MacBridgeError("ホスト名または IP アドレスの形式が正しくありません")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname  # DNS 名は接続のたびに resolve_private_address で検査する
    _reject_public(ip)
    return hostname


def _reject_public(ip: ipaddress._BaseAddress) -> None:
    if ip.is_global and not settings.MAC_BRIDGE_ALLOW_PUBLIC_HOSTS:
        raise MacBridgeError(
            "グローバル IP の Mac は登録できません。LAN または VPN（Tailscale 等）経由で接続してください"
        )


async def resolve_private_address(hostname: str) -> str:
    """
    ホスト名を解決し、全アドレスが LAN / VPN 内であることを確認して接続先 IP を返す。
    ssh にはこの IP を渡す（検査後に DNS が変わっても公開ホストへ接続しない）。
    """
    validate_hostname(hostname)
    try:
        return str(ipaddress.ip_address(hostname))
    except ValueError:
        pass
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        raise MacBridgeError("ホスト名を解決できません（Mac の電源・ネットワークを確認してください）")
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise MacBridgeError("ホスト名を解決できません")
    for a in addresses:
        _reject_public(ipaddress.ip_address(a.split("%")[0]))
    return addresses[0]


def validate_username(username: str) -> str:
    if not USERNAME_RE.match(username or ""):
        raise MacBridgeError("SSH ユーザー名の形式が正しくありません")
    return username


def validate_fingerprint(fp: str) -> str:
    fp = (fp or "").strip()
    if not FINGERPRINT_RE.match(fp):
        raise MacBridgeError(
            "ホスト鍵のフィンガープリントは SHA256:... 形式で入力してください"
            "（Mac で ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub を実行）"
        )
    return fp


def validate_key_path(key_path: str) -> str:
    p = Path(key_path or "").expanduser()
    if not p.is_file():
        raise MacBridgeError("SSH 秘密鍵ファイルが見つかりません")
    return str(p)


def fingerprint_of(key_b64: str) -> str:
    """公開鍵（base64）から OpenSSH 形式の SHA256 フィンガープリントを計算する。"""
    digest = hashlib.sha256(base64.b64decode(key_b64)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


# ─────────────────────────────────────────────
# プロセス実行
# ─────────────────────────────────────────────

async def run_process(argv: list[str], timeout: float, stdin_path: Optional[Path] = None) -> tuple[int, str, str]:
    """argv を直接起動する（シェル不使用）。タイムアウト・キャンセル時は強制終了する。"""
    stdin = open(stdin_path, "rb") if stdin_path else asyncio.subprocess.DEVNULL
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    finally:
        if stdin_path:
            stdin.close()
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        raise MacBridgeError(f"Mac からの応答がタイムアウトしました（{timeout:.0f} 秒）")
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    limit = settings.MAX_LOG_SIZE_BYTES
    return (
        proc.returncode,
        out[:limit].decode("utf-8", "replace"),
        err[:limit].decode("utf-8", "replace"),
    )


def data_dir() -> Path:
    d = Path(settings.MAC_BRIDGE_DATA_DIR or Path.home() / ".devmirror" / "mac-bridge")
    d.mkdir(parents=True, exist_ok=True)
    return d


# ─────────────────────────────────────────────
# ホスト鍵の確認（登録時）
# ─────────────────────────────────────────────

async def verify_host_key(hostname: str, port: int, expected_fp: str) -> str:
    """
    ssh-keyscan で取得した鍵のうち、ユーザーが入力したフィンガープリントと
    一致するものを known_hosts 行として返す。一致しなければ拒否する。
    """
    timeout = settings.MAC_BRIDGE_CONNECT_TIMEOUT
    address = await resolve_private_address(hostname)
    rc, out, err = await run_process(
        [settings.MAC_BRIDGE_SSH_KEYSCAN_BINARY, "-T", str(timeout), "-p", str(port), address],
        timeout + 5,
    )
    keys = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and not line.startswith("#"):
            keys.append((parts[1], parts[2]))
    if not keys:
        raise MacBridgeError("Mac に接続できません（ホスト名・ポート・リモートログイン設定を確認してください）")

    for key_type, key_b64 in keys:
        try:
            if fingerprint_of(key_b64) == expected_fp:
                # ssh 側は HostKeyAlias=<hostname> で照合するため、ポートを付けずに記録する
                return f"{hostname} {key_type} {key_b64}"
        except ValueError:
            continue
    logger.warning("ホスト鍵が一致しません", hostname=hostname, port=port)
    raise HostKeyMismatchError(
        "ホスト鍵のフィンガープリントが一致しません。接続先が正しい Mac か確認してください"
    )


# ─────────────────────────────────────────────
# 接続テスト・環境調査
# ─────────────────────────────────────────────

def build_ssh_argv(host, known_hosts_file: Path, remote_command: str, address: str) -> list[str]:
    return [
        settings.MAC_BRIDGE_SSH_BINARY,
        "-F", "none",  # ユーザーの ~/.ssh/config（ProxyCommand 等）を読まない
        "-T",
        "-p", str(host.port),
        "-i", host.key_path,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts_file}",
        "-o", "GlobalKnownHostsFile=none",
        # 接続先は検査済みの IP。ホスト鍵は登録時のホスト名で照合する
        "-o", f"HostKeyAlias={host.hostname}",
        "-o", "CheckHostIP=no",
        "-o", "IdentitiesOnly=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", f"ConnectTimeout={settings.MAC_BRIDGE_CONNECT_TIMEOUT}",
        "--",
        f"{host.username}@{address}",
        remote_command,
    ]


def classify_ssh_failure(stderr: str) -> ProbeResult:
    if "IDENTIFICATION HAS CHANGED" in stderr or "Host key verification failed" in stderr:
        return ProbeResult("host_key_mismatch", "ホスト鍵が登録時と異なります。接続を中止しました")
    if "Permission denied" in stderr:
        return ProbeResult("auth_failed", "SSH 鍵認証に失敗しました（authorized_keys を確認してください）")
    return ProbeResult("offline", "Mac に接続できません（電源・ネットワーク・リモートログインを確認してください）")


def _sections(stdout: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("@@"):
            current = line[2:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _runtime_label(runtime_id: str) -> str:
    # com.apple.CoreSimulator.SimRuntime.iOS-17-5 -> iOS 17.5
    name = runtime_id.rsplit(".", 1)[-1]
    platform, _, version = name.partition("-")
    return f"{platform} {version.replace('-', '.')}".strip()


def parse_probe(stdout: str) -> ProbeResult:
    s = _sections(stdout)
    if "end" not in s:
        return ProbeResult("error", "Mac の調査結果が途中で切れました")
    r = ProbeResult("online", "接続に成功しました")
    r.macos_version = s.get("macos") or None
    r.arch = s.get("arch") or None

    for line in s.get("xcode", "").splitlines():
        if line.startswith("Xcode "):
            r.xcode_version = line.split(" ", 1)[1].strip()
        elif line.startswith("Build version "):
            r.xcode_build = line.rsplit(" ", 1)[1].strip()
    devdir = s.get("devdir", "")
    r.developer_dir = devdir if devdir.startswith("/") else None

    try:
        devices = json.loads(s.get("sims") or "{}").get("devices", {})
    except json.JSONDecodeError:
        devices = {}
    for runtime_id, items in devices.items():
        for d in items:
            r.simulators.append({
                "name": d.get("name"),
                "udid": d.get("udid"),
                "state": d.get("state"),
                "runtime": _runtime_label(runtime_id),
            })

    disk = s.get("disk", "").split()
    if len(disk) >= 4 and disk[3].isdigit():
        r.disk_free_gb = round(int(disk[3]) / 1024 / 1024, 1)
    r.tools = [t for t in s.get("tools", "").split() if t]

    if not r.xcode_version:
        r.issues.append("Xcode がインストールされていないか、xcode-select が Command Line Tools を指しています")
    if not r.simulators:
        r.issues.append("利用可能な iOS シミュレータがありません")
    if r.disk_free_gb is not None and r.disk_free_gb < settings.MAC_BRIDGE_MIN_FREE_GB:
        r.issues.append(f"空き容量が不足しています（{r.disk_free_gb} GB / 推奨 {settings.MAC_BRIDGE_MIN_FREE_GB} GB 以上）")
    return r


_host_locks: dict[int, asyncio.Lock] = {}


def host_lock(host_id: int) -> asyncio.Lock:
    return _host_locks.setdefault(host_id, asyncio.Lock())


async def ssh_argv_for(host, remote_command: str) -> list[str]:
    """
    登録済み Mac 向けの ssh argv を作る。remote_command はこのパッケージ内で
    組み立てた固定コマンド（値は検証済み・shlex.quote 済み）に限る。
    """
    validate_username(host.username)
    address = await resolve_private_address(host.hostname)
    known_hosts = data_dir() / f"known_hosts_{host.id}"
    # DB をピン留めの正とし、毎回書き出す（ファイルの改ざん・取り違えを防ぐ）
    known_hosts.write_text(host.known_hosts_line + "\n", encoding="utf-8")
    return build_ssh_argv(host, known_hosts, remote_command, address)


def quote_all(argv: list[str]) -> str:
    """リモートシェルへ渡す引数を 1 つずつクォートして連結する。"""
    return " ".join(shlex.quote(a) for a in argv)


async def probe_host(host) -> ProbeResult:
    """登録済み Mac に接続し、固定の調査スクリプトだけを実行する。"""
    try:
        argv = await ssh_argv_for(host, PROBE_SCRIPT)
    except MacBridgeError as e:
        return ProbeResult("offline", str(e))
    try:
        rc, out, err = await run_process(argv, settings.MAC_BRIDGE_COMMAND_TIMEOUT)
    except MacBridgeError as e:
        return ProbeResult("offline", str(e))
    except FileNotFoundError:
        return ProbeResult("error", "ssh クライアントが見つかりません（Windows の OpenSSH クライアントを有効にしてください）")

    if rc == 255:
        result = classify_ssh_failure(err)
    else:
        result = parse_probe(out)
    logger.info("Mac 接続テスト", host_id=host.id, status=result.status, rc=rc)
    return result
