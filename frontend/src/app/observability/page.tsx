import { Card, PageHeader } from "@/components/ui";

export default function ObservabilityPage() {
  return (
    <div className="p-8">
      <PageHeader title="オブザーバビリティ" subtitle="traces / logs / metrics の統合計画" />
      <Card>
        <p className="text-yellow-300 font-semibold mb-2">未実装</p>
        <p className="text-sm text-dm-muted">
          OpenTelemetry と Linux eBPF はロードマップです。現時点では Incident Capsule のログとタイムラインのみを保存します。
        </p>
      </Card>
    </div>
  );
}
