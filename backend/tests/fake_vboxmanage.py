"""
テスト用の VBoxManage ダミー。

本物の VirtualBox  없이 VirtualBoxProvider のコマンド组装を検証するため、
VBoxManage が返す出力を模倣する。

環境変数で挙動を切り替える:
  FAKE_VBOX_LOG        : 呼び出しを記録するファイル
  FAKE_VBOX_STDOUT     : readcat が返す内容
  FAKE_VBOX_STDERR     : readcaterr が返す内容
  FAKE_VBOX_EXITCODE   : copyfrom で書き込む内容（終了コード検証用）
  FAKE_VBOX_NOT_READY  : この値なら getenv が失敗する（Guest Additions 未応答）
  FAKE_VBOX_MISSING    : この名前の VM は存在しない
"""
import os
import sys

# Windows ではパイプ出力がロケール・コードページ（cp932 など）になるため、
# 出力の_side_effect を確実にするため UTF-8 に固定する
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOG = os.environ.get("FAKE_VBOX_LOG", "")
STDOUT = os.environ.get("FAKE_VBOX_STDOUT", "")
STDERR = os.environ.get("FAKE_VBOX_STDERR", "")
EXITCODE = os.environ.get("FAKE_VBOX_EXITCODE", "0")
NOT_READY = os.environ.get("FAKE_VBOX_NOT_READY", "")
MISSING = os.environ.get("FAKE_VBOX_MISSING", "")

args = sys.argv[1:]


def log(line: str) -> None:
    if LOG:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def out(text: str) -> None:
    sys.stdout.write(text)


def err(text: str) -> None:
    sys.stderr.write(text)


log(" ".join(args))


def vm_is_known(vm: str) -> bool:
    """作成済み VM として認識させる（FAKE_VBOX_MISSING 以外）。"""
    return vm != MISSING and vm != "GhostVM"


# ---------------------------------------------------------------------- list
if args[:2] == ["list", "vms"]:
    # 登録済み VM を FAKE_VBOX_VMS（カンマ区切り）から再現する
    names = [x for x in os.environ.get("FAKE_VBOX_VMS", "").split(",") if x]
    for name in names:
        out(f'"{name}" {{00000000-0000-0000-0000-000000000000}}\n')
    sys.exit(0)

# ---------------------------------------------------------------- showvminfo
elif args[:1] == ["showvminfo"]:
    vm = args[1]
    if vm_is_known(vm):
        out(f'name="{vm}"\n')
        out('VMState="powered up"\n')
        sys.exit(0)
    err(f"VBoxManage.exe: error: Could not find a registered machine named '{vm}'\n")
    sys.exit(1)

# ------------------------------------------------------------------- clonevm
elif args[:1] == ["clonevm"]:
    base = args[1]
    if base == "NoSuchBase":
        err(f"VBoxManage.exe: error: Could not find a registered machine named '{base}'\n")
        sys.exit(1)
    out("VirtualBox Machine 0:...\n")
    sys.exit(0)

# ------------------------------------------------------------------ modifyvm
elif args[:1] == ["modifyvm"]:
    sys.exit(0)

# ------------------------------------------------------------------- startvm
elif args[:1] == ["startvm"]:
    if len(args) > 1 and not vm_is_known(args[1]):
        err(f"VBoxManage.exe: error: Could not find '{args[1]}'\n")
        sys.exit(1)
    out("Starting VM has been started!\n")
    sys.exit(0)

# ----------------------------------------------------------------- controlvm
elif args[:1] == ["controlvm"]:
    # controlvm <vm> acpipowerbutton | poweroff | screenshotpng <path>
    if len(args) >= 3 and args[2] == "screenshotpng":
        with open(args[3], "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n-fake-screenshot")
        sys.exit(0)
    if len(args) >= 3 and args[1] == "GhostVM":
        err("VBoxManage.exe: error: Could not find a running machine\n")
        sys.exit(1)
    sys.exit(0)

# -------------------------------------------------------------- unregistervm
elif args[:1] == ["unregistervm"]:
    sys.exit(0)

# --------------------------------------------------------------- guestcontrol
elif args[:1] == ["guestcontrol"]:
    if len(args) < 3:
        err("VBoxManage.exe: error: incomplete guestcontrol call\n")
        sys.exit(1)

    vm = args[1]
    sub = args[2]

    if not vm_is_known(vm):
        err(f"VBoxManage.exe: error: Could not find a running machine '{vm}'\n")
        sys.exit(1)

    if sub == "getenv":
        if NOT_READY:
            err("VBoxManage.exe: error: Guest Additions not responding\n")
            sys.exit(1)
        out("VBoxGuestAdditions=7.0.0\n")
        sys.exit(0)

    if sub == "mkdir":
        sys.exit(0)

    if sub in ("copyto", "copyfrom"):
        # copyto   <guestpath> <hostpath>
        # copyfrom <guestpath> <hostpath>
        # 認証オプションは後ろに付くため args[-1] ではなく位置引数を使う
        host_path = args[4]
        if sub == "copyfrom":
            with open(host_path, "w", encoding="utf-8") as fh:
                fh.write(EXITCODE)
        sys.exit(0)

    if sub == "run":
        out("Process ID: 4242\n")
        sys.exit(0)

    if sub in ("wait", "readcat", "readcaterr"):
        if sub == "readcat":
            out(STDOUT)
        elif sub == "readcaterr":
            out(STDERR)
        sys.exit(0)

    err(f"VBoxManage.exe: error: unknown subcommand '{sub}'\n")
    sys.exit(1)

err("VBoxManage.exe: error: unknown command\n")
sys.exit(1)
