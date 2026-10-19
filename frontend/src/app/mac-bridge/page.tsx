"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Laptop, Loader2, Plug, PlugZap, ShieldCheck, Trash2 } from "lucide-react";
import { api, getErrorMessage, type MacHost, type MacHostStatus, type RegisterMacRequest } from "@/lib/api";
import { Button, Card, EmptyState, PageHeader } from "@/components/ui";

const statusConfig: Record<MacHostStatus, { label: string; className: string }> = {
  online: { label: "オンライン", className: "bg-green-500/15 text-green-400 border-green-500/30" },
  offline: { label: "オフライン", className: "bg-gray-500/15 text-gray-400 border-gray-500/30" },
  auth_failed: { label: "認証失敗", className: "bg-red-500/15 text-red-400 border-red-500/30" },
  host_key_mismatch: { label: "ホスト鍵不一致", className: "bg-red-600/15 text-red-500 border-red-600/30" },
  error: { label: "エラー", className: "bg-orange-500/15 text-orange-400 border-orange-500/30" },
  disconnected: { label: "切断済み", className: "bg-gray-600/15 text-gray-500 border-gray-600/30" },
  unknown: { label: "未確認", className: "bg-blue-500/15 text-blue-400 border-blue-500/30" },
};

const emptyForm: RegisterMacRequest = {
  name: "",
  hostname: "",
  port: 22,
  username: "",
  key_path: "",
  host_key_fingerprint: "",
};

const inputClass =
  "w-full bg-dm-surface-2 border border-dm-border rounded-lg px-3 py-2 text-sm text-dm-text focus:outline-none focus:border-blue-500 transition-colors";

function formatDate(value: string | null) {
  return value ? new Date(value + "Z").toLocaleString("ja-JP") : "—";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs text-dm-muted uppercase tracking-wider block mb-1.5">{label}</span>
      {children}
    </label>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] text-dm-muted">{label}</div>
      <div className="text-sm text-dm-text font-mono break-all">{value ?? "—"}</div>
    </div>
  );
}

