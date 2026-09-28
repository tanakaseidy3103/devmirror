"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  Clock,
  FolderGit2,
  GitCompare,
  History,
  LayoutDashboard,
  Monitor,
  MonitorSmartphone,
  RefreshCw,
  Scan,
  Zap,
} from "lucide-react";

const navigation = [
  {
    section: "概要",
    items: [
      { href: "/", label: "ダッシュボード", icon: LayoutDashboard },
      { href: "/projects", label: "プロジェクト", icon: FolderGit2 },
    ],
  },
  {
    section: "環境",
    items: [
      { href: "/scanner", label: "環境スキャナー", icon: Scan },
      { href: "/fingerprints", label: "Fingerprint 一覧", icon: Monitor },
      { href: "/diff", label: "環境差分の比較", icon: GitCompare },
      { href: "/matrix", label: "環境マトリクス", icon: BarChart3 },
      { href: "/vm/console", label: "VM コンソール", icon: MonitorSmartphone },
    ],
  },
  {
    section: "インシデント",
    items: [
      { href: "/incidents", label: "インシデント一覧", icon: AlertTriangle },
      { href: "/replay", label: "インシデント再現", icon: RefreshCw },
      { href: "/history", label: "インシデント履歴", icon: History },
    ],
  },
  {
    section: "分析",
    items: [
      { href: "/diagnosis", label: "AI診断", icon: BrainCircuit },
      { href: "/timeline", label: "タイムライン", icon: Clock },
      { href: "/observability", label: "オブザーバビリティ", icon: Activity },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-dm-surface border-r border-dm-border flex flex-col z-50">
      {/* ロゴ */}
      <div className="p-5 border-b border-dm-border">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg">
              <Zap size={16} className="text-white" />
            </div>
            <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-dm-green rounded-full border-2 border-dm-surface pulse-dot" />
          </div>
          <div>
            <span className="text-base font-bold gradient-text tracking-tight">DevMirror</span>
            <div className="text-[10px] text-dm-muted font-mono">v0.1.0</div>
          </div>
        </Link>
      </div>

      {/* ナビゲーション */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-6">
        {navigation.map((group) => (
          <div key={group.section}>
            <div className="text-[10px] font-semibold text-dm-muted uppercase tracking-widest px-2 mb-2">
              {group.section}
            </div>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={`
                        flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium
                        transition-all duration-150
                        ${isActive
                          ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                          : "text-dm-muted hover:text-dm-text hover:bg-dm-surface-2"
                        }
                      `}
                    >
                      <Icon size={15} className={isActive ? "text-blue-400" : ""} />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* フッター */}
      <div className="p-4 border-t border-dm-border">
        <div className="text-[10px] text-dm-muted text-center font-mono">
          環境 → 差分 → 再現
        </div>
        <div className="text-[10px] text-dm-muted text-center font-mono">
          → 証拠 → 診断 → 再実行
        </div>
      </div>
    </aside>
  );
}
