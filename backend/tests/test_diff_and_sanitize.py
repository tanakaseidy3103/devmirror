from app.domain.models import (
    ArchitectureInfo,
    CompilerInfo,
    DependencyInfo,
    DependencyStatus,
    EnvironmentFingerprint,
    OSInfo,
)
from app.services.diff_engine import DiffEngine
from app.services.scanner import _sanitize_path, _SECRET_PATTERNS


def _fp(**kwargs) -> EnvironmentFingerprint:
    defaults = dict(
        environment_name="A",
        os=OSInfo(name="Windows", version="11"),
        architecture=ArchitectureInfo(cpu_arch="AMD64"),
        compiler=CompilerInfo(msvc="14.39"),
        dependencies=[],
    )
    defaults.update(kwargs)
    return EnvironmentFingerprint(**defaults)


def test_dx_library_missing_is_high_and_relevant():
    a = _fp(
        environment_name="環境A",
        dependencies=[
            DependencyInfo(name="DX Library", status=DependencyStatus.PRESENT, path=r"C:\DxLib\DxLib.dll"),
        ],
    )
    b = _fp(
        environment_name="環境B",
        dependencies=[
            DependencyInfo(name="DX Library", status=DependencyStatus.MISSING),
        ],
    )
    diff = DiffEngine().compare(a, b)
    dx = next(e for e in diff.entries if e.field == "DX Library")
    assert dx.status.value == "MISSING"
    assert dx.severity.value == "HIGH"
    assert dx.potentially_relevant is True
    assert dx.note is None or "Root Cause" not in (dx.note or "")


def test_matching_os_is_match():
    a = _fp()
    b = _fp(environment_name="B")
    diff = DiffEngine().compare(a, b)
    os_name = next(e for e in diff.entries if e.field == "name" and e.category == "os")
    assert os_name.status.value == "MATCH"


def test_secret_names_are_detected():
    assert _SECRET_PATTERNS.search("OPENAI_API_KEY")
    assert _SECRET_PATTERNS.search("password")
    assert not _SECRET_PATTERNS.search("PATH")


def test_path_username_is_redacted():
    sanitized = _sanitize_path(r"C:\Users\eduardo\DxLib")
    assert "eduardo" not in sanitized
    assert "<user>" in sanitized
