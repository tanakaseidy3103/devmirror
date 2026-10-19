# DevMirror Mac Bridge — アーキテクチャ

## 1. 既存 DevMirror の調査結果（フェーズ1）

| 領域 | 場所 | Mac Bridge との関係 |
|---|---|---|
| FastAPI エントリポイント | `backend/app/main.py`, `api/v1/router.py` | `/api/v1/mac-bridge` ルーターを追加 |
| 設定 | `backend/app/core/config.py`（pydantic-settings, `.env`） | `MAC_BRIDGE_*` を追加 |
| DB | SQLite + SQLAlchemy async（`core/database.py`, `db/models.py`）。`core/migrations.py` は ADD COLUMN のみ | 新テーブル `mac_hosts` / `mac_builds`（`create_all` で作成。既存テーブルは無変更） |
| VM Provider | `domain/providers.py` の `VMProvider`、`services/qemu_provider.py` / `virtualbox_provider.py` / `vm_provider.py`（Mock）、`vm_factory.py` | **使わない**（2 章） |
| Scanner / Fingerprint | `services/scanner.py`, `FingerprintModel` | 今後、Mac の調査結果を Fingerprint に変換して Diff Engine で比較 |
| Diff Engine | `services/diff_engine.py` | Windows ⇔ Mac の環境比較（Agent 2）で再利用 |
| Incident Capsule / Replay | `services/incident_manager.py`, `TestRunModel`, Evidence | 今後、ビルド結果を TestRun / Evidence として記録 |
| AI Analyzer | `services/ai_analyzer.py`（OpenAI） | MVP4 で Ollama プロバイダを追加（既存は維持） |
| テスト | `backend/tests`（pytest。導入前 159 件成功） | `test_mac_bridge.py` / `test_mac_build.py` を追加 |

## 2. なぜ Mac を VM として扱わないか

`VMProvider` は「作成・起動・停止・破棄・スナップショット」を前提にしている。
実機 Mac は **ユーザー本人が所有し、長期間存在する計算機** であり、DevMirror が
起動・破棄してはならない。そのため別の抽象「リモートビルドホスト」を設けた。
QEMU / VirtualBox のコードには一切手を入れていない。

```
            ┌──────────────── Windows（DevMirror） ────────────────┐
 Next.js /mac-bridge, /mac-bridge/builds ──HTTP(localhost のみ)──► FastAPI /api/v1/mac-bridge
                                     │
              ┌──────────────────────┴───────────────────────┐
              ▼                                              ▼
   services/mac_bridge.py（接続）              services/mac_build.py（ビルド）
   ├ 入力検証・DNS 解決後の IP 検査             ├ プロジェクト検出（許可フォルダ内のみ）
   ├ verify_host_key（登録時の指紋照合）        ├ tar.gz 作成（.git 等・シンボリックリンク除外）
   ├ ssh_argv_for（検査済み IP + HostKeyAlias） ├ 固定テンプレートのリモートコマンド
   ├ probe_host（固定の調査スクリプト）         ├ ログの逐次書き込み・タイムアウト・キャンセル
   └ run_process（argv 直接起動・kill）         └ ジョブ状態を DB に記録
                                     │  OpenSSH クライアント（ssh.exe）
                                     ▼  LAN / VPN のみ
            ┌───────────────────── Mac（実機） ─────────────────────┐
              sshd（鍵認証のみ）
              ~/DevMirrorWorkspaces/<build_id>/src   … 転送されたプロジェクト
              ~/DevMirrorWorkspaces/<build_id>/DerivedData
              xcodebuild / xcrun simctl / sw_vers
```

## 3. データモデル

**`mac_hosts`**: 表示名・ホスト名・ポート・ユーザー・**鍵ファイルのパス**（鍵本体は保存しない）・
ピン留めしたホスト鍵指紋と known_hosts 行・有効フラグ・状態・最終確認 / 最終接続成功時刻・
最後に成功した調査結果（JSON）。

