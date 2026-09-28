# DevMirror アーキテクチャ

## 原則

- ドメインは DX Library に依存しない
- 証拠・差異・仮説・調査提案を混ぜない
- 未実装は Mock または「未実装」と明示する
- シークレットを保存しない

## モジュール

| パス | 責務 |
| --- | --- |
| `app/services/scanner.py` | ホスト環境の Fingerprint 収集 |
| `app/services/diff_engine.py` | 2 Fingerprint の構造化比較 |
| `app/services/incident_manager.py` | Incident Capsule のライフサイクル |
| `app/services/ai_analyzer.py` | 証拠ベース診断 |
| `app/services/vm_provider.py` | MockVMProvider |
| `app/services/test_runner.py` | CommandTestRunner |
| `app/services/demo_seed.py` | DX Library 公式デモ |
| `app/services/github_integration.py` | MockGitHubClient |

## データ

SQLite テーブル: `projects` `fingerprints` `diffs` `incidents`

Fingerprint schema_version = `1.0`

## プロバイダ拡張

`VMProvider` に `VirtualBoxProvider` / `DockerProvider` を後から実装する。MVP では Mock のみ。
