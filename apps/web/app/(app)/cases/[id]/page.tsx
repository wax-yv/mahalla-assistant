"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, ClipboardList } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { ConfirmDialog, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import { CASE_STATUS, PRIORITY, TASK_STATUS, fmtDate, statusBadge } from "@/lib/format";

type CaseDetail = {
  id: string; title: string; category: string; description: string; status: string; priority: string;
  citizen_id?: string | null; citizen_name?: string | null; responsible_user?: string | null;
  opened_at: string; target_date?: string | null; outcome?: string; closed_at?: string | null;
  tasks: { id: string; title: string; status: string; priority: string; due_date: string | null }[];
};

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const toast = useToast();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setData(null);
    api
      .get<CaseDetail>(`/cases/${params.id}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [params.id]);

  useEffect(() => { void load(); }, [load]);

  async function changeStatus(status: string) {
    setBusy(true);
    try {
      await api.patch(`/cases/${params.id}`, { status });
      toast.show("success", `Holat yangilandi: ${statusBadge(CASE_STATUS, status).label}`);
      load();
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Amal bajarilmadi.");
    } finally {
      setBusy(false);
      setPending(null);
    }
  }

  if (error && !data) return <ErrorState note={error} onRetry={load} />;
  if (!data) return <SkeletonList rows={4} />;

  const st = statusBadge(CASE_STATUS, data.status);

  return (
    <>
      <nav aria-label="Breadcrumb" className="text-faint" style={{ fontSize: 13, marginBottom: 10, display: "flex", gap: 6, alignItems: "center" }}>
        <Link className="link" href="/cases">Murojaatlar</Link>
        <ChevronRight size={13} />
        <span style={{ color: "var(--color-text)" }}>{data.title}</span>
      </nav>
      <PageHead
        kicker={`Murojaat · ${data.id}`}
        title={data.title}
        lede={`${data.category} · ${fmtDate(data.opened_at)} da ochildi`}
        actions={<Link className="btn ghost" href="/cases">← Murojaatlar</Link>}
      />
      <div className="split s2r">
        <div className="card card-pad">
          <h3 className="mb">Mazmuni</h3>
          <dl className="kv">
            <dt>Holat</dt><dd><Badge tone={st.tone}>{st.label}</Badge></dd>
            <dt>Ustuvorlik</dt>
            <dd><Badge tone={statusBadge(PRIORITY, data.priority).tone}>{statusBadge(PRIORITY, data.priority).label}</Badge></dd>
            <dt>Fuqaro</dt>
            <dd>
              {data.citizen_id ? (
                <Link className="link" href={`/citizens/${data.citizen_id}`}>{data.citizen_name ?? data.citizen_id}</Link>
              ) : "—"}
            </dd>
            <dt>Mas'ul</dt><dd>{data.responsible_user ?? "—"}</dd>
            <dt>Nazorat muddati</dt><dd>{fmtDate(data.target_date)}</dd>
            {data.outcome && (<><dt>Natija</dt><dd>{data.outcome}</dd></>)}
          </dl>
          {data.description && <p className="mt text-soft" style={{ fontSize: 14 }}>{data.description}</p>}
          <div className="mt" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {["in_progress", "waiting", "resolved", "closed"].map((status) => (
              <button key={status} className="btn sm" disabled={busy} onClick={() => setPending(status)}>
                {statusBadge(CASE_STATUS, status).label}
              </button>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3>Bog'langan vazifalar</h3></div>
          <div className="card-pad">
            <div className="timeline">
              {data.tasks.map((task) => {
                const ts = statusBadge(TASK_STATUS, task.status);
                return (
                  <div className="tl-item" key={task.id}>
                    <span className="tl-dot" />
                    <div className="tl-body">
                      <h4>{task.title}</h4>
                      <div className="when"><Badge tone={ts.tone}>{ts.label}</Badge> · muddat {fmtDate(task.due_date)}</div>
                    </div>
                  </div>
                );
              })}
              {data.tasks.length === 0 && (
                <Empty title="Bog'langan vazifa yo'q" note="AI assistent orqali vazifa loyihasini yaratishingiz mumkin." icon={<ClipboardList size={17} />} />
              )}
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(pending)}
        onClose={() => setPending(null)}
        onConfirm={() => pending && void changeStatus(pending)}
        title="Murojaat holatini o'zgartirish"
        message={`Holat «${pending ? statusBadge(CASE_STATUS, pending).label : ""}» ga o'zgartiriladi. Davom etamizmi?`}
        confirmLabel="O'zgartirish"
        danger={pending === "closed" || pending === "cancelled"}
        busy={busy}
      />
    </>
  );
}
