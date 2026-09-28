"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, type Incident, type Project } from "@/lib/api";
import { Card, IncidentStatusBadge, LoadingSpinner, PageHeader, TestResultBadge } from "@/components/ui";

export default function ProjectDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [project, setProject] = useState<Project | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    api.getProject(id).then(setProject).catch(console.error);
  }, [id]);

  useEffect(() => {
    if (!project) return;
    api.listIncidents({ project_name: project.name }).then(setIncidents).catch(console.error);
  }, [project]);

  if (!project) {
    return <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>;
  }

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader title={project.name} subtitle={project.description || "プロジェクト詳細"} />
      <div className="grid grid-cols-3 gap-4 mb-6">
        <Card>
          <p className="text-xs text-dm-muted">言語</p>
          <p className="text-lg mt-1">{project.language || "不明"}</p>
        </Card>
        <Card>
          <p className="text-xs text-dm-muted">Git</p>
          <p className="text-sm mt-1 break-all">{project.git_url || "未設定"}</p>
        </Card>
        <Card>
          <p className="text-xs text-dm-muted">インシデント</p>
          <p className="text-lg mt-1">{incidents.length}</p>
        </Card>
      </div>
      <Card>
        <h2 className="font-semibold mb-4">関連インシデント</h2>
        <div className="space-y-2">
          {incidents.map((inc) => (
            <Link key={inc.incident_id} href={`/incidents/${inc.incident_id}`} className="flex items-center justify-between p-3 rounded-lg bg-dm-surface-2">
              <span className="mono text-blue-400 text-sm">{inc.incident_id}</span>
              <span className="text-sm">{inc.environment_name}</span>
              <TestResultBadge result={inc.test_result} />
              <IncidentStatusBadge status={inc.status} />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
