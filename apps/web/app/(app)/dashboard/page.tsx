"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle, ArrowRight, Bot, ClipboardList, Database, FileSpreadsheet,
  Inbox, Sparkles, Users,
} from "@/components/ui/icons";
import { Badge, PageHead } from "@/components/ui";
import { ErrorState, SkeletonBlock, SkeletonList } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import { CASE_STATUS, PRIORITY, TASK_STATUS, fmtDateTime, statusBadge } from "@/lib/format";

type Metric = { key: string; label: string; value: number | string; hint?: string };
type Distribution = { label: string; value: number }[];
type TaskRow = { id: string; title: string; status: string; priority: string; due_date: string | null; citizen_name?: string | null };
type CaseRow = { id: string; title: string; status: string; priority: string; citizen_name?: string | null };
type Activity = { id: string; action?: string; description?: string; title?: string; created_at: string };
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
  houses: "/families",
  streets: "/families",
  employed: "/citizens?employment_status=Ishlaydi",
  unemployed: "/citizens?employment_status=Ishsiz",
  open_cases: "/cases",
  today_tasks: "/tasks",
  overdue_tasks: "/tasks?timeframe=overdue",
};

function HBar({ rows, tone = "var(--brand-600)", maxHint }: { rows: Distribution; tone?: string; maxHint?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="hbar">
      {rows.slice(0, 8).map((row) => (
        <div className="row" key={row.label}>
          <span>{row.label}</span>
          <span className="track"><i style={{ width: `${Math.round((row.value / max) * 100)}%`, background: tone }} /></span>
          <b>{row.value}</b>
        </div>
      ))}
      {rows.length === 0 && <p className="text-faint" style={{ fontSize: 13 }}>{maxHint ?? "Ma'lumot mavjud emas"}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const setupFileRef = useRef<HTMLInputElement>(null);
  const [setupBusy, setSetupBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setError("");
    api
      .get<DashboardData>("/dashboard")
      .then((d) => alive && setData(d))
      .catch((err) => alive && setError(err instanceof Error ? err.message : "Xatolik"));
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
      setError(err instanceof Error ? err.message : "Yuklash amalga oshmadi.");
      setSetupBusy(false);
    }
  }

  if (error && !data) {
    return (
      <ErrorState
        title="Dashboard ma'lumotlari olinmadi"
        note={error}
        onRetry={() => { setData(null); setReloadKey((k) => k + 1); }}
      />
    );
  }
  if (!data) {
    return (
      <>
        <PageHead kicker="Boshqaruv paneli" title="Navbahor mahallasi" lede="Yuklanmoqda…" />
        <div className="grid grid-4 mb">
          {Array.from({ length: 4 }).map((_, i) => (
            <div className="card stat" key={i}>
              <SkeletonBlock h={11} w="55%" />
              <div style={{ height: 6 }} />
              <SkeletonBlock h={26} w="40%" />
              <div style={{ height: 8 }} />
              <SkeletonBlock h={11} w="70%" />
            </div>
          ))}
        </div>
        <SkeletonList rows={4} />
      </>
    );
  }

  const metric = (key: string) => data.metrics.find((item) => item.key === key);
  const isEmptyBase = (metric("citizens")?.value ?? 0) === 0;

  if (isEmptyBase) {
    return (
      <>
        <PageHead kicker="Boshqaruv paneli" title="Navbahor mahallasi — boshlash" lede="Baza hozircha bo'sh. Birinchi qadam — fuqarolar bazasini yuklash." />
        {error && <ErrorState title="Yuklashda xatolik" note={error} />}
        <div className="setup-hero mb">
          <div>
            <h2>1-qadam: bazani yuklang</h2>
            <div className="steps">
              <span>1. Excel (.xlsx), CSV, Word (.docx) yoki PDF faylni tanlang.</span>
              <span>2. Tizim ustunlarni avtomatik aniqlaydi va xatoliklar hisobotini beradi.</span>
              <span>3. Hisobotni ko'rib, tuzatishlarni kiritib, tasdiqlaysiz.</span>
              <span>4. Shu ondan AI agentlar sizning ma'lumotingiz bilan ishlaydi.</span>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 280 }}>
            <input ref={setupFileRef} type="file" accept=".xlsx,.csv,.docx,.pdf" className="input" aria-label="Baza fayli" />
            <button className="btn primary lg" disabled={setupBusy} onClick={() => void quickUpload()}>
              <FileSpreadsheet size={17} />
              {setupBusy ? "Tahlil qilinmoqda…" : "Faylni yuklash va tahlil qilish"}
            </button>
            <Link className="link" href="/documents">Hujjatlar bo'limiga o'tish →</Link>
          </div>
        </div>
        <div className="grid grid-4">
          {["Fuqarolar", "Oilalar", "Uylar", "AI agentlar"].map((label) => (
            <div className="card stat" key={label}>
              <span className="label">{label}</span>
              <span className="value">0</span>
              <span className="hint">Baza bo'sh — yuklangach ishlaydi</span>
            </div>
          ))}
        </div>
      </>
    );
  }

  const employmentTotal = data.employment.reduce((acc, e) => acc + e.value, 0);
  const attentionRows = [
    ...data.overdue_tasks.map((t) => ({ kind: "task", row: t })),
  ];
  const openCases = data.open_cases;

  return (
    <>
      <PageHead
        kicker="Boshqaruv paneli"
        title="Navbahor mahallasi — bugungi holat"
        lede={`Ma'lumotlar ${fmtDateTime(data.as_of)} holatiga ko'ra yangilandi. Xorazm viloyati, Urganch shahri.`}
        actions={
          <Link className="btn primary" href="/chat">
            <Sparkles size={16} /> AI assistent
          </Link>
        }
      />

      <div className="grid grid-4 mb">
        {[
          { key: "citizens", icon: <Users size={15} /> },
          { key: "families", icon: <Users size={15} /> },
          { key: "houses", icon: <Database size={15} /> },
          { key: "unemployed", icon: <AlertTriangle size={15} /> },
        ].map(({ key, icon }) => {
          const m = metric(key);
          if (!m) return null;
          return (
            <div className="card stat" key={key}>
              <span className="label">{icon}{m.label}</span>
              <span className="value">{m.value}</span>
              {m.hint && <span className="hint">{m.hint}</span>}
              {ROUTE_BY_KEY[key] && (
                <Link className="overlay-link" href={ROUTE_BY_KEY[key]} aria-label={`${m.label} — bo'limga o'tish`} />
              )}
            </div>
          );
        })}
      </div>

      <div className="split s2 mb">
        <div className="card">
          <div className="card-head">
            <h3>Vazifalar nazorati</h3>
            <Link className="link" href="/tasks">Barchasi →</Link>
          </div>
          <div className="card-pad" style={{ display: "grid", gap: 10 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <Link href="/tasks?timeframe=overdue" style={{ display: "grid", gap: 2, padding: "12px 14px", borderRadius: "var(--radius-sm)", background: "var(--danger-soft)" }}>
                <span style={{ fontSize: 24, fontWeight: 650, color: "var(--color-danger)", fontVariantNumeric: "tabular-nums" }}>{data.overdue_tasks.length}</span>
                <span style={{ fontSize: 12.5, color: "var(--color-danger)", fontWeight: 600 }}>Muddati o'tgan</span>
              </Link>
              <Link href="/tasks?timeframe=today" style={{ display: "grid", gap: 2, padding: "12px 14px", borderRadius: "var(--radius-sm)", background: "var(--warning-soft)" }}>
                <span style={{ fontSize: 24, fontWeight: 650, color: "var(--color-warning)", fontVariantNumeric: "tabular-nums" }}>{data.today_tasks.length}</span>
                <span style={{ fontSize: 12.5, color: "var(--color-warning)", fontWeight: 600 }}>Bugun</span>
              </Link>
            </div>
            {data.overdue_tasks.slice(0, 4).map((task) => {
              const st = statusBadge(TASK_STATUS, task.status);
              return (
                <div key={task.id} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <AlertTriangle size={15} style={{ color: "var(--color-warning)", flexShrink: 0, marginTop: 2 }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>{task.title}</div>
                    <div className="text-faint" style={{ fontSize: 12.5 }}>
                      {task.citizen_name ? `${task.citizen_name} · ` : ""}
                      {st.label} · muddat {task.due_date ?? "—"}
                    </div>
                  </div>
                </div>
              );
            })}
            {data.overdue_tasks.length === 0 && <p className="text-soft" style={{ fontSize: 13.5 }}>Muddati o'tgan vazifa yo'q — yaxshi ish!</p>}
          </div>
        </div>

        <div className="card card-pad">
          <h3 className="mb">Ma'lumotlar sifati</h3>
          <div className="progress mb"><i style={{ width: `${data.data_quality.score}%` }} /></div>
          <p className="text-soft mb" style={{ fontSize: 13.5 }}>
            Sifat: <b>{data.data_quality.score}%</b> · to'liq yozuvlar: <b className="num">{data.data_quality.complete}</b> · bugun yangilangan: <b className="num">{data.data_quality.updated_today}</b>
          </p>
          <p className="text-faint" style={{ fontSize: 12.5 }}>
            To'ldirilmagan yozuvlar: {data.data_quality.incomplete} · oxirgi sinxronlash: {fmtDateTime(data.data_quality.last_sync)}
          </p>
          <div className="mt" style={{ display: "grid", gap: 8 }}>
            <Link className="btn secondary sm" href="/documents" style={{ justifyContent: "center" }}>
              <FileSpreadsheet size={15} /> Baza faylini boshqarish
            </Link>
          </div>
        </div>
      </div>

      <div className="split s2 mb">
        <div className="card">
          <div className="card-head">
            <h3>Ochiq murojaatlar</h3>
            <Link className="link" href="/cases">Barchasi →</Link>
          </div>
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
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
                      <td>
                        <Link className="rowlink" href={`/cases/${row.id}`}>{row.title}</Link>
                        {row.citizen_name && <div className="cell-sub">{row.citizen_name}</div>}
                      </td>
                      <td><Badge tone={st.tone}>{st.label}</Badge></td>
                      <td><Badge tone={pr.tone}>{pr.label}</Badge></td>
                    </tr>
                  );
                })}
                {openCases.length === 0 && (
                  <tr><td colSpan={3}><div className="empty"><div className="icon"><Inbox size={18} /></div><h3>Ochiq murojaat yo'q</h3></div></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>Ko'chalar bo'yicha kesim</h3></div>
          <div className="card-pad">
            <HBar rows={data.streets.map((s) => ({ label: s.label, value: s.citizens }))} />
          </div>
        </div>
      </div>

      <div className="split s2">
        <div className="card">
          <div className="card-head"><h3>Ehtiyojlar taqsimoti</h3></div>
          <div className="card-pad"><HBar rows={data.needs} tone="var(--color-info)" /></div>
        </div>
        <div className="card">
          <div className="card-head"><h3>So'nggi harakatlar</h3></div>
          <div className="card-pad">
            <div className="timeline">
              {data.recent_activity.slice(0, 8).map((row) => (
                <div className="tl-item" key={row.id}>
                  <span className="tl-dot" />
                  <div className="tl-body">
                    <h4>{row.title ?? row.action ?? "Harakat"}</h4>
                    <div className="when">{fmtDateTime(row.created_at)}</div>
                    {row.description && <div className="desc">{row.description}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      {attentionRows.length === 0 && openCases.length === 0 && (
        <div className="alert info mt"><Bot size={16} /><span>Hammasi tartibda. AI assistent bilan kunlik rejani tuzing.</span></div>
      )}
    </>
  );
}
