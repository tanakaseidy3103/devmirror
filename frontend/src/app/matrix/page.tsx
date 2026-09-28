"use client";

import { AlertTriangle } from "lucide-react";
import type { TestResult } from "@/lib/api";
import { Card, PageHeader, TestResultBadge } from "@/components/ui";

const rows: { env: string; browser: string; result: TestResult; duration: string }[] = [
  { env: "Windows 11", browser: "Chrome", result: "PASS", duration: "1.2秒" },
  { env: "Windows 11", browser: "Edge", result: "PASS", duration: "1.4秒" },
  { env: "Windows 11", browser: "Firefox", result: "FAIL", duration: "2.1秒" },
  { env: "Linux (Docker)", browser: "Chromium", result: "UNKNOWN", duration: "—" },
];

export default function MatrixPage() {
  return (
    <div className="p-8 animate-fade-in">
      <PageHeader
        title="環境マトリクス"
        subtitle="Playwright によるブラウザ×OS の実行結果。本機能は未実装です。"
      />
      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 mb-6 flex gap-3">
        <AlertTriangle className="text-yellow-400 shrink-0" size={18} />
        <p className="text-sm text-yellow-200">
          <strong>未実装。</strong> 下表は将来のマトリクス UI の見本です。実テストは実行していません。DevMirror は BrowserStack の代替ではありません。
        </p>
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-dm-muted">
              <th className="pb-3">環境</th>
              <th className="pb-3">ブラウザ</th>
              <th className="pb-3">結果</th>
              <th className="pb-3">時間</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.env}-${row.browser}`} className="border-t border-dm-border">
                <td className="py-3">{row.env}</td>
                <td>{row.browser}</td>
                <td><TestResultBadge result={row.result} /></td>
                <td className="text-dm-muted">{row.duration}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
