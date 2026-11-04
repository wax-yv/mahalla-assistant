"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, RefreshCw, X } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Stat } from "@/components/ui";
import { ErrorState, SkeletonList } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type AgentInfo = {
  name: string; label: string; description: string; enabled: boolean; provider: string; model: string;
  last_run_at: string | null; last_status: string; latency_ms: number; tokens_today: number; success_rate: number;
};
type ModelInfo = { id: string; provider: string; label: string; context: number; rank: number };
type ProviderStatus = { id?: string; name: string; ok: boolean; detail: string };
type StatusData = {
  agents: AgentInfo[]; models: ModelInfo[]; active_model?: string;
  budget: { total_tokens: number; budget: number; remaining: number; requests: number };
  providers: ProviderStatus[];
};

const STATUS_MAP: Record<string, { label: string; tone: string }> = {
  completed: { label: "Ishladi", tone: "ok" },
  running: { label: "Ishlayapti", tone: "info" },
  idle: { label: "Kutishda", tone: "muted" },
  failed: { label: "Xatolik", tone: "danger" },
};

export default function AgentsPage() {
  const [data, setData] = useState<StatusData | null>(null);
  const [error, setError] = useState("");
  const [reloading, setReloading] = useState(false);

  const load = useCallback(() => {
    setReloading(true);
    api
      .get<StatusData>("/agents/status")
      .then((d) => { setData(d); setError(""); })
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
      .finally(() => setReloading(false));
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (error && !data) return <ErrorState note={error} onRetry={load} />;
  if (!data) return <SkeletonList rows={5} />;

  const budgetPct = data.budget.budget > 0 ? Math.min(100, Math.round((data.budget.total_tokens / data.budget.budget) * 100)) : 0;
  const activeProviders = data.providers.filter((p) => p.ok);

  return (
    <>
      <PageHead
        kicker="AI tizimi"
        title="Agentlar monitoringi"
        lede="Orkestrator so'rovni tahlil qiladi va kerakli agentlarga yo'naltiradi (bir so'rovda 3 tagacha). Yozuv amallar faqat tasdiq bilan bajariladi."
        actions={
          <button className="btn" onClick={load} disabled={reloading} aria-label="Yangilash">
            <RefreshCw size={15} className={reloading ? "spin" : ""} /> Yangilash
          </button>
        }
      />
      <div className="grid grid-4 mb">
        <Stat label="Bugungi token" value={data.budget.total_tokens.toLocaleString("uz-UZ")} hint={`limit ${data.budget.budget.toLocaleString("uz-UZ")}`} />
        <Stat label="So'rovlar" value={data.budget.requests} hint="bugun" />
        <Stat label="Provayderlar" value={activeProviders.length} hint={activeProviders.map((p) => p.name).join(", ") || "ulangan yo'q"} />
        <Stat label="Modellar" value={data.models.length} hint="fallback zanjiri" />
      </div>

      <div className="split s2 mb">
        <div className="card card-pad">
          <h3 className="mb">Token budjeti</h3>
          <div className="progress mb"><i style={{ width: `${budgetPct}%` }} /></div>
          <p className="text-soft" style={{ fontSize: 13.5 }}>
            Sarf: <b className="num">{data.budget.total_tokens.toLocaleString("uz-UZ")}</b> /{" "}
            <b className="num">{data.budget.budget.toLocaleString("uz-UZ")}</b> token ({budgetPct}%)
            {data.budget.total_tokens > data.budget.budget && " — limit oshgan!"}
          </p>
          <p className="text-faint mt" style={{ fontSize: 12.5 }}>
            So'rovlar: {data.budget.requests} · Qolgan: {Math.max(0, data.budget.remaining).toLocaleString("uz-UZ")}
          </p>
        </div>

        <div className="card card-pad">
          <h3 className="mb">Provayderlar holati</h3>
          <div className="timeline">
            {data.providers.map((provider) => (
              <div className="tl-item" key={provider.name}>
                <span className="tl-dot" style={{ borderColor: provider.ok ? "var(--color-success)" : "var(--color-danger)" }} />
                <div className="tl-body">
                  <h4>{provider.name}</h4>
                  <div className="desc" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <Badge tone={provider.ok ? "ok" : "danger"}>{provider.ok ? "Ulangan" : "Xatolik"}</Badge>
                    <span className="mono" style={{ fontSize: 12 }}>{provider.detail}</span>
                  </div>
                </div>
              </div>
            ))}
            {data.providers.length === 0 && <Empty title="Provayder sozlanmagan" />}
          </div>
        </div>
      </div>

      <div className="card mb">
        <div className="card-head">
          <h3>Model zanjiri (fallback tartibi)</h3>
          {data.active_model && <Badge tone="brand">Faol: {data.active_model}</Badge>}
        </div>
        <div className="card-pad">
          <div className="hbar">
            {data.models.map((model, index) => {
              const active = model.id === data.active_model;
              return (
                <div className="row" key={model.id} style={{ gridTemplateColumns: "28px minmax(140px,1fr) 90px 90px" }}>
                  <span className="badge muted num">{index + 1}</span>
                  <span style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
                    <b style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{model.label || model.id}</b>
                    {active && <Badge tone="brand">faol</Badge>}
                  </span>
                  <span className="text-faint nowrap">{model.provider}</span>
                  <span className="text-faint num nowrap" style={{ textAlign: "right" }}>{model.context ? `${Math.round(model.context / 1000)}K` : "—"}</span>
                </div>
              );
            })}
          </div>
          <p className="text-faint mt" style={{ fontSize: 12.5 }}>
            Faol modelni Sozlamalar → AI sozlamalaridan tanlash mumkin. Tanlangan modeldan so'ng zanjir avtomatik davom etadi.
          </p>
        </div>
      </div>

      <div className="grid grid-2">
        {data.agents.map((agent) => {
          const st = STATUS_MAP[agent.last_status] ?? { label: agent.last_status, tone: "muted" };
          return (
            <div className="card card-pad" key={agent.name}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                <h3>{agent.label}</h3>
                <Badge tone={st.tone}>{st.label}</Badge>
              </div>
              <p className="text-soft mt" style={{ minHeight: 40, fontSize: 13.5 }}>{agent.description}</p>
              <dl className="kv mt">
                <dt>Oxirgi ishlash</dt>
                <dd>{agent.last_run_at ? fmtDateTime(agent.last_run_at) : "—"}{agent.latency_ms ? ` · ${agent.latency_ms} ms` : ""}</dd>
                <dt>Muvaffaqiyat</dt><dd className="num">{agent.success_rate}% <span className="text-faint">(oxirgi 50)</span></dd>
                <dt>Bugungi token</dt><dd className="num">{agent.tokens_today.toLocaleString("uz-UZ")}</dd>
                <dt>Model</dt><dd className="mono" style={{ fontSize: 12 }}>{agent.model || "—"}</dd>
              </dl>
            </div>
          );
        })}
      </div>
    </>
  );
}
