"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type Settings = {
  theme: string;
  language: string;
  timezone: string;
  ai_provider: string;
  ai_budget: number;
  scheduler_time: string;
  mahalla: string;
  district: string;
  region: string;
  demo_mode: boolean;
  usage: { total_tokens: number; limit: number; remaining: number; requests: number };
  providers: { name: string; ok: boolean; detail: string }[];
};
type AuditRow = {
  id: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  actor_id?: string | null;
  created_at: string;
  description?: string;
};
type Usage = {
  today: { total_tokens: number; limit: number; remaining: number; requests: number };
  days: { date: string; total: number; requests: number }[];
  models: { model: string; provider: string; tokens: number; requests: number }[];
};
type Job = {
  id: string;
  name: string;
  job_type: string;
  schedule: string;
  status: string;
  next_run_at: string | null;
  last_run_at: string | null;
  error: string;
};

export default function AdminPage() {
  const [tab, setTab] = useState<"settings" | "audit" | "usage" | "jobs">("settings");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [audit, setAudit] = useState<Paged<AuditRow> | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    if (tab === "settings") api.get<Settings>("/admin/settings").then(setSettings).catch((err) => setError(err.message));
    if (tab === "audit") {
      api
        .get<Paged<AuditRow>>(`/admin/audit?page=${page}&page_size=25`)
        .then(setAudit)
        .catch((err) => setError(err.message));
    }
    if (tab === "usage") api.get<Usage>("/admin/usage?days=14").then(setUsage).catch((err) => setError(err.message));
    if (tab === "jobs") api.get<{ items: Job[] }>("/admin/jobs").then((data) => setJobs(data.items)).catch((err) => setError(err.message));
  }, [tab, page]);

  useEffect(() => {
    const timer = setTimeout(load, 150);
    return () => clearTimeout(timer);
  }, [load]);

  async function save() {
    if (!settings) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const updated = await api.patch<Settings>("/admin/settings", {
        values: {
          ai_provider: settings.ai_provider,
          ai_budget: settings.ai_budget,
          scheduler_time: settings.scheduler_time,
          mahalla: settings.mahalla,
          district: settings.district,
          region: settings.region,
        },
      });
      setSettings(updated);
      setNote("Sozlamalar saqlandi.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Saqlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  async function runJob(job: Job) {
    setBusy(true);
    setError("");
    try {
      const result = await api.post<{ status: string }>(`/admin/jobs/${job.id}/run`);
      setNote(`Job «${job.name}» ${result.status === "completed" ? "bajarildi" : "xatolik bilan tugadi"}.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job bajarilmadi.");
    } finally {
      setBusy(false);
    }
  }

  async function backup() {
    setBusy(true);
    try {
      const result = await api.post<{ backup_id: string; sha256: string }>("/admin/backups");
      setNote(`Zaxira nusxa yaratildi (${result.sha256.slice(0, 12)}…).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Zaxira yaratilmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Tizim"
        title="Sozlamalar, audit va nazorat"
        lede="Yagona administrator (wax) uchun boshqaruv: AI provayderlar, budjet, rejalashtirilgan joblar, audit jurnali va zaxira nusxalar."
        actions={
          <button className="btn" disabled={busy} onClick={backup}>
            Zaxira nusxa
          </button>
        }
      />
      {error && <ErrorNote message={error} />}
      {note && <div className="alert info">ℹ️ {note}</div>}
      <div className="tabbar">
        {(
          [
            ["settings", "Sozlamalar"],
            ["audit", "Audit jurnali"],
            ["usage", "AI sarflari"],
            ["jobs", "Joblar"],
          ] as const
        ).map(([key, label]) => (
          <a
            key={key}
            href="#"
            className={tab === key ? "active" : ""}
            onClick={(event) => {
              event.preventDefault();
              setTab(key);
              setPage(1);
            }}
          >
            {label}
          </a>
        ))}
      </div>

      {tab === "settings" &&
        (settings ? (
          <div className="split s2">
            <div className="card card-pad">
              <h3 className="mb">Asosiy sozlamalar</h3>
              <div className="field">
                <label>AI provayder (asosiy)</label>
                <select
                  className="select"
                  value={settings.ai_provider}
                  onChange={(e) => setSettings({ ...settings, ai_provider: e.target.value })}
                >
                  <option value="nvidia">NVIDIA NIM</option>
                  <option value="openrouter">OpenRouter</option>
                </select>
              </div>
              <div className="field">
                <label>Kunlik AI token budjeti</label>
                <input
                  className="input"
                  type="number"
                  value={settings.ai_budget}
                  onChange={(e) => setSettings({ ...settings, ai_budget: Number(e.target.value) })}
                />
              </div>
              <div className="field">
                <label>Kunlik hisobot vaqti</label>
                <input
                  className="input"
                  value={settings.scheduler_time}
                  onChange={(e) => setSettings({ ...settings, scheduler_time: e.target.value })}
                />
              </div>
              <div className="grid grid-2">
                <div className="field">
                  <label>Mahalla</label>
                  <input className="input" value={settings.mahalla} onChange={(e) => setSettings({ ...settings, mahalla: e.target.value })} />
                </div>
                <div className="field">
                  <label>Tuman</label>
                  <input className="input" value={settings.district} onChange={(e) => setSettings({ ...settings, district: e.target.value })} />
                </div>
                <div className="field">
                  <label>Viloyat</label>
                  <input className="input" value={settings.region} onChange={(e) => setSettings({ ...settings, region: e.target.value })} />
                </div>
                <div className="field">
                  <label>Rejim</label>
                  <p>
                    <Badge tone={settings.demo_mode ? "warn" : "ok"}>
                      {settings.demo_mode ? "Demo rejim" : "Ishlab chiqarish"}
                    </Badge>
                  </p>
                </div>
              </div>
              <button className="btn primary" disabled={busy} onClick={save}>
                Saqlash
              </button>
            </div>
            <div className="card card-pad">
              <h3 className="mb">AI provayderlar holati</h3>
              <div className="timeline">
                {settings.providers.map((provider) => (
                  <div className="tl-item" key={provider.name}>
                    <span className="tl-dot" />
                    <div className="tl-body">
                      <h4>{provider.name}</h4>
                      <div className="desc">
                        <Badge tone={provider.ok ? "ok" : "danger"}>{provider.ok ? "Ulangan" : "Xatolik"}</Badge>{" "}
                        <span className="mono">{provider.detail}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="progress mt">
                <i style={{ width: `${Math.min(100, (settings.usage.total_tokens / Math.max(1, settings.usage.limit)) * 100)}%` }} />
              </div>
              <p className="text-soft mt">
                Bugungi sarf: {settings.usage.total_tokens.toLocaleString()} / {settings.usage.limit.toLocaleString()} token ·{" "}
                {settings.usage.requests} so‘rov
              </p>
            </div>
          </div>
        ) : (
          <Loading />
        ))}

      {tab === "audit" &&
        (audit ? (
          <div className="card">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Vaqt</th>
                    <th>Amal</th>
                    <th>Ob'ekt</th>
                    <th>ID</th>
                    <th>Aktor</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.items.map((row) => (
                    <tr key={row.id}>
                      <td className="nowrap">{fmtDateTime(row.created_at)}</td>
                      <td className="mono">{row.action}</td>
                      <td>{row.entity_type}</td>
                      <td className="mono">{row.entity_id?.slice(0, 20) ?? "—"}</td>
                      <td className="mono">{row.actor_id?.slice(0, 12) ?? "system"}</td>
                    </tr>
                  ))}
                  {audit.items.length === 0 && (
                    <tr>
                      <td colSpan={5}>
                        <Empty title="Audit yozuvi yo‘q" icon="≡" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <Pager meta={audit.meta} onPage={setPage} />
          </div>
        ) : (
          <Loading />
        ))}

      {tab === "usage" &&
        (usage ? (
          <div className="split s2">
            <div className="card card-pad">
              <h3 className="mb">Bugungi sarf</h3>
              <div className="progress mb">
                <i style={{ width: `${Math.min(100, (usage.today.total_tokens / Math.max(1, usage.today.limit)) * 100)}%` }} />
              </div>
              <dl className="kv">
                <dt>Tokenlar</dt>
                <dd>{usage.today.total_tokens.toLocaleString()} / {usage.today.limit.toLocaleString()}</dd>
                <dt>Qolgan</dt>
                <dd>{usage.today.remaining.toLocaleString()}</dd>
                <dt>So‘rovlar</dt>
                <dd>{usage.today.requests}</dd>
              </dl>
            </div>
            <div className="card">
              <div className="card-head">
                <h3>Modellar bo‘yicha (14 kun)</h3>
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Provayder</th>
                      <th>Token</th>
                      <th>So‘rov</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.models.map((model) => (
                      <tr key={model.model}>
                        <td className="mono">{model.model}</td>
                        <td>{model.provider}</td>
                        <td>{model.tokens.toLocaleString()}</td>
                        <td>{model.requests}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : (
          <Loading />
        ))}

      {tab === "jobs" &&
        (jobs ? (
          <div className="card">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Tur</th>
                    <th>Jadval</th>
                    <th>Holat</th>
                    <th>Keyingi bajarilish</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        <b>{job.name}</b>
                        {job.error && <div className="text-faint">{job.error.slice(0, 80)}</div>}
                      </td>
                      <td className="mono">{job.job_type}</td>
                      <td>{job.schedule}</td>
                      <td>
                        <Badge tone={job.status === "active" ? "ok" : "danger"}>{job.status}</Badge>
                      </td>
                      <td className="nowrap">{fmtDateTime(job.next_run_at)}</td>
                      <td>
                        <button className="btn sm" disabled={busy} onClick={() => void runJob(job)}>
                          Hozir bajarish
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <Loading />
        ))}
    </>
  );
}
