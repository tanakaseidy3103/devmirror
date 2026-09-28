"""
GitHub 連携の抽象。MVP では実 API を呼ばない。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class GitHubClient(ABC):
    @abstractmethod
    async def comment_on_pull_request(self, repo: str, pr_number: int, body: str) -> Dict[str, Any]:
        ...


class MockGitHubClient(GitHubClient):
    """[MOCK] 実 GitHub API は呼び出さない。"""

    async def comment_on_pull_request(self, repo: str, pr_number: int, body: str) -> Dict[str, Any]:
        return {
            "provider": "MockGitHubClient",
            "implemented": False,
            "repo": repo,
            "pr_number": pr_number,
            "preview": body[:500],
        }
