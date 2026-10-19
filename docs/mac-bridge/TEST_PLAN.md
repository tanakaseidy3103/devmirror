# Mac Bridge テスト計画

## 1. 自動テスト（Mac 不要）

```powershell
cd backend
venv\Scripts\python -m pytest tests/test_mac_bridge.py tests/test_mac_build.py -v
```

- `test_mac_bridge.py`（接続）: `run_process`（ssh / ssh-keyscan）と DNS 解決だけをモック。
- `test_mac_build.py`（ビルド）: ssh の代わりに `tests/fake_mac.py` を **実プロセス** として起動。
  tar.gz の作成・stdin 経由の転送・展開、ログの逐次取得、キャンセル（プロセス kill）、タイムアウトは本物。
  **xcodebuild の出力は偽物であり、これが成功しても実機でビルドできたことにはならない。**

| 観点 | テスト |
|---|---|
| ホスト設定の検証 | `test_hostname_*`, `test_username_validation`, `test_fingerprint_validation`, `test_register_validation_errors` |
| DNS 名 → 公開 IP の拒否 | `test_dns_*` |
| localhost 以外の拒否 | `test_api_rejects_non_local_client` |
| 指紋計算が OpenSSH と一致 | `test_fingerprint_matches_openssh`（実 `ssh-keygen`） |
| 未知・変更されたホスト鍵 | `test_verify_host_key_rejects_unknown`, `test_register_rejects_wrong_fingerprint`, `test_changed_host_key_marks_mismatch_and_keeps_last_good` |
| 認証失敗 / 切断 / オフライン | `test_classify_ssh_failure`, `test_ssh_disconnect_is_not_reported_as_build_failure` |
| Xcode 未インストール | `test_parse_probe_without_xcode` |
| プロジェクト検出・存在しないフォルダ・許可外フォルダ | `test_find_containers_*`, `test_inspect_rejects_outside_roots_and_traversal`, `test_prepare_rejects_container_not_in_folder` |
| 転送内容（.git 等の除外・サイズ上限） | `test_archive_*`, `test_full_build_flow` |
| コマンドインジェクション | `test_build_command_quotes_hostile_values`, `test_invalid_parameters_rejected`, `test_workspace_dir_rejects_bad_ids` |
| scheme なし / 不正な scheme | `test_prepare_error_when_no_schemes`, `test_invalid_parameters_rejected` |
| ビルド成功 / 失敗・エラー行抽出 | `test_full_build_flow`, `test_build_failure_collects_errors` |
| キャンセル / タイムアウト | `test_cancel_stops_build_and_remote_process`, `test_timeout` |
| タスク間の隔離・同時実行制限 | `test_jobs_use_separate_workspaces`, `test_one_active_job_per_host` |
| ログ取得（UTF-8 境界） | `test_read_log_does_not_split_utf8` |
| 再起動後の中断表示 | `test_orphaned_running_job_marked_interrupted` |

---

## 2. 実機テストのチェックリスト（手動）

> **2026-10-19 時点で、実機 Mac での実行は一度も行っていません。**
> R1〜R8 がすべて期待どおりになるまで MVP1 は「完了」としません。B1〜B9 は MVP2 の判定です。
> 結果欄に ✅ / ❌ と、気づいたこと（エラーメッセージ等）を記入してください。

以下、`<mac-user>` は Mac のユーザー名、`<mac-host>` は `xxx.local` または LAN の IP。

### 2.0 準備

**Mac（ターミナル）**

```sh
sw_vers -productVersion
xcodebuild -version
xcode-select -p                      # /Applications/Xcode.app/... であること
xcrun simctl list devices available | head -20
scutil --get LocalHostName           # <mac-host> は「この名前.local」
ipconfig getifaddr en0               # Wi-Fi の IP（有線なら en1 等）
sudo systemsetup -getremotelogin     # On であること（Off なら システム設定 → 共有 → リモートログイン）
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub   # ← 表示された SHA256:... をメモ
```

**Windows（PowerShell）**

```powershell
ssh -V
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\devmirror_mac -C devmirror
Get-Content $env:USERPROFILE\.ssh\devmirror_mac.pub      # ← この 1 行を Mac へ
```

**Mac**: Windows で表示された公開鍵の 1 行を登録

```sh
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ここに devmirror_mac.pub の 1 行を貼る' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**Windows**: DevMirror を使わずに鍵ログインできるか先に確認（初回はホスト鍵の確認が出るので、
表示された指紋が Mac でメモした値と同じ場合だけ `yes`）

```powershell
ssh -i $env:USERPROFILE\.ssh\devmirror_mac <mac-user>@<mac-host> "sw_vers -productVersion && xcodebuild -version"
```

**Windows**: DevMirror を起動

```powershell
cd backend
venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
# 別の PowerShell
cd frontend
npm run dev
```

ブラウザで `http://localhost:3000/mac-bridge` を開く。

> `systemsetup` が「Full Disk Access」エラーになる場合は、システム設定 → 一般 → 共有 → リモートログイン のスイッチで代用してください。

### 2.1 接続（MVP1）

