"""
DevMirror - AI Analyzer Service

証拠に基づいた構造化診断を提供します。

IMPORTANT:
- AIは証拠なしに原因を断言しません
- Observed Evidence / Detected Difference / Hypothesis / Suggested Investigation を明確に分離します
- OpenAI APIが未設定の場合はMockAnalyzerを使用します
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import structlog

from app.core.config import settings
from app.domain.models import AIDiagnosis, EnvironmentDiff

logger = structlog.get_logger(__name__)


class BaseAIAnalyzer(ABC):
    """AI Analyzerのインターフェース"""

    @abstractmethod
    async def analyze(
        self,
        environment_diff: Optional[EnvironmentDiff],
        logs: str,
        test_results: Optional[Dict[str, Any]],
        project_info: Optional[Dict[str, Any]],
        incident_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AIDiagnosis:
        """
        証拠を分析してAI診断結果を返す

        Args:
            environment_diff: 環境差異情報
            logs: 収集されたログ
            test_results: テスト結果
            project_info: プロジェクト情報
            incident_history: 類似インシデントの履歴

        Returns:
            AIDiagnosis: 構造化された診断結果
        """
        ...


class MockAIAnalyzer(BaseAIAnalyzer):
    """
    MockAIAnalyzer

    [MOCK] OpenAI APIが未設定の場合に使用するモック実装。
    実際のAI分析は行いません。デモ・開発用途のみ。
    """

    async def analyze(
        self,
        environment_diff: Optional[EnvironmentDiff],
        logs: str,
        test_results: Optional[Dict[str, Any]],
        project_info: Optional[Dict[str, Any]],
        incident_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AIDiagnosis:
        logger.warning("[MOCK] MockAIAnalyzer を使用しています。OpenAI APIキーを設定してください。")

        observed_evidence: List[str] = []
        detected_differences: List[str] = []
        hypotheses: List[str] = []
        suggested_investigations: List[str] = []
        data_sources: List[str] = []

        # Diffから証拠を収集
        if environment_diff:
            data_sources.append("Environment Diff")
            relevant = [e for e in environment_diff.entries if e.potentially_relevant]
            for entry in relevant:
                observed_evidence.append(
                    f"環境 '{environment_diff.environment_a_name}' の {entry.field}: {entry.value_a}"
                )
                if entry.value_b:
                    observed_evidence.append(
                        f"環境 '{environment_diff.environment_b_name}' の {entry.field}: {entry.value_b}"
                    )
                detected_differences.append(
                    f"{entry.category} / {entry.field}: {entry.status.value} (重要度: {entry.severity.value})"
                )
                hypotheses.append(
                    f"{entry.field} の差異が実行失敗に関連している可能性があります（仮説・証拠不十分）"
                )
                suggested_investigations.append(
                    f"{entry.field} の設定・インストール状態を両環境で確認してください"
                )

        # ログから証拠を収集
        if logs:
            data_sources.append("Runtime Logs")
            if "error" in logs.lower() or "exception" in logs.lower():
                observed_evidence.append("ログにエラーまたは例外が含まれています")

        confidence = 0.3 if not environment_diff else min(
            0.7, 0.3 + len(detected_differences) * 0.1
        )

        return AIDiagnosis(
            summary=(
                "[MOCK] これはモック診断です。実際のAI分析にはOpenAI APIキーが必要です。"
                f" {len(detected_differences)}件の差異を検出しました。"
            ),
            observed_evidence=observed_evidence,
            detected_differences=detected_differences,
            hypotheses=hypotheses,
            suggested_investigations=suggested_investigations,
            confidence=confidence,
            data_sources_used=data_sources,
            is_mock=True,
        )


class OpenAIAnalyzer(BaseAIAnalyzer):
    """
    OpenAI API を使用した実装

    証拠ベースの診断を提供します。
    AIへの指示: 証拠なしに原因を断言しないこと。
    """

    SYSTEM_PROMPT = """あなたはDevMirrorのAI診断エンジンです。
    
役割:
- 提供された証拠（Environment Diff、ログ、テスト結果）を分析する
- 観測された証拠と仮説を明確に分離する
- 証拠なしに根本原因を断言しない

出力形式（JSON）:
{
  "summary": "簡潔な診断サマリー",
  "observed_evidence": ["実際に観測された証拠のリスト"],
  "detected_differences": ["検出された差異のリスト"],
  "hypotheses": ["証拠に基づく仮説（断定しない）"],
  "suggested_investigations": ["具体的な調査提案"],
  "confidence": 0.0〜1.0
}

重要なルール:
1. "Root Cause: X" と断言しない
2. 証拠リストは実際に観測されたもののみ
3. 仮説は「〜の可能性があります」という形式で表現
4. 証拠が不足している場合は confidence を低く設定する
"""

    async def analyze(
        self,
        environment_diff: Optional[EnvironmentDiff],
        logs: str,
        test_results: Optional[Dict[str, Any]],
        project_info: Optional[Dict[str, Any]],
        incident_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AIDiagnosis:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai パッケージがインストールされていません")
            return await MockAIAnalyzer().analyze(
                environment_diff, logs, test_results, project_info, incident_history
            )

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # コンテキストの構築
        context_parts: List[str] = []
        data_sources: List[str] = []

        if environment_diff:
            data_sources.append("Environment Diff")
            context_parts.append(f"## Environment Diff\n{environment_diff.model_dump_json(indent=2)}")

        if logs:
            data_sources.append("Runtime Logs")
            truncated_logs = logs[:3000] if len(logs) > 3000 else logs
            context_parts.append(f"## Logs\n{truncated_logs}")

        if test_results:
            data_sources.append("Test Results")
            context_parts.append(f"## Test Results\n{json.dumps(test_results, indent=2, ensure_ascii=False)}")

        if project_info:
            data_sources.append("Project Info")
            context_parts.append(f"## Project Info\n{json.dumps(project_info, indent=2, ensure_ascii=False)}")

        user_content = "\n\n".join(context_parts)

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=2048,
            )

            result = json.loads(response.choices[0].message.content)

            return AIDiagnosis(
                summary=result.get("summary", ""),
                observed_evidence=result.get("observed_evidence", []),
                detected_differences=result.get("detected_differences", []),
                hypotheses=result.get("hypotheses", []),
                suggested_investigations=result.get("suggested_investigations", []),
                confidence=float(result.get("confidence", 0.0)),
                data_sources_used=data_sources,
                is_mock=False,
            )

        except Exception as e:
            logger.error("OpenAI API エラー", error=str(e))
            return await MockAIAnalyzer().analyze(
                environment_diff, logs, test_results, project_info, incident_history
            )


def get_ai_analyzer() -> BaseAIAnalyzer:
    """設定に基づいて適切なAIAnalyzerを返す"""
    if settings.OPENAI_API_KEY:
        logger.info("OpenAIAnalyzer を使用します")
        return OpenAIAnalyzer()
    logger.warning("OpenAI APIキーが未設定のため MockAIAnalyzer を使用します")
    return MockAIAnalyzer()
