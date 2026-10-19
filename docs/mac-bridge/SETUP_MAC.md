# Mac 側のセットアップ

> 対象: DevMirror から接続する **自分の** Mac。SSH をインターネットに公開しないでください。

## 1. Xcode

1. App Store から Xcode をインストールし、一度起動してライセンスに同意する。
2. ターミナルで実行:
   ```sh
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
   xcodebuild -version
   xcrun simctl list devices available
   ```
   シミュレータが無い場合は Xcode → Settings → Platforms から iOS を追加する。

## 2. リモートログイン（SSH）

1. システム設定 → 一般 → 共有 → **リモートログイン** をオン。
2. 「アクセスを許可」を **自分のユーザーのみ** にする（推奨: 将来はビルド専用ユーザー）。

## 3. 公開鍵の登録

Windows で作成した公開鍵（`devmirror_mac.pub` の 1 行）を追記する:

```sh
mkdir -p ~/.ssh && chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys   # 公開鍵の 1 行を貼り付けて保存
chmod 600 ~/.ssh/authorized_keys
```

## 4. パスワード認証の無効化（鍵ログインを確認した後に実施）

`/etc/ssh/sshd_config.d/100-devmirror.conf` を作成:

```
PasswordAuthentication no
KbdInteractiveAuthentication no
```

その後、リモートログインを一度オフ → オンにする。

## 5. ホスト鍵フィンガープリントの確認

**Mac 本体の画面で** 実行し、表示された `SHA256:...` を DevMirror の登録フォームに入力する:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

ネットワーク越しに取得した値をそのまま信用しないこと（なりすまし対策）。

## 6. 接続先アドレス

- 同じ LAN: `ホスト名.local`（システム設定 → 共有 の上部に表示）または固定 IP。
- 外出先から: ルーターのポート開放は **しない**。Tailscale などの VPN 上のアドレスを登録する（今後対応）。
