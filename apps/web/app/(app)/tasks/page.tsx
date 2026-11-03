"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { PRIORITY, TASK_STATUS, fmtDate, statusBadge } from "@/lib/format";

type TaskRow = {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  category: string;
  due_date: string | null;
  citizen_id?: string | null;
  citizen_name?: string | null;
  assignee?: string | null;
  is_overdue: boolean;
  days_until_due?: number | null;
  evidence_note?: string | null;
};

export default function TasksPage() {
  const [data, setData] = useState<Paged<TaskRow> | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [timeframe, setTimeframe] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState("");
  const [completing, setCompleting] = useState<TaskRow | null>(null);
  const [evidence, setEvidence] = useState("");
  const [formError, setFormError] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) params.set("status", status);
    if (timeframe) params.set("timeframe", timeframe);
    api
      .get<Paged<TaskRow>>(`/tasks?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [status, timeframe, page]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  async function complete() {
    if (!completing) return;
    setBusy(completing.id);
    setFormError("");
    try {
      await api.post(`/tasks/${completing.id}/complete`, { evidence_note: evidence });
      setCompleting(null);
      setEvidence("");
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Amal bajarilmadi.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHead
        kicker="Vazifalar"
        title="Ish rejasi va nazorat"
        lede="Muddati va ustuvorligi bo‘yicha saralangan vazifalar. Bajarilgan vazifa ish yozuvi bilan tasdiqlanadi."
      />
      {error && <ErrorNote message={error} />}
      <div className="filters">
        <select className="select" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Holat — barchasi</option>
          <option value="new">Yangi</option>
          <option value="in_progress">Jarayonda</option>
          <option value="waiting">Kutilmoqda</option>
          <option value="completed">Bajarildi</option>
        </select>
        <select className="select" value={timeframe} onChange={(e) => { setTimeframe(e.target.value); setPage(1); }}>
          <option value="">Muddat — barchasi</option>
          <option value="overdue">Muddati o‘tgan</option>
          <option value="today">Bugun</option>
          <option value="week">Shu hafta</option>
        </select>
      </div>
      {completing && (
        <div className="card card-pad mb">
          <h3 className="mb">Vazifani bajarilgan deb belgilash</h3>
          <p className="text-soft mb">{completing.title}</p>
          {formError && <div className="alert danger">⚠️ {formError}</div>}
          <div className="field">
            <label>Dalil izohi (kamida 3 belgi)</label>
            <textarea className="textarea" rows={3} value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="Nima qilindi, natija qanday tasdiqlandi…" />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" disabled={busy === completing.id || evidence.trim().length < 3} onClick={complete}>
              Tasdiqlash
            </button>
            <button className="btn" onClick={() => setCompleting(null)}>
              Bekor qilish
            </button>
          </div>
        </div>
      )}
      {!data && !error && <Loading />}
      {data && (
        <div className="card">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Vazifa</th>
                  <th>Fuqaro</th>
                  <th>Muddat</th>
                  <th>Holat</th>
                  <th>Ustuvorlik</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((task) => {
                  const st = statusBadge(TASK_STATUS, task.status);
                  const pr = statusBadge(PRIORITY, task.priority);
                  return (
                    <tr key={task.id}>
                      <td>
                        <b>{task.title}</b>
                        {task.description && <div className="text-faint">{task.description.slice(0, 90)}</div>}
                      </td>
                      <td>{task.citizen_name ?? "—"}</td>
                      <td className="nowrap">
                        {fmtDate(task.due_date)}
                        {task.is_overdue && (
                          <div>
                            <Badge tone="danger">Kechikkan</Badge>
                          </div>
                        )}
                      </td>
                      <td>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </td>
                      <td>
                        <Badge tone={pr.tone}>{pr.label}</Badge>
                      </td>
                      <td>
                        {!["completed", "cancelled"].includes(task.status) && (
                          <button className="btn sm" onClick={() => setCompleting(task)}>
                            Bajarildi
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <Empty title="Vazifa topilmadi" icon="✓" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager meta={data.meta} onPage={setPage} />
        </div>
      )}
    </>
  );
}
