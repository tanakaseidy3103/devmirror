"""
DevMirror - 3 環境分の VM を準備するスクリプト

基準 VM (Guest Additions 入り) から 3 つの VM をクローンし、
DevMirror 用の設定 (CPU / メモリ / 共有フォルダ) を適用する。

使い方:
    # 3 つ作る（既定）
    python -m scripts.provision_vms

    # 環境名を明示する
    python -m scripts.provision_vms --names envA envB envC

    # 既に作る済みの VM を消す
    python -m scripts.provision_vms --destroy
"""
import argparse
import asyncio
import sys

from app.core.config import settings
from app.services.virtualbox_provider import VirtualBoxError, VirtualBoxProvider

DEFAULT_NAMES = ["envA", "envB", "envC"]


async def main() -> int:
    parser = argparse.ArgumentParser(description="DevMirror 用 VM を 3 台準備する")
    parser.add_argument("--names", nargs="+", default=DEFAULT_NAMES,
                        help=f"環境名（既定: {' '.join(DEFAULT_NAMES)}）")
    parser.add_argument("--destroy", action="store_true", help="作成済み VM を削除する")
    parser.add_argument("--memory", type=int, default=settings.VBOX_MEMORY_MB)
    parser.add_argument("--cpus", type=int, default=settings.VBOX_CPUS)
    parser.add_argument("--mode", choices=["linked", "all"], default=settings.VBOX_CLONE_MODE)
    args = parser.parse_args()

    provider = VirtualBoxProvider()

    try:
        exe = provider.resolve_executable()
    except VirtualBoxError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"VBoxManage : {exe}")
    print(f"基準 VM    : {settings.VBOX_BASE_VM}")
    print(f"VM 数     : {len(args.names)}")
    print()

    rc, out, err = await provider._vbox("list", "vms", timeout=60)
    if rc != 0:
        print(f"[ERROR] VBoxManage を実行できません: {err or out}", file=sys.stderr)
        return 1

    if args.destroy:
        for name in args.names:
            vm = provider._vm_name(name)
            ok = await provider.destroy(vm)
            print(f"  {'削除' if ok else '削除できず'} : {vm}")
        return 0

    registered = [
        line.split('"')[1] for line in out.splitlines()
        if line.strip().startswith('"') and '"' in line.strip()
    ]
    if settings.VBOX_BASE_VM not in registered:
        print(
            f"[ERROR] 基準 VM「{settings.VBOX_BASE_VM}」が登録されていません。\n"
            f"  まず Windows をインストールし、Guest Additions が入った VM を\n"
            f"  「{settings.VBOX_BASE_VM}」という名前で登録してください。\n"
            f"  現在の登録済み VM: {registered or '(なし)'}",
            file=sys.stderr,
        )
        return 1

    failed = []
    for name in args.names:
        vm = provider._vm_name(name)
        print(f"[{name}] 作成中 ... {vm}")
        try:
            await provider.create(name, {
                "memory_mb": args.memory,
                "cpus": args.cpus,
                "clone_mode": args.mode,
            })
        except VirtualBoxError as exc:
            print(f"  [ERROR] {exc}", file=sys.stderr)
            failed.append(name)
            continue
        print(f"  完了: {vm}  (memory={args.memory}MB cpus={args.cpus} mode={args.mode})")

    print()
    if failed:
        print(f"[ERROR] 作成に失敗しました: {', '.join(failed)}", file=sys.stderr)
        return 1

    print("完了しました。次の手順:")
    print(f"  1. 各 VM に {settings.VBOX_GUEST_PATH} としてゲームを配置する")
    print("  2. .env に VM_PROVIDER=virtualbox を書く")
    print("  3. VBOX_PROJECT_PATH（ホスト側）と VBOX_GUEST_PATH（ゲスト側）を設定する")
    print("  4. VBOX_GUEST_USERNAME / VBOX_GUEST_PASSWORD を設定する")
    print("  5. GET /api/v1/vm/status で接続を確認してから /replay を呼ぶ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
