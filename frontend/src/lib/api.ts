/**
 * DevMirror - API クライアント
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}/api/v1${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`APIエラー (${res.status}): ${error}`);
  }

  return res.json() as Promise<T>;
}

/**
 * catch節からユーザー向けメッセージを取り出します。
 * Error 以外（文字列など）が投げられた場合も表示できるようにします。
 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

// ─────────────────────────────────────────────
// 型定義
// ─────────────────────────────────────────────

export type DiffStatus = "MATCH" | "CHANGED" | "MISSING" | "ADDED" | "UNKNOWN";
export type DiffSeverity = "LOW" | "MEDIUM" | "HIGH";
export type IncidentStatus = "OPEN" | "INVESTIGATING" | "REPRODUCED" | "RESOLVED" | "ARCHIVED";
export type TestResult = "PASS" | "FAIL" | "ERROR" | "TIMEOUT" | "UNKNOWN";

export interface DashboardStats {
  projects: number;
  environments: number;
  incidents: {
    total: number;
    reproduced: number;
    failed_tests: number;
    open: number;
  };
  recent_incidents: RecentIncident[];
}

export interface RecentIncident {
  incident_id: string;
  project_name: string;
  environment_name: string;
  status: IncidentStatus;
  test_result: TestResult;
  created_at: string;
}

export interface Fingerprint {
  fingerprint_id: string;
  environment_name: string;
  schema_version: string;
  collected_at: string;
  os?: { name: string; version: string; build?: string; edition?: string };
  architecture?: {
    cpu_arch: string;
    physical_cores?: number;
    logical_cores?: number;
    total_memory_gb?: number;
  };
  runtime?: { python?: string; node?: string; php?: string; java?: string; dotnet?: string };
  compiler?: {
    msvc?: string;
    visual_studio?: string;
    windows_sdk?: string;
    gcc?: string;
    clang?: string;
    cmake?: string;
  };
  dependencies?: { name: string; status: string; version?: string; path?: string }[];
  project?: { name?: string; language?: string; git_commit?: string; git_branch?: string };
  path_entries?: string[];
}

export interface DiffEntry {
  field: string;
  category: string;
  status: DiffStatus;
  severity: DiffSeverity;
  value_a?: string;
  value_b?: string;
  note?: string;
  potentially_relevant: boolean;
}

export interface Diff {
  diff_id: string;
  created_at: string;
  environment_a_name: string;
  environment_b_name: string;
  fingerprint_a_id: string;
  fingerprint_b_id: string;
  high_severity_count: number;
  medium_severity_count: number;
  low_severity_count: number;
  entries: DiffEntry[];
}

export interface AIDiagnosis {
  diagnosis_id: string;
  created_at: string;
  summary: string;
  observed_evidence: string[];
  detected_differences: string[];
  hypotheses: string[];
  suggested_investigations: string[];
  confidence: number;
  data_sources_used: string[];
  is_mock: boolean;
}

export interface TimelineEvent {
  timestamp: string;
  event: string;
  detail: string;
}

export interface Incident {
  incident_id: string;
  created_at: string;
  updated_at: string;
  project_name: string;
  project_language?: string;
  environment_name: string;
  git_commit?: string;
  git_branch?: string;
  test_result: TestResult;
  command_executed?: string;
  logs: string;
  error_messages: string[];
  stack_traces: string[];
  screenshots: string[];
  fingerprint_id?: string;
  diff_id?: string;
  ai_diagnosis?: AIDiagnosis;
  status: IncidentStatus;
  timeline: TimelineEvent[];
  tags: string[];
  notes: string;
}

export interface Project {
  id: number;
  name: string;
  language?: string;
  description?: string;
  git_url?: string;
  created_at: string;
}

export interface VmStatus {
  provider: string;
  simulated: boolean;
  available: boolean;
  detail: string;
  base_vm: string;
  clone_mode?: string;
  clone_prefix?: string;
  memory_mb?: number;
  cpus?: number;
  project_path?: string;
  guest_path?: string;
  vboxmanage_path?: string;
  resolved_vboxmanage_path?: string;
  guest_username?: string;
  base_vm_found?: boolean;
  registered_vms?: string[];
}

// ─────────────────────────────────────────────
// API 関数
// ─────────────────────────────────────────────

export const api = {
  // Dashboard
  getDashboardStats: () => apiFetch<DashboardStats>("/dashboard/stats"),

  // Scanner
  scanEnvironment: (data: { environment_name: string; project_path?: string }) =>
    apiFetch<Fingerprint>("/scanner/scan", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Fingerprints
  listFingerprints: () => apiFetch<Fingerprint[]>("/fingerprints/"),
  getFingerprint: (id: string) => apiFetch<Fingerprint>(`/fingerprints/${id}`),

  // Diffs
  compareFingerprints: (data: { fingerprint_a_id: string; fingerprint_b_id: string }) =>
    apiFetch<Diff>("/diffs/compare", { method: "POST", body: JSON.stringify(data) }),
  listDiffs: () => apiFetch<Diff[]>("/diffs/"),
  getDiff: (id: string) => apiFetch<Diff>(`/diffs/${id}`),

  // Incidents
  createIncident: (data: Partial<Incident>) =>
    apiFetch<Incident>("/incidents/", { method: "POST", body: JSON.stringify(data) }),
  listIncidents: (params?: { project_name?: string; status?: IncidentStatus }) => {
    const qs = params ? `?${new URLSearchParams(params as Record<string, string>).toString()}` : "";
    return apiFetch<Incident[]>(`/incidents/${qs}`);
  },
  getIncident: (id: string) => apiFetch<Incident>(`/incidents/${id}`),
  updateIncidentStatus: (id: string, data: { status: IncidentStatus; note?: string }) =>
    apiFetch<Incident>(`/incidents/${id}/status`, { method: "PATCH", body: JSON.stringify(data) }),
  runAIDiagnosis: (id: string) =>
    apiFetch<Incident>(`/incidents/${id}/diagnose`, { method: "POST" }),
  replayIncident: (id: string) =>
    apiFetch<{
      replay_result: string;
      logs: string;
      provider?: string;
      simulated?: boolean;
      reproduction_verified?: boolean;
      incident: Incident;
    }>(`/incidents/${id}/replay`, { method: "POST" }),

  // VM
  getVmStatus: () => apiFetch<VmStatus>("/vm/status"),

  // Projects
  listProjects: () => apiFetch<Project[]>("/projects/"),
  createProject: (data: { name: string; language?: string; description?: string; git_url?: string }) =>
    apiFetch<Project>("/projects/", { method: "POST", body: JSON.stringify(data) }),
  getProject: (id: number) => apiFetch<Project>(`/projects/${id}`),

  seedDxDemo: () =>
    apiFetch<{
      seeded: boolean;
      message: string;
      incident_id: string;
      fingerprint_a_id?: string;
      fingerprint_b_id?: string;
      diff_id?: string;
      workflow?: string[];
    }>("/demo/dx-library", { method: "POST" }),
};