function HostCard({ host, onChange }: { host: MacHost; onChange: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const status = statusConfig[host.status] ?? statusConfig.unknown;

  const run = async (action: string, fn: () => Promise<unknown>) => {
    setBusy(action);
    setError(null);
    try {
      await fn();
      onChange();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <Laptop size={20} className="text-blue-400" />
          <div>
            <div className="font-semibold text-dm-text">{host.name}</div>
            <div className="text-xs text-dm-muted font-mono">
              {host.username}@{host.hostname}:{host.port}
            </div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full border ${status.className}`}>{status.label}</span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => run("test", () => api.testMacHost(host.id))} disabled={!!busy}>
            {busy === "test" ? <Loader2 size={12} className="animate-spin" /> : <PlugZap size={12} />}
            接続テスト
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => run("disconnect", () => api.disconnectMacHost(host.id))}
            disabled={!!busy || !host.enabled}
          >
            <Plug size={12} />
            切断
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              if (confirm(`「${host.name}」の登録を削除しますか？`)) run("delete", () => api.deleteMacHost(host.id));
            }}
            disabled={!!busy}
          >
            <Trash2 size={12} />
            削除
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Info label="macOS" value={host.macos_version} />
        <Info label="Xcode" value={host.xcode_version && `${host.xcode_version} (${host.xcode_build ?? "?"})`} />
        <Info label="アーキテクチャ" value={host.arch} />
        <Info label="空き容量" value={host.disk_free_gb != null ? `${host.disk_free_gb} GB` : null} />
        <Info label="最終接続成功" value={formatDate(host.last_connected_at)} />
        <Info label="最終確認" value={formatDate(host.last_checked_at)} />
        <Info label="開発ツール" value={host.tools.length ? host.tools.join(", ") : null} />
        <Info label="ホスト鍵" value={<span className="text-[11px]">{host.host_key_fingerprint}</span>} />
      </div>

      <div className="mt-4">
        <div className="text-[11px] text-dm-muted mb-1">利用可能なシミュレータ（{host.simulators.length}）</div>
        {host.simulators.length ? (
          <div className="flex flex-wrap gap-1.5">
            {host.simulators.map((s) => (
              <span key={s.udid} className="text-xs bg-dm-surface-2 border border-dm-border rounded px-2 py-0.5">
                {s.name} · {s.runtime}
              </span>
            ))}
          </div>
        ) : (
          <div className="text-xs text-dm-muted">—（接続テストで取得します）</div>
        )}
      </div>

      {(host.issues.length > 0 || host.last_error || error) && (
        <div className="mt-4 space-y-1">
          {[...(error ? [error] : []), ...(host.last_error ? [host.last_error] : []), ...host.issues].map((msg, i) => (
            <p key={i} className="text-xs text-yellow-400/90 flex items-start gap-2">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              {msg}
            </p>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function MacBridgePage() {
  const [hosts, setHosts] = useState<MacHost[] | null>(null);
  const [form, setForm] = useState<RegisterMacRequest>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listMacHosts().then(setHosts).catch((e) => setError(getErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const set = (key: keyof RegisterMacRequest) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: key === "port" ? Number(e.target.value) : e.target.value });

  const register = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.registerMacHost(form);
      setForm(emptyForm);
      load();
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const ready = form.name && form.hostname && form.username && form.key_path && form.host_key_fingerprint;

  return (
    <div className="p-4 md:p-8 animate-fade-in">
      <PageHeader
        title="Mac接続管理"
        subtitle="許可した実機 Mac に SSH で接続し、macOS・Xcode・シミュレータを確認します（Xcode は Mac 上で動作します）"
      />

      <div className="space-y-4 mb-8">
        {hosts === null ? (
          <Loader2 className="animate-spin text-dm-muted" />
        ) : hosts.length === 0 ? (
          <EmptyState icon={<Laptop size={24} />} title="Mac が登録されていません" description="下のフォームから Mac を登録してください" />
        ) : (
          hosts.map((h) => <HostCard key={h.id} host={h} onChange={load} />)
        )}
      </div>

      <Card>
        <h2 className="font-semibold text-dm-text mb-4 flex items-center gap-2">
          <ShieldCheck size={16} className="text-blue-400" />
          Mac を登録
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <Field label="表示名">
            <input className={inputClass} value={form.name} onChange={set("name")} placeholder="例: 自宅の MacBook" />
          </Field>
          <Field label="ホスト名 / IP アドレス">
            <input className={inputClass} value={form.hostname} onChange={set("hostname")} placeholder="例: my-mac.local / 192.168.1.20" />
          </Field>
          <Field label="SSH ユーザー">
            <input className={inputClass} value={form.username} onChange={set("username")} placeholder="Mac のユーザー名" />
          </Field>
          <Field label="ポート">
            <input className={inputClass} type="number" value={form.port} onChange={set("port")} />
          </Field>
          <Field label="SSH 秘密鍵のパス（Windows 側）">
            <input className={inputClass} value={form.key_path} onChange={set("key_path")} placeholder="例: C:\Users\you\.ssh\devmirror_mac" />
          </Field>
          <Field label="ホスト鍵フィンガープリント">
            <input className={inputClass} value={form.host_key_fingerprint} onChange={set("host_key_fingerprint")} placeholder="SHA256:..." />
          </Field>
        </div>
        <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-3 mb-4 text-xs text-yellow-400/80 space-y-1">
          <p>フィンガープリントは Mac 本体で次のコマンドを実行して確認してください（なりすまし防止）:</p>
          <code className="block font-mono text-dm-text">ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code>
          <p>秘密鍵・パスワードは保存しません。鍵ファイルのパスのみを保存します。</p>
        </div>
        {error && (
          <p className="text-xs text-red-400 mb-4 flex items-center gap-2">
            <AlertTriangle size={12} />
            {error}
          </p>
        )}
        <Button onClick={register} disabled={saving || !ready}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
          ホスト鍵を確認して登録
        </Button>
      </Card>
    </div>
  );
}
