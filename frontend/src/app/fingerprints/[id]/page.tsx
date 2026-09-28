"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ChevronDown, ChevronUp, Monitor } from "lucide-react";
import { api, type Fingerprint } from "@/lib/api";
import { dependencyStatusLabel } from "@/lib/labels";
import { Card, LoadingSpinner, PageHeader } from "@/components/ui";

export default function FingerprintDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [fp, setFp] = useState<Fingerprint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    setError(null);
    api
      .getFingerprint(id)
      .then(setFp)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6">
          <p className="font-semibold text-red-400 mb-1">Fingerprint を取得できません</p>
          <p className="text-sm text-dm-muted">{error}</p>
          <Link href="/fingerprints" className="text-xs text-blue-400 hover:text-blue-300 mt-3 inline-block">
            ← 一覧へ戻る
          </Link>
        </div>
      </div>
    );
  }

  if (!fp) {
    return <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>;
  }

  return (
    <div className="p-8 animate-fade-in">
      <Link
        href="/fingerprints"
        className="text-xs text-dm-muted hover:text-blue-400 flex items-center gap-1 mb-4 transition-colors"
      >
        <ArrowLeft size={12} /> 環境レジストリへ戻る
      </Link>

      <PageHeader
        title={fp.environment_name}
        subtitle={`Environment Fingerprint（スキーマ ${fp.schema_version}）· 収集日時 ${new Date(
          fp.collected_at
        ).toLocaleString("ja-JP")}`}
      />

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <h2 className="font-semibold mb-3">OS</h2>
          <KeyValues
            values={[
              ["名称", fp.os?.name],
              ["バージョン", fp.os?.version],
              ["ビルド", fp.os?.build],
              ["エディション", fp.os?.edition],
            ]}
          />
        </Card>

        <Card>
          <h2 className="font-semibold mb-3">アーキテクチャ</h2>
          <KeyValues
            values={[
              ["CPUアーキテクチャ", fp.architecture?.cpu_arch],
              ["物理コア数", fp.architecture?.physical_cores],
              ["論理コア数", fp.architecture?.logical_cores],
              ["メモリ容量", fp.architecture?.total_memory_gb ? `${fp.architecture.total_memory_gb} GB` : undefined],
            ]}
          />
        </Card>

        <Card>
          <h2 className="font-semibold mb-3">ランタイム</h2>
          <KeyValues
            values={[
              ["Python", fp.runtime?.python],
              ["Node.js", fp.runtime?.node],
              ["PHP", fp.runtime?.php],
              ["Java", fp.runtime?.java],
              [".NET", fp.runtime?.dotnet],
            ]}
          />
        </Card>

        <Card>
          <h2 className="font-semibold mb-3">コンパイラ</h2>
          <KeyValues
            values={[
              ["MSVC", fp.compiler?.msvc],
              ["Visual Studio", fp.compiler?.visual_studio],
              ["Windows SDK", fp.compiler?.windows_sdk],
              ["GCC", fp.compiler?.gcc],
              ["Clang", fp.compiler?.clang],
              ["CMake", fp.compiler?.cmake],
            ]}
          />
        </Card>

        <Card>
          <h2 className="font-semibold mb-3">プロジェクト</h2>
          <KeyValues
            values={[
              ["名称", fp.project?.name],
              ["言語", fp.project?.language],
              ["Gitコミット", fp.project?.git_commit],
              ["Gitブランチ", fp.project?.git_branch],
            ]}
          />
        </Card>

        <Card>
          <h2 className="font-semibold mb-3">依存関係</h2>
          {fp.dependencies?.length ? (
            <div className="space-y-1.5">
              {fp.dependencies.map((dep) => (
                <div key={dep.name} className="flex items-center justify-between gap-2">
                  <span className="text-sm text-dm-text truncate">{dep.name}</span>
                  <span className="flex items-center gap-2 shrink-0">
                    {dep.version && <span className="text-xs mono text-dm-muted">{dep.version}</span>}
                    <span
                      className={`badge text-[10px] ${
                        dep.status === "PRESENT"
                          ? "bg-green-500/15 text-green-400 border border-green-500/30"
                          : dep.status === "MISSING"
                          ? "bg-red-500/15 text-red-400 border border-red-500/30"
                          : "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30"
                      }`}
                    >
                      {dependencyStatusLabel(dep.status)}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-dm-muted">依存関係は収集されていません</p>
          )}
        </Card>

        <Card className="col-span-2">
          <h2 className="font-semibold mb-3">PATH エントリ（ユーザー名は伏せています）</h2>
          {fp.path_entries?.length ? (
            <pre className="text-xs mono text-dm-muted whitespace-pre-wrap">
              {fp.path_entries.join("\n")}
            </pre>
          ) : (
            <p className="text-sm text-dm-muted">PATH は収集されていません</p>
          )}
        </Card>
      </div>

      {/* 生のデータ */}
      <Card className="mt-4">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="w-full flex items-center justify-between text-left"
        >
          <h2 className="font-semibold flex items-center gap-2">
            <Monitor size={15} className="text-dm-muted" />
            生のデータ (JSON)
          </h2>
          {showRaw ? (
            <ChevronUp size={15} className="text-dm-muted" />
          ) : (
            <ChevronDown size={15} className="text-dm-muted" />
          )}
        </button>
        {showRaw && (
          <pre className="mono text-xs text-dm-muted overflow-auto max-h-96 bg-dm-surface-2 p-4 rounded-lg mt-3">
            {JSON.stringify(fp, null, 2)}
          </pre>
        )}
      </Card>
    </div>
  );
}

function KeyValues({ values }: { values: [string, string | number | undefined | null][] }) {
  const rows = values.filter(([, v]) => v !== undefined && v !== null && v !== "");

  if (!rows.length) {
    return <p className="text-sm text-dm-muted">情報がありません</p>;
  }

  return (
    <dl className="space-y-1.5">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between gap-3">
          <dt className="text-xs text-dm-muted shrink-0">{label}</dt>
          <dd className="text-xs mono text-dm-text text-right break-all">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
