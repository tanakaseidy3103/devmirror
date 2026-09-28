"""
DevMirror - Environment Diff Engine

2つのEnvironment Fingerprintを比較し、差異を構造化して返す。

NOTE: 差異を「Root Cause」とは断言しません。
      「Potentially Relevant Difference」として提示します。
"""
from typing import Any, List, Optional, Tuple

import structlog

from app.domain.models import (
    DependencyStatus,
    DiffEntry,
    DiffSeverity,
    DiffStatus,
    EnvironmentDiff,
    EnvironmentFingerprint,
)

logger = structlog.get_logger(__name__)


def _compare_values(a: Any, b: Any) -> DiffStatus:
    """2値を比較してDiffStatusを返す"""
    if a is None and b is None:
        return DiffStatus.UNKNOWN
    if a is None:
        return DiffStatus.MISSING
    if b is None:
        return DiffStatus.ADDED
    if str(a).strip().lower() == str(b).strip().lower():
        return DiffStatus.MATCH
    return DiffStatus.CHANGED


def _severity_for_category(category: str, field: str, status: DiffStatus) -> DiffSeverity:
    """
    カテゴリとフィールドに基づいて重要度を決定する

    HIGH: コンパイラ・ランタイム・依存関係の不一致
    MEDIUM: OSバージョン・アーキテクチャの差異
    LOW: CPU数・メモリ・その他
    """
    if status == DiffStatus.MATCH:
        return DiffSeverity.LOW

    high_fields = {
        "dependency", "compiler.msvc", "compiler.visual_studio",
        "runtime.python", "runtime.node", "compiler.gcc",
    }
    medium_fields = {
        "os.version", "os.name", "architecture.cpu_arch",
        "compiler.cmake", "runtime.php",
    }

    full_field = f"{category}.{field}"
    if any(h in full_field for h in high_fields) or category == "dependency":
        return DiffSeverity.HIGH
    if any(m in full_field for m in medium_fields):
        return DiffSeverity.MEDIUM
    return DiffSeverity.LOW


