"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Plus, Search } from "lucide-react";
import { api, type Incident } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  IncidentStatusBadge,
  LoadingSpinner,
  PageHeader,
  TestResultBadge,
} from "@/components/ui";

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    api
      .listIncidents()
      .then(setIncidents)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const filtered = incidents.filter(
    (inc) =>
      inc.incident_id.toLowerCase().includes(search.toLowerCase()) ||
      inc.project_name.toLowerCase().includes(search.toLowerCase()) ||
      inc.environment_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader
        title="インシデント一覧"
        subtitle="記録されたすべてのIncident Capsuleを管理します"
        action={
          <Link href="/incidents/new">
            <Button>
              <Plus size={14} />
              新規インシデント
            </Button>
          </Link>
        }
      />

      {/* 検索 */}
      <div className="relative mb-6">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-dm-muted" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="インシデントID・プロジェクト・環境で検索..."
          className="w-full bg-dm-surface border border-dm-border rounded-xl pl-9 pr-4 py-2.5 text-sm text-dm-text placeholder:text-dm-muted focus:outline-none focus:border-blue-500 transition-colors"
        />
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle size={40} />}
          title="インシデントが見つかりません"
          description="スキャンを実行してインシデントを記録してください"
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((inc) => (
            <Link key={inc.incident_id} href={`/incidents/${inc.incident_id}`}>
              <Card hover className="mb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    {/* インシデントID */}
                    <div className="mono text-blue-400 font-bold text-sm w-24 shrink-0">
                      {inc.incident_id}
                    </div>

                    {/* プロジェクト・環境 */}
                    <div>
                      <p className="font-medium text-dm-text">{inc.project_name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-dm-muted">{inc.environment_name}</span>
                        {inc.git_commit && (
                          <>
                            <span className="text-dm-muted">·</span>
                            <span className="mono text-xs text-dm-muted">{inc.git_commit.slice(0, 7)}</span>
                          </>
                        )}
                        {inc.project_language && (
                          <>
                            <span className="text-dm-muted">·</span>
                            <span className="text-xs text-dm-muted">{inc.project_language}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* タグ */}
                    {inc.tags?.slice(0, 2).map((tag) => (
                      <span key={tag} className="text-xs bg-dm-surface-2 text-dm-muted px-2 py-0.5 rounded-full">
                        {tag}
                      </span>
                    ))}

                    {/* AI診断あり */}
                    {inc.ai_diagnosis && (
                      <span className="badge bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                        AI診断済み
                      </span>
                    )}

                    <TestResultBadge result={inc.test_result} />
                    <IncidentStatusBadge status={inc.status} />

                    <span className="text-xs text-dm-muted">
                      {new Date(inc.created_at).toLocaleDateString("ja-JP")}
                    </span>

                    <ArrowRight size={14} className="text-dm-muted" />
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