**`mac_builds`**: ビルド ID（uuid4 hex。Mac 側の作業フォルダ名）・Mac・元フォルダ・
プロジェクト / ワークスペース・候補 scheme / configuration・選択値・宛先・状態・終了コード・
エラー行（最大 20）・警告数・macOS / Xcode バージョン・開始 / 終了時刻・所要時間・作業フォルダ削除済みフラグ。
ログ本体は `%USERPROFILE%\.devmirror\mac-bridge\builds\<id>.log`。

ビルドの状態遷移:

```
preparing ──► ready ──► running ──► succeeded / failed / timeout / cancelled / error
    │           │
    └► error    └► cancelled（作業フォルダ削除時）
（バックエンド再起動で実行中タスクが消えた場合は interrupted）
```

## 4. API

すべて **localhost からの要求のみ** 受け付ける（それ以外は 403）。
**コマンド文字列を受け取る API は存在しない。**

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/hosts` | 登録済み Mac 一覧 |
| POST | `/hosts` | 登録（指紋不一致 409、到達不能 502、入力不正 400） |
| POST | `/hosts/{id}/test` | 接続テスト + 環境調査 |
| POST | `/hosts/{id}/disconnect` | 無効化 |
| DELETE | `/hosts/{id}` | 登録削除 |
| POST | `/projects/inspect` | Windows のフォルダから .xcodeproj / .xcworkspace を検出 |
| POST | `/builds` | 準備: 転送 + `xcodebuild -list -json`（非同期、202） |
| GET | `/builds`, `/builds/{id}` | 履歴・詳細 |
| GET | `/builds/{id}/log?offset=N` | ログの差分取得（1 秒ごとにポーリング） |
| POST | `/builds/{id}/start` | ビルド開始（scheme / configuration / destination は候補と照合） |
| POST | `/builds/{id}/cancel` | キャンセル（ローカル ssh を kill + Mac 側 xcodebuild に SIGTERM） |
| POST | `/builds/{id}/cleanup` | Mac の作業フォルダ削除 |

（パスはすべて `/api/v1/mac-bridge` 配下）

## 5. ビルドで Mac 上に実行されるコマンド（全種類）

`<id>` はサーバ生成の 32 桁 hex のみ。`'…'` は `shlex.quote` 済みの値。

| 用途 | コマンド |
|---|---|
| 転送 | `rm -rf "$HOME/DevMirrorWorkspaces/<id>" && mkdir -p …/src && tar -xzf - -C …/src` |
| scheme 取得 | `cd …/src && xcodebuild -list -json -workspace|-project '<container>'` |
| ビルド | `cd …/src && echo $$ > …/pid && exec xcodebuild -workspace|-project '<container>' -scheme '<scheme>' -configuration '<cfg>' -destination '<dest>' -derivedDataPath ../DerivedData CODE_SIGNING_ALLOWED=NO build` |
| キャンセル | `test -f …/pid && kill -TERM "$(cat …/pid)"` |
| 削除 | `rm -rf "$HOME/DevMirrorWorkspaces/<id>"` |
| 調査 | `PROBE_SCRIPT`（sw_vers / uname / xcodebuild -version / xcode-select -p / simctl list / df / command -v） |

## 6. 今後の拡張（未実装・承認待ち）

- **MVP3 テスト**: `xcodebuild test -resultBundlePath` → `xcrun xcresulttool` で合否を抽出。
- **MVP4 AI**: Ollama（ローカル）プロバイダ。ツールは backend 定義の関数のみ、出力は Pydantic で検証。
- **Incident 統合**: 既存 `TestRunModel` / Evidence に `mac_builds` の情報を紐づける。
- **成果物ダウンロード**: 許可した拡張子（.app を zip 化、.xcresult 等）のみ。
- **BYOM**: `mac_hosts` / `mac_builds` に `owner_id` を追加し、ユーザー・ホスト・認証情報・プロジェクト・タスク・成果物の権限を分離。
  クラウド Mac 等は「リモートビルドホスト」の別実装として追加できる。
