"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AlertTriangle, BrainCircuit, CheckCircle, Clock, Search, ShieldAlert, FileText, Terminal, PlayCircle } from "lucide-react";
import { api, getErrorMessage, type Incident, type IncidentStatus } from "@/lib/api";
import { testResultLabel } from "@/lib/labels";
import { Button, Card, IncidentStatusBadge, LoadingSpinner, TestResultBadge } from "@/components/ui";

export default function IncidentDetailPage() {
  const params = useParams();
  const id = params.id as string;
  
  const [incident, setIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [diagnosing, setDiagnosing] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replayResult, setReplayResult] = useState<{ result: string, logs: string } | null>(null);

  const loadIncident = async () => {
    try {
      const data = await api.getIncident(id);
      setIncident(data);
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadIncident();
  }, [id]);

  const handleStatusChange = async (status: IncidentStatus) => {
    try {
      await api.updateIncidentStatus(id, { status });
      await loadIncident();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    }
  };

  const handleDiagnose = async () => {
    setDiagnosing(true);
    try {
      await api.runAIDiagnosis(id);
      await loadIncident();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setDiagnosing(false);
    }
  };

  const handleReplay = async () => {
    setReplaying(true);
    setReplayResult(null);
    try {
      const result = await api.replayIncident(id);
      setReplayResult({ result: result.replay_result, logs: result.logs });
      await loadIncident();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setReplaying(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>;
  }

  if (error || !incident) {
    return (
      <div className="p-8">
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 flex flex-col items-center">
          <AlertTriangle size={48} className="text-red-400 mb-4" />
          <h2 className="text-xl font-bold text-red-400">インシデントが見つかりません</h2>
          <p className="text-sm text-dm-muted mt-2">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 animate-fade-in max-w-6xl mx-auto">
      {/* ヘッダー */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold text-dm-text mono">{incident.incident_id}</h1>
            <IncidentStatusBadge status={incident.status} />
            <TestResultBadge result={incident.test_result} />
          </div>
          <p className="text-lg text-dm-muted">
            {incident.project_name} <span className="mx-2 text-dm-border">/</span> {incident.environment_name}
          </p>
        </div>
        
        <div className="flex gap-3">
          <select 
            value={incident.status} 
            onChange={(e) => handleStatusChange(e.target.value as IncidentStatus)}
            className="bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
          >
            <option value="OPEN">オープン</option>
            <option value="INVESTIGATING">調査中</option>
            <option value="REPRODUCED">再現済み</option>
            <option value="RESOLVED">解決済み</option>
            <option value="ARCHIVED">アーカイブ</option>
          </select>
          <Button onClick={handleDiagnose} disabled={diagnosing} className="bg-cyan-600 hover:bg-cyan-500">
            {diagnosing ? <LoadingSpinner size="sm" /> : <BrainCircuit size={14} />}
            AI診断を実行
          </Button>
          <Button onClick={handleReplay} disabled={replaying} variant="secondary">
            {replaying ? <LoadingSpinner size="sm" /> : <PlayCircle size={14} className="text-green-400" />}
            再実行
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* メインコンテンツ (左側2カラム) */}
        <div className="col-span-2 space-y-6">
          
          {/* Replay 結果 */}
          {replayResult && (
            <Card className="border-green-500/30 bg-green-500/5 shadow-[0_0_15px_rgba(34,197,94,0.1)]">
              <div className="flex items-center gap-2 mb-4 text-green-400">
                <PlayCircle size={18} />
                <h2 className="font-semibold text-lg">再実行結果</h2>
              </div>

              <div className="mb-4">
                <span className="text-sm text-dm-muted">テスト結果: </span>
                <span className={`badge ml-2 ${
                  replayResult.result === "PASS" ? "bg-green-500/15 text-green-400 border border-green-500/30" :
                  "bg-red-500/15 text-red-400 border border-red-500/30"
                }`}>
                  {testResultLabel(replayResult.result)}
                </span>
              </div>
              
              <div className="bg-[#0d1117] border border-dm-border rounded-lg overflow-hidden">
                <div className="bg-dm-surface-2 px-3 py-1.5 border-b border-dm-border flex items-center justify-between">
                  <span className="text-xs text-dm-muted mono flex items-center gap-2">
                    <Terminal size={12} /> replay_logs.txt
                  </span>
                </div>
                <pre className="p-4 text-xs mono text-dm-text overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                  {replayResult.logs}
                </pre>
              </div>
            </Card>
          )}
          
          {/* AI診断結果 */}
          {incident.ai_diagnosis && (
            <Card className="border-cyan-500/30 shadow-[0_0_15px_rgba(6,182,212,0.1)]">
              <div className="flex items-center gap-2 mb-4 text-cyan-400">
                <BrainCircuit size={18} />
                <h2 className="font-semibold text-lg">AI診断レポート</h2>
                {incident.ai_diagnosis.is_mock && (
                  <span className="ml-auto text-[10px] bg-cyan-500/20 px-2 py-0.5 rounded-full border border-cyan-500/30 tracking-widest">
                    モック
                  </span>
                )}
              </div>
              
              <p className="text-sm text-dm-text mb-6 leading-relaxed bg-dm-surface-2 p-3 rounded-lg border border-dm-border">
                {incident.ai_diagnosis.summary}
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-xs font-semibold text-dm-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <Search size={12} className="text-blue-400" /> 観測された証拠
                    </h3>
                    <ul className="space-y-1">
                      {incident.ai_diagnosis.observed_evidence.map((item, i) => (
                        <li key={i} className="text-xs text-dm-text flex items-start gap-2">
                          <span className="text-blue-500 mt-0.5">•</span> <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold text-dm-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <ShieldAlert size={12} className="text-orange-400" /> 仮説
                    </h3>
                    <ul className="space-y-1">
                      {incident.ai_diagnosis.hypotheses.map((item, i) => (
                        <li key={i} className="text-xs text-dm-text flex items-start gap-2">
                          <span className="text-orange-500 mt-0.5">•</span> <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                
                <div className="space-y-4">
                  <div>
                    <h3 className="text-xs font-semibold text-dm-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <AlertTriangle size={12} className="text-yellow-400" /> 検出された差異
                    </h3>
                    <ul className="space-y-1">
                      {incident.ai_diagnosis.detected_differences.map((item, i) => (
                        <li key={i} className="text-xs text-dm-text flex items-start gap-2">
                          <span className="text-yellow-500 mt-0.5">•</span> <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold text-dm-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <CheckCircle size={12} className="text-green-400" /> 推奨される調査
                    </h3>
                    <ul className="space-y-1">
                      {incident.ai_diagnosis.suggested_investigations.map((item, i) => (
                        <li key={i} className="text-xs text-dm-text flex items-start gap-2">
                          <span className="text-green-500 mt-0.5">•</span> <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* ログ */}
          <Card>
            <h2 className="font-semibold text-dm-text mb-4 flex items-center gap-2">
              <Terminal size={16} className="text-blue-400" />
              実行ログ & 証拠
            </h2>
            {incident.command_executed && (
              <div className="mb-4">
                <div className="text-xs text-dm-muted mb-1">実行コマンド</div>
                <div className="bg-black/50 border border-dm-border rounded p-2 text-xs mono text-green-400 flex items-center gap-2">
                  <span className="text-dm-muted">$</span> {incident.command_executed}
                </div>
              </div>
            )}
            
            <div className="bg-[#0d1117] border border-dm-border rounded-lg overflow-hidden">
              <div className="bg-dm-surface-2 px-3 py-1.5 border-b border-dm-border flex items-center justify-between">
                <span className="text-xs text-dm-muted mono flex items-center gap-2">
                  <FileText size={12} /> logs.txt
                </span>
              </div>
              <pre className="p-4 text-xs mono text-dm-text overflow-x-auto max-h-[400px] overflow-y-auto whitespace-pre-wrap">
                {incident.logs || "ログは記録されていません。"}
              </pre>
            </div>
          </Card>
          
        </div>

        {/* サイドバー (右側1カラム) */}
        <div className="space-y-6">
          {/* メタデータ */}
          <Card>
            <h3 className="text-sm font-semibold text-dm-text mb-4">メタデータ</h3>
            <div className="space-y-3">
              <div>
                <span className="text-xs text-dm-muted block mb-1">プロジェクト</span>
                <span className="text-sm font-medium">{incident.project_name}</span>
                {incident.project_language && <span className="text-xs text-dm-muted ml-2">({incident.project_language})</span>}
              </div>
              <div>
                <span className="text-xs text-dm-muted block mb-1">環境</span>
                <span className="text-sm font-medium">{incident.environment_name}</span>
              </div>
              {incident.git_commit && (
                <div>
                  <span className="text-xs text-dm-muted block mb-1">Git Commit</span>
                  <span className="text-sm mono text-blue-400">{incident.git_commit.slice(0, 8)}</span>
                </div>
              )}
              {incident.fingerprint_id && (
                <div>
                  <span className="text-xs text-dm-muted block mb-1">Fingerprint ID</span>
                  <span className="text-xs mono">{incident.fingerprint_id.slice(0, 8)}...</span>
                </div>
              )}
              {incident.diff_id && (
                <div>
                  <span className="text-xs text-dm-muted block mb-1">Diff ID</span>
                  <span className="text-xs mono">{incident.diff_id.slice(0, 8)}...</span>
                </div>
              )}
              <div>
                <span className="text-xs text-dm-muted block mb-1">作成日時</span>
                <span className="text-sm">{new Date(incident.created_at).toLocaleString("ja-JP")}</span>
              </div>
            </div>
          </Card>

          {/* タイムライン */}
          <Card>
            <h3 className="text-sm font-semibold text-dm-text mb-4 flex items-center gap-2">
              <Clock size={14} className="text-purple-400" />
              インシデント タイムライン
            </h3>
            <div className="relative">
              <div className="space-y-6 relative before:absolute before:inset-0 before:ml-2 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-dm-border before:to-transparent">
                {incident.timeline.map((event, i) => (
                  <div key={i} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    <div className="flex items-center justify-center w-5 h-5 rounded-full border border-dm-border bg-dm-surface text-dm-muted shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 group-[.is-active]:bg-blue-500/20 group-[.is-active]:border-blue-500 group-[.is-active]:text-blue-400">
                      <div className="w-1.5 h-1.5 bg-current rounded-full"></div>
                    </div>
                    <div className="w-[calc(100%-2rem)] md:w-[calc(50%-1.5rem)] bg-dm-surface-2 p-3 rounded-lg border border-dm-border">
                      <div className="flex items-center justify-between mb-1">
                        <div className="text-xs font-semibold text-dm-text">{event.event}</div>
                        <time className="text-[10px] text-dm-muted mono">{new Date(event.timestamp).toLocaleTimeString("ja-JP")}</time>
                      </div>
                      <div className="text-xs text-dm-muted">{event.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
