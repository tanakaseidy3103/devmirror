"""
テスト用のダミー QEMU / qemu-img

本物の QEMU を使わずに argv の組み立てとエラー処理を検証する。

第 1 引数にツール名（qemu-system-x86_64 など）、以降が実際の引数。
呼び出し側は exe を [python, このスクリプト, ツール名] に差し替える。

環境変数で挙動を切り替える:

  FAKE_QEMU_LOG       : 呼び出し履歴を書き出すファイル
  FAKE_QEMU_STDOUT    : 標準出力
  FAKE_QEMU_STDERR    : 標準エラー
  FAKE_QEMU_EXITCODE  : 終了コード（既定 0）
  FAKE_QEMU_MISSING   : 1 なら「実行ファイルが無い」エラー
  FAKE_QEMU_VMS       : list vms 用の 1 行（; 区切り）
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

tool = os.path.basename(sys.argv[1]) if len(sys.argv) > 1 else "qemu-system-x86_64"
argv = sys.argv[2:]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _write_pid(path: str) -> None:
    """pidfile を書く。実際のプロセスなので自分の pid を入れる。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))


def _touch_qmp(spec: str) -> None:
    """-qmp unix:<path>,server,nowait からパスを抜き touch する。"""
    for part in spec.split(","):
        if part.startswith("unix:"):
            path = part[len("unix:"):]
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("")
            return


log = env("FAKE_QEMU_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"{tool} {' '.join(argv)}\n")

if env("FAKE_QEMU_MISSING") == "1":
    print(f"{tool}: command not found", file=sys.stderr)
    raise SystemExit(127)

# qemu-img create は実際にファイルを作る（overlay の存在確認に使う）
if tool.startswith("qemu-img") and argv[:1] == ["create"]:
    target = argv[-1]
    with open(target, "wb") as fh:
        fh.write(b"QFI\xfb" + b"\0" * 100)
    print(f"Formatting '{target}' with qcow2 (v3), 8192B clusters.")
    raise SystemExit(int(env("FAKE_QEMU_EXITCODE", "0")))

if argv[:1] == ["list"] and len(argv) > 1 and argv[1] == "vms":
    vms = env("FAKE_QEMU_VMS")
    if vms:
        for line in vms.split(";"):
            if line.strip():
                print(line.strip())
    raise SystemExit(int(env("FAKE_QEMU_EXITCODE", "0")))

# -daemonize で起動する実際の QEMU は、pidfile と QMP ソケットを作る
# （start() の「既に起動中」判定と _wait_for_port がこのファイルを見るため）
if "-daemonize" in argv:
    for flag, make in (("-pidfile", _write_pid), ("-qmp", _touch_qmp)):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 < len(argv):
                make(argv[idx + 1])

out = env("FAKE_QEMU_STDOUT")
if out:
    print(out)

err = env("FAKE_QEMU_STDERR")
if err:
    print(err, file=sys.stderr)

raise SystemExit(int(env("FAKE_QEMU_EXITCODE", "0")))
