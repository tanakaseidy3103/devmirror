"""
DevMirror - ドメインモデル定義
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class DiffStatus(str, Enum):
    MATCH = "MATCH"
    CHANGED = "CHANGED"
    MISSING = "MISSING"
    ADDED = "ADDED"
    UNKNOWN = "UNKNOWN"


class DiffSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    REPRODUCED = "REPRODUCED"
    RESOLVED = "RESOLVED"
    ARCHIVED = "ARCHIVED"


class TestResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class ReplayStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    MISMATCH = "MISMATCH"


# ─────────────────────────────────────────────
# Environment Fingerprint
# ─────────────────────────────────────────────

class OSInfo(BaseModel):
    name: str
    version: str
    build: Optional[str] = None
    edition: Optional[str] = None


class ArchitectureInfo(BaseModel):
    cpu_arch: str  # x64, x86, arm64
    physical_cores: Optional[int] = None
    logical_cores: Optional[int] = None
    total_memory_gb: Optional[float] = None


class RuntimeInfo(BaseModel):
    python: Optional[str] = None
    node: Optional[str] = None
    php: Optional[str] = None
    java: Optional[str] = None
    dotnet: Optional[str] = None


class CompilerInfo(BaseModel):
    msvc: Optional[str] = None
    visual_studio: Optional[str] = None
    windows_sdk: Optional[str] = None
    gcc: Optional[str] = None
    clang: Optional[str] = None
    cmake: Optional[str] = None


class DependencyStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    UNKNOWN = "UNKNOWN"


class DependencyInfo(BaseModel):
    name: str
    status: DependencyStatus
    version: Optional[str] = None
    path: Optional[str] = None


class ProjectInfo(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None


class EnvironmentFingerprint(BaseModel):
    """
    Environment Fingerprint v1
    環境情報を安全に収集した構造化データ
    
    NOTE: パスワード・APIキー・シークレットは絶対に含まれません
    """
    schema_version: str = "1.0"
    fingerprint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    environment_name: str = "Unknown"

    os: Optional[OSInfo] = None
    architecture: Optional[ArchitectureInfo] = None
    runtime: Optional[RuntimeInfo] = None
    compiler: Optional[CompilerInfo] = None
    dependencies: List[DependencyInfo] = Field(default_factory=list)
    project: Optional[ProjectInfo] = None

    # PATH (サニタイズ済み)
    path_entries: List[str] = Field(default_factory=list)

    # 追加メタデータ
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Environment Diff
# ─────────────────────────────────────────────

class DiffEntry(BaseModel):
    """環境差異の1エントリ"""
    field: str
    category: str  # os, runtime, compiler, dependency, etc.
    status: DiffStatus
    severity: DiffSeverity
    value_a: Optional[Any] = None
    value_b: Optional[Any] = None
    note: Optional[str] = None
    # 重要: 差異が原因と断言しない
    potentially_relevant: bool = False


class EnvironmentDiff(BaseModel):
    """2つのEnvironment Fingerprintの差異比較結果"""
    diff_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    fingerprint_a_id: str
    fingerprint_b_id: str
    environment_a_name: str
    environment_b_name: str
    entries: List[DiffEntry] = Field(default_factory=list)
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0


# ─────────────────────────────────────────────
# AI Diagnosis
# ─────────────────────────────────────────────

class AIDiagnosis(BaseModel):
    """
    AI診断結果
    
    NOTE: AIは証拠なしに原因を断言しません。
    Observed Evidence / Detected Difference / Hypothesis / Suggested Investigation を分離します。
    """
    diagnosis_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    summary: str
    observed_evidence: List[str] = Field(default_factory=list)
    detected_differences: List[str] = Field(default_factory=list)
    hypotheses: List[str] = Field(default_factory=list)
    suggested_investigations: List[str] = Field(default_factory=list)
    
    # 0.0 〜 1.0 (低い = 証拠不足)
    confidence: float = 0.0
    
    # 分析に使用したデータのリスト
    data_sources_used: List[str] = Field(default_factory=list)
    
    is_mock: bool = False


# ─────────────────────────────────────────────
# Incident Capsule
# ─────────────────────────────────────────────

class IncidentCapsule(BaseModel):
    """
    Incident Capsule - 再現可能なインシデントの完全な記録
    """
    incident_id: str  # INC-XXXX 形式
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # プロジェクト情報
    project_name: str
    project_language: Optional[str] = None
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    
    # 環境
    environment_name: str
    fingerprint_id: Optional[str] = None
    diff_id: Optional[str] = None
    
    # テスト結果
    test_result: TestResult = TestResult.UNKNOWN
    command_executed: Optional[str] = None
    build_result: Optional[str] = None
    
    # 証拠
    logs: str = ""
    error_messages: List[str] = Field(default_factory=list)
    stack_traces: List[str] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)
    
    # AI診断
    ai_diagnosis: Optional[AIDiagnosis] = None
    
    # ステータス
    status: IncidentStatus = IncidentStatus.OPEN
    
    # タイムライン
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    
    # タグ・メモ
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
