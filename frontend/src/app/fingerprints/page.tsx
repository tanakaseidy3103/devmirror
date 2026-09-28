"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Monitor } from "lucide-react";
import { api, type Fingerprint } from "@/lib/api";
import { Card, EmptyState, LoadingSpinner, PageHeader } from "@/components/ui";

export default function FingerprintsPage() {
  const [items, setItems] = useState<Fingerprint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listFingerprints().then(setItems).catch(console.error).finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 animate-fade-in">
      <PageHeader title="環境レジストリ" subtitle="保存済みの Environment Fingerprint" />
      {loading ? (
        <div className="flex justify-center py-20"><LoadingSpinner size="lg" /></div>
      ) : !items.length ? (
        <EmptyState icon={<Monitor size={32} />} title="Fingerprint がありません" description="スキャナーまたは公式デモから作成できます" />
      ) : (
        <div className="space-y-3">
          {items.map((fp) => (
            <Link key={fp.fingerprint_id} href={`/fingerprints/${fp.fingerprint_id}`}>
              <Card hover>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{fp.environment_name}</p>
                    <p className="text-xs text-dm-muted mt-1">
                      {fp.os?.name} {fp.os?.build} · {fp.architecture?.cpu_arch} · スキーマ {fp.schema_version}
                    </p>
                  </div>
                  <span className="mono text-xs text-blue-400">{fp.fingerprint_id.slice(0, 8)}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
