"use client";

/**
 * DevMirror - VM コンソール
 *
 * ブラウザの中から VM に「入る」ための画面。
 * noVNC が WebSocket 経由で VNC を話し、VM の画面をそのまま操作できる。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Monitor, Play, Power, RotateCcw } from "lucide-react";
import { Button, Card, PageHeader } from "@/components/ui";
import type RFB from "@novnc/novnc";

type VmState = {
  name: string;
  created: boolean;
  running: boolean;
  pid: number | null;
  vnc_port: number | null;
  overlay: string;
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function call(path: string, method: "GET" | "POST" = "GET") {
  const res = await fetch(`${API}/api/v1${path}`, { method });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function VmConsolePage() {
  const [vms, setVms] = useState<VmState[]>([]);
  const [active, setActive] = useState<string>("envA");
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [status, setStatus] = useState("未接続");

  const screenRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<RFB | null>(null);

  const load = useCallback(async () => {
    try {
      setVms(await call("/vm/console/list"));
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 5000);
    return () => clearInterval(t);
  }, [load]);

  // noVNC は ESM なので動的インポートする（SSR を避ける）
  useEffect(() => {
    let disposed = false;

    async function connect() {
      const el = screenRef.current;
      if (!el) return;

      if (rfbRef.current) {
        rfbRef.current.disconnect();
        rfbRef.current = null;
      }
      el.innerHTML = "";

      try {
        const { default: RFB } = await import("@novnc/novnc");
        if (disposed) return;

        const proto = location.protocol === "https:" ? "wss" : "ws";
        const host = API.replace(/^https?:\/\//, "");
        const url = `${proto}://${host}/api/v1/vm/console/${active}/vnc`;

        const rfb = new RFB(el, url, { credentials: { password: "" } });
        rfbRef.current = rfb;

        rfb.addEventListener("connect", () => setStatus("接続しました（操作できます）"));
        rfb.addEventListener("disconnect", () => setStatus("切断されました"));
        rfb.addEventListener("securityfailure", () => setStatus("認証に失敗しました"));
        rfb.scaleViewport = true;
        rfb.resizeSession = false;
      } catch (e) {
        setStatus(`接続できません: ${String(e)}`);
      }
    }

    void connect();
    return () => {
      disposed = true;
      if (rfbRef.current) {
        rfbRef.current.disconnect();
        rfbRef.current = null;
      }
    };
  }, [active]);

  const act = async (name: string, action: string) => {
    setBusy(name + action);
    try {
      await call(`/vm/console/${name}/${action}`, "POST");
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
      await load();
    }
  };

  const current = vms.find((v) => v.name === active);

  return (
    <div className="space-y-6">
      <PageHeader
        title="VM コンソール"
        subtitle="ブラウザの中から VM に入って、そのまま操作できます"
      />

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <span className="text-sm break-all">{error}</span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {vms.map((vm) => (
          <Card key={vm.name} className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Monitor className="w-4 h-4 text-dm-muted" />
                <span className="font-mono font-semibold">{vm.name}</span>
              </div>
              {vm.running ? (
                <span className="flex items-center gap-1 text-xs text-dm-accent">
                  <CheckCircle2 className="w-3 h-3" /> 起動中
                </span>
              ) : (
                <span className="text-xs text-dm-muted">停止</span>
              )}
            </div>

            <div className="text-xs text-dm-muted space-y-1">
              <p className="truncate" title={vm.overlay}>
                overlay:{" "}
                <span className="font-mono">{vm.created ? "作成済み" : "未作成"}</span>
              </p>
              <p>
                VNC: <span className="font-mono">{vm.vnc_port ?? "-"}</span>
                {vm.pid !== null && (
                  <span className="font-mono"> / pid {vm.pid}</span>
                )}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant={active === vm.name ? "primary" : "secondary"}
                onClick={() => setActive(vm.name)}
              >
                開く
              </Button>
              {!vm.created && (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={!!busy}
                  onClick={() => void act(vm.name, "create")}
                >
                  作成
                </Button>
              )}
              <Button
                size="sm"
                variant="secondary"
                disabled={!!busy}
                onClick={() => void act(vm.name, vm.running ? "stop" : "start")}
              >
                {vm.running ? (
                  <Power className="w-3 h-3" />
                ) : (
                  <Play className="w-3 h-3" />
                )}
                {vm.running ? "停止" : "起動"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={!!busy}
                onClick={() => void act(vm.name, "reset")}
              >
                <RotateCcw className="w-3 h-3" /> リセット
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <Card className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-medium">コンソール — {active}</span>
          <span className="text-xs text-dm-muted">{status}</span>
        </div>

        {current && !current.running && (
          <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <span className="font-mono font-semibold">{active}</span> が停止しています。
            上の「起動」を押すと、ここに VM の画面が出ます。
          </p>
        )}

        <div
          ref={screenRef}
          className="min-h-[460px] w-full overflow-hidden rounded-lg border border-dm-border bg-black"
        />
        <p className="text-xs text-dm-muted">
          VM の画面をクリックして、キーボードとマウスで操作できます。
        </p>
      </Card>
    </div>
  );
}
