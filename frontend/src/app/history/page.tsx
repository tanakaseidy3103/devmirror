"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Incident, type IncidentStatus } from "@/lib/api";
import { Card, IncidentStatusBadge, PageHeader, TestResultBadge } from "@/components/ui";

export default function HistoryPage() {
  const [items, setItems] = useState<Incident[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<IncidentStatus | "">("");

  useEffect(() => {
    api.listIncidents(status ? { status } : undefined).then(setItems).catch(console.error);
  }, [status]);

  const filtered = items.filter((inc) => {
    const hay = `${inc.incident_id} ${inc.project_name} ${inc.environment_name} ${inc.git_commit || ""} ${inc.logs}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader title="インシデント履歴" subtitle="プロジェクト・エラー・環境・コミットで検索" />
      <div className="flex gap-3 mb-6">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="検索..."
          className="flex-1 bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as IncidentStatus | "")}
          className="bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm"
        >
          <option value="">すべての状態</option>
          <option value="OPEN">オープン</option>
          <option value="INVESTIGATING">調査中</option>
          <option value="REPRODUCED">再現済み</option>
          <option value="RESOLVED">解決済み</option>
        </select>
      </div>
      <div className="space-y-2">
        {filtered.map((inc) => (
          <Link key={inc.incident_id} href={`/incidents/${inc.incident_id}`}>
            <Card hover>
              <div className="flex items-center justify-between">
                <div>
                  <span className="mono text-blue-400 mr-3">{inc.incident_id}</span>
                  <span>{inc.project_name}</span>
                  <p className="text-xs text-dm-muted mt-1">{inc.environment_name} · {inc.git_commit || "commit なし"}</p>
                </div>
                <div className="flex gap-2">
                  <TestResultBadge result={inc.test_result} />
                  <IncidentStatusBadge status={inc.status} />
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
