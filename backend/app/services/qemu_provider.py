"""
DevMirror - QEMU VM Provider

WSL2 + KVM で VM を動かし、VNC を公開してブラウザから「VM に入る」ための実装。

VirtualBox と違い、VM の画面をネットワーク越しに出せるため、
DevMirror の画面を開いたまま VM に入って操作できる。

ディスク構成:
    基準ディスク (base.qcow2)
      |- envA.qcow2  (overlay: 差分だけ)
      |- envB.qcow2  (overlay)
      |- envC.qcow2  (overlay)

overlay は基準ディスクへの差分しか持たないので非常に小さく、
リセットしても基準ディスクが壊れない。
"""
import asyncio
import json
import os
import shutil
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_VM_DIR = Path.home() / ".devmirror" / "vms"


class QemuError(RuntimeError):
    """QEMU の操作に失敗したときに投げられる例外。"""


class QemuProvider:
    """QEMU で VM を作り、起動し、止め、リセットし、コンソールを公開する。"""

    def __init__(
        self,
        binary: str = "",
        img_binary: str = "",
        base_image: str = "",
        boot_iso: str = "",
        vm_dir: str = "",
        vnc_base_port: int = 5901,
        memory_mb: int = 2048,
        cpus: int = 2,
        accel: str = "kvm",
        boot_timeout: int = 180,
        stop_timeout: int = 30,
    ) -> None:
        self.binary = binary
        self.img_binary = img_binary
        self.base_image = base_image
        self.boot_iso = boot_iso
        self.vm_dir = Path(vm_dir) if vm_dir else DEFAULT_VM_DIR
        self.vnc_base_port = vnc_base_port
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.accel = accel
        self.boot_timeout = boot_timeout
        self.stop_timeout = stop_timeout

    # ------------------------------------------------------------------
    # パス
    # ------------------------------------------------------------------
    def overlay_path(self, name: str) -> Path:
        return self.vm_dir / f"{name}.qcow2"

    def pid_path(self, name: str) -> Path:
        return self.vm_dir / f"{name}.pid"

    def qmp_path(self, name: str) -> Path:
        return self.vm_dir / f"{name}.qmp"

    def log_path(self, name: str) -> Path:
        return self.vm_dir / f"{name}.log"

    def names(self) -> List[str]:
        from app.core.config import settings

        return list(settings.QEMU_VM_NAMES)

    def vnc_port(self, name: str) -> int:
        """envA -> 5901、envB -> 5902 のように安定した番号を返す。"""
        try:
            index = self.names().index(name)
        except ValueError as exc:
            raise QemuError(
                f"未知の環境名です: {name}（設定は {self.names()}）"
            ) from exc
        return self.vnc_base_port + index

    @staticmethod
    def check_host() -> None:
        """
        QEMU が立てられない環境向けのチェック。

        QEMU + KVM は Linux（WSL2）でしか動かず、QMP も UNIX ソケットを使う。
        Windows 上の Python で起動すると paths もソケットも Windows 側を
        指ilik込むため、ここで明確に落とす。
        """
        if os.name == "nt":
            raise QemuError(
                "QEMU を使う場合、バックエンドは WSL 上の Python で起動してください。"
                "（QMP が UNIX ソケットを、KVM が /dev/kvm を使うためです）"
            )

    # ------------------------------------------------------------------
    # 実行ファイルの解決
    # ------------------------------------------------------------------
    def resolve_binary(self) -> str:
        if self.binary:
            return self.binary
        found = shutil.which("qemu-system-x86_64")
        if not found:
            raise QemuError(
                "qemu-system-x86_64 が見つかりません。"
                "WSL で `sudo apt install -y qemu-system-x86` を実行してください。"
            )
        return found

    def resolve_img_binary(self) -> str:
        if self.img_binary:
            return self.img_binary
        found = shutil.which("qemu-img")
        if not found:
            raise QemuError(
                "qemu-img が見つかりません。"
                "WSL で `sudo apt install -y qemu-utils` を実行してください。"
            )
        return found

    def resolve_base_image(self) -> Path:
        if not self.base_image:
            raise QemuError(
                "QEMU_BASE_IMAGE が未設定です。基準ディスクを指定してください。"
            )
        path = Path(self.base_image)
        if not path.exists():
            raise QemuError(f"基準ディスクが存在しません: {path}")
        return path

    # ------------------------------------------------------------------
    # プロセス実行
    # ------------------------------------------------------------------
    async def _run(self, argv: List[str], timeout: float = 120) -> Tuple[int, str, str]:
        logger.debug("qemu 実行", args=argv[1:])
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise QemuError(f"実行ファイルが見つかりません: {argv[0]}") from exc

        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise QemuError(
                f"QEMU が時間内に終了しませんでした: {' '.join(argv[1:])}"
            ) from exc

        out = raw_out.decode("utf-8", errors="replace")
        err = raw_err.decode("utf-8", errors="replace")
        return proc.returncode or 0, out, err

    # ------------------------------------------------------------------
    # QMP (QEMU Machine Protocol) — 停止とスクリーンショット用
    # ------------------------------------------------------------------
    async def _qmp(
        self, name: str, command: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """QMP ソケットにコマンドを送り、応答を dict で返す。"""
        sock_path = self.qmp_path(name)
        if not sock_path.exists():
            raise QemuError(f"QMP ソケットがありません（VM が停止中?）: {name}")

        try:
            reader, writer = await asyncio.open_unix_connection(str(sock_path))
        except OSError as exc:
            raise QemuError(f"QMP に接続できません: {name} ({exc})") from exc

        try:
            # 接続直後にバナーが飛んでくるので読み取っておく
            greeting = await asyncio.wait_for(reader.readline(), timeout=10)
            if not greeting:
                raise QemuError(f"QMP ハンドシェイクに失敗しました: {name}")

            await self._qmp_exchange(reader, writer, "qmp_capabilities", None)
            return await self._qmp_exchange(reader, writer, command, arguments)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - クローズ失敗は無視してよい
                pass

    async def _qmp_exchange(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        command: str,
        arguments: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"execute": command}
        if arguments:
            payload["arguments"] = arguments
        writer.write((json.dumps(payload) + "\r\n").encode("utf-8"))
        await writer.drain()

        # QMP はイベントと応答が混在するので、return か error が来るまで読む
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=30)
            if not line:
                raise QemuError(f"QMP 接続が切断されました（{command}）")
            data = json.loads(line.decode("utf-8", errors="replace"))
            if "error" in data:
                raise QemuError(f"QMP コマンドが失敗しました: {data['error']}")
            if "return" in data:
                return data["return"]

    # ------------------------------------------------------------------
    # 状態の取得
    # ------------------------------------------------------------------
    def read_pid(self, name: str) -> Optional[int]:
        path = self.pid_path(name)
        if not path.exists():
            return None
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """
        pid のプロセスが生きているか。

        os.kill(pid, 0) は POSIX のirmation であり、Windows では
        TerminateProcess として扱われてプロセスを殺してしまう。
        QEMU は WSL（Linux）上で動かす前提なので、ここでだけ POSIX 相当の
        判定を行い、Windows で呼ばれた場合は安全側に倒す。
        """
        if os.name == "nt":
            # Windows では判定に Process Explorer 等が要るため、
            # 生存とみなして呼び出し側の停止処理に任せる
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def is_running(self, name: str) -> bool:
        """pid ファイルからプロセスの有無を判定する。"""
        pid = self.read_pid(name)
        if pid is None:
            return False
        return self._pid_alive(pid)

    async def status(self, name: str) -> Dict[str, Any]:
        """1 台分の状態をまとめて返す。"""
        overlay = self.overlay_path(name)
        running = self.is_running(name)
        return {
            "name": name,
            "created": overlay.exists(),
            "running": running,
            "pid": self.read_pid(name) if running else None,
            "overlay": str(overlay),
            "vnc_port": self.vnc_port(name) if name in self.names() else None,
        }

    async def list_vms(self) -> List[Dict[str, Any]]:
        return [await self.status(name) for name in self.names()]

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------
    async def create(self, name: str) -> bool:
        """基準ディスクから overlay を作る（既存なら何もしない）。"""
        self._check_name(name)
        overlay = self.overlay_path(name)
        if overlay.exists():
            logger.info("overlay は既存", vm=name, path=str(overlay))
            return False

        base = self.resolve_base_image()
        self.vm_dir.mkdir(parents=True, exist_ok=True)

        rc, out, err = await self._run([
            self.resolve_img_binary(),
            "create",
            "-f", "qcow2",
            "-F", "qcow2",
            "-b", str(base),
            str(overlay),
        ])
        if rc != 0:
            raise QemuError(f"overlay を作成できません: {err or out}")

        logger.info("overlay 作成", vm=name, path=str(overlay))
        return True

    async def start(self, name: str) -> bool:
        """VM を起動する。既に起動中なら何もしない。"""
        self._check_name(name)
        if self.is_running(name):
            logger.info("既に起動中", vm=name)
            return False

        overlay = self.overlay_path(name)
        if not overlay.exists():
            raise QemuError(
                f"overlay がありません: {overlay}\n先に VM を作成してください。"
            )

        self.vm_dir.mkdir(parents=True, exist_ok=True)
        for stale in (self.pid_path(name), self.qmp_path(name)):
            stale.unlink(missing_ok=True)

        port = self.vnc_port(name)
        display = port - 5900

        argv = [
            self.resolve_binary(),
            "-name", f"devmirror-{name}",
            "-machine", "q35",
            "-accel", self.accel,
            "-cpu", "host",
            "-smp", str(self.cpus),
            "-m", str(self.memory_mb),
            "-drive", f"file={overlay},if=virtio,format=qcow2",
            "-netdev", "user,id=net0",
            "-device", "virtio-net-pci,netdev=net0",
        ]

        # インストール ISO を付けると、CD から起動する distro は
        # ディスクに一切インストールせずにそのまま動く
        if self.boot_iso and Path(self.boot_iso).exists():
            argv += [
                "-drive", f"file={self.boot_iso},media=cdrom,readonly=on",
                "-boot", "d",
            ]

        argv += [
            "-vnc", f"127.0.0.1:{display}",
            "-display", "none",
            "-qmp", f"unix:{self.qmp_path(name)},server,nowait",
            "-pidfile", str(self.pid_path(name)),
            "-D", str(self.log_path(name)),
            "-daemonize",
            "-no-reboot",
        ]

        rc, out, err = await self._run(argv, timeout=60)
        if rc != 0:
            raise QemuError(f"VM を起動できません: {err or out}")

        await self._wait_for_port(name, port, self.boot_timeout)
        logger.info("VM 起動", vm=name, vnc_port=port)
        return True

    async def stop(self, name: str) -> bool:
        """VM を停止する。停止していなければ False。"""
        self._check_name(name)
        pid = self.read_pid(name)
        if pid is None or not self.is_running(name):
            self._cleanup_runtime_files(name)
            return False

        # QMP の quit で素直に落とす
        try:
            await self._qmp(name, "quit")
        except QemuError:
            logger.debug("QMP quit に失敗（強制終了にフォールバック）", vm=name)

        deadline = asyncio.get_event_loop().time() + self.stop_timeout
        while asyncio.get_event_loop().time() < deadline:
            if not self.is_running(name):
                self._cleanup_runtime_files(name)
                logger.info("VM 停止", vm=name)
                return True
            await asyncio.sleep(0.3)

        # まだ生きているなら強制終了
        kill_signal = getattr(signal, "SIGKILL", None) or signal.SIGTERM
        try:
            os.kill(pid, kill_signal)
            logger.warning("VM を強制終了", vm=name, pid=pid)
        except OSError:
            pass

        await asyncio.sleep(0.5)
        self._cleanup_runtime_files(name)
        return True

    async def reset(self, name: str) -> bool:
        """VM を初期状態に戻す（overlay を作り直す）。"""
        self._check_name(name)
        await self.stop(name)
        overlay = self.overlay_path(name)
        if overlay.exists():
            overlay.unlink()
            logger.info("overlay 削除", vm=name)
        await self.create(name)
        return True

    async def delete(self, name: str) -> bool:
        """VM を完全に消す。"""
        self._check_name(name)
        await self.stop(name)
        removed = False
        overlay = self.overlay_path(name)
        if overlay.exists():
            overlay.unlink()
            removed = True
        self._cleanup_runtime_files(name)
        return removed

    # ------------------------------------------------------------------
    # 補助
    # ------------------------------------------------------------------
    def _check_name(self, name: str) -> None:
        if name not in self.names():
            raise QemuError(f"未知の環境名です: {name}（設定は {self.names()}）")

    def _cleanup_runtime_files(self, name: str) -> None:
        for path in (self.pid_path(name), self.qmp_path(name)):
            path.unlink(missing_ok=True)

    async def _wait_for_port(self, name: str, port: int, timeout: int) -> None:
        """VNC ポートが開くまで待つ。開かなければエラー。"""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if not self.is_running(name):
                raise QemuError(
                    f"VM が起動直後に停止しました。QEMU ログ: {self.log_path(name)}"
                )
            if await self._port_open(port):
                return
            await asyncio.sleep(0.5)
        raise QemuError(f"VNC ({port}) が {timeout} 秒以内に開きませんでした。")

    @staticmethod
    async def _port_open(port: int, host: str = "127.0.0.1") -> bool:
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError:
            return False
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True

    async def screenshot(self, name: str, dest: Path) -> bool:
        """QMP の screendump でスクリーンショットを撮る。"""
        self._check_name(name)
        if not self.is_running(name):
            raise QemuError("VM が起動していないため撮影できません。")
        dest.parent.mkdir(parents=True, exist_ok=True)
        await self._qmp(name, "screendump", {"filename": str(dest)})

        # 書き込みは非同期なので、少し待つ
        for _ in range(50):
            if dest.exists() and dest.stat().st_size > 0:
                return True
            await asyncio.sleep(0.1)
        raise QemuError("スクリーンショットが生成されませんでした。")
