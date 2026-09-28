"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  FolderGit2,
  Monitor,
  RefreshCw,
  Scan,
  Zap,
} from "lucide-react";
import { api, getErrorMessage, type DashboardStats } from "@/lib/api";
import {
  Card,
  EmptyState,
  IncidentStatusBadge,
  LoadingSpinner,
  StatCard,
  TestResultBadge,
} from "@/components/ui";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  const loadStats = () =>
    api
      .getDashboardStats()
      .then(setStats)
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    loadStats();
  }, []);

  const handleSeed = async () => {
    setSeeding(true);
    setSeedMessage(null);
    try {
      const result = await api.seedDxDemo();
      setSeedMessage(result.message);
      setLoading(true);
      await loadStats();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="p-8 animate-fade-in">
      {/* ヘッダー */}
      <div className="mb-10">
        <div className="flex items-center gap-2 text-dm-muted text-xs mb-3 font-mono">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 pulse-dot" />
          システム稼働中
        </div>
        <h1 className="text-3xl font-bold text-dm-text">
          <span className="gradient-text">DevMirror</span> ダッシュボード
        </h1>
        <p className="text-dm-muted mt-2 text-sm">
          環境 → 差分 → 再現 → 証拠 → 診断 → 保存 → 再実行
        </p>
        <button
          onClick={handleSeed}
          disabled={seeding}
          className="mt-4 text-xs px-3 py-1.5 rounded-lg bg-blue-500/15 text-blue-300 border border-blue-500/30 hover:bg-blue-500/25 disabled:opacity-50"
        >
          {seeding ? "デモ投入中..." : "DX Library 公式デモを投入"}
        </button>
        {seedMessage && <p className="text-xs text-green-400 mt-2">{seedMessage}</p>}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <LoadingSpinner size="lg" />
        </div>
      ) : error ? (
        <ApiErrorBanner error={error} />
      ) : (
        <>
          {/* 統計カード */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
            <StatCard
              title="プロジェクト"
              value={stats?.projects ?? 0}
              icon={<FolderGit2 size={18} />}
              color="blue"
            />
            <StatCard
              title="環境"
              value={stats?.environments ?? 0}
              subtitle="スキャン済み"
              icon={<Monitor size={18} />}
              color="purple"
            />
            <StatCard
              title="インシデント"
              value={stats?.incidents.total ?? 0}
              subtitle={`${stats?.incidents.open ?? 0} オープン`}
              icon={<AlertTriangle size={18} />}
              color="yellow"
            />
            <StatCard
              title="再現済み"
              value={stats?.incidents.reproduced ?? 0}
              subtitle={`${stats?.incidents.failed_tests ?? 0} テスト失敗`}
              icon={<RefreshCw size={18} />}
              color="green"
            />
          </div>

          <div className="grid grid-cols-3 gap-6 mb-8">
            {/* 最近のインシデント */}
            <div className="col-span-2">
              <Card>
                <div className="flex items-center justify-between mb-5">
                  <h2 className="font-semibold text-dm-text flex items-center gap-2">
                    <AlertTriangle size={16} className="text-yellow-400" />
                    最近のインシデント
                  </h2>
                  <Link
                    href="/incidents"
                    className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
                  >
                    すべて見る <ArrowRight size={12} />
                  </Link>
                </div>

                {!stats?.recent_incidents?.length ? (
                  <EmptyState
                    icon={<AlertTriangle size={32} />}
                    title="インシデントなし"
                    description="インシデントはまだ記録されていません"
                  />
                ) : (
                  <div className="space-y-2">
                    {stats.recent_incidents.map((inc) => (
                      <Link
                        key={inc.incident_id}
                        href={`/incidents/${inc.incident_id}`}
                        className="flex items-center justify-between p-3 rounded-lg bg-dm-surface-2 hover:bg-dm-border transition-colors group"
                      >
                        <div className="flex items-center gap-3">
                          <span className="mono text-xs text-blue-400 font-bold w-20">
                            {inc.incident_id}
                          </span>
                          <div>
                            <p className="text-sm text-dm-text font-medium group-hover:text-blue-300 transition-colors">
                              {inc.project_name}
                            </p>
                            <p className="text-xs text-dm-muted">{inc.environment_name}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <TestResultBadge result={inc.test_result} />
                          <IncidentStatusBadge status={inc.status} />
                          <ArrowRight size={12} className="text-dm-muted group-hover:text-blue-400 transition-colors" />
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            {/* クイックアクション */}
            <div>
              <Card>
                <h2 className="font-semibold text-dm-text mb-5 flex items-center gap-2">
                  <Zap size={16} className="text-blue-400" />
                  クイックアクション
                </h2>
                <div className="space-y-2">
                  {[
                    {
                      href: "/scanner",
                      label: "環境スキャン",
                      desc: "現在の環境を分析",
                      icon: Scan,
                      color: "text-blue-400",
                    },
                    {
                      href: "/diff",
                      label: "環境差分の比較",
                      desc: "2つの環境を比較",
                      icon: BarChart3,
                      color: "text-purple-400",
                    },
                    {
                      href: "/incidents/new",
                      label: "インシデント作成",
                      desc: "新しい障害を記録",
                      icon: AlertTriangle,
                      color: "text-yellow-400",
                    },
                    {
                      href: "/replay",
                      label: "インシデント再現",
                      desc: "過去の障害を再現",
                      icon: RefreshCw,
                      color: "text-green-400",
                    },
                    {
                      href: "/diagnosis",
                      label: "AI診断",
                      desc: "証拠ベース分析",
                      icon: BrainCircuit,
                      color: "text-cyan-400",
                    },
                  ].map((action) => {
                    const Icon = action.icon;
                    return (
                      <Link
                        key={action.href}
                        href={action.href}
                        className="flex items-center gap-3 p-3 rounded-lg hover:bg-dm-surface-2 transition-colors group"
                      >
                        <Icon size={15} className={action.color} />
                        <div>
                          <p className="text-sm text-dm-text group-hover:text-blue-300 transition-colors">
                            {action.label}
                          </p>
                          <p className="text-xs text-dm-muted">{action.desc}</p>
                        </div>
                        <ArrowRight
                          size={12}
                          className="ml-auto text-dm-muted group-hover:text-blue-400 transition-colors"
                        />
                      </Link>
                    );
                  })}
                </div>
              </Card>
            </div>
          </div>

          {/* ワークフロー説明 */}
          <Card>
            <h2 className="font-semibold text-dm-text mb-5 flex items-center gap-2">
              <Activity size={16} className="text-cyan-400" />
              DevMirror ワークフロー
            </h2>
            <div className="flex items-center gap-1 flex-wrap">
              {[
                { label: "環境", sub: "Environment", color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/20" },
                { label: "→", color: "text-dm-muted", bg: "" },
                { label: "差分", sub: "Diff", color: "text-purple-400", bg: "bg-purple-500/10 border-purple-500/20" },
                { label: "→", color: "text-dm-muted", bg: "" },
                { label: "再現", sub: "Reproduce", color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/20" },
                { label: "→", color: "text-dm-muted", bg: "" },
                { label: "証拠", sub: "Evidence", color: "text-orange-400", bg: "bg-orange-500/10 border-orange-500/20" },
                { label: "→", color: "text-dm-muted", bg: "" },
                { label: "診断", sub: "Diagnose", color: "text-cyan-400", bg: "bg-cyan-500/10 border-cyan-500/20" },
                { label: "→", color: "text-dm-muted", bg: "" },
                { label: "保存", sub: "Save", color: "text-green-400", bg: "bg-green-500/10 border-green-500/20" },
                { label: "→", color: "text-dm-muted", bg: "" },
                { label: "再実行", sub: "Replay", color: "text-green-300", bg: "bg-green-400/10 border-green-400/20" },
              ].map((step, i) => (
                <span
                  key={i}
                  className={`
                    font-mono text-sm font-semibold flex flex-col items-center leading-tight
                    ${step.bg ? `px-3 py-1.5 rounded-lg border ${step.bg}` : ""}
                    ${step.color}
                  `}
                >
                  {step.label}
                  {"sub" in step && step.sub && (
                    <span className="text-[10px] font-normal opacity-70">{step.sub}</span>
                  )}
                </span>
              ))}
            </div>
            <p className="text-xs text-dm-muted mt-4">
              DevMirrorは「AIがバグを直す」ツールではありません。
              環境問題・障害再現・インシデント証拠を<strong className="text-dm-text">観測可能・再現可能・分析可能</strong>にするプラットフォームです。
            </p>
          </Card>
        </>
      )}
    </div>
  );
}

function ApiErrorBanner({ error }: { error: string }) {
  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 flex items-start gap-4">
      <AlertTriangle size={20} className="text-red-400 shrink-0 mt-0.5" />
      <div>
        <p className="font-semibold text-red-400">バックエンドに接続できません</p>
        <p className="text-sm text-dm-muted mt-1">
          バックエンドが起動しているか確認してください：{" "}
          <code className="mono text-xs bg-dm-surface px-1 rounded">
            cd backend && uvicorn app.main:app --reload
          </code>
        </p>
        <p className="text-xs text-red-400/70 mt-2 mono">{error}</p>
      </div>
    </div>
  );
}
