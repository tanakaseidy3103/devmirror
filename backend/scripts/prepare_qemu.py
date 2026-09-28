"""
DevMirror - QEMU 環境の準備スクリプト

ブラウザから VM に入れる環境を用意する。

方針:
    基準ディスク (base.qcow2) を作り、そこから 3 環境分の overlay を作る。
    overlay は差分しか持たないので小さく、リセットしても基準は無傷。

    Alpine の virt ISO は initramfs で起動するため、ディスクに一切
    インストールせず CD から起動するだけで動く。よって
    「インストール済み VM 相当」のお試し環境を最小の作業で作れる。

手順:
    # 1. ISO を取得する（初回のみ / 約 60MB）
    python -m scripts.prepare_qemu --download

    # 2. 基準ディスクと 3 環境を作る
    python -m scripts.prepare_qemu --build

    # 3. 起動する（コンソールは http://localhost:3000/vm/console）
    python -m scripts.prepare_qemu --start

    # 4. 止める
    python -m scripts.prepare_qemu --stop
"""
import argparse
import asyncio
import subprocess
import sys
import urllib.request
from pathlib import Path

from app.services.qemu_provider import QemuError
from app.services.vm_factory import get_qemu_provider

# Alpine virt: インストール不要・起動が速い・容量が小さい
ISO_URL = (
    "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/"
    "alpine-virt-3.20.3-x86_64.iso"
)
ISO_NAME = "alpine-virt.iso"

VMS_DIR = Path.home() / ".devmirror" / "vms"
BASE_IMAGE = VMS_DIR / "base.qcow2"
BASE_SIZE = "8G"


def paths() -> tuple[Path, Path]:
    return VMS_DIR, BASE_IMAGE


def download_iso() -> int:
    """インストール ISO を取得する。"""
    vms_dir, _ = paths()
    vms_dir.mkdir(parents=True, exist_ok=True)
    dest = vms_dir / ISO_NAME

    if dest.exists():
        print(f"[SKIP] 既に取得済み: {dest}")
        return 0

    print(f"[GET ] {ISO_URL}")
    try:
        with urllib.request.urlopen(ISO_URL) as resp, open(dest, "wb") as out:
            total = 0
            while chunk := resp.read(256 * 1024):
                out.write(chunk)
                total += len(chunk)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] ダウンロードに失敗しました: {exc}", file=sys.stderr)
        return 1

    print(f"[OK  ] {dest}  ({total / 1024 / 1024:.1f} MB)")
    return 0


def build_base() -> int:
    """基準ディスクと 3 環境分の overlay を作る。"""
    vms_dir, base = paths()

    if download_iso() != 0:
        return 1

    if not base.exists():
        print(f"[MK  ] 基準ディスクを作成: {base} ({BASE_SIZE})")
        rc = subprocess.call(["qemu-img", "create", "-f", "qcow2", str(base), BASE_SIZE])
        if rc != 0:
            print("[ERROR] qemu-img create に失敗しました", file=sys.stderr)
            return 1
    else:
        print(f"[SKIP] 基準ディスクが既に存在します: {base}")

    iso = vms_dir / ISO_NAME
    provider = get_qemu_provider()
    provider.base_image = str(base)
    provider.boot_iso = str(iso)

    vms_dir.mkdir(parents=True, exist_ok=True)
    try:
        for name in provider.names():
            created = asyncio.run(provider.create(name))
            print(f"  {'作成' if created else '既存'}: {name} -> {provider.overlay_path(name)}")
    except QemuError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print()
    print("完成しました。backend/.env に以下を設定してください:")
    print()
    print(f"VM_PROVIDER=qemu")
    print(f"QEMU_BASE_IMAGE={base}")
    print(f"QEMU_BOOT_ISO={iso}")
    print(f"QEMU_VM_DIR={vms_dir}")
    print()
    print("その後、 python -m scripts.prepare_qemu --start で起動します。")
    return 0


async def start_all() -> int:
    vms_dir, base = paths()
    provider = get_qemu_provider()
    provider.base_image = str(base)
    provider.boot_iso = str(vms_dir / ISO_NAME)

    for name in provider.names():
        try:
            if not provider.overlay_path(name).exists():
                await provider.create(name)
            started = await provider.start(name)
            print(f"  {'起動' if started else '起動済み'}: {name}  VNC={provider.vnc_port(name)}")
        except QemuError as exc:
            print(f"  [ERROR] {name}: {exc}", file=sys.stderr)
            return 1

    print()
    print("コンソール: http://localhost:3000/vm/console")
    return 0


async def stop_all() -> int:
    provider = get_qemu_provider()
    for name in provider.names():
        try:
            stopped = await provider.stop(name)
            print(f"  {'停止' if stopped else '停止済み'}: {name}")
        except QemuError as exc:
            print(f"  [ERROR] {name}: {exc}", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DevMirror 用 QEMU 環境を準備する")
    parser.add_argument("--download", action="store_true", help="ISO のみ取得する")
    parser.add_argument("--build", action="store_true", help="基準ディスクと 3 環境を作る")
    parser.add_argument("--start", action="store_true", help="3 環境を起動する")
    parser.add_argument("--stop", action="store_true", help="3 環境を停止する")
    args = parser.parse_args()

    if not any([args.download, args.build, args.start, args.stop]):
        parser.print_help()
        return 1

    if args.download:
        return download_iso()
    if args.build:
        return build_base()
    if args.start:
        return asyncio.run(start_all())
    if args.stop:
        return asyncio.run(stop_all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
