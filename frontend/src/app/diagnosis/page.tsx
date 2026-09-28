"use client";

import { useEffect, useState } from "react";
import { api, type Incident } from "@/lib/api";
import { dataSourceLabel } from "@/lib/labels";
import { Button, Card, PageHeader } from "@/components/ui";

export default function DiagnosisPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState("");
  const [incident, setIncident] = useState<Incident | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.listIncidents().then(setIncidents).catch(console.error);
  }, []);

  const load = async (id: string) => {
    setSelected(id);
    setIncident(await api.getIncident(id));
  };

  const diagnose = async () => {
    if (!selected) return;
    setRunning(true);
    try {
      setIncident(await api.runAIDiagnosis(selected));
    } finally {
      setRunning(false);
    }
  };

  const d = incident?.ai_diagnosis;

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader title="AI診断" subtitle="証拠・差異・仮説・調査提案を分離して表示します。原因の断定はしません。" />
      <Card className="mb-6">
        <select
          value={selected}
          onChange={(e) => load(e.target.value)}
          className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm mb-4"
        >
          <option value="">インシデントを選択</option>
          {incidents.map((inc) => (
            <option key={inc.incident_id} value={inc.incident_id}>
              {inc.incident_id} · {inc.project_name}
            </option>
          ))}
        </select>
        <Button onClick={diagnose} disabled={!selected || running}>
          {running ? "分析中..." : "AI診断を実行"}
        </Button>
      </Card>

      {d && (
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <h2 className="font-semibold text-green-400 mb-2">観測された証拠</h2>
            <ul className="text-sm space-y-1 list-disc pl-4">{d.observed_evidence.map((x) => <li key={x}>{x}</li>)}</ul>
          </Card>
          <Card>
            <h2 className="font-semibold text-purple-400 mb-2">検出された差異</h2>
            <ul className="text-sm space-y-1 list-disc pl-4">{d.detected_differences.map((x) => <li key={x}>{x}</li>)}</ul>
          </Card>
          <Card>
            <h2 className="font-semibold text-yellow-400 mb-2">仮説</h2>
            <ul className="text-sm space-y-1 list-disc pl-4">{d.hypotheses.map((x) => <li key={x}>{x}</li>)}</ul>
          </Card>
          <Card>
            <h2 className="font-semibold text-cyan-400 mb-2">調査提案</h2>
            <ul className="text-sm space-y-1 list-disc pl-4">{d.suggested_investigations.map((x) => <li key={x}>{x}</li>)}</ul>
          </Card>
          <Card className="col-span-2">
            <p className="text-sm">{d.summary}</p>
            <p className="text-xs text-dm-muted mt-2">
              信頼度 {(d.confidence * 100).toFixed(0)}% · 使用データ:{" "}
              {d.data_sources_used.map(dataSourceLabel).join("、") || "なし"}
              {d.is_mock ? " · モック（実AI分析ではありません）" : ""}
            </p>
          </Card>
        </div>
      )}
    </div>
  );
}
