"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FolderGit2 } from "lucide-react";
import { api, type Project } from "@/lib/api";
import { Card, EmptyState, LoadingSpinner, PageHeader } from "@/components/ui";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listProjects().then(setProjects).catch(console.error).finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader title="プロジェクト" subtitle="リポジトリ、言語、関連インシデントの入口" />
      {loading ? (
        <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
      ) : !projects.length ? (
        <EmptyState
          icon={<FolderGit2 size={32} />}
          title="プロジェクトがありません"
          description="環境スキャンまたは公式デモの投入で作成されます"
        />
      ) : (
        <div className="grid gap-4">
          {projects.map((p) => (
            <Link key={p.id} href={`/projects/${p.id}`}>
              <Card hover>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-dm-text">{p.name}</p>
                    <p className="text-xs text-dm-muted mt-1">
                      {p.language || "言語未検出"} {p.git_url ? `· ${p.git_url}` : ""}
                    </p>
                    {p.description && <p className="text-sm text-dm-muted mt-2">{p.description}</p>}
                  </div>
                  <span className="mono text-xs text-blue-400">#{p.id}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
