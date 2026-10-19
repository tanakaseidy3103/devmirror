# Mac Bridge テスト計画

## 1. 自動テスト（Mac 不要）

```powershell
cd backend
venv\Scripts\python -m pytest tests/test_mac_bridge.py -v
```

`run_process`（ssh / ssh-keyscan の起動）だけをモックし、それ以外は実コードを通す。

| 観点 | テスト |
|---|---|
| ホスト設定の検証 | `test_hostname_*`, `test_username_validation`, `test_fingerprint_validation`, `test_register_validation_errors` |
| 指紋計算が OpenSSH と一致 | `test_fingerprint_matches_openssh`（実 `ssh-keygen` を使用） |
| 未知・変更されたホスト鍵の拒否 | `test_verify_host_key_rejects_unknown`, `test_register_rejects_wrong_fingerprint`, `test_changed_host_key_marks_mismatch_and_keeps_last_good` |
| 認証失敗 / 切断 / オフライン | `test_classify_ssh_failure` |
| タイムアウト時の kill | `test_run_process_timeout_kills`（実プロセス）, `test_offline_and_timeout` |
| Xcode 未インストール | `test_parse_probe_without_xcode` |
| ssh の安全なオプション・固定スクリプト | `test_register_and_test_connection` |
| API | 登録・接続テスト・切断・削除・重複名 |

## 2. 実機 Mac での結合テスト（手動）

> **注意: 2026-10-19 時点で、実機 Mac での実行はまだ行っていません。** 実施したら結果欄に記録してください。

| # | 手順 | 期待結果 | 結果 |
|---|---|---|---|
| R1 | 正しい指紋で登録 | 201、状態「未確認」 | |
| R2 | 接続テスト | 「オンライン」。macOS・Xcode・シミュレータ・空き容量が表示される | |
| R3 | 指紋の 1 文字を変えて登録 | 409「一致しません」 | |
| R4 | Mac のリモートログインをオフにして接続テスト | 「オフライン」。最終接続成功時刻は変わらない | |
| R5 | `authorized_keys` から鍵を削除して接続テスト | 「認証失敗」 | |
| R6 | DevMirror の DB 上の known_hosts 行を別ホストの鍵に差し替えて接続テスト | 「ホスト鍵不一致」で接続中止 | |
| R7 | `xcode-select` を CommandLineTools に切り替えて接続テスト | Xcode 未検出の警告 | |
| R8 | Mac をスリープさせて接続テスト | タイムアウト以内に「オフライン」 | |
