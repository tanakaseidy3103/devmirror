"use client";

import { useState } from "react";
import { Scan, AlertTriangle, CheckCircle, Loader2 } from "lucide-react";
import { api, getErrorMessage, type Fingerprint } from "@/lib/api";
import { dependencyStatusLabel } from "@/lib/labels";
import { Button, Card, PageHeader } from "@/components/ui";

export default function ScannerPage() {
  const [environmentName, setEnvironmentName] = useState("環境A");
  const [projectPath, setProjectPath] = useState("");
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<Fingerprint | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    setResult(null);
    try {
      const fp = await api.scanEnvironment({
        environment_name: environmentName,
        project_path: projectPath || undefined,
      });
      setResult(fp);
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader
        title="環境スキャナー"
        subtitle="現在の環境をスキャンして Environment Fingerprint を生成します"
      />

      {/* スキャン設定 */}
      <Card className="mb-6">
        <h2 className="font-semibold text-dm-text mb-4 flex items-center gap-2">
          <Scan size={16} className="text-blue-400" />
          スキャン設定
        </h2>
        <div className="grid grid-cols-2 gap-4 mb-5">
          <div>
            <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
              環境名
            </label>
            <input
              type="text"
              value={environmentName}
              onChange={(e) => setEnvironmentName(e.target.value)}
              className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="例: Windows 11 開発環境"
            />
          </div>
          <div>
            <label className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">
              プロジェクトパス（任意）
            </label>
            <input
              type="text"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              className="w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="例: C:\Projects\DXGame"
            />
          </div>
        </div>

        <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-3 mb-5">
          <p className="text-xs text-yellow-400/80 flex items-center gap-2">
            <AlertTriangle size={12} />
            スキャンはパスワード・APIキー・シークレット・プライベートキーを収集しません
          </p>
        </div>

        <Button onClick={handleScan} disabled={scanning || !environmentName}>
          {scanning ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              スキャン中...
            </>
          ) : (
            <>
              <Scan size={14} />
              環境をスキャン
            </>
          )}
        </Button>
      </Card>

      {/* エラー */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6 flex items-center gap-3">
          <AlertTriangle size={16} className="text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* スキャン結果 */}
      {result && (
        <div className="animate-slide-up space-y-4">
          <div className="flex items-center gap-2 text-green-400 mb-2">
            <CheckCircle size={16} />
            <span className="text-sm font-medium">スキャン完了</span>
            <span className="mono text-xs text-dm-muted">ID: {result.fingerprint_id.slice(0, 8)}...</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* OS */}
            {result.os && (
              <Card>
                <h3 className="text-xs text-dm-muted uppercase tracking-wider mb-3">OS</h3>
                <FingerprintSection data={{
                  名前: result.os.name,
                  バージョン: result.os.version,
                  ビルド: result.os.build,
                }} />
              </Card>
            )}

            {/* アーキテクチャ */}
            {result.architecture && (
              <Card>
                <h3 className="text-xs text-dm-muted uppercase tracking-wider mb-3">アーキテクチャ</h3>
                <FingerprintSection data={{
                  CPU: result.architecture.cpu_arch,
                  物理コア: result.architecture.physical_cores,
                  メモリ: result.architecture.total_memory_gb ? `${result.architecture.total_memory_gb} GB` : undefined,
                }} />
              </Card>
            )}

            {/* ランタイム */}
            {result.runtime && (
              <Card>
                <h3 className="text-xs text-dm-muted uppercase tracking-wider mb-3">ランタイム</h3>
                <FingerprintSection data={{
                  Python: result.runtime.python,
                  "Node.js": result.runtime.node,
                  PHP: result.runtime.php,
                }} />
              </Card>
            )}

            {/* コンパイラ */}
            {result.compiler && (
              <Card>
                <h3 className="text-xs text-dm-muted uppercase tracking-wider mb-3">コンパイラ</h3>
                <FingerprintSection data={{
                  MSVC: result.compiler.msvc,
                  "Visual Studio": result.compiler.visual_studio,
                  GCC: result.compiler.gcc,
                  CMake: result.compiler.cmake,
                }} />
              </Card>
            )}
          </div>

          {/* 依存関係 */}
          {result.dependencies && result.dependencies.length > 0 && (
            <Card>
              <h3 className="text-xs text-dm-muted uppercase tracking-wider mb-3">依存関係</h3>
              <div className="space-y-2">
                {result.dependencies.map((dep) => (
                  <div key={dep.name} className="flex items-center justify-between py-2 border-b border-dm-border last:border-0">
                    <span className="text-sm text-dm-text font-mono">{dep.name}</span>
                    <div className="flex items-center gap-3">
                      {dep.version && <span className="text-xs text-dm-muted mono">{dep.version}</span>}
                      <span className={`badge text-xs ${
                        dep.status === "PRESENT"
                          ? "bg-green-500/15 text-green-400 border border-green-500/30"
                          : dep.status === "MISSING"
                          ? "bg-red-500/15 text-red-400 border border-red-500/30"
                          : "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30"
                      }`}>
                        {dependencyStatusLabel(dep.status)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* JSONダンプ */}
          <Card>
            <h3 className="text-xs text-dm-muted uppercase tracking-wider mb-3">Fingerprint 生のデータ (JSON)</h3>
            <pre className="mono text-xs text-dm-muted overflow-auto max-h-64 bg-dm-surface-2 p-4 rounded-lg">
              {JSON.stringify(result, null, 2)}
            </pre>
          </Card>
        </div>
      )}
    </div>
  );
}

function FingerprintSection({ data }: { data: Record<string, string | number | undefined | null> }) {
  return (
    <dl className="space-y-1.5">
      {Object.entries(data)
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => (
          <div key={k} className="flex items-center justify-between">
            <dt className="text-xs text-dm-muted">{k}</dt>
            <dd className="text-xs text-dm-text mono">{String(v)}</dd>
          </div>
        ))}
    </dl>
  );
}
