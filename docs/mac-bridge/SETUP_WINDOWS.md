# Windows 側のセットアップ

## 1. OpenSSH クライアント

Windows 11 には標準で入っています。確認:

```powershell
ssh -V
```

無い場合: 設定 → システム → オプション機能 → 「OpenSSH クライアント」を追加。

## 2. DevMirror 専用の鍵を作成

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\devmirror_mac -C devmirror
```

- パスフレーズを付けた場合は `ssh-agent` に登録してください（DevMirror は対話入力をしません）:
  ```powershell
  Get-Service ssh-agent | Set-Service -StartupType Manual
  Start-Service ssh-agent
  ssh-add $env:USERPROFILE\.ssh\devmirror_mac
  ```
- `devmirror_mac.pub` の内容を Mac の `~/.ssh/authorized_keys` に追加する（SETUP_MAC.md 参照）。

## 3. DevMirror の設定（任意）

`backend/.env`（既定値。必要な場合だけ変更）:

```
MAC_BRIDGE_SSH_BINARY=ssh
MAC_BRIDGE_CONNECT_TIMEOUT=10
MAC_BRIDGE_COMMAND_TIMEOUT=60
MAC_BRIDGE_MIN_FREE_GB=20
# ビルド対象として選べるフォルダ（JSON 配列）。未設定ならユーザーのホーム配下
MAC_BRIDGE_PROJECT_ROOTS=["C:/Users/you/Projects"]
MAC_BRIDGE_MAX_UPLOAD_MB=500
MAC_BRIDGE_UPLOAD_TIMEOUT=600
MAC_BRIDGE_BUILD_TIMEOUT=1800
```

バックエンドは必ず localhost で起動してください（Mac Bridge は localhost 以外からの要求を拒否します）:

```powershell
cd backend
venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

known_hosts は `%USERPROFILE%\.devmirror\mac-bridge\` に DevMirror 専用として保存されます。
ユーザーの `~/.ssh/known_hosts` や `~/.ssh/config` は読みません。

## 4. 登録

1. バックエンドとフロントエンドを起動し、サイドバー「Mac接続管理」（`/mac-bridge`）を開く。
2. 表示名・ホスト名・ユーザー・鍵パス（例 `C:\Users\you\.ssh\devmirror_mac`）・フィンガープリントを入力。
3. 「ホスト鍵を確認して登録」→「接続テスト」。macOS / Xcode / シミュレータが表示されれば完了。
