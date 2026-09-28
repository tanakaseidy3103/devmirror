"""
DevMirror - VM Provider Abstraction
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class VMProvider(ABC):
    """
    仮想化・コンテナ環境の抽象インターフェース
    """

    @abstractmethod
    async def create(self, environment_name: str, config: Dict[str, Any]) -> str:
        """VMを作成し、インスタンスIDを返す"""
        pass

    @abstractmethod
    async def start(self, instance_id: str) -> bool:
        """VMを起動する"""
        pass

    @abstractmethod
    async def stop(self, instance_id: str) -> bool:
        """VMを停止する"""
        pass

    @abstractmethod
    async def destroy(self, instance_id: str) -> bool:
        """VMを破棄する"""
        pass

    @abstractmethod
    async def copy_project(self, instance_id: str, local_path: str, remote_path: str) -> bool:
        """プロジェクトファイルをVMにコピーする"""
        pass

    @abstractmethod
    async def install_dependencies(self, instance_id: str, dependencies: List[Dict[str, Any]]) -> bool:
        """依存関係をインストールする"""
        pass

    @abstractmethod
    async def run_command(self, instance_id: str, command: str) -> tuple[int, str, str]:
        """コマンドを実行し、(returncode, stdout, stderr) を返す"""
        pass

    @abstractmethod
    async def collect_logs(self, instance_id: str, remote_path: str) -> str:
        """ログを収集して文字列として返す"""
        pass

    @abstractmethod
    async def take_screenshot(self, instance_id: str) -> Optional[bytes]:
        """スクリーンショットを撮影する（サポートされている場合）"""
        pass
