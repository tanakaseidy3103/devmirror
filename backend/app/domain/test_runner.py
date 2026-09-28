"""
DevMirror - Test Runner Abstraction
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from app.domain.models import TestResult


class TestRunner(ABC):
    """
    テストエンジンの抽象インターフェース
    VMProvider上でテストを実行し、結果を解析する
    """

    @abstractmethod
    async def run(
        self,
        instance_id: str,
        project_path: str,
        command: str,
        env_vars: Optional[Dict[str, str]] = None
    ) -> tuple[TestResult, str, str]:
        """
        テストを実行し、(TestResult, logs, error_message) を返す
        """
        pass
