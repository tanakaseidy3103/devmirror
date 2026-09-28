"""
DevMirror - Environment Scanner Service
Windows / Linux / macOS に対応した環境スキャナー

NOTE: パスワード・APIキー・シークレット・Cookieは絶対に収集しません
"""
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import List, Optional

import psutil
import structlog

from app.domain.models import (
    ArchitectureInfo,
    CompilerInfo,
    DependencyInfo,
    DependencyStatus,
    EnvironmentFingerprint,
    OSInfo,
    ProjectInfo,
    RuntimeInfo,
)

logger = structlog.get_logger(__name__)

# シークレットサニタイズパターン
_SECRET_PATTERNS = re.compile(
    r"(password|passwd|api_?key|secret|token|credential|auth|private_?key|access_?key)",
    re.IGNORECASE,
)

_PATH_SANITIZE_PATTERNS = re.compile(
    r"(Users|user|home)[/\\][^/\\]+",
    re.IGNORECASE,
)


def _sanitize_env_var_name(name: str) -> bool:
    """シークレットっぽい環境変数名をフィルタリング"""
    return bool(_SECRET_PATTERNS.search(name))


def _sanitize_path(path: str) -> str:
    """パスからユーザー名を隠す"""
    return _PATH_SANITIZE_PATTERNS.sub(r"\1/<user>", path)


