"""
DevMirror - Mock VM Provider
"""
import asyncio
import uuid
from typing import Any, Dict, List, Optional

import structlog

from app.domain.providers import VMProvider

logger = structlog.get_logger(__name__)


class MockVMProvider(VMProvider):
    """
    MockVMProvider

    MVP用・デモ用のダミー仮想環境プロバイダー。
    実際にはVMを作成せず、指定秒数待機して成功を返します。
    """

    def __init__(self, delay_seconds: float = 0.05):
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._delay = delay_seconds

    async def create(self, environment_name: str, config: Dict[str, Any]) -> str:
        """モックインスタンスの作成"""
        instance_id = f"mock-vm-{uuid.uuid4().hex[:8]}"
        self._instances[instance_id] = {
            "name": environment_name,
            "status": "CREATED",
            "config": config,
        }
        logger.info("[MockVM] VMを作成しました", instance_id=instance_id, env=environment_name)
        await asyncio.sleep(self._delay)
        return instance_id

    async def start(self, instance_id: str) -> bool:
        """モックVMの起動"""
        if instance_id not in self._instances:
            return False
        self._instances[instance_id]["status"] = "RUNNING"
        logger.info("[MockVM] VMを起動しました", instance_id=instance_id)
        await asyncio.sleep(self._delay)
        return True

    async def stop(self, instance_id: str) -> bool:
        """モックVMの停止"""
        if instance_id not in self._instances:
            return False
        self._instances[instance_id]["status"] = "STOPPED"
        logger.info("[MockVM] VMを停止しました", instance_id=instance_id)
        await asyncio.sleep(self._delay)
        return True

    async def destroy(self, instance_id: str) -> bool:
        """モックVMの破棄"""
        if instance_id in self._instances:
            del self._instances[instance_id]
            logger.info("[MockVM] VMを破棄しました", instance_id=instance_id)
            await asyncio.sleep(self._delay)
            return True
        return False

    async def copy_project(self, instance_id: str, local_path: str, remote_path: str) -> bool:
        """ファイルのコピーをシミュレーション"""
        logger.info(
            "[MockVM] プロジェクトをコピーしました",
            instance_id=instance_id,
            src=local_path,
            dest=remote_path,
        )
        await asyncio.sleep(self._delay)
        return True

    async def install_dependencies(self, instance_id: str, dependencies: List[Dict[str, Any]]) -> bool:
        """依存関係のインストールをシミュレーション"""
        logger.info("[MockVM] 依存関係をインストール中...", instance_id=instance_id)
        for dep in dependencies:
            logger.debug(f"[MockVM] インストール: {dep.get('name')}")
            await asyncio.sleep(self._delay)
        logger.info("[MockVM] 依存関係のインストール完了")
        return True

    async def run_command(self, instance_id: str, command: str) -> tuple[int, str, str]:
        """コマンド実行のシミュレーション"""
        logger.info("[MockVM] コマンド実行", instance_id=instance_id, cmd=command)
        await asyncio.sleep(self._delay)
        
        # デモ用の特定コマンドの振る舞い
        if "make test" in command or "pytest" in command:
            # 失敗をシミュレート
            return 1, "テストを実行しています...\n[失敗] Test_DXLibrary_Init", "エラー: PATH に dx_library が見つかりません"

        return 0, f"実行しました: {command}\n成功しました。", ""

    async def collect_logs(self, instance_id: str, remote_path: str) -> str:
        """ログ収集のシミュレーション"""
        await asyncio.sleep(self._delay)
        return (
            f"[MockVM] {remote_path} から収集したシミュレーションログです。\n"
            "情報: アプリケーションを起動しました。\n"
            "エラー: 検索パス内に DxLib.dll が見つかりませんでした。"
        )

    async def take_screenshot(self, instance_id: str) -> Optional[bytes]:
        """スクリーンショットのモック"""
        logger.info("[MockVM] スクリーンショットを撮影しました", instance_id=instance_id)
        return b"mock-screenshot-data"
