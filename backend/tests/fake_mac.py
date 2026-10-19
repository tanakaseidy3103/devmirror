"""
テスト用の「Mac」。ssh の代わりに起動され、リモートコマンド文字列（argv[1]）を解釈する。

実機の挙動を再現するものではない。DevMirror 側の
「転送・ログの逐次取得・キャンセル・タイムアウト」を実プロセスで検証するためのもの。

環境変数:
  FAKE_MAC_DIR        転送された tar.gz を展開する先 / コマンド履歴（commands.log）
  FAKE_MAC_LIST       xcodebuild -list -json の出力
  FAKE_MAC_BUILD_OUT  ビルドの出力（\n 区切り）
  FAKE_MAC_BUILD_RC   ビルドの終了コード
  FAKE_MAC_SLEEP      ビルド出力の後に待つ秒数
"""
import io
import os
import sys
import tarfile
import time
from pathlib import Path

cmd = sys.argv[1]
base = Path(os.environ["FAKE_MAC_DIR"])
base.mkdir(parents=True, exist_ok=True)
with open(base / "commands.log", "a", encoding="utf-8") as f:
    f.write(cmd + "\n")

if "tar -xzf -" in cmd:
    data = sys.stdin.buffer.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(base / "src", filter="data")
elif "xcodebuild -list" in cmd:
    print(os.environ.get("FAKE_MAC_LIST", "{}"))
elif "exec xcodebuild" in cmd:
    for line in os.environ.get("FAKE_MAC_BUILD_OUT", "").split("\\n"):
        print(line, flush=True)
    time.sleep(float(os.environ.get("FAKE_MAC_SLEEP", "0")))
    sys.exit(int(os.environ.get("FAKE_MAC_BUILD_RC", "0")))
