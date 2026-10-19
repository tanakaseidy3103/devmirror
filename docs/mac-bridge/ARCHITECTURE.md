# DevMirror Mac Bridge — アーキテクチャ

## 1. 既存 DevMirror の調査結果（フェーズ1）

| 領域 | 場所 | Mac Bridge との関係 |
|---|---|---|
| FastAPI エントリポイント | `backend/app/main.py`, `api/v1/router.py` | `/api/v1/mac-bridge` ルーターを追加 |
| 設定 | `backend/app/core/config.py`（pydantic-settings, `.env`） | `MAC_BRIDGE_*` を追加 |
| DB | SQLite + SQLAlchemy async（`core/database.py`, `db/models.py`）。`core/migrations.py` は ADD COLUMN のみ | 新テーブル `mac_hosts`（`create_all` で作成。既存テーブルは無変更） |
| VM Provider | `domain/providers.py` の `VMProvider`、`services/qemu_provider.py` / `virtualbox_provider.py` / `vm_provider.py`（Mock）、`vm_factory.py` | **使わない**（下記 2 章） |
| Scanner / Fingerprint | `services/scanner.py`, `FingerprintModel` | MVP4 以降、Mac の調査結果を Fingerprint に変換して Diff Engine で比較 |
| Diff Engine | `services/diff_engine.py` | Windows ⇔ Mac の環境比較（Agent 2）で再利用 |
| Incident Capsule / Replay | `services/incident_manager.py`, `TestRunModel`, Evidence | MVP2 以降、ビルド結果を TestRun / Evidence として記録 |
| AI Analyzer | `services/ai_analyzer.py`（OpenAI） | MVP4 で Ollama プロバイダを追加（既存は維持） |
| テスト | `backend/tests`（pytest。導入前 159 件成功） | `tests/test_mac_bridge.py` を追加 |

## 2. なぜ Mac を VM として扱わないか

`VMProvider` は「作成・起動・停止・破棄・スナップショット」を前提にしている。
実機 Mac は **ユーザー本人が所有し、長期間存在する計算機** であり、DevMirror が
起動・破棄してはならない。そのため別の抽象「リモートビルドホスト」を設けた。
QEMU / VirtualBox のコードには一切手を入れていない。

```
            ┌──────────────── Windows（DevMirror） ────────────────┐
 Next.js /mac-bridge ──HTTP──► FastAPI /api/v1/mac-bridge
                                     │
                                     ▼
                         services/mac_bridge.py
                         ├ 入力検証（ホスト名 / ユーザー / 指紋 / 鍵パス）
                         ├ verify_host_key … ssh-keyscan + 指紋照合（登録時）
                         ├ probe_host      … 固定スクリプトのみ実行
                         └ run_process     … argv 直接起動・タイムアウト・kill
                                     │  OpenSSH クライアント（ssh.exe）
                                     ▼  LAN / VPN のみ
            ┌───────────────────── Mac（実機） ─────────────────────┐
              sshd（鍵認証のみ） → sw_vers / xcodebuild / xcrun simctl / df
```

## 3. データモデル（MVP1）

`mac_hosts`: 表示名・ホスト名・ポート・ユーザー・**鍵ファイルのパス**（鍵本体は保存しない）・
ピン留めしたホスト鍵指紋と known_hosts 行・有効フラグ・状態・最終確認 / 最終接続成功時刻・
最後に成功した調査結果（JSON）。

状態: `unknown` / `online` / `offline` / `auth_failed` / `host_key_mismatch` / `error` / `disconnected`

## 4. API（MVP1）

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/v1/mac-bridge/hosts` | 登録済み Mac 一覧 |
| POST | `/api/v1/mac-bridge/hosts` | 登録（指紋不一致は 409、到達不能は 502、入力不正は 400） |
| POST | `/api/v1/mac-bridge/hosts/{id}/test` | 接続テスト + 環境調査 |
| POST | `/api/v1/mac-bridge/hosts/{id}/disconnect` | 無効化（常駐セッションは持たない） |
| DELETE | `/api/v1/mac-bridge/hosts/{id}` | 登録削除 |

**コマンド文字列を受け取る API は存在しない。**

## 5. 今後の拡張（未実装）

- **MVP2 ビルド**: `BuildJob`（構造化パラメータ: project_id / scheme / configuration / destination）。
  プロジェクトは Mac の `~/DevMirrorWorkspaces/<job_id>/` へ転送し、
  `xcodebuild` の argv はサーバ側で組み立てる（scheme は `xcodebuild -list -json` の結果と照合）。
  ログは SSE で逐次配信、ホストごとに同時実行 1 件。
- **MVP3 テスト**: `xcodebuild test -resultBundlePath` → `xcrun xcresulttool` で合否を抽出。
- **MVP4 AI**: Ollama（ローカル）プロバイダ。ツールは backend 定義の関数のみ、出力は Pydantic で検証。
- **Incident 統合**: 既存 `TestRunModel` / Evidence に Mac 情報（macOS / Xcode / SDK / scheme）を紐づける。
- **BYOM**: `mac_hosts` に `owner_id` を追加し、ユーザー・ホスト・認証情報・プロジェクト・タスク・成果物の権限を分離。
  クラウド Mac 等は「リモートビルドホスト」の別実装として追加できる。
