"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle, ArrowRight, Check, CircleDashed, ClipboardList, Database, FileSpreadsheet,
  Home, Inbox, LogIn, Settings, Sparkles, Users, Wallet,
} from "@/components/ui/icons";
import { Badge, PageHead, StatCard } from "@/components/ui";
import { ErrorState, SkeletonDashboard } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import { CASE_STATUS, PRIORITY, TASK_STATUS, fmtDateTime, statusBadge } from "@/lib/format";

type Metric = { key: string; label: string; value: number | string; hint?: string };
type Distribution = { label: string; value: number }[];
type TaskRow = { id: string; title: string; status: string; priority: string; due_date: string | null; citizen_name?: string | null };
type CaseRow = { id: string; title: string; status: string; priority: string; citizen_name?: string | null };
type Activity = { id: string; action?: string; description?: string; title?: string; created_at: string; tone?: string };
type DashboardData = {
  metrics: Metric[];
  employment: Distribution;
  social: Distribution;
  education: Distribution;
  needs: Distribution;
  streets: { label: string; houses: number; citizens: number }[];
  today_tasks: TaskRow[];
  overdue_tasks: TaskRow[];
  open_cases: CaseRow[];
  recent_activity: Activity[];
  data_quality: { score: number; incomplete: number; complete: number; updated_today: number; last_sync: string };
  as_of: string;
};

const ROUTE_BY_KEY: Record<string, string> = {
  citizens: "/citizens",
  families: "/families",
  houses: "/families?tab=houses",
  streets: "/families?tab=streets",
  employed: "/citizens?employment_status=Ishlaydi",
  unemployed: "/citizens?employment_status=Ishsiz",
  open_cases: "/cases",
  today_tasks: "/tasks",
  overdue_tasks: "/tasks?timeframe=overdue",
};

const KPI_META: Record<string, { icon: React.ReactNode; tone: "teal" | "coral" | "amber" | "sky" | "plum" }> = {
  citizens: { icon: <Users size={20} />, tone: "teal" },
  families: { icon: <Home size={20} />, tone: "sky" },
  houses: { icon: <Database size={20} />, tone: "plum" },
  unemployed: { icon: <AlertTriangle size={20} />, tone: "coral" },
};

/** Harakat turiga mos ikon va rang (P0-6) */
const ACTIVITY_ICON: Record<string, { icon: React.ReactNode; tone: string }> = {
  login: { icon: <LogIn size={12} />, tone: "tone-ok" },
  chat: { icon: <Sparkles size={12} />, tone: "tone-info" },
  settings: { icon: <Settings size={12} />, tone: "tone-muted" },
  error: { icon: <AlertTriangle size={12} />, tone: "tone-danger" },
  task: { icon: <ClipboardList size={12} />, tone: "tone-ok" },
  wallet: { icon: <Wallet size={12} />, tone: "tone-info" },
};

function activityVisual(action: string) {
  const a = action ?? "";
  if (a.includes("login") || a.includes("logout")) return ACTIVITY_ICON.login;
  if (a.includes("agent") || a.includes("chat") || a.includes("draft")) return ACTIVITY_ICON.chat;
  if (a.includes("settings") || a.includes("auth")) return ACTIVITY_ICON.settings;
  if (a.includes("failed") || a.includes("error")) return ACTIVITY_ICON.error;
  if (a.includes("task") || a.includes("case") || a.includes("citizen") || a.includes("document") || a.includes("report")) return ACTIVITY_ICON.task;
  return ACTIVITY_ICON.wallet;
}

