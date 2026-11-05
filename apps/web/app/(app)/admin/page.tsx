"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Download, Database, Play, Search } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Stat } from "@/components/ui";
import { ConfirmDialog, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { api, type Paged } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type ProviderStatus = { name: string; ok: boolean; detail: string; models?: Array<{ id: string; label: string }> };
type Settings = {
  theme: string; language: string; timezone: string; ai_provider: string; ai_model: string;
  ai_budget: number; scheduler_time: string; mahalla: string; district: string; region: string;
  demo_mode: boolean;
  usage: { total_tokens: number; budget: number; remaining: number; requests: number };
  providers: ProviderStatus[];
};
type AuditRow = { id: string; action: string; entity_type: string; entity_id?: string | null; actor_id?: string | null; created_at: string };
type Usage = {
  today: { total_tokens: number; budget: number; remaining: number; requests: number };
  days: { date: string; total: number; requests: number }[];
  models: { model: string; provider: string; tokens: number; requests: number }[];
};
type Job = { id: string; name: string; job_type: string; schedule: string; status: string; next_run_at: string | null; last_run_at: string | null; error: string };

const TABS = [
  { key: "settings", label: "Sozlamalar" },
  { key: "audit", label: "Audit jurnali" },
  { key: "usage", label: "AI sarflari" },
  { key: "jobs", label: "Joblar" },
] as const;

function auditTone(action: string): string {
  if (action.includes("created") || action.includes("completed") || action.includes("approved") || action.includes("login")) return "ok";
  if (action.includes("archived") || action.includes("cancelled") || action.includes("deleted") || action.includes("failed")) return "danger";
  if (action.includes("updated") || action.includes("synced")) return "info";
  return "muted";
}

export default function AdminPage() {
  const toast = useToast();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("settings");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [audit, setAudit] = useState<Paged<AuditRow> | null>(null);
  const [auditQ, setAuditQ] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditPage, setAuditPage] = useState(1);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [backupOpen, setBackupOpen] = useState(false);
  const [backing, setBacking] = useState(false);

  const load = useCallback(() => {
    setError("");
    if (tab === "settings") api.get<Settings>("/admin/settings").then(setSettings).catch((err) => setError(err.message));
    if (tab === "audit") {
      const params = new URLSearchParams({ page: String(auditPage), page_size: "25" });
      if (auditQ) params.set("q", auditQ);
      if (auditAction) params.set("action", auditAction);
      api.get<Paged<AuditRow>>(`/admin/audit?${params}`).then(setAudit).catch((err) => setError(err.message));
    }
    if (tab === "usage") api.get<Usage>("/admin/usage?days=14").then(setUsage).catch((err) => setError(err.message));
    if (tab === "jobs") api.get<{ items: Job[] }>("/admin/jobs").then((d) => setJobs(d.items)).catch((err) => setError(err.message));
  }, [tab, auditPage, auditQ, auditAction]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
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
          ai_model: settings.ai_model,
          ai_budget: settings.ai_budget,
          scheduler_time: settings.scheduler_time,
          mahalla: settings.mahalla,
          district: settings.district,
          region: settings.region,
          language: settings.language,
          timezone: settings.timezone,
        },
      });
      setSettings(updated);
      toast.show("success", "Sozlamalar saqlandi.");
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
    setBacking(true);
    try {
      const result = await api.post<{ backup_id: string; sha256: string }>("/admin/backups");
      toast.show("success", `Zaxira nusxa yaratildi (${result.sha256.slice(0, 12)}…).`);
      setBackupOpen(false);
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Zaxira yaratilmadi.");
    } finally {
      setBacking(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Tizim"
        title="Sozlamalar, audit va nazorat"
        lede="Yagona administrator uchun boshqaruv: AI provayder va model, budjet, joblar, audit jurnali va zaxira nusxalar."
        actions={
          <button className="btn" disabled={busy} onClick={() => setBackupOpen(true)}>
            <Database size={15} /> Zaxira nusxa
          </button>
        }
      />
      {error && <ErrorState note={error} />}
      {note && <div className="alert success" role="alert">{note}</div>}
      <div className="tabbar" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "settings" &&
        (settings ? (
          <div className="split s2">
            <div className="card card-pad">
              <h3 className="mb">Mahalla va hudud</h3>
              <div className="grid grid-2">
                <Field label="Mahalla" htmlFor="s-mahalla"><input id="s-mahalla" className="input" value={settings.mahalla} onChange={(e) => setSettings({ ...settings, mahalla: e.target.value })} /></Field>
                <Field label="Tuman" htmlFor="s-district"><input id="s-district" className="input" value={settings.district} onChange={(e) => setSettings({ ...settings, district: e.target.value })} /></Field>
                <Field label="Viloyat" htmlFor="s-region"><input id="s-region" className="input" value={settings.region} onChange={(e) => setSettings({ ...settings, region: e.target.value })} /></Field>
                <Field label="Rejim" htmlFor="s-demo">
                  <p style={{ paddingTop: 8 }}><Badge tone={settings.demo_mode ? "warn" : "ok"}>{settings.demo_mode ? "Demo rejim" : "Ishlab chiqarish"}</Badge></p>
                </Field>
              </div>
              <h3 className="mt mb">Lokal</h3>
              <div className="grid grid-2">
                <Field label="Til" htmlFor="s-lang">
                  <select id="s-lang" className="select" value={settings.language} onChange={(e) => setSettings({ ...settings, language: e.target.value })}>
                    <option value="uz-Latn">O'zbek (lotin)</option>
                    <option value="uz-Cyrl">O'zbek (kirill)</option>
                    <option value="ru">Русский</option>
                  </select>
                </Field>
                <Field label="Vaqt zonasi" htmlFor="s-tz">
                  <select id="s-tz" className="select" value={settings.timezone} onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}>
                    <option value="Asia/Tashkent">Asia/Tashkent</option>
                    <option value="UTC">UTC</option>
                  </select>
                </Field>
              </div>
              <h3 className="mt mb">Rejalashtiruvchi</h3>
              <Field label="Kunlik hisobot vaqti" htmlFor="s-sched" hint="Asia/Tashkent bo'yicha, masalan 21:00">
                <input id="s-sched" className="input" value={settings.scheduler_time} onChange={(e) => setSettings({ ...settings, scheduler_time: e.target.value })} />
              </Field>
              <button className="btn primary" disabled={busy} onClick={() => void save()}>Saqlash</button>
            </div>
            <div>
              <div className="card card-pad mb">
                <h3 className="mb">AI konfiguratsiya</h3>
                <Field label="Asosiy provayder" htmlFor="s-provider">
                  <select id="s-provider" className="select" value={settings.ai_provider} onChange={(e) => setSettings({ ...settings, ai_provider: e.target.value })}>
                    <option value="nvidia">NVIDIA NIM</option>
                    <option value="openrouter">OpenRouter</option>
                  </select>
                </Field>
                <Field label="Model" hint="Tanlangan model zanjir boshida; xatolik bo'lsa avtomatik davom etadi" htmlFor="s-model">
                  <select id="s-model" className="select" value={settings.ai_model} onChange={(e) => setSettings({ ...settings, ai_model: e.target.value })}>
                    <option value="">Avto (registratsiya tartibida)</option>
                    {(settings.providers ?? []).flatMap((provider) =>
                      (provider.models ?? []).map((model: { id: string; label: string }) => (
                        <option key={model.id} value={model.id}>{model.label || model.id}</option>
                      ))
                    )}
                  </select>
                </Field>
                <Field label="Kunlik AI token budjeti" htmlFor="s-budget">
                  <input id="s-budget" className="input" type="number" value={settings.ai_budget} onChange={(e) => setSettings({ ...settings, ai_budget: Number(e.target.value) })} />
                </Field>
                <button className="btn primary" disabled={busy} onClick={() => void save()}>Saqlash</button>
              </div>
              <div className="card card-pad">
                <h3 className="mb">Provayderlar holati</h3>
                <div className="timeline">
                  {settings.providers.map((provider) => (
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
                </div>
                <div className="progress mt">
                  <i style={{ width: `${Math.min(100, (settings.usage.total_tokens / Math.max(1, settings.usage.budget)) * 100)}%` }} />
                </div>
                <p className="text-soft mt" style={{ fontSize: 13 }}>
                  Bugungi sarf: <b className="num">{settings.usage.total_tokens.toLocaleString("uz-UZ")}</b> / {settings.usage.budget.toLocaleString("uz-UZ")} token · {settings.usage.requests} so'rov
                </p>
              </div>
            </div>
          </div>
        ) : (
          <SkeletonList rows={4} />
        ))}

      {tab === "audit" &&
        (audit ? (
          <>
            <div className="toolbar">
              <div style={{ position: "relative", minWidth: 240 }}>
                <Search size={15} style={{ position: "absolute", left: 12, top: 13, color: "var(--color-text-muted)" }} />
                <input className="input" style={{ paddingLeft: 36 }} placeholder="Audit bo'yicha qidiruv (amal, ID)…" value={auditQ} onChange={(e) => { setAuditQ(e.target.value); setAuditPage(1); }} aria-label="Audit qidiruv" />
              </div>
              <select className="select" value={auditAction} onChange={(e) => { setAuditAction(e.target.value); setAuditPage(1); }} aria-label="Amal filtri">
                <option value="">Amal — barchasi</option>
                {["agent.chat", "auth.login", "citizen", "case", "task", "document", "report", "legislation", "settings", "job", "draft"].map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </div>
            <div className="card">
              <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
                <table className="data">
                  <thead><tr><th>Vaqt</th><th>Amal</th><th>Ob'ekt</th><th>ID</th><th>Aktor</th></tr></thead>
                  <tbody>
                    {audit.items.map((row) => (
                      <tr key={row.id}>
                        <td className="nowrap">{fmtDateTime(row.created_at)}</td>
                        <td><Badge tone={auditTone(row.action)}><span className="mono" style={{ fontSize: 11.5 }}>{row.action}</span></Badge></td>
                        <td>{row.entity_type}</td>
                        <td className="mono">{row.entity_id?.slice(0, 20) ?? "—"}</td>
                        <td className="mono">{row.actor_id?.slice(0, 12) ?? "system"}</td>
                      </tr>
                    ))}
                    {audit.items.length === 0 && <tr><td colSpan={5}><Empty title="Audit yozuvi topilmadi" /></td></tr>}
                  </tbody>
                </table>
              </div>
              {audit.meta.total_pages > 1 && (
                <div className="pager">
                  <span className="num">{audit.meta.total} yozuv · {audit.meta.page}/{audit.meta.total_pages}</span>
                  <span style={{ display: "flex", gap: 8 }}>
                    <button className="btn sm" disabled={auditPage <= 1} onClick={() => setAuditPage(auditPage - 1)}>‹ Oldingi</button>
                    <button className="btn sm" disabled={auditPage >= audit.meta.total_pages} onClick={() => setAuditPage(auditPage + 1)}>Keyingi ›</button>
                  </span>
                </div>
              )}
            </div>
          </>
        ) : (
          <SkeletonList rows={5} />
        ))}

      {tab === "usage" &&
        (usage ? (
          <div className="split s2">
            <div className="card card-pad">
              <h3 className="mb">Bugungi sarf</h3>
              <div className="progress mb"><i style={{ width: `${Math.min(100, (usage.today.total_tokens / Math.max(1, usage.today.budget)) * 100)}%` }} /></div>
              <dl className="kv">
                <dt>Tokenlar</dt><dd className="num">{usage.today.total_tokens.toLocaleString("uz-UZ")} / {usage.today.budget.toLocaleString("uz-UZ")}</dd>
                <dt>Qolgan</dt><dd className="num">{usage.today.remaining.toLocaleString("uz-UZ")}</dd>
                <dt>So'rovlar</dt><dd className="num">{usage.today.requests}</dd>
              </dl>
            </div>
            <div className="card">
              <div className="card-head"><h3>14 kunlik trend</h3></div>
              <div className="card-pad">
                {usage.days.length === 0 ? (
                  <Empty title="Ma'lumot yo'q" note="Bu davrda AI so'rovlari bo'lmagan." />
                ) : (
                  <div className="hbar">
                    {usage.days.map((day) => {
                      const max = Math.max(...usage.days.map((d) => d.total), 1);
                      return (
                        <div className="row" key={day.date}>
                          <span className="mono" style={{ fontSize: 11.5 }}>{day.date.slice(5)}</span>
                          <span className="track"><i style={{ width: `${Math.round((day.total / max) * 100)}%` }} /></span>
                          <b className="num">{day.total.toLocaleString("uz-UZ")}</b>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <div className="card-head"><h3>Modellar bo'yicha (14 kun)</h3></div>
              <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
                <table className="data">
                  <thead><tr><th>Model</th><th>Provayder</th><th className="num">Token</th><th className="num">So'rov</th></tr></thead>
                  <tbody>
                    {usage.models.map((model) => (
                      <tr key={model.model}>
                        <td className="mono">{model.model}</td>
                        <td>{model.provider}</td>
                        <td className="num">{model.tokens.toLocaleString("uz-UZ")}</td>
                        <td className="num">{model.requests}</td>
                      </tr>
                    ))}
                    {usage.models.length === 0 && <tr><td colSpan={4}><Empty title="AI so'rovlari yo'q" /></td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : (
          <SkeletonList rows={4} />
        ))}

      {tab === "jobs" &&
        (jobs ? (
          <div className="card">
            <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
              <table className="data">
                <thead><tr><th>Job</th><th>Tur</th><th>Jadval</th><th>Holat</th><th>Keyingi bajarilish</th><th aria-label="Amallar" /></tr></thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        <b style={{ fontWeight: 600 }}>{job.name}</b>
                        {job.error && (
                          <div style={{ marginTop: 4 }}>
                            <button className="chip" onClick={() => setJobError(jobError === job.id ? null : job.id)} aria-expanded={jobError === job.id}>
                              <AlertTriangle size={12} /> Xatoni ko'rish
                            </button>
                            {jobError === job.id && (
                              <pre className="mono" style={{ marginTop: 6, background: "var(--danger-soft)", color: "var(--color-danger)", padding: 8, borderRadius: 8, whiteSpace: "pre-wrap", fontSize: 11.5, maxWidth: 420 }}>
                                {job.error}
                              </pre>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="mono">{job.job_type}</td>
                      <td>{job.schedule}</td>
                      <td><Badge tone={job.status === "active" ? "ok" : "danger"}>{job.status}</Badge></td>
                      <td className="nowrap">{fmtDateTime(job.next_run_at)}</td>
                      <td>
                        <button className="btn sm" disabled={busy} onClick={() => void runJob(job)}>
                          <Play size={13} /> Hozir bajarish
                        </button>
                      </td>
                    </tr>
                  ))}
                  {jobs.length === 0 && <tr><td colSpan={6}><Empty title="Job yo'q" /></td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <SkeletonList rows={3} />
        ))}

      <ConfirmDialog
        open={backupOpen}
        onClose={() => setBackupOpen(false)}
        onConfirm={() => void backup()}
        title="Zaxira nusxa yaratish"
        message="Fuqarolar, oilalar, murojaatlar, vazifalar va hisobotlarning JSON zaxirasi yaratiladi. Davom etamizmi?"
        confirmLabel="Zaxira yaratish"
        danger={false}
        busy={backing}
      />
    </>
  );
}
