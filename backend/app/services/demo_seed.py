"""
C++ + DX Library デモデータの投入。

実機の DLL スキャンではなく、再現可能なデモ用 Fingerprint を生成する。
同じデモを何度実行しても INC-0001 を複製しない。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DiffModel, FingerprintModel, IncidentModel, ProjectModel
from app.domain.models import (
    ArchitectureInfo,
    CompilerInfo,
    DependencyInfo,
    DependencyStatus,
    EnvironmentFingerprint,
    IncidentStatus,
    OSInfo,
    ProjectInfo,
    RuntimeInfo,
    TestResult,
)
from app.services.ai_analyzer import MockAIAnalyzer
from app.services.diff_engine import DiffEngine

logger = structlog.get_logger(__name__)

DEMO_PROJECT = "DXGame"
DEMO_COMMIT = "abc1234"
DEMO_TAG = "dx-library-demo"


def _fingerprint_a() -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        environment_name="環境A（動作する）",
        os=OSInfo(name="Windows", version="10.0.22631", build="11", edition="Windows 11"),
        architecture=ArchitectureInfo(
            cpu_arch="AMD64",
            physical_cores=8,
            logical_cores=16,
            total_memory_gb=32.0,
        ),
        runtime=RuntimeInfo(python="3.11.8"),
        compiler=CompilerInfo(
            msvc="14.39",
            visual_studio="2022",
            windows_sdk="10.0.22621.0",
            cmake="3.28.1",
        ),
        dependencies=[
            DependencyInfo(
                name="DX Library",
                status=DependencyStatus.PRESENT,
                version="3.24d",
                path=r"C:\DxLib\DxLib.dll",
            ),
            DependencyInfo(name="git", status=DependencyStatus.PRESENT, version="2.44.0"),
        ],
        project=ProjectInfo(
            name=DEMO_PROJECT,
            language="C++",
            git_commit=DEMO_COMMIT,
            git_branch="main",
        ),
        path_entries=[r"C:\DxLib", r"C:\Windows\System32"],
    )


def _fingerprint_b() -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        environment_name="環境B（失敗する）",
        os=OSInfo(name="Windows", version="10.0.22631", build="11", edition="Windows 11"),
        architecture=ArchitectureInfo(
            cpu_arch="AMD64",
            physical_cores=4,
            logical_cores=8,
            total_memory_gb=16.0,
        ),
        runtime=RuntimeInfo(python="3.11.8"),
        compiler=CompilerInfo(
            msvc="14.39",
            visual_studio="2022",
            windows_sdk="10.0.22621.0",
            cmake="3.28.1",
        ),
        dependencies=[
            DependencyInfo(name="DX Library", status=DependencyStatus.MISSING),
            DependencyInfo(name="git", status=DependencyStatus.PRESENT, version="2.44.0"),
        ],
        project=ProjectInfo(
            name=DEMO_PROJECT,
            language="C++",
            git_commit=DEMO_COMMIT,
            git_branch="main",
        ),
        path_entries=[r"C:\Windows\System32"],
    )


def _persist_fingerprint(session: AsyncSession, fp: EnvironmentFingerprint, project_id: int) -> FingerprintModel:
    model = FingerprintModel(
        fingerprint_id=fp.fingerprint_id,
        environment_name=fp.environment_name,
        schema_version=fp.schema_version,
        collected_at=fp.collected_at,
        os_info=fp.os.model_dump() if fp.os else None,
        architecture_info=fp.architecture.model_dump() if fp.architecture else None,
        runtime_info=fp.runtime.model_dump() if fp.runtime else None,
        compiler_info=fp.compiler.model_dump() if fp.compiler else None,
        dependencies=[d.model_dump() for d in fp.dependencies],
        project_info=fp.project.model_dump() if fp.project else None,
        path_entries=fp.path_entries,
        project_id=project_id,
    )
    session.add(model)
    return model


async def seed_dx_library_demo(session: AsyncSession) -> Dict[str, Any]:
    """DX Library デモを投入する。既存なら再利用する。"""
    existing = await session.execute(
        select(IncidentModel).where(IncidentModel.incident_id == "INC-0001")
    )
    incident = existing.scalar_one_or_none()
    if incident:
        logger.info("DX Library デモは既に存在します", incident_id=incident.incident_id)
        return {
            "seeded": False,
            "message": "デモデータは既に投入済みです",
            "incident_id": incident.incident_id,
            "fingerprint_a_id": incident.fingerprint_id,
            "diff_id": incident.diff_id,
        }

    project_result = await session.execute(select(ProjectModel).where(ProjectModel.name == DEMO_PROJECT))
    project = project_result.scalar_one_or_none()
    if project is None:
        project = ProjectModel(
            name=DEMO_PROJECT,
            language="C++",
            description="DX Library を使う C++ デモ。環境Aでは起動し、環境Bでは DLL 欠落で失敗する。",
            git_url="https://example.local/dxgame",
        )
        session.add(project)
        await session.flush()

    fp_a = _fingerprint_a()
    fp_b = _fingerprint_b()
    _persist_fingerprint(session, fp_a, project.id)
    _persist_fingerprint(session, fp_b, project.id)

    diff = DiffEngine().compare(fp_a, fp_b)
    session.add(
        DiffModel(
            diff_id=diff.diff_id,
            fingerprint_a_id=diff.fingerprint_a_id,
            fingerprint_b_id=diff.fingerprint_b_id,
            environment_a_name=diff.environment_a_name,
            environment_b_name=diff.environment_b_name,
            entries=[e.model_dump() for e in diff.entries],
            high_severity_count=diff.high_severity_count,
            medium_severity_count=diff.medium_severity_count,
            low_severity_count=diff.low_severity_count,
        )
    )

    logs = (
        "DXGame.exe を起動しました。\n"
        "ERROR: 指定されたモジュールが見つかりません: DxLib.dll\n"
        "プロセスは終了コード 0xC0000135 で停止しました。"
    )
    diagnosis = await MockAIAnalyzer().analyze(
        environment_diff=diff,
        logs=logs,
        test_results={"result": "FAIL", "command": "DXGame.exe"},
        project_info={"name": DEMO_PROJECT, "language": "C++", "commit": DEMO_COMMIT},
    )

    now = datetime.utcnow().isoformat()
    incident = IncidentModel(
        incident_id="INC-0001",
        project_name=DEMO_PROJECT,
        project_language="C++",
        git_commit=DEMO_COMMIT,
        git_branch="main",
        environment_name=fp_b.environment_name,
        fingerprint_id=fp_b.fingerprint_id,
        diff_id=diff.diff_id,
        test_result=TestResult.FAIL,
        command_executed="DXGame.exe",
        build_result="SUCCESS",
        logs=logs,
        error_messages=["指定されたモジュールが見つかりません: DxLib.dll"],
        stack_traces=[],
        screenshots=[],
        ai_diagnosis=diagnosis.model_dump(mode="json"),
        status=IncidentStatus.REPRODUCED,
        timeline=[
            {"timestamp": now, "event": "環境Aをスキャン", "detail": "DX Library が検出された"},
            {"timestamp": now, "event": "環境Bをスキャン", "detail": "DX Library が欠落している"},
            {"timestamp": now, "event": "Environment Diff を作成", "detail": "依存関係の不一致を検出"},
            {"timestamp": now, "event": "実行失敗を記録", "detail": "DxLib.dll が見つからない"},
            {"timestamp": now, "event": "証拠を保存", "detail": "ログと Diff を Incident Capsule に格納"},
            {"timestamp": now, "event": "AI診断（Mock）", "detail": "証拠と仮説を分離して記録"},
        ],
        tags=[DEMO_TAG, "cpp", "dll"],
        notes="公式デモ: 動作する環境と失敗する環境の差分を示す。原因の断定ではない。",
        project_id=project.id,
    )
    session.add(incident)
    await session.flush()

    logger.info("DX Library デモを投入しました", incident_id=incident.incident_id)
    return {
        "seeded": True,
        "message": "DX Library デモを投入しました",
        "incident_id": incident.incident_id,
        "project": DEMO_PROJECT,
        "fingerprint_a_id": fp_a.fingerprint_id,
        "fingerprint_b_id": fp_b.fingerprint_id,
        "diff_id": diff.diff_id,
        "workflow": [
            "環境Aをスキャン",
            "環境Bをスキャン",
            "Fingerprint を保存",
            "Environment Diff",
            "関連しうる差異を検出",
            "Incident Capsule を作成",
            "ログを保存",
            "AI が証拠を分析（Mock）",
            "インシデントを保存",
        ],
    }
