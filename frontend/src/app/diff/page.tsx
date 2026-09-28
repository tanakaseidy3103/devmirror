"use client";

import { useEffect, useState } from "react";
import { GitCompare, Loader2, AlertTriangle } from "lucide-react";
import { api, getErrorMessage, type Fingerprint, type Diff, type DiffEntry } from "@/lib/api";
import { diffCategoryLabel, diffFieldLabel, diffValueLabel } from "@/lib/labels";
import { Button, Card, DiffSeverityBadge, DiffStatusBadge, PageHeader } from "@/components/ui";

export default function DiffPage() {
  const [fingerprints, setFingerprints] = useState<Fingerprint[]>([]);
  const [fpAId, setFpAId] = useState("");
  const [fpBId, setFpBId] = useState("");
  const [loading, setLoading] = useState(false);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listFingerprints().then(setFingerprints).catch(console.error);
  }, []);

  const handleCompare = async () => {
    if (!fpAId || !fpBId) return;
    setLoading(true);
    setError(null);
    setDiff(null);
    try {
      const result = await api.compareFingerprints({
        fingerprint_a_id: fpAId,
        fingerprint_b_id: fpBId,
      });
      setDiff(result);
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const relevantEntries = diff?.entries.filter((e) => e.potentially_relevant) ?? [];
  const matchEntries = diff?.entries.filter((e) => e.status === "MATCH") ?? [];

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader
        title="環境差分の比較"
        subtitle="2つの Environment Fingerprint を比較して差異を検出します"
      />

      {/* 比較設定 */}
      <Card className="mb-6">
        <h2 className="font-semibold text-dm-text mb-4 flex items-center gap-2">
          <GitCompare size={16} className="text-purple-400" />
          Fingerprint 比較
        </h2>
        <div className="grid grid-cols-2 gap-6 mb-5">
          <div>
            <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
              環境A（基準）
            </label>
            <select
              value={fpAId}
              onChange={(e) => setFpAId(e.target.value)}
              className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
            >
              <option value="">— 選択してください —</option>
              {fingerprints.map((fp) => (
                <option key={fp.fingerprint_id} value={fp.fingerprint_id}>
                  {fp.environment_name} ({fp.fingerprint_id.slice(0, 8)}...)
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
              環境B（比較対象）
            </label>
            <select
              value={fpBId}
              onChange={(e) => setFpBId(e.target.value)}
              className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
            >
              <option value="">— 選択してください —</option>
              {fingerprints.map((fp) => (
                <option key={fp.fingerprint_id} value={fp.fingerprint_id}>
                  {fp.environment_name} ({fp.fingerprint_id.slice(0, 8)}...)
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3 mb-5">
          <p className="text-xs text-blue-400/80">
            ※ 差異は「根本原因」とは断言されません。「潜在的に関連する差異」として提示されます。
          </p>
        </div>

        <Button onClick={handleCompare} disabled={loading || !fpAId || !fpBId}>
          {loading ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              比較中...
            </>
          ) : (
            <>
              <GitCompare size={14} />
              差分を検出
            </>
          )}
        </Button>
      </Card>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6 flex items-center gap-3">
          <AlertTriangle size={16} className="text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {diff && (
        <div className="animate-slide-up space-y-4">
          {/* サマリー */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-red-400">{diff.high_severity_count}</p>
              <p className="text-xs text-dm-muted mt-1">重要度：高</p>
            </div>
            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-yellow-400">{diff.medium_severity_count}</p>
              <p className="text-xs text-dm-muted mt-1">重要度：中</p>
            </div>
            <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-green-400">{matchEntries.length}</p>
              <p className="text-xs text-dm-muted mt-1">一致</p>
            </div>
          </div>

          {/* 潜在的に関連する差異 */}
          {relevantEntries.length > 0 && (
            <Card className="border-yellow-500/30 bg-yellow-500/5">
              <h3 className="font-semibold text-yellow-400 mb-4 flex items-center gap-2">
                <AlertTriangle size={15} />
                潜在的に関連する差異（{relevantEntries.length}件）
              </h3>
              <p className="text-xs text-dm-muted mb-3">
                ※ これらは「根本原因」ではなく「調査すべき差異候補」です
              </p>
              <div className="space-y-2">
                {relevantEntries.map((entry, i) => (
                  <DiffEntryRow key={i} entry={entry} envA={diff.environment_a_name} envB={diff.environment_b_name} highlight />
                ))}
              </div>
            </Card>
          )}

          {/* 全差異テーブル */}
          <Card>
            <h3 className="font-semibold text-dm-text mb-4">全差異一覧（{diff.entries.length}件）</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-dm-border">
                    <th className="text-left py-2 px-3 text-xs text-dm-muted uppercase tracking-wider">カテゴリ</th>
                    <th className="text-left py-2 px-3 text-xs text-dm-muted uppercase tracking-wider">フィールド</th>
                    <th className="text-left py-2 px-3 text-xs text-dm-muted uppercase tracking-wider">{diff.environment_a_name}</th>
                    <th className="text-left py-2 px-3 text-xs text-dm-muted uppercase tracking-wider">{diff.environment_b_name}</th>
                    <th className="text-left py-2 px-3 text-xs text-dm-muted uppercase tracking-wider">状態</th>
                    <th className="text-left py-2 px-3 text-xs text-dm-muted uppercase tracking-wider">重要度</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.entries.map((entry, i) => (
                    <tr
                      key={i}
                      className={`border-b border-dm-border/50 ${
                        entry.potentially_relevant ? "bg-yellow-500/5" : ""
                      }`}
                    >
                      <td className="py-2 px-3 text-xs text-dm-muted">{diffCategoryLabel(entry.category)}</td>
                      <td className="py-2 px-3 text-sm text-dm-text">
                        {entry.category === "dependency"
                          ? entry.field
                          : diffFieldLabel(entry.field)}
                      </td>
                      <td className="py-2 px-3 text-xs mono text-dm-muted">
                        {diffValueLabel(entry.category, entry.value_a)}
                      </td>
                      <td className="py-2 px-3 text-xs mono text-dm-muted">
                        {diffValueLabel(entry.category, entry.value_b)}
                      </td>
                      <td className="py-2 px-3">
                        <DiffStatusBadge status={entry.status} />
                      </td>
                      <td className="py-2 px-3">
                        {entry.status !== "MATCH" && <DiffSeverityBadge severity={entry.severity} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function DiffEntryRow({
  entry,
  envA,
  envB,
  highlight = false,
}: {
  entry: DiffEntry;
  envA: string;
  envB: string;
  highlight?: boolean;
}) {
  return (
    <div className={`p-3 rounded-lg ${highlight ? "bg-dm-surface-2 border border-yellow-500/20" : "bg-dm-surface-2"}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-dm-muted">{diffCategoryLabel(entry.category)}</span>
          <span className="text-sm font-medium text-dm-text">
            {entry.category === "dependency" ? entry.field : diffFieldLabel(entry.field)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <DiffStatusBadge status={entry.status} />
          <DiffSeverityBadge severity={entry.severity} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs mono">
        <div className="bg-dm-bg rounded p-2">
          <span className="text-dm-muted block mb-0.5">{envA}</span>
          <span className="text-green-400">{diffValueLabel(entry.category, entry.value_a)}</span>
        </div>
        <div className="bg-dm-bg rounded p-2">
          <span className="text-dm-muted block mb-0.5">{envB}</span>
          <span className="text-red-400">{diffValueLabel(entry.category, entry.value_b)}</span>
        </div>
      </div>
      {entry.note && (
        <p className="text-xs text-yellow-400/80 mt-2">{entry.note}</p>
      )}
    </div>
  );
}
