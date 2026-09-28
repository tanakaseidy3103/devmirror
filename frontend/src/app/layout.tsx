import type { Metadata } from "next";
import { Noto_Sans_JP } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";

const notoSansJp = Noto_Sans_JP({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "DevMirror — 環境差異の可視化・障害再現プラットフォーム",
  description:
    "Environment → Diff → Reproduce → Evidence → Diagnose → Save → Replay. 問題を再現可能なインシデントへ変換するエンジニアリングプラットフォーム。",
  keywords: ["DevOps", "環境差異", "障害再現", "インシデント管理", "デバッグ"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja" className="dark">
      <body className={`${notoSansJp.className} bg-dm-bg text-dm-text antialiased`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 ml-64 min-h-screen overflow-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
