"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Database, Play, Search } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Pager } from "@/components/ui";
import { ConfirmDialog, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { Tabs, TabPanel } from "@/components/ui/Tabs";
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
type BackupRow = { id: string; kind: string; status: string; started_at: string; size_bytes: number; location: string; error: string };

function jobStatusTone(status: string): { tone: "ok" | "danger" | "info" | "muted"; label: string } {
  if (status === "active") return { tone: "ok", label: "Faol" };
  if (status === "running") return { tone: "info", label: "Bajarilmoqda" };
  if (status === "failed") return { tone: "danger", label: "Xato" };
  return { tone: "muted", label: status };
}

const TABS = [
  { key: "settings", label: "Sozlamalar" },
  { key: "audit", label: "Audit jurnali" },
  { key: "usage", label: "AI sarflari" },
  { key: "jobs", label: "Joblar" },
  { key: "backup", label: "Zaxira nusxalar" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const AUDIT_ACTIONS = ["agent.chat", "auth.login", "citizen", "case", "task", "document", "report", "legislation", "settings", "job", "draft"];

function auditTone(action: string): string {
  if (action.includes("created") || action.includes("completed") || action.includes("approved") || action.includes("login")) return "ok";
  if (action.includes("archived") || action.includes("cancelled") || action.includes("deleted") || action.includes("failed")) return "danger";
  if (action.includes("updated") || action.includes("synced")) return "info";
  return "muted";
}

export default function AdminPage() {
  const toast = useToast();
  const [tab, setTab] = useState<TabKey>("settings");
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
  const [backups, setBackups] = useState<BackupRow[] | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<BackupRow | null>(null);
  const [restoreMode, setRestoreMode] = useState<"merge" | "replace">("merge");
  const [restoring, setRestoring] = useState(false);

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
    if (tab === "backup") api.get<{ items: BackupRow[] }>("/admin/backups").then((d) => setBackups(d.items)).catch((err) => setError(err.message));
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
      load();
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Zaxira yaratilmadi.");
    } finally {
      setBacking(false);
    }
  }

  async function restoreBackup() {
    if (!restoreTarget) return;
    setRestoring(true);
    try {
      const result = await api.post<{ results: Record<string, { inserted: number }> }>(
        `/admin/backups/${restoreTarget.id}/restore`,
        { mode: restoreMode },
      );
      const inserted = Object.values(result.results).reduce((sum, r) => sum + r.inserted, 0);
      toast.show("success", `Zaxira tiklandi (${inserted} ta yozuv qo'shildi).`);
      setRestoreTarget(null);
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Zaxira tiklanmadi.");
    } finally {
      setRestoring(false);
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
      {note && <div className="alert success" role="alert"><Check size={16} /><span>{note}</span></div>}

      <Tabs tabs={TABS} value={tab} onChange={setTab} ariaLabel="Administrator bo‘limlari">
                <TabPanel tabKey="settings">
          {settings ? (
            <div className="split s2">
              <div className="card card-pad">
                <h3 className="mb">Mahalla va hudud</h3>
                <div className="grid grid-2">
                  <Field label="Mahalla" htmlFor="s-mahalla"><input id="s-mahalla" className="input" value={settings.mahalla} onChange={(e) => setSettings({ ...settings, mahalla: e.target.value })} /></Field>
                  <Field label="Tuman" htmlFor="s-district"><input id="s-district" className="input" value={settings.district} onChange={(e) => setSettings({ ...settings, district: e.target.value })} /></Field>
                  <Field label="Viloyat" htmlFor="s-region"><input id="s-region" className="input" value={settings.region} onChange={(e) => setSettings({ ...settings, region: e.target.value })} /></Field>
                  <Field label="Rejim" htmlFor="s-demo">
                    <p className="mt-sm"><Badge tone={settings.demo_mode ? "warn" : "ok"}>{settings.demo_mode ? "Demo rejim" : "Ishlab chiqarish"}</Badge></p>
                  </Field>
                </div>
                <h3 className="mt mb">Lokal</h3>
                <div className="grid grid-2">
                  <Field label="Til" htmlFor="s-lang">
                    <select id="s-lang" className="select" value={settings.language} onChange={(e) => setSettings({ ...settings, language: e.target.value })}>
                      <option value="uz-Latn">O‘zbek (lotin)</option>
                      <option value="uz-Cyrl">O‘zbek (kirill)</option>
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
                <Field label="Kunlik hisobot vaqti" htmlFor="s-sched" hint="Asia/Tashkent bo‘yicha, masalan 21:00">
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
                  <Field label="Model" hint="Tanlangan model zanjir boshida; xatolik bo‘lsa avtomatik davom etadi" htmlFor="s-model">
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
                        <span className={`tl-dot ${provider.ok ? "tone-ok" : "tone-danger"}`} aria-hidden="true" />
                        <div className="tl-body">
                          <h4>{provider.name}</h4>
                          <div className="desc row-wrap">
                            <Badge tone={provider.ok ? "ok" : "danger"}>{provider.ok ? "Ulangan" : "Xatolik"}</Badge>
                            <span className="mono fs-12">{provider.detail}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="progress mt">
                    <i style={{ width: `${Math.min(100, (settings.usage.total_tokens / Math.max(1, settings.usage.budget)) * 100)}%` }} />
                  </div>
                  <p className="text-soft mt fs-13">
                    Bugungi sarf: <b className="num">{settings.usage.total_tokens.toLocaleString("uz-UZ")}</b> / {settings.usage.budget.toLocaleString("uz-UZ")} token · {settings.usage.requests} so‘rov
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <SkeletonList rows={4} />
          )}
        </TabPanel>

              <TabPanel tabKey="audit">
          {audit ? (
            <>
              <div className="toolbar">
                <div className="search-field">
                  <Search className="search-ico" size={15} />
                  <input className="input" placeholder="Audit bo‘yicha qidiruv (amal, ID)…" value={auditQ} onChange={(e) => { setAuditQ(e.target.value); setAuditPage(1); }} aria-label="Audit qidiruv" />
                </div>
                <select className="select" value={auditAction} onChange={(e) => { setAuditAction(e.target.value); setAuditPage(1); }} aria-label="Amal filtri">
                  <option value="">Amal — barchasi</option>
                  {AUDIT_ACTIONS.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div className="card">
                <div className="table-wrap flush">
                  <table className="data">
                    <thead><tr><th>Vaqt</th><th>Amal</th><th>Ob’ekt</th><th>ID</th><th>Aktor</th></tr></thead>
                    <tbody>
                      {audit.items.map((row) => (
                        <tr key={row.id}>
                          <td className="nowrap" data-label="Vaqt">{fmtDateTime(row.created_at)}</td>
                          <td data-label="Amal"><Badge tone={auditTone(row.action)}><span className="mono fs-11_5">{row.action}</span></Badge></td>
                          <td data-label="Ob’ekt">{row.entity_type}</td>
                          <td className="mono" data-label="ID">{row.entity_id?.slice(0, 20) ?? "—"}</td>
                          <td className="mono" data-label="Aktor">{row.actor_id?.slice(0, 12) ?? "tizim"}</td>
                        </tr>
                      ))}
                      {audit.items.length === 0 && <tr><td colSpan={5}><Empty title="Audit yozuvi topilmadi" note="Qidiruv shartini o‘zgartirib, qayta urinib ko‘ring." /></td></tr>}
                    </tbody>
                  </table>
                </div>
                <Pager meta={audit.meta} onPage={setAuditPage} />
              </div>
            </>
          ) : (
            <SkeletonList rows={5} />
          )}
        </TabPanel>

              <TabPanel tabKey="usage">
          {usage ? (
            <div className="split s2">
              <div className="card card-pad">
                <h3 className="mb">Bugungi sarf</h3>
                <div className="progress mb"><i style={{ width: `${Math.min(100, (usage.today.total_tokens / Math.max(1, usage.today.budget)) * 100)}%` }} /></div>
                <dl className="kv">
                  <dt>Tokenlar</dt><dd className="num">{usage.today.total_tokens.toLocaleString("uz-UZ")} / {usage.today.budget.toLocaleString("uz-UZ")}</dd>
                  <dt>Qolgan</dt><dd className="num">{usage.today.remaining.toLocaleString("uz-UZ")}</dd>
                  <dt>So‘rovlar</dt><dd className="num">{usage.today.requests}</dd>
                </dl>
              </div>
              <div className="card">
                <div className="card-head"><h3>14 kunlik trend</h3></div>
                <div className="card-pad">
                  {usage.days.length === 0 ? (
                    <Empty title="Ma’lumot yo‘q" note="Bu davrda AI so‘rovlari bo‘lmagan." />
                  ) : (
                    <div className="hbar">
                      {usage.days.map((day) => {
                        const max = Math.max(...usage.days.map((d) => d.total), 1);
                        return (
                          <div className="row" key={day.date}>
                            <span className="mono fs-11_5">{day.date.slice(5)}</span>
                            <span className="track"><i style={{ width: `${Math.round((day.total / max) * 100)}%` }} /></span>
                            <b className="num">{day.total.toLocaleString("uz-UZ")}</b>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
              <div className="card grid-full">
                <div className="card-head"><h3>Modellar bo‘yicha (14 kun)</h3></div>
                <div className="table-wrap flush">
                  <table className="data">
                    <thead><tr><th>Model</th><th>Provayder</th><th className="num">Token</th><th className="num">So‘rov</th></tr></thead>
                    <tbody>
                      {usage.models.map((model) => (
                        <tr key={model.model}>
                          <td className="mono" data-label="Model">{model.model}</td>
                          <td data-label="Provayder">{model.provider}</td>
                          <td className="num" data-label="Token">{model.tokens.toLocaleString("uz-UZ")}</td>
                          <td className="num" data-label="So‘rov">{model.requests}</td>
                        </tr>
                      ))}
                      {usage.models.length === 0 && <tr><td colSpan={4}><Empty title="AI so‘rovlari yo‘q" note="Shu davr uchun model statistikasi mavjud emas." /></td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <SkeletonList rows={4} />
          )}
        </TabPanel>

              <TabPanel tabKey="jobs">
          {jobs ? (
            <div className="card">
              <div className="table-wrap flush">
                <table className="data">
                  <thead><tr><th>Job</th><th>Tur</th><th>Jadval</th><th>Holat</th><th>Keyingi bajarilish</th><th aria-label="Amallar" /></tr></thead>
                  <tbody>
                    {jobs.map((job) => (
                      <tr key={job.id}>
                        <td data-label="Job">
                          <b className="fw-600">{job.name}</b>
                          {job.error && (
                            <div className="mt-xs">
                              <button className="chip" onClick={() => setJobError(jobError === job.id ? null : job.id)} aria-expanded={jobError === job.id}>
                                <AlertTriangle size={12} /> Xatoni ko‘rish
                              </button>
                              {jobError === job.id && <pre className="mono error-block">{job.error}</pre>}
                            </div>
                          )}
                        </td>
                        <td className="mono" data-label="Tur">{job.job_type}</td>
                        <td data-label="Jadval">{job.schedule}</td>
                        <td data-label="Holat">{(() => { const st = jobStatusTone(job.status); return <Badge tone={st.tone}>{st.label}</Badge>; })()}</td>
                        <td className="nowrap" data-label="Keyingi bajarilish">{fmtDateTime(job.next_run_at)}</td>
                        <td data-label="Amallar">
                          <button className="btn sm" disabled={busy} onClick={() => void runJob(job)}>
                            <Play size={13} /> Hozir bajarish
                          </button>
                        </td>
                      </tr>
                    ))}
                    {jobs.length === 0 && <tr><td colSpan={6}><Empty title="Job yo‘q" note="Hali rejalashtirilgan vazifa ishlar yo‘q." /></td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <SkeletonList rows={3} />
          )}
        </TabPanel>
        <TabPanel tabKey="backup">
          {backups ? (
            <div className="card card-pad">
              <div className="row-between mb">
                <h3>Zaxira nusxalar</h3>
                <button className="btn" disabled={backing} onClick={() => setBackupOpen(true)}>
                  <Database size={15} /> Yangi zaxira
                </button>
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Sana</th><th>Holat</th><th>Hajm</th><th>Amallar</th></tr></thead>
                  <tbody>
                    {backups.map((b) => (
                      <tr key={b.id}>
                        <td data-label="Sana">{fmtDateTime(b.started_at)}</td>
                        <td data-label="Holat">{b.status === "completed" ? "Tayyor" : b.status}</td>
                        <td data-label="Hajm" className="tnum">{Math.round(b.size_bytes / 1024)} KB</td>
                        <td data-label="Amallar">
                          <button className="btn sm" disabled={b.status !== "completed"} onClick={() => { setRestoreTarget(b); setRestoreMode("merge"); }}>
                            Tiklash
                          </button>
                          <a className="btn sm" href={`/api/v1/admin/backups/${b.id}/download`}>Yuklab olish</a>
                        </td>
                      </tr>
                    ))}
                    {backups.length === 0 && <tr><td colSpan={4}><Empty title="Zaxira yo‘q" note="«Yangi zaxira» tugmasi bilan birinchi nusxani yarating." /></td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <SkeletonList rows={3} />
          )}
        </TabPanel>
      </Tabs>

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

      <ConfirmDialog
        open={restoreTarget !== null}
        onClose={() => setRestoreTarget(null)}
        onConfirm={() => void restoreBackup()}
        title={restoreMode === "replace" ? "Zaxiradan TO'LIQ almashtirish" : "Zaxiradan tiklash (birlashtirish)"}
        message={
          restoreMode === "replace"
            ? "DIQQAT: mavjud fuqarolar, oilalar, murojaatlar va vazifalar O'CHIRILIB, zaxiradagi holat qaytariladi. Foydalanuvchilar va sozlamalar saqlanadi. Davom etamizmi?"
            : "Bazada yetishmayotgan yozuvlar zaxiradan qo'shiladi. Mavjud yozuvlar o'zgarmaydi. Davom etamizmi?"
        }
        confirmLabel={restoreMode === "replace" ? "To'liq almashtirish" : "Tiklash"}
        danger={restoreMode === "replace"}
        busy={restoring}
      >
        {restoreTarget && (
          <div className="stack-sm" role="radiogroup" aria-label="Tiklash rejimi">
            <label className="chip-inline">
              <input type="radio" name="restore-mode" checked={restoreMode === "merge"} onChange={() => setRestoreMode("merge")} />
              Birlashtirish — yetishmayotgan yozuvlar qo'shiladi (xavfsiz)
            </label>
            <label className="chip-inline">
              <input type="radio" name="restore-mode" checked={restoreMode === "replace"} onChange={() => setRestoreMode("replace")} />
              To'liq almashtirish — mavjud ma'lumotlar o'chirilib zaxira qaytariladi (xavfli)
            </label>
          </div>
        )}
      </ConfirmDialog>
    </>
  );
}