| # | 手順 | 期待結果 | 結果 |
|---|---|---|---|
| R1 | 表示名 / `<mac-host>` / `<mac-user>` / 22 / `C:\Users\<you>\.ssh\devmirror_mac` / メモした `SHA256:...` を入力して「ホスト鍵を確認して登録」 | カードが追加され、状態「未確認」 | |
| R2 | 「接続テスト」 | 「オンライン」。macOS・Xcode（ビルド番号）・アーキテクチャ・空き容量・シミュレータ一覧・最終接続成功時刻が表示される。値が 2.0 で Mac に表示された値と一致する | |
| R3 | 一度カードを削除し、指紋の末尾 1 文字を変えて登録 | 赤字で「ホスト鍵のフィンガープリントが一致しません」。カードは作られない（その後、正しい指紋で再登録） | |
| R4 | Mac で `sudo systemsetup -setremotelogin off` → 接続テスト | 「オフライン」。「最終接続成功」は R2 の時刻のまま。確認後 `sudo systemsetup -setremotelogin on` | |
| R5 | Mac で `cp ~/.ssh/authorized_keys ~/.ssh/ak.bak && : > ~/.ssh/authorized_keys` → 接続テスト | 「認証失敗」。確認後 `mv ~/.ssh/ak.bak ~/.ssh/authorized_keys` | |
| R6 | 下の R6 スクリプトで DevMirror が記憶するホスト鍵を別の鍵に差し替え → 接続テスト | 「ホスト鍵不一致」。接続は行われない。確認後カードを削除して正しい指紋で再登録 | |
| R7 | Mac で `sudo xcode-select -s /Library/Developer/CommandLineTools` → 接続テスト | 「Xcode がインストールされていないか…」の警告。確認後 `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` | |
| R8 | Mac をスリープ（アップルメニュー → スリープ）→ 接続テスト | 約 10〜60 秒以内に「オフライン」。画面が固まらない | |

**R6 スクリプト（Windows PowerShell、`backend` フォルダで実行。バックエンドは止めなくてよい）**

```powershell
ssh-keygen -q -t ed25519 -f $env:TEMP\fake_host_key    # パスフレーズは空のまま Enter を 2 回
$fake = (Get-Content $env:TEMP\fake_host_key.pub).Split(" ")[1]
venv\Scripts\python -c "import sqlite3,sys; c=sqlite3.connect('devmirror.db'); h=c.execute('select hostname from mac_hosts where id=1').fetchone()[0]; c.execute('update mac_hosts set known_hosts_line=? where id=1', (h+' ssh-ed25519 '+sys.argv[1],)); c.commit(); print('replaced for', h)" $fake
```

（`id=1` は最初に登録した Mac。違う場合は `GET http://localhost:8000/api/v1/mac-bridge/hosts` で id を確認）

### 2.2 ビルド（MVP2）

**テスト用プロジェクトの用意（Mac）**: Xcode → File → New → Project → iOS → App、
Product Name `DemoSwiftUI`、Interface `SwiftUI`、「Include Tests」オン、保存先 `~/Developer`。
Product → Scheme → Manage Schemes… で `DemoSwiftUI` の **Shared** にチェック。

**Windows へコピー**（Windows の PowerShell）:

```powershell
mkdir $env:USERPROFILE\Projects -Force
scp -i $env:USERPROFILE\.ssh\devmirror_mac -r <mac-user>@<mac-host>:Developer/DemoSwiftUI $env:USERPROFILE\Projects\
```

`http://localhost:3000/mac-bridge/builds` を開き、フォルダに `C:\Users\<you>\Projects\DemoSwiftUI` を入力。

| # | 手順 | 期待結果 | 結果 |
|---|---|---|---|
| B1 | 「Xcode プロジェクトを検出」→「Mac へ転送して scheme を取得」 | `DemoSwiftUI.xcodeproj` が検出され、状態が「設定待ち」。scheme に `DemoSwiftUI` が出る。Mac で `ls ~/DevMirrorWorkspaces/*/src` にプロジェクトがあり `.git` が無い | |
| B2 | 構成 Debug・ビルド先「任意の iOS シミュレータ」→「ビルド開始」 | ログが 1 秒ごとに増える。最後に `** BUILD SUCCEEDED **`、状態「成功」、終了コード 0、所要時間が表示 | |
| B3 | 新しく準備し、ビルド先に一覧のシミュレータ（例: iPhone 15）を選んでビルド | 「成功」。ログの `-destination` 相当の行にその UDID | |
| B4 | Windows で `DemoSwiftUI\DemoSwiftUI\ContentView.swift` の `body` 内に `let x: Int = "a"` を追加 → 準備 → ビルド | 状態「失敗」、終了コード 65。「エラー」フィルタで `error: cannot convert value of type 'String'...` の行だけが表示 | |
| B5 | ビルド開始直後に「キャンセル」 | 数秒で「キャンセル」。Mac で `pgrep -fl xcodebuild` が何も表示しない | |
| B6 | `backend/.env` に `MAC_BRIDGE_BUILD_TIMEOUT=5` を書いてバックエンド再起動 → ビルド | 「タイムアウト」。Mac で `pgrep -fl xcodebuild` が空。確認後 .env の行を削除して再起動 | |
| B7 | 終了したビルドで「Mac の作業フォルダを削除」 | Mac で `ls ~/DevMirrorWorkspaces/` からそのビルド ID が消える。他のビルドのフォルダは残る | |
| B8 | ビルド中に Mac の Wi-Fi をオフ | 「エラー」（SSH 接続が切断されました）。「失敗」とは表示されない | |
| B9 | バックエンドを `--host 0.0.0.0` で起動し、**別の PC / スマホ** から `http://<Windows の IP>:8000/api/v1/mac-bridge/hosts` を開く | 403。確認後 `--host 127.0.0.1` に戻す | |

### 2.3 結果の記録

失敗した場合は、画面のエラーメッセージ、ビルドログ（`%USERPROFILE%\.devmirror\mac-bridge\builds\<id>.log`）、
バックエンドのコンソール出力を保存してください。秘密鍵・パスワードは共有しないでください。
