"use client";

import { useEffect, useState } from "react";
import { api, type Incident } from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";

export default function TimelinePage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState<Incident | null>(null);

  useEffect(() => {
    api.listIncidents().then(setIncidents).catch(console.error);
  }, []);

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader title="インシデントタイムライン" subtitle="保存されたイベント列。OpenTelemetry 連携は未実装です。" />
      <select
        className="mb-6 w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm"
        onChange={async (e) => {
          if (!e.target.value) return;
          setSelected(await api.getIncident(e.target.value));
        }}
      >
        <option value="">インシデントを選択</option>
        {incidents.map((inc) => (
          <option key={inc.incident_id} value={inc.incident_id}>
            {inc.incident_id}
          </option>
        ))}
      </select>
      <Card>
        {(selected?.timeline || []).map((ev, i) => (
          <div key={i} className="flex gap-4 py-3 border-b border-dm-border last:border-0">
            <span className="mono text-xs text-dm-muted w-48 shrink-0">{ev.timestamp}</span>
            <div>
              <p className="text-sm font-medium">{ev.event}</p>
              <p className="text-xs text-dm-muted">{ev.detail}</p>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}