/** HBar — yagona brend rangi (P1-9), bo‘sh joy yo‘q */
function HBar({ rows, maxHint }: { rows: Distribution; maxHint?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  if (rows.length === 0) {
    return <p className="text-faint fs-13">{maxHint ?? "Ma’lumot mavjud emas"}</p>;
  }
  return (
    <div className="hbar fill">
      {rows.slice(0, 8).map((row) => (
        <div className="row" key={row.label}>
          <span>{row.label}</span>
          <span className="track"><i style={{ width: `${Math.round((row.value / max) * 100)}%` }} /></span>
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  );
}

/** Donut — ko‘chalar kesimi (7.4) */
const DONUT_COLORS = ["var(--brand-700)", "var(--brand-500)", "var(--brand-400)", "var(--brand-300)", "var(--brand-200)", "var(--color-info)", "var(--color-warning)", "var(--color-text-muted)"];

function Donut({ rows }: { rows: Array<{ label: string; value: number }> }) {
  const data = rows.filter((r) => r.value > 0).slice(0, 8);
  const total = data.reduce((acc, r) => acc + r.value, 0);
  if (total === 0) return <p className="text-faint fs-13">Ko‘chalarda ko‘rsatiladigan fuqaro yo‘q.</p>;
  const r = 60;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut-wrap">
      <div className="donut">
        <svg width="148" height="148" viewBox="0 0 148 148" role="img" aria-label={`Ko‘chalar bo‘yicha fuqarolar kesimi, jami ${total}`}>
          <circle cx="74" cy="74" r={r} fill="none" stroke="var(--color-surface-3)" strokeWidth="18" />
          {data.map((row, i) => {
            const len = (row.value / total) * c;
            const dash = `${len} ${c - len}`;
            const el = (
              <circle
                key={row.label}
                className="donut-seg"
                cx="74"
                cy="74"
                r={r}
                fill="none"
                stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
                strokeWidth="18"
                strokeDasharray={dash}
                strokeDashoffset={-offset}
              >
                <title>{`${row.label}: ${row.value} fuqaro`}</title>
              </circle>
            );
            offset += len;
            return el;
          })}
        </svg>
        <div className="donut-center">
          <b className="num">{total.toLocaleString("uz-UZ")}</b>
          <span>jami fuqaro</span>
        </div>
      </div>
      <div className="donut-legend">
        {data.map((row, i) => (
          <div className="dl-row" key={row.label}>
            <span className="dl-dot" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span className="dl-label">{row.label}</span>
            <span className="dl-value">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Onboarding checklist (7.7) */
const ONBOARD_KEY = "mahalla-onboarding";

type OnboardState = { base: boolean; street: boolean; ai: boolean };

function readOnboard(): OnboardState {
  if (typeof window === "undefined") return { base: false, street: false, ai: false };
  try {
    const raw = window.localStorage.getItem(ONBOARD_KEY);
    if (raw) return { base: false, street: false, ai: false, ...(JSON.parse(raw) as Partial<OnboardState>) };
  } catch { /* localStorage bo‘lmasa — boshlang‘ich holat */ }
  return { base: false, street: false, ai: false };
}

function writeOnboard(state: OnboardState) {
  try { window.localStorage.setItem(ONBOARD_KEY, JSON.stringify(state)); } catch { /* xotira cheklovi */ }
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const setupFileRef = useRef<HTMLInputElement>(null);
  const [setupBusy, setSetupBusy] = useState(false);
  const [onboard, setOnboard] = useState<OnboardState>({ base: false, street: false, ai: false });

  useEffect(() => {
    setOnboard(readOnboard());
  }, []);

  useEffect(() => {
    let alive = true;
    setError("");
    api
      .get<DashboardData>("/dashboard")
      .then((d) => alive && setData(d))
      .catch((err) => alive && setError(err instanceof Error ? err.message : "Yuklab bo‘lmadi"));
    return () => { alive = false; };
  }, [reloadKey]);

  async function quickUpload() {
    const file = setupFileRef.current?.files?.[0];
    if (!file) return;
    setSetupBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("analyze", "true");
      await api.upload("/documents", form);
      router.push("/documents");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklanmadi. O‘lcham 4 MB dan oshmasligini tekshirib, qayta yuklang.");
      setSetupBusy(false);
    }
  }

  function markStep(step: keyof OnboardState) {
    setOnboard((prev) => {
      const next = { ...prev, [step]: true };
      writeOnboard(next);
      return next;
    });
  }

  if (error && !data) {
    return (
      <ErrorState
        title="Dashboard ma’lumotlari olinmadi"
        note={`${error}. Internet aloqasini tekshirib, qayta urinishni bosing.`}
        onRetry={() => { setData(null); setReloadKey((k) => k + 1); }}
      />
    );
  }
  if (!data) {
    return (
      <>
        <PageHead kicker="Boshqaruv paneli" title="Navbahor mahallasi" lede="Ma’lumotlar yuklanmoqda, iltimos kuting…" />
        <SkeletonDashboard />
      </>
    );
  }

  const metric = (key: string) => data.metrics.find((item) => item.key === key);
  const isEmptyBase = Number(metric("citizens")?.value ?? 0) === 0;

  /* P0-4: bo‘sh holatda soxta “0” KPI yo‘q — onboarding checklist */
  if (isEmptyBase) {
    const steps = [
      {
        key: "base" as const,
        title: "Bazani yuklang",
        note: "Excel, CSV, Word yoki PDF fayldan fuqarolar bazasini yuklang. Tizim ustunlarni avtomatik aniqlaydi.",
        done: onboard.base,
      },
      {
        key: "street" as const,
        title: "Birinchi ko‘chani tekshiring",
        note: "Ko‘chalar kesimini ko‘rib chiqing va manzil yozuvlarini to‘ldiring.",
        done: onboard.street,
      },
      {
        key: "ai" as const,
        title: "AI suhbatni sinab ko‘ring",
        note: "“Bugun qaysi vazifalarga e’tibor berishim kerak?” deb so‘rang.",
        done: onboard.ai,
      },
    ];
    const doneCount = steps.filter((s) => s.done).length;
    const progress = Math.round((doneCount / steps.length) * 100);

    return (
      <>
        <PageHead
          kicker="Boshqaruv paneli"
          title="Navbahor mahallasi — boshlash"
          lede="Baza hozircha bo‘sh. Quyidagi uch qadamni bajarib, tizimni ishga tushiring."
        />
        {error && <ErrorState title="Yuklashda xatolik" note={error} />}

        <div className="card card-pad mb">
          <div className="row-between-top mb">
            <h3>Boshlang‘ich ro‘yxat</h3>
            <Badge tone={doneCount === steps.length ? "ok" : "info"}>{doneCount}/{steps.length} qadam bajarildi</Badge>
          </div>
          <div className="progress mb"><i style={{ width: `${progress}%` }} /></div>

          <div className="onboard-list">
            {steps.map((step) => (
              <div className={`onboard-item${step.done ? " done" : ""}`} key={step.key}>
                <span className="oi-ico" aria-hidden="true">
                  {step.done ? <Check size={14} /> : <CircleDashed size={14} />}
                </span>
                <span className="grow">
                  <b>{step.title}</b>
                  <p>{step.note}</p>
                </span>
                {!step.done ? (
                  <button className="btn sm" onClick={() => markStep(step.key)}>Bajarildi deb belgilash</button>
                ) : (
                  <Badge tone="ok">Bajarilgan</Badge>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="setup-hero mb">
          <div>
            <h2>1-qadam: bazani yuklang</h2>
            <div className="steps">
              <span>1. Excel (.xlsx), CSV, Word (.docx) yoki PDF faylni tanlang.</span>
              <span>2. Tizim ustunlarni avtomatik aniqlaydi va xatoliklar hisobotini beradi.</span>
              <span>3. Hisobotni ko‘rib, tuzatishlarni kiritib, tasdiqlaysiz.</span>
              <span>4. Shu ondan AI agentlar sizning ma’lumotingiz bilan ishlaydi.</span>
            </div>
          </div>
          <div className="setup-actions">
            <input ref={setupFileRef} type="file" accept=".xlsx,.csv,.docx,.pdf" className="input" aria-label="Baza fayli" />
            <button className="btn primary lg" disabled={setupBusy} onClick={() => void quickUpload()}>
              <FileSpreadsheet size={17} />
              {setupBusy ? "Tahlil qilinmoqda…" : "Fayl yuklash → Avtomatik tahlil"}
            </button>
            <Link className="link" href="/documents">Hujjatlar bo‘limiga o‘tish →</Link>
          </div>
        </div>
      </>
    );
  }

  const openCases = data.open_cases;

  return (
    <>
      <PageHead
        kicker="Boshqaruv paneli"
        title="Navbahor mahallasi — bugungi holat"
        lede={`Ma’lumotlar ${fmtDateTime(data.as_of)} holatiga ko‘ra yangilandi. Xorazm viloyati, Urganch shahri.`}
        actions={
          <Link className="btn primary" href="/chat">
            <Sparkles size={16} /> AI assistent
          </Link>
        }
      />

      <div className="grid grid-4 mb">
        {["citizens", "families", "houses", "unemployed"].map((key) => {
          const m = metric(key);
          if (!m) return null;
          const meta = KPI_META[key];
          return (
            <StatCard
              key={key}
              label={m.label}
              value={m.value}
              hint={m.hint}
              icon={meta.icon}
              tone={meta.tone}
              link={ROUTE_BY_KEY[key]}
              linkLabel={`${m.label} — bo‘limga o‘tish`}
            />
          );
        })}
      </div>

      <div className="split s2 mb">
        <div className="card">
          <div className="card-head">
            <h3>Vazifalar nazorati</h3>
            <Link className="link row-sm" href="/tasks">Barchasi <ArrowRight size={13} /></Link>
          </div>
          <div className="card-pad stack">
            <div className="grid-2-cols">
              <Link href="/tasks?timeframe=overdue" className="panel-stat panel-danger">
                <b>{data.overdue_tasks.length}</b>
                <span>Muddati o‘tgan vazifalar</span>
              </Link>
              <Link href="/tasks?timeframe=today" className="panel-stat panel-warn">
                <b>{data.today_tasks.length}</b>
                <span>Bugungi reja</span>
              </Link>
            </div>
            {data.overdue_tasks.slice(0, 4).map((task) => {
              const st = statusBadge(TASK_STATUS, task.status);
              return (
                <div key={task.id} className="row-top">
                  <AlertTriangle size={15} className="text-warn-ico shrink0 mt-xs" />
                  <div className="min0">
                    <div className="fw-600 fs-13_5">{task.title}</div>
                    <div className="text-faint fs-12_5">
                      {task.citizen_name ? `${task.citizen_name} · ` : ""}
                      {st.label} · muddat {task.due_date ?? "—"}
                    </div>
                  </div>
                </div>
              );
            })}
            {data.overdue_tasks.length === 0 && (
              <p className="text-soft fs-13_5 row-sm">
                <Check size={15} className="text-ok-ico" />
                Muddati o‘tgan vazifa yo‘q — barcha reja tartibda
              </p>
            )}
          </div>
        </div>

        <div className="card card-pad">
          <h3 className="mb">Ma’lumotlar sifati</h3>
          <div className="progress mb"><i style={{ width: `${data.data_quality.score}%` }} /></div>
          <p className="text-soft mb fs-13_5">
            Sifat: <b>{data.data_quality.score}%</b> · to‘liq yozuvlar: <b className="num">{data.data_quality.complete}</b> · bugun yangilangan: <b className="num">{data.data_quality.updated_today}</b>
          </p>
          <p className="text-faint fs-12_5">
            To‘ldirilmagan yozuvlar: {data.data_quality.incomplete} · oxirgi sinxronlash: {fmtDateTime(data.data_quality.last_sync)}
          </p>
          <div className="mt">
            <Link className="btn secondary sm" href="/documents">
              <FileSpreadsheet size={15} /> Baza faylini boshqarish
            </Link>
          </div>
        </div>
      </div>

      <div className="split s2 mb">
        <div className="card">
          <div className="card-head">
            <h3>Ochiq murojaatlar</h3>
            <Link className="link row-sm" href="/cases">Barchasi <ArrowRight size={13} /></Link>
          </div>
          <div className="table-wrap flush">
            <table className="data">
              <thead>
                <tr><th>Murojaat</th><th>Holat</th><th>Ustuvorlik</th></tr>
              </thead>
              <tbody>
                {openCases.slice(0, 7).map((row) => {
                  const st = statusBadge(CASE_STATUS, row.status);
                  const pr = statusBadge(PRIORITY, row.priority);
                  return (
                    <tr key={row.id}>
                      <td data-label="Murojaat">
                        <Link className="rowlink" href={`/cases/${row.id}`}>{row.title}</Link>
                        {row.citizen_name && <div className="cell-sub">{row.citizen_name}</div>}
                      </td>
                      <td data-label="Holat"><Badge tone={st.tone}>{st.label}</Badge></td>
                      <td data-label="Ustuvorlik" className={`pri-bar pri-${row.priority}`}><Badge tone={pr.tone}>{pr.label}</Badge></td>
                    </tr>
                  );
                })}
                {openCases.length === 0 && (
                  <tr><td colSpan={3}><div className="empty"><div className="icon"><Inbox size={18} /></div><h3>Ochiq murojaat yo‘q</h3></div></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>Ko‘chalar bo‘yicha kesim</h3></div>
          <div className="card-pad">
            <Donut rows={data.streets.map((s) => ({ label: s.label, value: s.citizens }))} />
          </div>
        </div>
      </div>

      <div className="split s2">
        <div className="card">
          <div className="card-head"><h3>Ehtiyojlar taqsimoti</h3></div>
          <div className="card-pad h-full">
            <HBar rows={data.needs} maxHint="Ehtiyoj bo‘yicha yozuvlar hali kiritilmagan" />
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <h3>So‘nggi harakatlar</h3>
            <Link className="link row-sm" href="/worklogs">Barchasi <ArrowRight size={13} /></Link>
          </div>
          <div className="card-pad">
            <div className="timeline">
              {data.recent_activity.slice(0, 5).map((row) => {
                const visual = activityVisual(row.action ?? "");
                return (
                  <div className="tl-item" key={row.id}>
                    <span className={`tl-dot ${visual.tone}`} aria-hidden="true">{visual.icon}</span>
                    <div className="tl-body">
                      <h4>{row.title ?? row.action ?? "Harakat"}</h4>
                      <div className="when">{fmtDateTime(row.created_at)}</div>
                      {row.description && <div className="desc">{row.description}</div>}
                    </div>
                  </div>
                );
              })}
              {data.recent_activity.length === 0 && (
                <p className="text-faint fs-13_5">Hali harakatlar qayd etilmagan.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
