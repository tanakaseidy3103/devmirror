import pytest

from app.domain.models import DependencyInfo, DependencyStatus
from app.services.ai_analyzer import MockAIAnalyzer
from app.services.diff_engine import DiffEngine
from tests.test_diff_and_sanitize import _fp


@pytest.mark.asyncio
async def test_mock_analyzer_does_not_claim_root_cause():
    a = _fp(
        environment_name="環境A",
        dependencies=[DependencyInfo(name="DX Library", status=DependencyStatus.PRESENT)],
    )
    b = _fp(
        environment_name="環境B",
        dependencies=[DependencyInfo(name="DX Library", status=DependencyStatus.MISSING)],
    )
    diff = DiffEngine().compare(a, b)
    diagnosis = await MockAIAnalyzer().analyze(
        environment_diff=diff,
        logs="ERROR: DxLib.dll missing",
        test_results={"result": "FAIL"},
        project_info={"name": "DXGame"},
    )
    assert diagnosis.is_mock is True
    assert "Root Cause" not in diagnosis.summary
    assert diagnosis.observed_evidence
    assert diagnosis.hypotheses
    assert all("可能性があります" in h or "仮説" in h for h in diagnosis.hypotheses)
    assert "Environment Diff" in diagnosis.data_sources_used
    assert "Runtime Logs" in diagnosis.data_sources_used
