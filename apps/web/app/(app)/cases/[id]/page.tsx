"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, ErrorNote, Loading, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { CASE_STATUS, PRIORITY, TASK_STATUS, fmtDate, fmtDateTime, statusBadge } from "@/lib/format";

type CaseDetail = {
  id: string;
  title: string;
  category: string;
  description: string;
  status: string;
  priority: string;
  citizen_id?: string | null;
  citizen_name?: string | null;
  responsible_user?: string | null;
  opened_at: string;
  target_date?: string | null;
  outcome?: string;
  closed_at?: string | null;
  tasks: { id: string; title: string; status: string; priority: string; due_date: string | null }[];
};

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .get<CaseDetail>(`/cases/${params.id}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function changeStatus(status: string) {
    setBusy(true);
    try {
      await api.patch(`/cases/${params.id}`, { status });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Amal bajarilmadi.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) return <ErrorNote message={error} />;
  if (!data) return <Loading />;

  const st = statusBadge(CASE_STATUS, data.status);

  return (
    <>
      <PageHead
        kicker={`Murojaat · ${data.id}`}
        title={data.title}
        lede={`${data.category} · ${fmtDate(data.opened_at)} da ochildi`}
        actions={
          <Link className="btn" href="/cases">
            ← Murojaatlar
          </Link>
        }
      />
      {error && <ErrorNote message={error} />}
      <div className="split s2r">
        <div className="card card-pad">
          <h3 className="mb">Mazmuni</h3>
          <dl className="kv">
            <dt>Holat</dt>
            <dd>
              <Badge tone={st.tone}>{st.label}</Badge>
            </dd>
            <dt>Ustuvorlik</dt>
            <dd>
              <Badge tone={statusBadge(PRIORITY, data.priority).tone}>
                {statusBadge(PRIORITY, data.priority).label}
              </Badge>
            </dd>
            <dt>Fuqaro</dt>
            <dd>
              {data.citizen_id ? (
                <Link className="link" href={`/citizens/${data.citizen_id}`}>
                  {data.citizen_name ?? data.citizen_id}
                </Link>
              ) : (
                "—"
              )}
            </dd>
            <dt>Mas'ul</dt>
            <dd>{data.responsible_user ?? "—"}</dd>
            <dt>Nazorat muddati</dt>
            <dd>{fmtDate(data.target_date)}</dd>
            {data.outcome && (
              <>
                <dt>Natija</dt>
                <dd>{data.outcome}</dd>
              </>
            )}
          </dl>
          {data.description && <p className="mt text-soft">{data.description}</p>}
          <div className="mt" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {["in_progress", "waiting", "resolved", "closed"].map((status) => (
              <button key={status} className="btn sm" disabled={busy} onClick={() => void changeStatus(status)}>
                {statusBadge(CASE_STATUS, status).label}
              </button>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <h3>Bog‘langan vazifalar</h3>
          </div>
          <div className="card-pad">
            <div className="timeline">
              {data.tasks.map((task) => {
                const ts = statusBadge(TASK_STATUS, task.status);
                return (
                  <div className="tl-item" key={task.id}>
                    <span className="tl-dot" />
                    <div className="tl-body">
                      <h4>{task.title}</h4>
                      <div className="when">
                        <Badge tone={ts.tone}>{ts.label}</Badge> · muddat {fmtDate(task.due_date)}
                      </div>
                    </div>
                  </div>
                );
              })}
              {data.tasks.length === 0 && (
                <p className="text-soft">Bu murojaatga bog‘langan vazifa yo‘q. AI assistent orqali vazifa loyihasini yaratishingiz mumkin.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
