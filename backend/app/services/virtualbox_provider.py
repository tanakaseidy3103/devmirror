"""
DevMirror - VirtualBox Provider
"""
import asyncio
import hashlib
import ntpath
import os
import re
import shutil
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.core.config import settings
from app.domain.providers import VMProvider

logger = structlog.get_logger(__name__)

# Windows / Linux / macOS の標準インストールパス
_CANDIDATE_PATHS = [
    r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
    r"C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe",
    "/usr/bin/vboxmanage",
    "/usr/local/bin/vboxmanage",
    "/opt/homebrew/bin/vboxmanage",
]


class VirtualBoxError(RuntimeError):
    """VBoxManage の実行に失敗した場合に送出する"""


class VirtualBoxProvider(VMProvider):
    """
    VirtualBoxProvider

    VBoxManage.exe を CLI として使い、VM の作成・起動・破棄と、
    Guest Additions の guestcontrol によるコマンド実行・ファイル転送を行う。
    """

    def __init__(
        self,
        vboxmanage_path: Optional[str] = None,
        base_vm: Optional[str] = None,
        clone_mode: Optional[str] = None,
        clone_prefix: Optional[str] = None,
        memory_mb: Optional[int] = None,
        cpus: Optional[int] = None,
        boot_timeout: Optional[int] = None,
        guest_ready_timeout: Optional[int] = None,
        guest_username: Optional[str] = None,
        guest_password: Optional[str] = None,
    ):
        self._vboxmanage = vboxmanage_path or settings.VBOXMANAGE_PATH
        self._base_vm = base_vm or settings.VBOX_BASE_VM
        self._clone_mode = clone_mode or settings.VBOX_CLONE_MODE
        self._clone_prefix = clone_prefix or settings.VBOX_CLONE_PREFIX
        self._memory_mb = memory_mb if memory_mb is not None else settings.VBOX_MEMORY_MB
        self._cpus = cpus if cpus is not None else settings.VBOX_CPUS
        self._boot_timeout = (
            boot_timeout if boot_timeout is not None else settings.VBOX_BOOT_TIMEOUT
        )
        self._guest_ready_timeout = (
            guest_ready_timeout
            if guest_ready_timeout is not None
            else settings.VBOX_GUEST_READY_TIMEOUT
        )
        self._guest_user = (
            guest_username if guest_username is not None else settings.VBOX_GUEST_USERNAME
        )
        self._guest_password = (
            guest_password
            if guest_password is not None
            else settings.VBOX_GUEST_PASSWORD
        )

    # ------------------------------------------------------------------ #
    # 低レベル: VBoxManage 実行
    # ------------------------------------------------------------------ #

    def resolve_executable(self) -> str:
        """VBoxManage の実体パスを返す。未設定なら標準パスを探索する。"""
        if self._vboxmanage:
            return self._vboxmanage

        for candidate in _CANDIDATE_PATHS:
            if os.path.isfile(candidate):
                self._vboxmanage = candidate
                return candidate

        found = shutil.which("VBoxManage") or shutil.which("vboxmanage")
        if found:
            self._vboxmanage = found
            return found

        raise VirtualBoxError(
            "VBoxManage が見つかりません。VirtualBox をインストールするか "
            "VBOXMANAGE_PATH を設定してください。"
        )

    async def _vbox(
        self,
        *args: str,
        timeout: Optional[int] = None,
        check: bool = False,
    ) -> Tuple[int, str, str]:
        """VBoxManage を実行し (returncode, stdout, stderr) を返す。"""
        exe = self.resolve_executable()
        cmd = [exe, *args]
        logger.debug("[VBox] 実行", args=" ".join(args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise VirtualBoxError(f"VBoxManage が見つかりません: {exe}") from exc

        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise VirtualBoxError(
                f"VBoxManage がタイムアウトしました: {' '.join(args)}"
            ) from exc

        out = raw_out.decode("utf-8", errors="replace")
        err = raw_err.decode("utf-8", errors="replace")
        rc = proc.returncode or 0

        if check and rc != 0:
            raise VirtualBoxError(
                f"VBoxManage が失敗しました (rc={rc}): {' '.join(args)}\n{err or out}"
            )
        return rc, out, err

    def _auth(self) -> List[str]:
        """guestcontrol に渡す認証引数。"""
        args: List[str] = []
        if self._guest_user:
            args += ["--username", self._guest_user]
        if self._guest_password:
            args += ["--password", self._guest_password]
        return args

    # ------------------------------------------------------------------ #
    # VM ライフサイクル
    # ------------------------------------------------------------------ #

    def _vm_name(self, environment_name: str) -> str:
        """
        環境名から決定的な VM 名を作る（例: DevMirror-envA）。

        VM 名は VirtualBox のディレクトリ名としても使われるため ASCII に絞る。
        日本語を含む環境名は、固有名詞だけ残すと「環境A（動作する）」と
        「環境A（失敗する）」が両方 "A" へ潰れてしまうためハッシュを添える。
        """
        ascii_slug = re.sub(r"[^0-9A-Za-z._-]+", "-", environment_name).strip("-.")
        if re.search(r"[^\x00-\x7F]", environment_name):
            digest = hashlib.sha1(environment_name.encode("utf-8")).hexdigest()[:8]
            slug = f"{ascii_slug}-{digest}" if ascii_slug else f"env-{digest}"
        else:
            slug = ascii_slug or "env"
        return f"{self._clone_prefix}-{slug[:48]}"

    async def _exists(self, vm_name: str) -> bool:
        rc, out, _ = await self._vbox("showvminfo", vm_name, "--machinereadable")
        if rc == 0:
            return True
        return f'name="{vm_name}"' in out

    async def create(self, environment_name: str, config: Dict[str, Any]) -> str:
        """基準 VM をクローンして対象 VM を登録し、VM 名を返す"""
        vm_name = self._vm_name(environment_name)
        config = config or {}

        if await self._exists(vm_name):
            logger.info("[VBox] 同名の VM があるため作り直します", vm=vm_name)
            await self._vbox("controlvm", vm_name, "poweroff", check=False)
            await self._vbox("unregistervm", vm_name, "--delete", check=False)

        base_vm = config.get("base_vm") or self._base_vm
        mode = config.get("clone_mode") or self._clone_mode
        memory_mb = config.get("memory_mb") or self._memory_mb
        cpus = config.get("cpus") or self._cpus

        logger.info("[VBox] VM をクローンします", base=base_vm, vm=vm_name, mode=mode)
        await self._vbox(
            "clonevm", base_vm,
            "--name", vm_name,
            "--register",
            "--mode", mode,
            check=True,
            timeout=300,
        )
        await self._vbox(
            "modifyvm", vm_name,
            "--memory", str(memory_mb),
            "--cpus", str(cpus),
            "--vram", "128",
            "--cpus-hw-virt", "on",
            "--ioapic", "on",
            check=True,
            timeout=120,
        )
        logger.info("[VBox] VM を作成しました", vm=vm_name)
        return vm_name

    async def start(self, instance_id: str) -> bool:
        """VM をヘッドレス起動し、Guest Additions の応答を待つ"""
        rc, out, err = await self._vbox(
            "startvm", instance_id, "--type", "headless", check=False
        )
        if rc != 0 and "already" not in (out + err).lower():
            raise VirtualBoxError(f"VM を起動できません: {out}{err}")

        logger.info("[VBox] VM を起動しました", vm=instance_id)
        await self._wait_for_boot(instance_id)
        await self._wait_for_guest(instance_id)
        return True

    async def _wait_for_boot(self, instance_id: str) -> None:
        """VMState が "powered up" になるまで待つ"""
        deadline = _now() + self._boot_timeout
        while _now() < deadline:
            rc, out, _ = await self._vbox("showvminfo", instance_id, "--machinereadable")
            if rc == 0 and 'VMState="powered up"' in out:
                return
            await asyncio.sleep(2)
        raise VirtualBoxError(
            f"VM が起動しませんでした（{self._boot_timeout}秒）: {instance_id}"
        )

    async def _wait_for_guest(self, instance_id: str) -> None:
        """Guest Additions が応答するまで待つ"""
        if not self._guest_user:
            logger.warning(
                "[VBox] VBOX_GUEST_USERNAME が未設定のため "
                "Guest Additions の応答確認をスキップします"
            )
            return

        deadline = _now() + self._guest_ready_timeout
        while _now() < deadline:
            rc, _, _ = await self._vbox(
                "guestcontrol", instance_id, "getenv", *self._auth(),
                timeout=20, check=False,
            )
            if rc == 0:
                logger.info("[VBox] Guest Additions の応答を確認", vm=instance_id)
                return
            await asyncio.sleep(3)
        raise VirtualBoxError(
            "Guest Additions が応答しません。VM に Guest Additions を"
            "インストールし、username / password を確認してください。"
        )

    async def stop(self, instance_id: str) -> bool:
        """VM を ACPI ボタン経由で安全に停止する"""
        rc, _, err = await self._vbox(
            "controlvm", instance_id, "acpipowerbutton", check=False
        )
        if rc != 0 and "not running" not in err.lower():
            logger.warning("[VBox] 停止に失敗しました", vm=instance_id, err=err)
            return False
        logger.info("[VBox] VM を停止しました", vm=instance_id)
        return True

    async def destroy(self, instance_id: str) -> bool:
        """VM を強制停止して削除する"""
        await self._vbox("controlvm", instance_id, "poweroff", check=False)
        rc, _, err = await self._vbox("unregistervm", instance_id, "--delete", check=False)
        if rc != 0:
            logger.warning("[VBox] VM の削除に失敗しました", vm=instance_id, err=err)
            return False
        logger.info("[VBox] VM を破棄しました", vm=instance_id)
        return True

    # ------------------------------------------------------------------ #
    # ファイル転送・コマンド実行
    # ------------------------------------------------------------------ #

    async def copy_project(
        self, instance_id: str, local_path: str, remote_path: str
    ) -> bool:
        """ホストのディレクトリをゲストへ再帰的にコピーする"""
        if not os.path.exists(local_path):
            raise VirtualBoxError(f"コピー元が見つかりません: {local_path}")

        # ゲストパスは Windows 形式なので ntpath で解析する
        # （os.path は Linux 実行時に "\" を区切りとみなさない）
        parent = ntpath.dirname(remote_path.rstrip("\\/")) or remote_path

        await self._vbox(
            "guestcontrol", instance_id, "mkdir", parent, "--parents",
            *self._auth(), check=True, timeout=120,
        )
        await self._vbox(
            "guestcontrol", instance_id, "copyto", remote_path, local_path,
            "--recursive", *self._auth(), check=True, timeout=600,
        )
        logger.info(
            "[VBox] プロジェクトをコピーしました",
            vm=instance_id, src=local_path, dest=remote_path,
        )
        return True

    async def install_dependencies(
        self, instance_id: str, dependencies: List[Dict[str, Any]]
    ) -> bool:
        """依存関係をゲスト側でインストールする"""
        for dep in dependencies or []:
            name = dep.get("name", "unknown")
            install_cmd = dep.get("install_command")
            if not install_cmd:
                logger.info(
                    "[VBox] インストールコマンドが未指定のためスキップします", dep=name
                )
                continue
            logger.info("[VBox] 依存関係をインストールします", dep=name, vm=instance_id)
            returncode, stdout, stderr = await self.run_command(instance_id, install_cmd)
            if returncode != 0:
                raise VirtualBoxError(
                    f"依存関係のインストールに失敗しました: {name}\n{stderr or stdout}"
                )
        return True

    async def run_command(
        self, instance_id: str, command: str
    ) -> Tuple[int, str, str]:
        """
        ゲストでコマンドを実行し (returncode, stdout, stderr) を返す。

        終了コードは guestcontrol の出力書式に依存しないよう、
        コマンド側で %ERRORLEVEL% をファイルに書き出させ 이를読み取る。

        NOTE: command はゲストの cmd.exe に渡され評価される。
        呼び出し側（CommandTestRunner 等）で入力を検証すること。
        """
        timeout = settings.ALLOWED_COMMAND_TIMEOUT
        marker = f"C:\\Windows\\Temp\\dm_exit_{uuid.uuid4().hex}.txt"
        # 括弧でコマンドをまとめ、成否にかかわらず終了コードを記録する
        wrapped = f'({command}) & echo %ERRORLEVEL% > "{marker}"'

        rc, out, err = await self._vbox(
            "guestcontrol", instance_id, "run", "cmd.exe", "/c", wrapped,
            *self._auth(), check=False, timeout=60,
        )
        if rc != 0:
            raise VirtualBoxError(f"コマンドの起動に失敗しました: {out}{err}")

        pid = self._parse_pid(out)
        if not pid:
            raise VirtualBoxError(f"プロセスIDを取得できません: {out}")

        await self._vbox(
            "guestcontrol", instance_id, "wait", pid, *self._auth(),
            timeout=timeout, check=False,
        )

        stdout = await self._process_output(instance_id, pid, "readcat")
        stderr = await self._process_output(instance_id, pid, "readcaterr")
        returncode = await self._read_exit_code(instance_id, marker)
        return returncode, stdout, stderr

    @staticmethod
    def _parse_pid(output: str) -> Optional[str]:
        """run の出力からプロセスIDを抽出する"""
        match = re.search(r"process ID:\s*(\d+)", output, re.IGNORECASE)
        return match.group(1) if match else None

    async def _process_output(
        self, instance_id: str, pid: str, subcommand: str
    ) -> str:
        """readcat / readcaterr でプロセスの出力を読む"""
        _, out, err = await self._vbox(
            "guestcontrol", instance_id, subcommand, pid, *self._auth(),
            timeout=settings.ALLOWED_COMMAND_TIMEOUT, check=False,
        )
        return out or ""

    async def _read_exit_code(self, instance_id: str, marker: str) -> int:
        """
        書き出された終了コードを読み取る。

        取得できなかった場合は 0 を返す。これは「成功」ではなく
        「判定できなかった」ことを意味するため、呼び出し側でログを残すこと。
        """
        with tempfile.TemporaryDirectory() as tmp:
            local_file = os.path.join(tmp, "exitcode.txt")
            rc, _, _ = await self._vbox(
                "guestcontrol", instance_id, "copyfrom", marker, local_file,
                *self._auth(), check=False, timeout=60,
            )
            if rc != 0 or not os.path.exists(local_file):
                logger.warning("[VBox] 終了コードを読み取れませんでした", vm=instance_id)
                return 0
            with open(local_file, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read().strip()

        match = re.search(r"-?\d+", raw)
        return int(match.group(0)) if match else 0

    async def collect_logs(self, instance_id: str, remote_path: str) -> str:
        """ゲストのログファイルを取得して文字列として返す"""
        with tempfile.TemporaryDirectory() as tmp:
            local_file = os.path.join(tmp, "collected.logs")
            await self._vbox(
                "guestcontrol", instance_id, "copyfrom", remote_path, local_file,
                *self._auth(), check=False, timeout=120,
            )
            if not os.path.exists(local_file):
                logger.info("[VBox] ログが見つかりませんでした", vm=instance_id, path=remote_path)
                return ""
            with open(local_file, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()

        if len(content.encode("utf-8")) > settings.MAX_LOG_SIZE_BYTES:
            content = content[: settings.MAX_LOG_SIZE_BYTES]
            logger.warning("[VBox] ログを最大サイズで切り詰めました", vm=instance_id)
        return content

    async def take_screenshot(self, instance_id: str) -> Optional[bytes]:
        """VM のスクリーンショットを PNG で取得する"""
        with tempfile.TemporaryDirectory() as tmp:
            png_path = os.path.join(tmp, "screenshot.png")
            rc, _, err = await self._vbox(
                "controlvm", instance_id, "screenshotpng", png_path,
                check=False, timeout=60,
            )
            if rc != 0 or not os.path.exists(png_path):
                logger.warning("[VBox] スクリーンショットに失敗しました", vm=instance_id, err=err)
                return None
            with open(png_path, "rb") as fh:
                return fh.read()


def _now() -> float:
    """単調増加の現在時刻（loop.time のラッパ）"""
    return asyncio.get_running_loop().time()
