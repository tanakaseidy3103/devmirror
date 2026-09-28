"""
DevMirror - アプリケーション設定
"""
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # アプリケーション
    APP_NAME: str = "DevMirror"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # データベース
    DATABASE_URL: str = "sqlite+aiosqlite:///./devmirror.db"

    # AI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # セキュリティ
    ALLOWED_COMMAND_TIMEOUT: int = 30
    MAX_LOG_SIZE_BYTES: int = 1_048_576  # 1MB

    # VM Provider: "mock" / "virtualbox" / "qemu"
    VM_PROVIDER: str = "mock"

    # QEMU（ブラウザから VM に入れる方式）
    # 空なら PATH から自動検出する
    QEMU_BINARY: str = ""
    QEMU_IMG_BINARY: str = ""
    # 全環境の親となる基準ディスク（qcow2）
    QEMU_BASE_IMAGE: str = ""
    # 起動時に CD として挿す ISO（Alpine のようにインストール不要で動く distro 用）
    QEMU_BOOT_ISO: str = ""
    # 各環境の overlay（差分ディスク）を置くディレクトリ
    QEMU_VM_DIR: str = ""
    # VNC のポート。envA=5901, envB=5902, envA のように連番で割り当てる
    QEMU_VNC_BASE_PORT: int = 5901
    QEMU_MEMORY_MB: int = 2048
    QEMU_CPUS: int = 2
    # "kvm"（ハードウェア加速）または "tcg"（エミュレーション）
    QEMU_ACCEL: str = "kvm"
    # 起動完了を待つ秒数
    QEMU_BOOT_TIMEOUT: int = 180
    # 停止を待つ秒数
    QEMU_STOP_TIMEOUT: int = 30
    # 3 環境の名前
    QEMU_VM_NAMES: List[str] = ["envA", "envB", "envC"]

    # VirtualBox
    # 空なら OS ごとの標準パスを自動検出する
    VBOXMANAGE_PATH: str = ""
    # Guest Additions を入れた基準 VM（クローン元）
    VBOX_BASE_VM: str = "DevMirror-Base"
    # "linked"（高速・ディスク共有）または "all"（完全複製）
    VBOX_CLONE_MODE: str = "linked"
    VBOX_CLONE_PREFIX: str = "DevMirror"
    VBOX_MEMORY_MB: int = 2048
    VBOX_CPUS: int = 2
    # VM 起動完了（"powered up"）を待つ秒数
    VBOX_BOOT_TIMEOUT: int = 180
    # Guest Additions が応答するまで待つ秒数
    VBOX_GUEST_READY_TIMEOUT: int = 120
    # guestcontrol の認証情報
    VBOX_GUEST_USERNAME: str = ""
    VBOX_GUEST_PASSWORD: str = ""
    # ホスト側 DX プロジェクトの場所（VM へコピーする元）
    VBOX_PROJECT_PATH: str = ""
    # ゲスト側の配置先
    VBOX_GUEST_PATH: str = r"C:\DevMirror\app"
    # 再実行のたびに VM を破棄しない（状態を残したい場合）
    VBOX_KEEP_VM: bool = False

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]


settings = Settings()
