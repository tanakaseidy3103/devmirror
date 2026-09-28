/**
 * DevMirror - UI日本語化マッピング
 *
 * バックエンドが返す識別子（enum値・フィールド名・カテゴリ名）を
 * UI表示用の日本語ラベルに変換します。
 *
 * 変換表に無い値はそのまま表示します（未知の値を勝手に要約しないため）。
 */

import type { DiffSeverity, DiffStatus, IncidentStatus, TestResult } from "@/lib/api";

// ─────────────────────────────────────────────
// Diff ステータス
// ─────────────────────────────────────────────

export const diffStatusLabels: Record<DiffStatus, string> = {
  MATCH: "一致",
  CHANGED: "変更",
  MISSING: "欠落",
  ADDED: "追加",
  UNKNOWN: "不明",
};

export const diffSeverityLabels: Record<DiffSeverity, string> = {
  HIGH: "高",
  MEDIUM: "中",
  LOW: "低",
};

export function diffStatusLabel(status: string): string {
  return diffStatusLabels[status as DiffStatus] ?? status;
}

export function diffSeverityLabel(severity: string): string {
  return diffSeverityLabels[severity as DiffSeverity] ?? severity;
}

// ─────────────────────────────────────────────
// インシデント / テスト結果
// ─────────────────────────────────────────────

export const incidentStatusLabels: Record<IncidentStatus, string> = {
  OPEN: "オープン",
  INVESTIGATING: "調査中",
  REPRODUCED: "再現済み",
  RESOLVED: "解決済み",
  ARCHIVED: "アーカイブ",
};

export const testResultLabels: Record<TestResult, string> = {
  PASS: "成功",
  FAIL: "失敗",
  ERROR: "エラー",
  TIMEOUT: "タイムアウト",
  UNKNOWN: "不明",
};

export function testResultLabel(result: string): string {
  return testResultLabels[result as TestResult] ?? result;
}

// ─────────────────────────────────────────────
// 依存関係ステータス
// ─────────────────────────────────────────────

export const dependencyStatusLabels: Record<string, string> = {
  PRESENT: "インストール済み",
  MISSING: "未インストール",
  VERSION_MISMATCH: "バージョン不一致",
  UNKNOWN: "不明",
};

export function dependencyStatusLabel(status: string): string {
  return dependencyStatusLabels[status] ?? status;
}

// ─────────────────────────────────────────────
// Diff カテゴリ
// ─────────────────────────────────────────────

export const diffCategoryLabels: Record<string, string> = {
  os: "OS",
  architecture: "アーキテクチャ",
  runtime: "ランタイム",
  compiler: "コンパイラ",
  dependency: "依存関係",
};

export function diffCategoryLabel(category: string): string {
  return diffCategoryLabels[category] ?? category;
}

// ─────────────────────────────────────────────
// Diff フィールド名
// ─────────────────────────────────────────────

const diffFieldLabels: Record<string, string> = {
  // OS
  name: "名称",
  version: "バージョン",
  build: "ビルド",
  edition: "エディション",
  // アーキテクチャ
  cpu_arch: "CPUアーキテクチャ",
  physical_cores: "物理コア数",
  logical_cores: "論理コア数",
  total_memory_gb: "メモリ容量 (GB)",
  // ランタイム
  python: "Python",
  node: "Node.js",
  php: "PHP",
  java: "Java",
  dotnet: ".NET",
  // コンパイラ
  msvc: "MSVC",
  visual_studio: "Visual Studio",
  windows_sdk: "Windows SDK",
  gcc: "GCC",
  clang: "Clang",
  cmake: "CMake",
};

export function diffFieldLabel(field: string): string {
  return diffFieldLabels[field] ?? field;
}

/**
 * Diff の値を日本語ラベルに変換します。
 *
 * 依存関係カテゴリのみ、値の先頭にステータスが含まれるため
 * `PRESENT (3.24d)` → `インストール済み (3.24d)` のように変換します。
 * バージョン部分はそのまま（捏造しない）表示します。
 */
export function diffValueLabel(category: string, value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (category !== "dependency") return value;

  const match = /^([A-Z_]+)(\s*\(.*\))?$/.exec(value);
  if (!match) return value;
  const [, status, version] = match;
  const statusLabel = dependencyStatusLabels[status];
  if (!statusLabel) return value;
  return version ? `${statusLabel}${version}` : statusLabel;
}

// ─────────────────────────────────────────────
// AI 診断のデータソース
// ─────────────────────────────────────────────

const dataSourceLabels: Record<string, string> = {
  "Environment Diff": "環境Diff",
  "Runtime Logs": "実行ログ",
  "Test Results": "テスト結果",
  "Project Info": "プロジェクト情報",
};

export function dataSourceLabel(source: string): string {
  return dataSourceLabels[source] ?? source;
}

// ─────────────────────────────────────────────
// Replay プロバイダー
// ─────────────────────────────────────────────

export const providerLabels: Record<string, string> = {
  MockVMProvider: "MockVMProvider（仮想化なし）",
  VirtualBoxProvider: "VirtualBoxProvider（実VM）",
  DockerProvider: "DockerProvider（将来）",
};

export function providerLabel(provider: string): string {
  return providerLabels[provider] ?? provider;
}

// ─────────────────────────────────────────────
// Fingerprint 追加フィールド
// ─────────────────────────────────────────────

const runtimeFieldLabels: Record<string, string> = {
  python: "Python",
  node: "Node.js",
  php: "PHP",
  java: "Java",
  dotnet: ".NET",
};

const compilerFieldLabels: Record<string, string> = {
  msvc: "MSVC",
  visual_studio: "Visual Studio",
  windows_sdk: "Windows SDK",
  gcc: "GCC",
  clang: "Clang",
  cmake: "CMake",
};

export function runtimeFieldLabel(field: string): string {
  return runtimeFieldLabels[field] ?? field;
}

export function compilerFieldLabel(field: string): string {
  return compilerFieldLabels[field] ?? field;
}
