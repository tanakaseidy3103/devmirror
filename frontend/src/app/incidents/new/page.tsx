"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Plus, Loader2 } from "lucide-react";
import { api, getErrorMessage, type Fingerprint, type TestResult } from "@/lib/api";
import { Button, Card, PageHeader } from "@/components/ui";

export default function NewIncidentPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [fingerprints, setFingerprints] = useState<Fingerprint[]>([]);
  
  // フォームステート
  const [projectName, setProjectName] = useState("");
  const [environmentName, setEnvironmentName] = useState("");
  const [fingerprintId, setFingerprintId] = useState("");
  const [testResult, setTestResult] = useState<TestResult>("FAIL");
  const [commandExecuted, setCommandExecuted] = useState("");
  const [logs, setLogs] = useState("");
  
  useEffect(() => {
    api.listFingerprints().then(setFingerprints).catch(console.error);
  }, []);

  const handleCreate = async () => {
    if (!projectName || !environmentName) {
      setError("プロジェクト名と環境名は必須です");
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const incident = await api.createIncident({
        project_name: projectName,
        environment_name: environmentName,
        test_result: testResult,
        command_executed: commandExecuted || undefined,
        logs: logs,
        fingerprint_id: fingerprintId || undefined,
        status: "OPEN",
      });
      
      router.push(`/incidents/${incident.incident_id}`);
    } catch (e: unknown) {
      setError(getErrorMessage(e));
      setLoading(false);
    }
  };

  return (
    <div className="p-8 animate-fade-in max-w-4xl mx-auto">
      <PageHeader
        title="新規インシデント作成"
        subtitle="手動で新しいIncident Capsuleを記録します"
      />
      
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6 flex items-center gap-3">
          <AlertTriangle size={16} className="text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      <Card>
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-6">
            {/* プロジェクト名 */}
            <div>
              <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
                プロジェクト名 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="例: DXGame"
              />
            </div>
            
            {/* 環境名 */}
            <div>
              <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
                環境名 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={environmentName}
                onChange={(e) => setEnvironmentName(e.target.value)}
                className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="例: Windows 11 Dev"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* テスト結果 */}
            <div>
              <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
                テスト結果
              </label>
              <select
                value={testResult}
                onChange={(e) => setTestResult(e.target.value as TestResult)}
                className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
              >
                <option value="FAIL">失敗</option>
                <option value="ERROR">エラー</option>
                <option value="TIMEOUT">タイムアウト</option>
                <option value="PASS">成功</option>
                <option value="UNKNOWN">不明</option>
              </select>
            </div>
            
            {/* Fingerprint紐付け */}
            <div>
              <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
                関連 Fingerprint (任意)
              </label>
              <select
                value={fingerprintId}
                onChange={(e) => setFingerprintId(e.target.value)}
                className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
              >
                <option value="">— 紐付けなし —</option>
                {fingerprints.map((fp) => (
                  <option key={fp.fingerprint_id} value={fp.fingerprint_id}>
                    {fp.environment_name} ({fp.fingerprint_id.slice(0, 8)})
                  </option>
                ))}
              </select>
            </div>
          </div>
          
          {/* コマンド */}
          <div>
            <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
              実行したコマンド (任意)
            </label>
            <input
              type="text"
              value={commandExecuted}
              onChange={(e) => setCommandExecuted(e.target.value)}
              className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text font-mono focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="例: make test"
            />
          </div>
          
          {/* ログ */}
          <div>
            <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
              ログ・エラー出力 (任意)
            </label>
            <textarea
              value={logs}
              onChange={(e) => setLogs(e.target.value)}
              rows={8}
              className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text font-mono focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="ログ出力を貼り付けてください..."
            />
          </div>
          
          <div className="flex justify-end pt-4">
            <Button onClick={handleCreate} disabled={loading}>
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  保存中...
                </>
              ) : (
                <>
                  <Plus size={14} />
                  インシデントを作成
                </>
              )}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