class DiffEngine:
    """
    Environment Diff エンジン

    2つのEnvironment Fingerprintを比較し、
    構造化されたDiff結果を生成します。
    """

    def compare(
        self,
        fp_a: EnvironmentFingerprint,
        fp_b: EnvironmentFingerprint,
    ) -> EnvironmentDiff:
        """
        2つのFingerprintを比較してEnvironmentDiffを返す

        Args:
            fp_a: 基準環境（例: 動作する環境A）
            fp_b: 比較環境（例: 失敗する環境B）

        Returns:
            EnvironmentDiff: 構造化された差異情報
        """
        logger.info(
            "Environment Diff を実行",
            env_a=fp_a.environment_name,
            env_b=fp_b.environment_name,
        )

        entries: List[DiffEntry] = []

        # OS の比較
        entries.extend(self._compare_os(fp_a, fp_b))

        # アーキテクチャの比較
        entries.extend(self._compare_architecture(fp_a, fp_b))

        # ランタイムの比較
        entries.extend(self._compare_runtime(fp_a, fp_b))

        # コンパイラの比較
        entries.extend(self._compare_compiler(fp_a, fp_b))

        # 依存関係の比較
        entries.extend(self._compare_dependencies(fp_a, fp_b))

        # 重要度カウント
        high = sum(1 for e in entries if e.severity == DiffSeverity.HIGH and e.status != DiffStatus.MATCH)
        medium = sum(1 for e in entries if e.severity == DiffSeverity.MEDIUM and e.status != DiffStatus.MATCH)
        low = sum(1 for e in entries if e.severity == DiffSeverity.LOW and e.status != DiffStatus.MATCH)

        diff = EnvironmentDiff(
            fingerprint_a_id=fp_a.fingerprint_id,
            fingerprint_b_id=fp_b.fingerprint_id,
            environment_a_name=fp_a.environment_name,
            environment_b_name=fp_b.environment_name,
            entries=entries,
            high_severity_count=high,
            medium_severity_count=medium,
            low_severity_count=low,
        )

        logger.info(
            "Diff 完了",
            diff_id=diff.diff_id,
            high=high,
            medium=medium,
            low=low,
        )
        return diff

    def _make_entry(
        self,
        category: str,
        field: str,
        val_a: Any,
        val_b: Any,
        note: Optional[str] = None,
    ) -> DiffEntry:
        """DiffEntryを生成するヘルパー"""
        status = _compare_values(val_a, val_b)
        severity = _severity_for_category(category, field, status)
        # 高重要度の不一致は「潜在的に関連あり」とマーク
        potentially_relevant = (
            severity == DiffSeverity.HIGH and status != DiffStatus.MATCH
        )
        return DiffEntry(
            field=field,
            category=category,
            status=status,
            severity=severity,
            value_a=str(val_a) if val_a is not None else None,
            value_b=str(val_b) if val_b is not None else None,
            note=note,
            potentially_relevant=potentially_relevant,
        )

    def _compare_os(
        self,
        fp_a: EnvironmentFingerprint,
        fp_b: EnvironmentFingerprint,
    ) -> List[DiffEntry]:
        """OS情報を比較"""
        entries = []
        os_a = fp_a.os
        os_b = fp_b.os

        for field in ["name", "version", "build"]:
            val_a = getattr(os_a, field, None) if os_a else None
            val_b = getattr(os_b, field, None) if os_b else None
            entries.append(self._make_entry("os", field, val_a, val_b))

        return entries

    def _compare_architecture(
        self,
        fp_a: EnvironmentFingerprint,
        fp_b: EnvironmentFingerprint,
    ) -> List[DiffEntry]:
        """アーキテクチャ情報を比較"""
        entries = []
        arch_a = fp_a.architecture
        arch_b = fp_b.architecture

        for field in ["cpu_arch", "physical_cores", "logical_cores", "total_memory_gb"]:
            val_a = getattr(arch_a, field, None) if arch_a else None
            val_b = getattr(arch_b, field, None) if arch_b else None
            entries.append(self._make_entry("architecture", field, val_a, val_b))

        return entries

    def _compare_runtime(
        self,
        fp_a: EnvironmentFingerprint,
        fp_b: EnvironmentFingerprint,
    ) -> List[DiffEntry]:
        """ランタイムバージョンを比較"""
        entries = []
        rt_a = fp_a.runtime
        rt_b = fp_b.runtime

        for field in ["python", "node", "php", "java", "dotnet"]:
            val_a = getattr(rt_a, field, None) if rt_a else None
            val_b = getattr(rt_b, field, None) if rt_b else None
            entries.append(self._make_entry("runtime", field, val_a, val_b))

        return entries

    def _compare_compiler(
        self,
        fp_a: EnvironmentFingerprint,
        fp_b: EnvironmentFingerprint,
    ) -> List[DiffEntry]:
        """コンパイラ情報を比較"""
        entries = []
        cc_a = fp_a.compiler
        cc_b = fp_b.compiler

        for field in ["msvc", "visual_studio", "windows_sdk", "gcc", "clang", "cmake"]:
            val_a = getattr(cc_a, field, None) if cc_a else None
            val_b = getattr(cc_b, field, None) if cc_b else None
            entries.append(self._make_entry("compiler", field, val_a, val_b))

        return entries

    def _compare_dependencies(
        self,
        fp_a: EnvironmentFingerprint,
        fp_b: EnvironmentFingerprint,
    ) -> List[DiffEntry]:
        """依存関係を比較"""
        entries = []

        deps_a = {dep.name: dep for dep in fp_a.dependencies}
        deps_b = {dep.name: dep for dep in fp_b.dependencies}

        all_names = set(deps_a.keys()) | set(deps_b.keys())

        for name in sorted(all_names):
            dep_a = deps_a.get(name)
            dep_b = deps_b.get(name)

            val_a = dep_a.status.value if dep_a else None
            val_b = dep_b.status.value if dep_b else None

            note = None
            if dep_a and dep_b:
                if dep_a.version and dep_b.version and dep_a.version != dep_b.version:
                    note = f"バージョン不一致: {dep_a.version} vs {dep_b.version}"

            status = _compare_values(val_a, val_b)
            if dep_a and dep_b:
                if dep_a.status == DependencyStatus.PRESENT and dep_b.status == DependencyStatus.MISSING:
                    status = DiffStatus.MISSING
                elif dep_a.status == DependencyStatus.MISSING and dep_b.status == DependencyStatus.PRESENT:
                    status = DiffStatus.ADDED
                elif (
                    dep_a.status == DependencyStatus.PRESENT
                    and dep_b.status == DependencyStatus.PRESENT
                    and dep_a.version != dep_b.version
                ):
                    # Dependency presence alone is insufficient: versions and
                    # resolved locations can differ while both are PRESENT.
                    status = DiffStatus.CHANGED
                elif dep_a.path != dep_b.path and (dep_a.path or dep_b.path):
                    status = DiffStatus.CHANGED

            severity = DiffSeverity.HIGH if status != DiffStatus.MATCH else DiffSeverity.LOW
            potentially_relevant = status != DiffStatus.MATCH

            entries.append(DiffEntry(
                field=name,
                category="dependency",
                status=status,
                severity=severity,
                value_a=(f"{val_a} ({dep_a.version})" if dep_a and dep_a.version else val_a),
                value_b=(f"{val_b} ({dep_b.version})" if dep_b and dep_b.version else val_b),
                note=note,
                potentially_relevant=potentially_relevant,
            ))

        return entries
