"""
DevMirror - Xcode Remote Build Engine（Xcodeリモートビルドエンジン）

流れ:
  1. Windows 側のフォルダから .xcodeproj / .xcworkspace を検出する
  2. 準備: フォルダを tar.gz にして Mac の ~/DevMirrorWorkspaces/<job_id>/src へ転送し、
     xcodebuild -list -json で scheme / configuration を取得する
  3. ビルド: 検証済みの値だけで xcodebuild の argv を組み立て、ログを逐次ファイルへ書く
  4. キャンセル / クリーンアップ

リモートで実行するコマンドはすべてこのモジュールで組み立てる。
フロントエンドからは「候補の中から選んだ値」だけを受け取り、候補と照合してから使う。
作業ディレクトリ名は サーバが生成した uuid4 hex のみ（パストラバーサル不可）。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tarfile
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

from app.core.config import settings
from app.services import mac_bridge
from app.services.mac_bridge import MacBridgeError

logger = structlog.get_logger(__name__)

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
UDID_RE = re.compile(r"^[0-9A-Fa-f-]{36}$")
CONTAINER_SUFFIXES = {".xcodeproj": "project", ".xcworkspace": "workspace"}
# 転送しないディレクトリ（ビルド生成物・VCS・個人設定）
SKIP_DIRS = {".git", "DerivedData", "build", ".build", "node_modules", "xcuserdata"}
MAX_CONTAINER_DEPTH = 4
GENERIC_DESTINATION = "generic"
ACTIVE_STATUSES = {"preparing", "running"}
ERROR_LINE_RE = re.compile(r"(^|\s)(error|fatal error):\s", re.IGNORECASE)
WARNING_LINE_RE = re.compile(r"(^|\s)warning:\s", re.IGNORECASE)

# 実行中ジョブ（プロセス再起動で消える。DB 上に残った実行中ジョブは interrupted 扱い）
_tasks: dict[str, asyncio.Task] = {}


# ─────────────────────────────────────────────
# Windows 側: プロジェクト選択
# ─────────────────────────────────────────────

def project_roots() -> list[Path]:
    roots = settings.MAC_BRIDGE_PROJECT_ROOTS or [str(Path.home())]
    return [Path(r).expanduser().resolve() for r in roots]


def resolve_source(path: str) -> Path:
    """許可フォルダ配下の実在ディレクトリであることを確認する（シンボリックリンクも解決）。"""
    try:
        p = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise MacBridgeError("フォルダが見つかりません")
    if not p.is_dir():
        raise MacBridgeError("フォルダを指定してください")
    if not any(p == r or p.is_relative_to(r) for r in project_roots()):
        raise MacBridgeError("許可されていない場所です（MAC_BRIDGE_PROJECT_ROOTS を確認してください）")
    return p


def find_containers(root: Path) -> list[dict[str, str]]:
    """root 配下の .xcodeproj / .xcworkspace を探す（.xcodeproj 内部の workspace は除外）。"""
    found = []
    for dirpath, dirnames, _ in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        keep = []
        for d in sorted(dirnames):
            suffix = Path(d).suffix
            if suffix in CONTAINER_SUFFIXES:
                found.append({"path": (rel / d).as_posix(), "type": CONTAINER_SUFFIXES[suffix]})
            elif d not in SKIP_DIRS and not d.startswith(".") and len(rel.parts) < MAX_CONTAINER_DEPTH:
                keep.append(d)
        dirnames[:] = keep
    # workspace を優先（CocoaPods 等では workspace でないとビルドできない）
    return sorted(found, key=lambda c: (c["type"] != "workspace", c["path"]))[:50]


def create_archive(src: Path, dest: Path) -> int:
    """src を tar.gz にする。シンボリックリンクと SKIP_DIRS は含めない。返り値は元サイズ合計。"""
    limit = settings.MAC_BRIDGE_MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    with tarfile.open(dest, "w:gz") as tar:
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d)))
            for name in sorted(filenames):
                full = Path(dirpath) / name
                if full.is_symlink() or not full.is_file():
                    continue
                total += full.stat().st_size
                if total > limit:
                    raise MacBridgeError(f"プロジェクトが大きすぎます（上限 {settings.MAC_BRIDGE_MAX_UPLOAD_MB} MB）")
                tar.add(full, arcname=full.relative_to(src).as_posix(), recursive=False)
    return total


# ─────────────────────────────────────────────
# リモートコマンド（固定テンプレート）
# ─────────────────────────────────────────────

def workspace_dir(job_id: str) -> str:
    if not JOB_ID_RE.match(job_id):
        raise MacBridgeError("不正なジョブ ID です")
    # job_id は hex のみなのでダブルクォート内に置いても安全（$HOME だけ展開させる）
    return f'"$HOME/DevMirrorWorkspaces/{job_id}"'


def upload_command(job_id: str) -> str:
    ws = workspace_dir(job_id)
    # macOS の bsdtar は絶対パス・".." を含むエントリを既定で展開しない
    return f"rm -rf {ws} && mkdir -p {ws}/src && tar -xzf - -C {ws}/src"


def list_command(job_id: str, container: str, container_type: str) -> str:
    flag = "-workspace" if container_type == "workspace" else "-project"
    return f"cd {workspace_dir(job_id)}/src && " + mac_bridge.quote_all(["xcodebuild", "-list", "-json", flag, container])


def build_command(job_id: str, container: str, container_type: str, scheme: str,
                  configuration: str, destination: str) -> str:
    flag = "-workspace" if container_type == "workspace" else "-project"
    argv = [
        "xcodebuild", flag, container,
        "-scheme", scheme,
        "-configuration", configuration,
        "-destination", destination,
        "-derivedDataPath", "../DerivedData",
        # MVP はシミュレータ向けのみ。署名・証明書は扱わない
        "CODE_SIGNING_ALLOWED=NO",
        "build",
    ]
    ws = workspace_dir(job_id)
    # $$ は exec 後の xcodebuild の PID になる（キャンセル用）
    return f"cd {ws}/src && echo $$ > {ws}/pid && exec " + mac_bridge.quote_all(argv)


def cancel_command(job_id: str) -> str:
    ws = workspace_dir(job_id)
    return f'test -f {ws}/pid && kill -TERM "$(cat {ws}/pid)" 2>/dev/null; true'


def cleanup_command(job_id: str) -> str:
    return f"rm -rf {workspace_dir(job_id)}"


# ─────────────────────────────────────────────
# 解析・検証
# ─────────────────────────────────────────────

def parse_list(stdout: str) -> tuple[list[str], list[str]]:
    """xcodebuild -list -json の出力から scheme と configuration を取り出す。"""
    start = stdout.find("{")
    if start < 0:
        raise MacBridgeError("xcodebuild -list の結果を読み取れません")
    try:
        data = json.loads(stdout[start:])
    except json.JSONDecodeError:
        raise MacBridgeError("xcodebuild -list の結果を読み取れません")
    info = data.get("workspace") or data.get("project") or {}
    schemes = [s for s in info.get("schemes", []) if isinstance(s, str)]
    configurations = [c for c in info.get("configurations", []) if isinstance(c, str)] or ["Debug", "Release"]
    return schemes, configurations


def destination_options(host) -> list[dict[str, str]]:
    options = [{"id": GENERIC_DESTINATION, "label": "任意の iOS シミュレータ（generic）"}]
    for s in (host.probe or {}).get("simulators", []):
        if s.get("udid") and UDID_RE.match(s["udid"]):
            options.append({"id": s["udid"], "label": f"{s.get('name')} · {s.get('runtime')}"})
    return options


def resolve_destination(host, destination_id: str) -> tuple[str, str]:
    """選択 ID を xcodebuild の -destination 文字列に変換する（候補外は拒否）。"""
    if destination_id == GENERIC_DESTINATION:
        return "generic/platform=iOS Simulator", "任意の iOS シミュレータ（generic）"
    for s in (host.probe or {}).get("simulators", []):
        if s.get("udid") == destination_id and UDID_RE.match(destination_id):
            platform = (s.get("runtime") or "iOS").split()[0]
            return f"platform={platform} Simulator,id={destination_id}", f"{s.get('name')} · {s.get('runtime')}"
    raise MacBridgeError("選択したシミュレータはこの Mac にありません（接続テストで一覧を更新してください）")


def summarize_log(log_path: Path) -> tuple[list[str], int]:
    errors, warnings = [], 0
    if log_path.exists():
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if ERROR_LINE_RE.search(line):
                    if len(errors) < 20 and line.strip() not in errors:
                        errors.append(line.strip()[:500])
                elif WARNING_LINE_RE.search(line):
                    warnings += 1
    return errors, warnings


# ─────────────────────────────────────────────
# ログ
# ─────────────────────────────────────────────

def log_path(job_id: str) -> Path:
    if not JOB_ID_RE.match(job_id):
        raise MacBridgeError("不正なジョブ ID です")
    d = mac_bridge.data_dir() / "builds"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{job_id}.log"


def append_log(job_id: str, text: str) -> None:
    with open(log_path(job_id), "a", encoding="utf-8", newline="") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def read_log(job_id: str, offset: int, limit: int = 256 * 1024) -> tuple[str, int]:
    p = log_path(job_id)
    if not p.exists():
        return "", 0
    with open(p, "rb") as f:
        f.seek(max(0, offset))
        chunk = f.read(limit)
    # UTF-8 の途中で切れた末尾は次回に回す
    i = len(chunk) - 1
    while i >= 0 and (chunk[i] & 0xC0) == 0x80:
        i -= 1
    if i >= 0 and chunk[i] >= 0xC0:
        need = 2 if chunk[i] < 0xE0 else 3 if chunk[i] < 0xF0 else 4
        if len(chunk) - i < need:
            chunk = chunk[:i]
    return chunk.decode("utf-8", "replace"), max(0, offset) + len(chunk)


async def stream_process(argv: list[str], job_id: str, timeout: float) -> int:
    """プロセスの stdout+stderr を 1 行ずつログへ追記する。タイムアウト・キャンセル時は kill。"""
    limit = settings.MAC_BRIDGE_MAX_BUILD_LOG_MB * 1024 * 1024
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def pump():
        written = 0
        with open(log_path(job_id), "ab") as f:
            while line := await proc.stdout.readline():
                if written < limit:
                    f.write(line)
                    f.flush()
                    written += len(line)
        return await proc.wait()

    try:
        return await asyncio.wait_for(pump(), timeout)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


# ─────────────────────────────────────────────
# ジョブ実行（バックグラウンド）
# ─────────────────────────────────────────────

def new_job_id() -> str:
    return uuid.uuid4().hex


def is_running(job_id: str) -> bool:
    task = _tasks.get(job_id)
    return task is not None and not task.done()


def spawn(job_id: str, coro) -> None:
    task = asyncio.create_task(coro)
    _tasks[job_id] = task
    task.add_done_callback(lambda _: _tasks.pop(job_id, None))


def cancel(job_id: str) -> bool:
    task = _tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _update(session_factory: Callable, job_id: str, **fields) -> None:
    from app.db.models import MacBuildModel

    async with session_factory() as db:
        job = await db.get(MacBuildModel, job_id)
        for k, v in fields.items():
            setattr(job, k, v)
        await db.commit()


async def _load(session_factory: Callable, job_id: str):
    from app.db.models import MacBuildModel, MacHostModel

    async with session_factory() as db:
        job = await db.get(MacBuildModel, job_id)
        host = await db.get(MacHostModel, job.host_id) if job and job.host_id else None
        return job, host


async def prepare_job(job_id: str, session_factory: Callable) -> None:
    """転送 + scheme 取得。結果は DB とログに記録する。"""
    fd, name = tempfile.mkstemp(prefix="devmirror-", suffix=".tar.gz")
    os.close(fd)  # Windows では開いたままだと削除できない
    archive = Path(name)
    try:
        job, host = await _load(session_factory, job_id)
        if host is None:
            raise MacBridgeError("Mac の登録が削除されています")
        append_log(job_id, f"[DevMirror] プロジェクトを圧縮しています: {job.source_path}")
        size = await asyncio.to_thread(create_archive, Path(job.source_path), archive)
        append_log(job_id, f"[DevMirror] 転送しています（元サイズ {size / 1024 / 1024:.1f} MB → 圧縮後 {archive.stat().st_size / 1024 / 1024:.1f} MB）")

        argv = await mac_bridge.ssh_argv_for(host, upload_command(job_id))
        rc, out, err = await mac_bridge.run_process(argv, settings.MAC_BRIDGE_UPLOAD_TIMEOUT, stdin_path=archive)
        if rc != 0:
            raise MacBridgeError(_ssh_error(rc, err, "転送に失敗しました"))

        append_log(job_id, f"[DevMirror] scheme を取得しています: {job.container}")
        argv = await mac_bridge.ssh_argv_for(host, list_command(job_id, job.container, job.container_type))
        rc, out, err = await mac_bridge.run_process(argv, settings.MAC_BRIDGE_COMMAND_TIMEOUT)
        if rc != 0:
            append_log(job_id, err.strip())
            raise MacBridgeError(_ssh_error(rc, err, "xcodebuild -list に失敗しました"))
        schemes, configurations = parse_list(out)
        if not schemes:
            raise MacBridgeError("scheme が見つかりません（Xcode で scheme を Shared にしてください）")
        append_log(job_id, f"[DevMirror] 準備完了: scheme {len(schemes)} 件")
        await _update(session_factory, job_id, status="ready", schemes=schemes, configurations=configurations)
    except asyncio.CancelledError:
        append_log(job_id, "[DevMirror] 準備をキャンセルしました")
        await _update(session_factory, job_id, status="cancelled", finished_at=datetime.utcnow())
        raise
    except MacBridgeError as e:
        append_log(job_id, f"[DevMirror] エラー: {e}")
        await _update(session_factory, job_id, status="error", error_message=str(e), finished_at=datetime.utcnow())
    except Exception as e:  # 想定外でもジョブを preparing のまま残さない
        logger.exception("ビルド準備で予期しないエラー", job_id=job_id)
        append_log(job_id, f"[DevMirror] 予期しないエラー: {type(e).__name__}")
        await _update(session_factory, job_id, status="error", error_message="予期しないエラーが発生しました", finished_at=datetime.utcnow())
    finally:
        archive.unlink(missing_ok=True)


async def run_build(job_id: str, session_factory: Callable) -> None:
    started = datetime.utcnow()
    status, exit_code, message, host = "error", None, None, None
    try:
        job, host = await _load(session_factory, job_id)
        if host is None:
            raise MacBridgeError("Mac の登録が削除されています")
        cmd = build_command(job_id, job.container, job.container_type, job.scheme, job.configuration, job.destination)
        append_log(job_id, f"[DevMirror] ビルド開始: scheme={job.scheme} configuration={job.configuration} destination={job.destination}")
        argv = await mac_bridge.ssh_argv_for(host, cmd)
        exit_code = await stream_process(argv, job_id, settings.MAC_BRIDGE_BUILD_TIMEOUT)
        if exit_code == 255:
            status, message = "error", "SSH 接続が切断されました（ビルド結果は不明です）"
        else:
            status = "succeeded" if exit_code == 0 else "failed"
    except asyncio.TimeoutError:
        status, message = "timeout", f"ビルドがタイムアウトしました（{settings.MAC_BRIDGE_BUILD_TIMEOUT} 秒）"
        await _remote_cancel(host, job_id)
    except asyncio.CancelledError:
        status, message = "cancelled", "ユーザーがキャンセルしました"
        await _remote_cancel(host, job_id)
    except MacBridgeError as e:
        status, message = "error", str(e)
    except Exception as e:
        logger.exception("ビルドで予期しないエラー", job_id=job_id)
        status, message = "error", f"予期しないエラー: {type(e).__name__}"
    finally:
        finished = datetime.utcnow()
        errors, warnings = summarize_log(log_path(job_id))
        append_log(job_id, f"[DevMirror] 終了: {status}" + (f"（exit {exit_code}）" if exit_code is not None else "") + (f" {message}" if message else ""))
        await _update(
            session_factory, job_id,
            status=status, exit_code=exit_code, error_message=message, errors=errors,
            warning_count=warnings, started_at=started, finished_at=finished,
            duration_sec=round((finished - started).total_seconds(), 1),
        )
        logger.info("Mac ビルド終了", job_id=job_id, status=status, exit_code=exit_code)


async def _remote_cancel(host, job_id: str) -> None:
    """Mac 側の xcodebuild も止める（ssh を切っただけでは残る場合がある）。失敗しても続行。"""
    if host is None:
        return
    try:
        argv = await mac_bridge.ssh_argv_for(host, cancel_command(job_id))
        await asyncio.shield(mac_bridge.run_process(argv, settings.MAC_BRIDGE_CONNECT_TIMEOUT + 5))
    except Exception as e:
        logger.warning("Mac 側のビルド停止に失敗", job_id=job_id, error=str(e))
        append_log(job_id, "[DevMirror] 警告: Mac 側のプロセス停止を確認できませんでした")


async def cleanup_workspace(host, job_id: str) -> None:
    argv = await mac_bridge.ssh_argv_for(host, cleanup_command(job_id))
    rc, _, err = await mac_bridge.run_process(argv, settings.MAC_BRIDGE_COMMAND_TIMEOUT)
    if rc != 0:
        raise MacBridgeError(_ssh_error(rc, err, "作業ディレクトリの削除に失敗しました"))


def _ssh_error(rc: int, stderr: str, fallback: str) -> str:
    if rc == 255:
        return mac_bridge.classify_ssh_failure(stderr).message
    return fallback
