"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { CASE_STATUS, PRIORITY, fmtDate, statusBadge } from "@/lib/format";

type CaseRow = {
  id: string;
  title: string;
  category: string;
  status: string;
  priority: string;
  citizen_name?: string | null;
  opened_at: string;
  task_count: number;
};

export default function CasesPage() {
  const [data, setData] = useState<Paged<CaseRow> | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    title: "",
    category: "Ijtimoiy yordam",
    description: "",
    priority: "normal",
    citizen_id: "",
    target_date: "",
  });
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    api
      .get<Paged<CaseRow>>(`/cases?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [status, q, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  async function submit() {
    setBusy(true);
    setFormError("");
    try {
      await api.post("/cases", {
        title: form.title,
        category: form.category,
        description: form.description,
        priority: form.priority,
        citizen_id: form.citizen_id || undefined,
        target_date: form.target_date || undefined,
      });
      setShowForm(false);
      setForm({ title: "", category: "Ijtimoiy yordam", description: "", priority: "normal", citizen_id: "", target_date: "" });
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Saqlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Murojaatlar"
        title="Fuqarolar murojaatlari"
        lede="Har bir murojaat holati, ustuvorligi va bog‘langan vazifalar bilan nazorat qilinadi."
        actions={
          <button className="btn primary" onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Bekor qilish" : "+ Yangi murojaat"}
          </button>
        }
      />
      {showForm && (
        <div className="card card-pad mb">
          <h3 className="mb">Yangi murojaat</h3>
          {formError && <div className="alert danger">⚠️ {formError}</div>}
          <div className="grid grid-2">
            <div className="field">
              <label>Nomi</label>
              <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Masalan: Moddiy yordam ajratish masalasi" />
            </div>
            <div className="field">
              <label>Toifa</label>
              <select className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {["Bandlik", "Ijtimoiy yordam", "Kredit va subsidiya", "Ta'lim", "Tibbiy yordam", "Uy-joy", "Hujjatlar", "Oila munosabatlari", "Boshqa"].map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Fuqaro ID (ixtiyoriy)</label>
              <input className="input mono" value={form.citizen_id} onChange={(e) => setForm({ ...form, citizen_id: e.target.value })} placeholder="F-00001" />
            </div>
            <div className="field">
              <label>Ustuvorlik</label>
              <select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="low">Past</option>
                <option value="normal">Oddiy</option>
                <option value="high">Yuqori</option>
                <option value="urgent">Shoshilinch</option>
              </select>
            </div>
            <div className="field">
              <label>Nazorat muddati</label>
              <input type="date" className="input" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} />
            </div>
          </div>
          <div className="field">
            <label>Tavsif</label>
            <textarea className="textarea" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <button className="btn primary" disabled={busy || form.title.trim().length < 3} onClick={submit}>
            {busy ? "Saqlanmoqda…" : "Murojaatni ro‘yxatga olish"}
          </button>
        </div>
      )}
      <div className="filters">
        <select className="select" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Holat — barchasi</option>
          <option value="open">Yangi</option>
          <option value="in_progress">Jarayonda</option>
          <option value="waiting">Kutilmoqda</option>
          <option value="resolved">Hal qilindi</option>
          <option value="closed">Yopilgan</option>
        </select>
        <input className="input" placeholder="Qidiruv…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      </div>
      {!data && !error && <Loading />}
      {data && (
        <div className="card">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Murojaat</th>
                  <th>Fuqaro</th>
                  <th>Toifa</th>
                  <th>Holat</th>
                  <th>Ustuvorlik</th>
                  <th>Ochildi</th>
                  <th>Vazifa</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => {
                  const st = statusBadge(CASE_STATUS, row.status);
                  const pr = statusBadge(PRIORITY, row.priority);
                  return (
                    <tr key={row.id}>
                      <td>
                        <Link className="rowlink" href={`/cases/${row.id}`}>
                          {row.title}
                        </Link>
                      </td>
                      <td>{row.citizen_name ?? "—"}</td>
                      <td>{row.category}</td>
                      <td>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </td>
                      <td>
                        <Badge tone={pr.tone}>{pr.label}</Badge>
                      </td>
                      <td className="nowrap">{fmtDate(row.opened_at)}</td>
                      <td>{row.task_count}</td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <Empty title="Murojaat topilmadi" />
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