def _run_command(cmd: List[str], timeout: int = 5) -> Optional[str]:
    """コマンドを安全に実行して出力を返す"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return None


def _get_command_version(cmd: str, *args: str) -> Optional[str]:
    """コマンドのバージョンを取得する"""
    which = shutil.which(cmd)
    if not which:
        return None
    out = _run_command([cmd, *args])
    if out:
        # 最初の行の数値バージョンを抽出
        match = re.search(r"\d+\.\d+[\.\d]*", out)
        return match.group(0) if match else out.split("\n")[0][:64]
    return None


class EnvironmentScanner:
    """
    Environment Fingerprint スキャナー

    安全に環境情報を収集します。
    シークレット・パスワード・APIキーは収集しません。
    """

    def __init__(self, environment_name: str = "Unknown", project_path: Optional[str] = None):
        self.environment_name = environment_name
        self.project_path = project_path
        self._is_windows = sys.platform == "win32"

    def scan(self) -> EnvironmentFingerprint:
        """完全なEnvironment Fingerprintを収集する"""
        logger.info("環境スキャンを開始", environment=self.environment_name)

        fingerprint = EnvironmentFingerprint(
            environment_name=self.environment_name,
            os=self._scan_os(),
            architecture=self._scan_architecture(),
            runtime=self._scan_runtime(),
            compiler=self._scan_compiler(),
            dependencies=self._scan_dependencies(),
            project=self._scan_project(),
            path_entries=self._scan_path(),
        )

        logger.info(
            "環境スキャン完了",
            fingerprint_id=fingerprint.fingerprint_id,
            environment=self.environment_name,
        )
        return fingerprint

    def _scan_os(self) -> OSInfo:
        """OS情報を収集"""
        return OSInfo(
            name=platform.system(),
            version=platform.version(),
            build=platform.release(),
            edition=platform.platform(),
        )

    def _scan_architecture(self) -> ArchitectureInfo:
        """アーキテクチャ・ハードウェア情報を収集"""
        mem = psutil.virtual_memory()
        return ArchitectureInfo(
            cpu_arch=platform.machine(),
            physical_cores=psutil.cpu_count(logical=False),
            logical_cores=psutil.cpu_count(logical=True),
            total_memory_gb=round(mem.total / (1024**3), 2),
        )

    def _scan_runtime(self) -> RuntimeInfo:
        """ランタイムバージョンを収集"""
        return RuntimeInfo(
            python=platform.python_version(),
            node=_get_command_version("node", "--version"),
            php=_get_command_version("php", "--version"),
        )

    def _scan_compiler(self) -> CompilerInfo:
        """コンパイラ情報を収集"""
        info = CompilerInfo(
            gcc=_get_command_version("gcc", "--version"),
            clang=_get_command_version("clang", "--version"),
            cmake=_get_command_version("cmake", "--version"),
        )

        if self._is_windows:
            info.msvc = self._detect_msvc()
            info.visual_studio = self._detect_vs()
            info.windows_sdk = self._detect_windows_sdk()

        return info

    def _detect_msvc(self) -> Optional[str]:
        """MSVCバージョンを検出 (Windows)"""
        cl_path = shutil.which("cl")
        if cl_path:
            out = _run_command(["cl"])
            if out:
                match = re.search(r"(\d{2}\.\d{2})", out)
                return match.group(1) if match else "detected"
        # レジストリからの検出（将来の拡張）
        return None

    def _detect_vs(self) -> Optional[str]:
        """Visual Studioバージョンを検出 (Windows)"""
        common_paths = [
            r"C:\Program Files\Microsoft Visual Studio\2022",
            r"C:\Program Files (x86)\Microsoft Visual Studio\2019",
            r"C:\Program Files (x86)\Microsoft Visual Studio\2017",
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p.split("\\")[-1]
        return None

    def _detect_windows_sdk(self) -> Optional[str]:
        """Windows SDKバージョンを検出"""
        sdk_path = r"C:\Program Files (x86)\Windows Kits\10\Include"
        if os.path.exists(sdk_path):
            try:
                versions = [d for d in os.listdir(sdk_path) if re.match(r"\d+\.\d+", d)]
                return max(versions) if versions else None
            except PermissionError:
                return "detected (access denied)"
        return None

    def _scan_dependencies(self) -> List[DependencyInfo]:
        """プロジェクト依存関係を検出"""
        deps: List[DependencyInfo] = []

        # DX Libraryの検出 (デモ用)
        deps.extend(self._detect_dx_library())

        # Gitの検出
        git_ver = _get_command_version("git", "--version")
        deps.append(DependencyInfo(
            name="git",
            status=DependencyStatus.PRESENT if git_ver else DependencyStatus.MISSING,
            version=git_ver,
        ))

        # Dockerの検出
        docker_ver = _get_command_version("docker", "--version")
        deps.append(DependencyInfo(
            name="docker",
            status=DependencyStatus.PRESENT if docker_ver else DependencyStatus.MISSING,
            version=docker_ver,
        ))

        return deps

    def _detect_dx_library(self) -> List[DependencyInfo]:
        """DX Library の検出 (C++ デモ用)"""
        deps: List[DependencyInfo] = []
        dll_paths = [
            r"C:\DxLib",
            r"C:\DxLib_VC",
            r"C:\Program Files\DxLib",
        ]
        if self.project_path:
            dll_paths.insert(0, self.project_path)

        found = False
        found_path = None
        for base in dll_paths:
            dll = os.path.join(base, "DxLib.dll")
            if os.path.exists(dll):
                found = True
                found_path = _sanitize_path(dll)
                break

        deps.append(DependencyInfo(
            name="DX Library",
            status=DependencyStatus.PRESENT if found else DependencyStatus.MISSING,
            path=found_path,
        ))
        return deps

    def _scan_project(self) -> Optional[ProjectInfo]:
        """プロジェクト情報を収集"""
        if not self.project_path or not os.path.exists(self.project_path):
            return None

        project = ProjectInfo()

        # Gitコミット
        commit = _run_command(
            ["git", "-C", self.project_path, "rev-parse", "--short", "HEAD"]
        )
        project.git_commit = commit

        branch = _run_command(
            ["git", "-C", self.project_path, "rev-parse", "--abbrev-ref", "HEAD"]
        )
        project.git_branch = branch

        # プロジェクト名 (ディレクトリ名)
        project.name = os.path.basename(self.project_path)

        # 言語の推測
        project.language = self._detect_language()

        return project

    def _detect_language(self) -> Optional[str]:
        """ファイル拡張子からプロジェクト言語を推測"""
        if not self.project_path:
            return None
        ext_counts: dict = {}
        try:
            for root, _, files in os.walk(self.project_path):
                # node_modules, .git などを除外
                if any(skip in root for skip in [".git", "node_modules", "__pycache__", ".venv"]):
                    continue
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext:
                        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        except PermissionError:
            return None

        lang_map = {
            ".py": "Python", ".cpp": "C++", ".c": "C",
            ".ts": "TypeScript", ".js": "JavaScript",
            ".php": "PHP", ".go": "Go", ".rs": "Rust",
        }
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1]):
            if ext in lang_map:
                return lang_map[ext]
        return None

    def _scan_path(self) -> List[str]:
        """PATH環境変数を安全に収集（サニタイズ済み）"""
        raw_path = os.environ.get("PATH", "")
        entries = raw_path.split(os.pathsep)
        return [_sanitize_path(e) for e in entries if e][:50]  # 最大50エントリ
