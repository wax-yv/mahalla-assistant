"use client";

import { useEffect, useState } from "react";
import { Badge, ErrorNote, Loading, PageHead, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type AgentInfo = {
  name: string;
  label: string;
  description: string;
  enabled: boolean;
  provider: string;
  model: string;
  last_run_at: string | null;
  last_status: string;
  latency_ms: number;
  tokens_today: number;
  success_rate: number;
};
type ModelInfo = { id: string; provider: string; label: string; context: number; rank: number };
type ProviderStatus = { name: string; ok: boolean; detail: string };
type StatusData = {
  agents: AgentInfo[];
  models: ModelInfo[];
  budget: { total_tokens: number; budget: number; remaining: number; requests: number };
  providers: ProviderStatus[];
};

const TONES: Record<string, string> = {
  completed: "ok",
  running: "info",
  idle: "muted",
  failed: "danger",
};

export default function AgentsPage() {
  const [data, setData] = useState<StatusData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<StatusData>("/agents/status")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  if (error) return <ErrorNote message={error} />;
  if (!data) return <Loading />;

  const orchestrator = data.agents.find((a) => a.name === "orchestrator");

  return (
    <>
      <PageHead
        kicker="AI tizimi"
        title="Agentlar monitoringi"
        lede="Orkestrator so'rovni tahlil qiladi va kerakli agentlarga yo'naltiradi. Har bir agent o'z sohasiga ixtisoslashgan, yozuv amallar faqat tasdiq bilan bajariladi."
      />
      <div className="grid grid-4 mb">
        <Stat label="Bugungi token" value={data.budget.total_tokens.toLocaleString("uz-UZ")} hint={`limit ${data.budget.budget.toLocaleString("uz-UZ")}`} />
        <Stat label="So'rovlar" value={data.budget.requests} hint="bugun" />
        <Stat label="Provayderlar" value={data.providers.filter((p) => p.ok).length} hint="ulangan" />
        <Stat label="Modellar" value={data.models.length} hint="fallback zanjiri" />
      </div>

      <div className="card card-pad mb">
        <h3 className="mb">Zanjir (eng kuchlidan)</h3>
        <div className="chips">
          {data.models.map((model, index) => (
            <span key={model.id} className="chip" title={`context: ${model.context}`}>
              {index + 1}. {model.label || model.id} <b className="text-faint">· {model.provider}</b>
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-2">
        {data.agents.map((agent) => (
          <div className="card card-pad" key={agent.name}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
              <h3>{agent.label}</h3>
              <Badge tone={TONES[agent.last_status] ?? "muted"}>{agent.last_status === "completed" ? "ishladi" : agent.last_status}</Badge>
            </div>
            <p className="text-soft mt" style={{ minHeight: 40 }}>{agent.description}</p>
            <dl className="kv mt">
              <dt>Oxirgi ishlash</dt>
              <dd>{agent.last_run_at ? fmtDateTime(agent.last_run_at) : "—"}{agent.latency_ms ? ` · ${agent.latency_ms} ms` : ""}</dd>
              <dt>Muvaffaqiyat</dt>
              <dd>{agent.success_rate}% (oxirgi 50)</dd>
              <dt>Bugungi token</dt>
              <dd>{agent.tokens_today.toLocaleString("uz-UZ")}</dd>
              <dt>Model</dt>
              <dd className="mono">{agent.model || "—"}</dd>
            </dl>
          </div>
        ))}
      </div>

      {orchestrator && (
        <p className="text-faint mt" style={{ fontSize: 12.5 }}>
          Orkestrator bir so'rovda 3 tagacha agentni ketma-ket ishga tushirishi mumkin; har bir qadam AgentRun
          jurnalida saqlanadi (Sozlamalar → Audit).
        </p>
      )}
    </>
  );
}
