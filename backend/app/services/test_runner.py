"""
DevMirror - Command Test Runner
"""
from typing import Optional, Dict
import structlog

from app.domain.test_runner import TestRunner
from app.domain.models import TestResult
from app.domain.providers import VMProvider

logger = structlog.get_logger(__name__)


class CommandTestRunner(TestRunner):
    """
    汎用的なコマンド実行テストランナー。
    VMProviderを使用してコマンドを実行し、終了コードで成否を判定する。
    """
    def __init__(self, vm_provider: VMProvider):
        self.vm_provider = vm_provider

    async def run(
        self,
        instance_id: str,
        project_path: str,
        command: str,
        env_vars: Optional[Dict[str, str]] = None
    ) -> tuple[TestResult, str, str]:
        
        logger.info("[TestRunner] テストコマンドを実行します", instance_id=instance_id, command=command)
        
        # 実VM(Windows ゲスト)ではドライブをまたぐ cd が失敗するため /d を付ける。
        # POSIX 環境（/app など）では /d を付けない。
        if len(project_path) > 1 and project_path[1] == ":":
            full_command = f'cd /d "{project_path}" && {command}'
        else:
            full_command = f"cd {project_path} && {command}"
        
        try:
            returncode, stdout, stderr = await self.vm_provider.run_command(instance_id, full_command)
            
            logs = stdout + "\n" + stderr if stderr else stdout
            error_msg = stderr if returncode != 0 else ""
            
            if returncode == 0:
                result = TestResult.PASS
            else:
                result = TestResult.FAIL
                
            logger.info("[TestRunner] テスト完了", instance_id=instance_id, result=result.value)
            return result, logs, error_msg
            
        except Exception as e:
            logger.error("[TestRunner] テスト実行中にエラー発生", error=str(e))
            return TestResult.ERROR, "", str(e)
