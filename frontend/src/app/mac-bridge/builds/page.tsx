"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  FolderSearch,
  Hammer,
  Loader2,
  Square,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import {
  api,
  getErrorMessage,
  type MacBuild,
  type MacBuildStatus,
  type MacHost,
  type XcodeContainer,
} from "@/lib/api";
import { Button, Card, EmptyState, PageHeader } from "@/components/ui";

const statusConfig: Record<MacBuildStatus, { label: string; className: string }> = {
  preparing: { label: "準備中", className: "bg-blue-500/15 text-blue-400 border-blue-500/30" },
  ready: { label: "設定待ち", className: "bg-blue-500/15 text-blue-400 border-blue-500/30" },
  running: { label: "ビルド中", className: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30" },
  succeeded: { label: "成功", className: "bg-green-500/15 text-green-400 border-green-500/30" },
  failed: { label: "失敗", className: "bg-red-500/15 text-red-400 border-red-500/30" },
  cancelled: { label: "キャンセル", className: "bg-gray-500/15 text-gray-400 border-gray-500/30" },
  timeout: { label: "タイムアウト", className: "bg-orange-500/15 text-orange-400 border-orange-500/30" },
  error: { label: "エラー", className: "bg-red-600/15 text-red-500 border-red-600/30" },
  interrupted: { label: "中断", className: "bg-gray-600/15 text-gray-500 border-gray-600/30" },
};

const ACTIVE: MacBuildStatus[] = ["preparing", "running"];
type LogFilter = "all" | "errors" | "warnings";

const inputClass =
  "w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors";

function StatusBadge({ status }: { status: MacBuildStatus }) {
  const c = statusConfig[status] ?? statusConfig.error;
  return <span className={`text-xs px-2 py-0.5 rounded-full border whitespace-nowrap ${c.className}`}>{c.label}</span>;
}

function formatDate(value: string | null) {
  return value ? new Date(value + "Z").toLocaleString("ja-JP") : "—";
}

function Label({ children }: { children: React.ReactNode }) {
  return <span className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">{children}</span>;
}

function lineClass(line: string) {
  if (/(^|\s)(error|fatal error):\s/i.test(line) || line.includes("BUILD FAILED")) return "text-red-400";
  if (/(^|\s)warning:\s/i.test(line)) return "text-yellow-400";
  if (line.includes("BUILD SUCCEEDED")) return "text-green-400";
  if (line.startsWith("[DevMirror]")) return "text-blue-400";
  return "text-dm-text/80";
}

// ─────────────────────────────────────────────
// ビルドコンソール
// ─────────────────────────────────────────────

function BuildConsole({ buildId, onChange }: { buildId: string; onChange: () => void }) {
  const [build, setBuild] = useState<MacBuild | null>(null);
  const [log, setLog] = useState("");
  const [filter, setFilter] = useState<LogFilter>("all");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scheme, setScheme] = useState("");
  const [configuration, setConfiguration] = useState("Debug");
  const [destination, setDestination] = useState("generic");
  // ビルド開始時に増やしてポーリングを再開する（ready で一度止まるため）
  const [pollKey, setPollKey] = useState(0);
  const offset = useRef(0);
  const logEnd = useRef<HTMLDivElement>(null);

  // ログはファイルの差分（offset 以降）を 1 秒ごとに取得する
  // shortcut: ポーリング方式。同時閲覧が増えたら SSE に切り替える
  useEffect(() => {
    let stopped = false;
    offset.current = 0;
    setLog("");
    setBuild(null);
    const tick = async () => {
      try {
        const [b, chunk] = await Promise.all([
          api.getMacBuild(buildId),
          api.getMacBuildLog(buildId, offset.current),
        ]);
        if (stopped) return;
        offset.current = chunk.offset;
        if (chunk.text) setLog((prev) => prev + chunk.text);
        setBuild(b);
        if (!ACTIVE.includes(b.status)) {
          onChange();
          return;
        }
      } catch (e: unknown) {
        if (!stopped) setError(getErrorMessage(e));
      }
      if (!stopped) setTimeout(tick, 1000);
    };
    tick();
    return () => {
      stopped = true;
    };
  }, [buildId, onChange, pollKey]);

  useEffect(() => {
    if (build?.status === "ready" && !scheme && build.schemes.length) {
      setScheme(build.schemes[0]);
      setConfiguration(build.configurations.includes("Debug") ? "Debug" : build.configurations[0]);
    }
  }, [build, scheme]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "nearest" });
  }, [log]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChange();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!build) {
    return (
      <Card>
        <Loader2 className="animate-spin text-dm-muted" />
      </Card>
    );
  }

  const lines = log.split("\n").filter((l) => {
    if (filter === "errors") return /(^|\s)(error|fatal error):\s/i.test(l);
    if (filter === "warnings") return /(^|\s)warning:\s/i.test(l);
    return true;
  });
  const running = ACTIVE.includes(build.status);

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <Hammer size={18} className="text-blue-400 shrink-0" />
          <div className="min-w-0">
            <div className="font-semibold text-dm-text truncate">{build.container}</div>
            <div className="text-xs text-dm-muted font-mono truncate">
              {build.host_name} · macOS {build.macos_version ?? "?"} · Xcode {build.xcode_version ?? "?"}
            </div>
          </div>
          <StatusBadge status={build.status} />
        </div>
        <div className="flex gap-2">
          {running && (
            <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.cancelMacBuild(buildId))}>
              <Square size={12} />
              キャンセル
            </Button>
          )}
          {!running && !build.workspace_cleaned && (
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => act(async () => setBuild(await api.cleanupMacBuild(buildId)))}
            >
              <Trash2 size={12} />
              Mac の作業フォルダを削除
            </Button>
          )}
        </div>
      </div>

      {build.status === "ready" && (
        <div className="bg-dm-surface-2/50 border border-dm-border rounded-lg p-4 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <label>
              <Label>Scheme</Label>
              <select className={inputClass} value={scheme} onChange={(e) => setScheme(e.target.value)}>
                {build.schemes.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              <Label>構成</Label>
              <select className={inputClass} value={configuration} onChange={(e) => setConfiguration(e.target.value)}>
                {build.configurations.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              <Label>ビルド先</Label>
              <select className={inputClass} value={destination} onChange={(e) => setDestination(e.target.value)}>
                {build.destinations.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs text-dm-muted mb-3">
            iOS シミュレータ向けにコード署名なし（CODE_SIGNING_ALLOWED=NO）でビルドします。証明書は送信しません。
          </p>
          <Button
            disabled={busy || !scheme}
            onClick={() =>
              act(async () => {
                await api.startMacBuild(buildId, { scheme, configuration, destination });
                setPollKey((k) => k + 1);
              })
            }
          >
            <Hammer size={14} />
            ビルド開始
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
        <div>
          <div className="text-[11px] text-dm-muted">Scheme / 構成</div>
          <div className="font-mono text-dm-text break-all">
            {build.scheme ?? "—"} / {build.configuration ?? "—"}
          </div>
        </div>
        <div>
          <div className="text-[11px] text-dm-muted">ビルド先</div>
          <div className="text-dm-text break-all">{build.destination_label ?? "—"}</div>
        </div>
        <div>
          <div className="text-[11px] text-dm-muted">所要時間</div>
          <div className="font-mono text-dm-text flex items-center gap-1">
            <Clock size={12} />
            {build.duration_sec != null ? `${build.duration_sec} 秒` : running ? "計測中…" : "—"}
          </div>
        </div>
        <div>
          <div className="text-[11px] text-dm-muted">終了コード / 警告</div>
          <div className="font-mono text-dm-text">
            {build.exit_code ?? "—"} / {build.warning_count}
          </div>
        </div>
      </div>

      {(build.error_message || error) && (
        <p className="text-xs text-red-400 mb-3 flex items-start gap-2">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          {error ?? build.error_message}
        </p>
      )}

      <div className="flex gap-1 mb-2">
        {(
          [
            ["all", "すべて"],
            ["errors", "エラー"],
            ["warnings", "警告"],
          ] as [LogFilter, string][]
        ).map(([key, label]) => (
          <Button key={key} size="sm" variant={filter === key ? "primary" : "ghost"} onClick={() => setFilter(key)}>
            {label}
          </Button>
        ))}
      </div>
      <div className="bg-black/40 border border-dm-border rounded-lg p-3 h-96 overflow-auto font-mono text-xs leading-relaxed">
        {lines.map((l, i) => (
          <div key={i} className={`whitespace-pre-wrap break-all ${lineClass(l)}`}>
            {l || "\u00a0"}
          </div>
        ))}
        <div ref={logEnd} />
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────
// ページ
// ─────────────────────────────────────────────

export default function MacBuildPage() {
  const [hosts, setHosts] = useState<MacHost[]>([]);
  const [builds, setBuilds] = useState<MacBuild[]>([]);
  const [hostId, setHostId] = useState<number | null>(null);
  const [sourcePath, setSourcePath] = useState("");
  const [containers, setContainers] = useState<XcodeContainer[] | null>(null);
  const [container, setContainer] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBuilds = useCallback(() => {
    api.listMacBuilds().then(setBuilds).catch(() => undefined);
  }, []);

  useEffect(() => {
    api
      .listMacHosts()
      .then((h) => {
        const usable = h.filter((x) => x.enabled);
        setHosts(usable);
        setHostId(usable.find((x) => x.status === "online")?.id ?? usable[0]?.id ?? null);
      })
      .catch((e) => setError(getErrorMessage(e)));
    loadBuilds();
  }, [loadBuilds]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const inspect = () =>
    run(async () => {
      setContainers(null);
      const r = await api.inspectXcodeProject(sourcePath);
      setSourcePath(r.source_path);
      setContainers(r.containers);
      setContainer(r.containers[0]?.path ?? "");
    });

  const prepare = () =>
    run(async () => {
      if (hostId == null) return;
      const b = await api.prepareMacBuild({ host_id: hostId, source_path: sourcePath, container });
      setSelected(b.id);
      loadBuilds();
    });

  return (
    <div className="p-4 md:p-8 animate-fade-in">
      <PageHeader
        title="Xcodeリモートビルド"
        subtitle="Windows のプロジェクトを接続済みの Mac へ転送し、Mac 上の xcodebuild でビルドします"
      />

      <Card className="mb-6">
        <h2 className="font-semibold text-dm-text mb-4 flex items-center gap-2">
          <FolderSearch size={16} className="text-blue-400" />
          プロジェクトを選択
        </h2>
        {hosts.length === 0 ? (
          <p className="text-sm text-dm-muted">
            利用できる Mac がありません。先に「Mac接続管理」で Mac を登録・接続テストしてください。
          </p>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <label className="md:col-span-2">
                <Label>プロジェクトのフォルダ（Windows）</Label>
                <input
                  className={inputClass}
                  value={sourcePath}
                  onChange={(e) => {
                    setSourcePath(e.target.value);
                    setContainers(null);
                  }}
                  placeholder="例: C:\Users\you\Projects\MySwiftUIApp"
                />
              </label>
              <label>
                <Label>Mac</Label>
                <select className={inputClass} value={hostId ?? ""} onChange={(e) => setHostId(Number(e.target.value))}>
                  {hosts.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name}（{h.status === "online" ? "オンライン" : h.status}）
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <Button variant="secondary" onClick={inspect} disabled={busy || !sourcePath}>
                <FolderSearch size={14} />
                Xcode プロジェクトを検出
              </Button>
              {containers && (
                <>
                  <label className="min-w-64">
                    <Label>プロジェクト / ワークスペース</Label>
                    <select className={inputClass} value={container} onChange={(e) => setContainer(e.target.value)}>
                      {containers.map((c) => (
                        <option key={c.path} value={c.path}>
                          {c.path}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Button onClick={prepare} disabled={busy || !container || hostId == null}>
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                    Mac へ転送して scheme を取得
                  </Button>
                </>
              )}
            </div>
            <p className="text-xs text-dm-muted mt-3">
              .git・DerivedData・build フォルダとシンボリックリンクは転送しません。Mac 側では
              ~/DevMirrorWorkspaces/&lt;ビルドID&gt; にのみ展開します。
            </p>
          </>
        )}
        {error && (
          <p className="text-xs text-red-400 mt-3 flex items-center gap-2">
            <AlertTriangle size={12} />
            {error}
          </p>
        )}
      </Card>

      {selected && (
        <div className="mb-6">
          <BuildConsole key={selected} buildId={selected} onChange={loadBuilds} />
        </div>
      )}

      <Card>
        <h2 className="font-semibold text-dm-text mb-4">ビルド履歴</h2>
        {builds.length === 0 ? (
          <EmptyState icon={<Hammer size={24} />} title="ビルド履歴はありません" description="プロジェクトを選択して開始してください" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-dm-muted border-b border-dm-border">
                  <th className="py-2 pr-3">状態</th>
                  <th className="py-2 pr-3">プロジェクト</th>
                  <th className="py-2 pr-3">Scheme</th>
                  <th className="py-2 pr-3">Mac</th>
                  <th className="py-2 pr-3">所要時間</th>
                  <th className="py-2">日時</th>
                </tr>
              </thead>
              <tbody>
                {builds.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => setSelected(b.id)}
                    className={`border-b border-dm-border/50 cursor-pointer hover:bg-dm-surface-2 ${selected === b.id ? "bg-dm-surface-2" : ""}`}
                  >
                    <td className="py-2 pr-3">
                      <span className="inline-flex items-center gap-1.5">
                        {b.status === "succeeded" && <CheckCircle size={12} className="text-green-400" />}
                        {b.status === "failed" && <XCircle size={12} className="text-red-400" />}
                        <StatusBadge status={b.status} />
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{b.container}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{b.scheme ?? "—"}</td>
                    <td className="py-2 pr-3 text-xs">{b.host_name}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{b.duration_sec != null ? `${b.duration_sec} 秒` : "—"}</td>
                    <td className="py-2 text-xs text-dm-muted">{formatDate(b.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
