"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, PageHead, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { CASE_STATUS, PRIORITY, TASK_STATUS, fmtDateTime, statusBadge } from "@/lib/format";

type Metric = { key: string; label: string; value: number | string; hint?: string };
type Distribution = { label: string; value: number }[];
type TaskRow = {
  id: string;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  citizen_name?: string | null;
};
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

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<DashboardData>("/dashboard")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  if (error) return <ErrorNote message={error} />;
  if (!data) return <Loading />;

  const metric = (key: string) => data.metrics.find((item) => item.key === key);

  return (
    <>
      <PageHead
        kicker="Boshqaruv paneli"
        title="Navbahor mahallasi — bugungi holat"
        lede={`Ma'lumotlar ${fmtDateTime(data.as_of)} holatiga ko'ra yangilandi. Xorazm viloyati, Urganch shahri.`}
        actions={
          <Link className="btn primary" href="/chat">
            ✦ AI assistent bilan maslahat
          </Link>
        }
      />

      <div className="grid grid-4 mb">
        <Stat label="Fuqarolar" value={metric("citizens")?.value ?? "—"} hint="Faol yozuvlar" />
        <Stat label="Oilalar" value={metric("families")?.value ?? "—"} hint={metric("families")?.hint} />
        <Stat label="Uylar" value={metric("houses")?.value ?? "—"} hint={metric("houses")?.hint} />
        <Stat
          label="Bandlik"
          value={`${metric("employed")?.value ?? 0} / ${(Number(metric("employed")?.value ?? 0) + Number(metric("unemployed")?.value ?? 0))}`}
          hint="Band fuqarolar / iqtisodiy faol"
        />
        <Stat label="Ishsizlar" value={metric("unemployed")?.value ?? "—"} hint="Bandlik markazi bilan ishlash" />
      </div>

      <div className="split s2 mb">
        <div className="card">
          <div className="card-head">
            <h3>Vazifalar nazorati</h3>
            <Link className="link" href="/tasks">
              Barchasi →
            </Link>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Muddati o‘tgan</th>
                  <th>Bugun</th>
                  <th>Shu haftada</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontSize: 24, fontWeight: 700, color: "var(--danger)" }}>
                    {data.overdue_tasks.length}
                  </td>
                  <td style={{ fontSize: 24, fontWeight: 700, color: "var(--accent)" }}>
                    {data.today_tasks.length}
                  </td>
                  <td style={{ fontSize: 24, fontWeight: 700, color: "var(--brand)" }}>
                    {Math.max(0, data.today_tasks.length)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div style={{ padding: "6px 16px 14px" }}>
            {data.overdue_tasks.slice(0, 4).map((task) => (
              <div key={task.id} className="tl-item" style={{ gridTemplateColumns: "1fr" }}>
                <div className="tl-body">
                  <h4>⚠️ {task.title}</h4>
                  <div className="when">
                    {task.citizen_name ? `${task.citizen_name} · ` : ""}
                    {statusBadge(TASK_STATUS, task.status).label} · muddat {task.due_date ?? "—"}
                  </div>
                </div>
              </div>
            ))}
            {data.overdue_tasks.length === 0 && (
              <p className="text-soft">Muddati o‘tgan vazifa yo‘q — yaxshi ish!</p>
            )}
          </div>
        </div>

        <div className="card card-pad">
          <h3 className="mb">Ma'lumotlar sifati</h3>
          <div className="progress mb">
            <i style={{ width: `${data.data_quality.score}%` }} />
          </div>
          <p className="text-soft mb">
            Sifat ko‘rsatkichi: <b>{data.data_quality.score}%</b> · to‘liq yozuvlar:{" "}
            <b>{data.data_quality.complete}</b> · bugun yangilangan: <b>{data.data_quality.updated_today}</b>
          </p>
          <p className="text-soft">
            To‘ldirilmagan yozuvlar: <b>{data.data_quality.incomplete}</b>. Oxirgi sinxronlash:{" "}
            {fmtDateTime(data.data_quality.last_sync)}.
          </p>
        </div>
      </div>

      <div className="split s2 mb">
        <div className="card">
          <div className="card-head">
            <h3>Ochiq murojaatlar</h3>
            <Link className="link" href="/cases">
              Barchasi →
            </Link>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Murojaat</th>
                  <th>Holat</th>
                  <th>Ustuvorlik</th>
                </tr>
              </thead>
              <tbody>
                {data.open_cases.slice(0, 7).map((row) => {
                  const status = statusBadge(CASE_STATUS, row.status);
                  const priority = statusBadge(PRIORITY, row.priority);
                  return (
                    <tr key={row.id}>
                      <td>
                        <Link className="rowlink" href={`/cases?focus=${row.id}`}>
                          {row.title}
                        </Link>
                        {row.citizen_name && <div className="text-faint">{row.citizen_name}</div>}
                      </td>
                      <td>
                        <Badge tone={status.tone}>{status.label}</Badge>
                      </td>
                      <td>
                        <Badge tone={priority.tone}>{priority.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
                {data.open_cases.length === 0 && (
                  <tr>
                    <td colSpan={3}>
                      <Empty title="Ochiq murojaat yo‘q" icon="✓" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Ko‘chalar bo‘yicha kesim</h3>
          </div>
          <div className="card-pad hbar">
            {data.streets.slice(0, 8).map((row) => {
              const max = Math.max(...data.streets.map((s) => s.citizens), 1);
              return (
                <div className="row" key={row.label}>
                  <span className="text-soft">{row.label}</span>
                  <span className="track">
                    <i style={{ width: `${Math.round((row.citizens / max) * 100)}%` }} />
                  </span>
                  <b>{row.citizens}</b>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="split s2">
        <div className="card">
          <div className="card-head">
            <h3>Ehtiyojlar taqsimoti</h3>
          </div>
          <div className="card-pad hbar">
            {data.needs.slice(0, 8).map((row) => {
              const max = Math.max(...data.needs.map((s) => s.value), 1);
              return (
                <div className="row" key={row.label}>
                  <span className="text-soft">{row.label}</span>
                  <span className="track">
                    <i style={{ width: `${Math.round((row.value / max) * 100)}%` }} />
                  </span>
                  <b>{row.value}</b>
                </div>
              );
            })}
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <h3>So‘nggi harakatlar</h3>
          </div>
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
    </>
  );
}
