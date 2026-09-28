"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { api, type Incident, type VmStatus } from "@/lib/api";
import { providerLabel, testResultLabel } from "@/lib/labels";
import { Button, Card, PageHeader, TestResultBadge } from "@/components/ui";

const steps = [
  "環境を準備",
  "依存関係を確認",
  "ビルド",
  "テスト実行",
  "証拠を収集",
  "元インシデントと比較",
];

export default function ReplayPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);
  const [activeStep, setActiveStep] = useState(-1);
  const [vm, setVm] = useState<VmStatus | null>(null);
  const [result, setResult] = useState<{
    replay_result: string;
    logs: string;
    simulated?: boolean;
    reproduction_verified?: boolean;
    provider?: string;
  } | null>(null);

  const loadVmStatus = useCallback(() => {
    api.getVmStatus()
      .then(setVm)
      .catch((e) =>
        setVm({
          provider: "-",
          simulated: true,
          available: false,
          detail: `VM 情報を取得できません: ${String(e)}`,
          base_vm: "-",
        })
      );
  }, []);

  useEffect(() => {
    api.listIncidents().then(setIncidents).catch(console.error);
    loadVmStatus();
  }, [loadVmStatus]);

  const handleReplay = async () => {
    if (!selected) return;
    setRunning(true);
    setResult(null);
    setActiveStep(0);
    const timer = setInterval(() => {
      setActiveStep((s) => (s < steps.length - 1 ? s + 1 : s));
    }, 250);
    try {
      const data = await api.replayIncident(selected);
      setResult(data);
    } finally {
      clearInterval(timer);
      setActiveStep(steps.length - 1);
      setRunning(false);
    }
  };

  const original = incidents.find((i) => i.incident_id === selected);

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader
        title="インシデント再実行"
        subtitle="保存済みの Incident Capsule から環境を再構築し、結果を比較します"
      />
      <Card className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            {vm?.available ? (
              <CheckCircle2 className="w-5 h-5 text-dm-accent shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium">
                VM 環境: {vm ? providerLabel(vm.provider) : "確認中..."}
                {vm?.simulated && "（シミュレーション）"}
              </p>
              <p className="text-xs text-dm-muted mt-1 break-words">
                  {vm?.detail ?? "VM 環境を確認しています"}
              </p>
              {vm && !vm.simulated && vm.base_vm_found && (
                <p className="text-xs text-dm-muted mt-1">
                  基準 VM: <span className="mono">{vm.base_vm}</span>
                  {vm.registered_vms && vm.registered_vms.length > 0 && (
                    <> · 登録済み {vm.registered_vms.length} 台</>
                  )}
                </p>
              )}
              {vm && !vm.simulated && (
                <p className="text-xs text-dm-muted mt-2">
                  3 台の VM は <span className="mono">python -m scripts.provision_vms</span>{" "}
                  で作成します。
                </p>
              )}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={loadVmStatus} aria-label="VM 環境を確認">
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </Card>

      <Card className="mb-6">
        <label className="text-xs text-dm-muted block mb-2">対象インシデント</label>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm mb-4"
        >
          <option value="">選択してください</option>
          {incidents.map((inc) => (
            <option key={inc.incident_id} value={inc.incident_id}>
              {inc.incident_id} · {inc.project_name}
            </option>
          ))}
        </select>
        <Button onClick={handleReplay} disabled={!selected || running}>
          <RefreshCw size={14} /> {running ? "再実行中..." : "インシデントを再実行"}
        </Button>
      </Card>

      <div className="grid grid-cols-2 gap-6">
        <Card>
          <h2 className="font-semibold mb-4">進行状況</h2>
          <ol className="space-y-2">
            {steps.map((step, i) => (
              <li key={step} className={i <= activeStep ? "text-blue-300" : "text-dm-muted"}>
                {i <= activeStep ? "●" : "○"} {step}
              </li>
            ))}
          </ol>
        </Card>
        <Card>
          <h2 className="font-semibold mb-4">比較</h2>
          {original && (
            <p className="text-sm mb-2">
              元インシデント: <TestResultBadge result={original.test_result} />
            </p>
          )}
          {result && (
            <>
              <p className="text-sm mb-2">
                再実行結果: <span className="mono">{testResultLabel(result.replay_result)}</span>
              </p>
              <p className="text-xs text-yellow-300">
                プロバイダ: {providerLabel(result.provider || "MockVMProvider")} · シミュレーション:{" "}
                {result.simulated ? "はい" : "いいえ"} · 検証済み再現:{" "}
                {result.reproduction_verified ? "はい" : "いいえ"}
              </p>
              <pre className="text-xs text-dm-muted mt-3 whitespace-pre-wrap">{result.logs}</pre>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
