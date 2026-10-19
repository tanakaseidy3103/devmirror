# Mac Bridge セキュリティ設計

| 脅威 | 対策（MVP1 で実装済み） |
|---|---|
| なりすまし Mac（MITM） | 登録時、ユーザーが Mac 本体で確認した SHA256 指紋と `ssh-keyscan` の結果を照合し、不一致なら登録拒否。以降は `StrictHostKeyChecking=yes` + DevMirror 専用 known_hosts（DB を正として毎回書き出し）。ホスト鍵が変わった場合は `host_key_mismatch` として中止。自動信頼（TOFU）や検証の無効化は一切しない |
| 認証情報の漏えい | パスワードは扱わない（`BatchMode=yes`, `PasswordAuthentication=no`）。秘密鍵は保存せずパスのみ保存。API レスポンスに鍵パス・known_hosts 行を含めない |
| 任意コマンド実行 | リモートで実行するのはコード内の固定スクリプト `PROBE_SCRIPT`（読み取り専用）のみ。コマンドを受け取る API は無い。LLM にシェルを渡さない |
| ローカルのコマンドインジェクション | シェルを使わず argv で起動。ホスト名・ユーザー名は正規表現で検証（先頭 `-` 不可）、`--` で宛先とオプションを分離。`-F none` でユーザーの ssh_config（ProxyCommand 等）を無視 |
| インターネットへの公開 | グローバル IP の登録を既定で拒否（`MAC_BRIDGE_ALLOW_PUBLIC_HOSTS=false`）。LAN / VPN のみを想定 |
| ハング・資源枯渇 | 接続タイムアウトと全体タイムアウト。超過時はプロセスを kill。ホストごとに接続テストは同時 1 件。出力は `MAX_LOG_SIZE_BYTES` で切り詰め |

## 既知の制限

- DNS 名は解決せずに許可するため、公開 IP に解決される名前は検出しない。
- DevMirror API 自体に認証は無い（既存の DevMirror と同じ）。バックエンドは localhost でのみ公開すること。BYOM 対応時にユーザー認証を追加する。
- Mac 側の権限制限（専用ユーザー・作業ディレクトリの限定）は MVP2 のビルド実装時に追加する。推奨: ビルド専用の macOS ユーザーを作成する。
