"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Inbox, Plus, Search } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { SearchSelect } from "@/components/ui/inputs";
import { api, type Paged } from "@/lib/api";
import { CASE_STATUS, PRIORITY, fmtDate, statusBadge } from "@/lib/format";

type CaseRow = {
  id: string; title: string; category: string; status: string; priority: string;
  citizen_name?: string | null; opened_at: string; task_count: number;
};
type Option = { value: string; label: string; sub?: string };

const CATEGORIES = ["Bandlik", "Ijtimoiy yordam", "Kredit va subsidiya", "Ta'lim", "Tibbiy yordam", "Uy-joy", "Hujjatlar", "Oila munosabatlari", "Boshqa"];
const PRIORITIES = [
  { value: "low", label: "Past" }, { value: "normal", label: "Oddiy" },
  { value: "high", label: "Yuqori" }, { value: "urgent", label: "Shoshilinch" },
];

function CasesInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const [data, setData] = useState<Paged<CaseRow> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(Number(searchParams.get("page") ?? "1"));
  const status = searchParams.get("status") ?? "";
  const q = searchParams.get("q") ?? "";

  const [formOpen, setFormOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [citizenOptions, setCitizenOptions] = useState<Option[]>([]);
  const [citizenLoading, setCitizenLoading] = useState(false);
  const [form, setForm] = useState({
    title: "", category: "Ijtimoiy yordam", description: "", priority: "normal",
    citizen_id: "", target_date: "",
  });

  const setParam = useCallback(
    (patch: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      router.replace(`/cases?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    api
      .get<Paged<CaseRow>>(`/cases?${params}`)
      .then((d) => { setData(d); setError(""); })
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
      .finally(() => setLoading(false));
  }, [status, q, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  function openForm() {
    setFormOpen(true);
    setFormError("");
    if (citizenOptions.length === 0 && !citizenLoading) {
      setCitizenLoading(true);
      api
        .get<{ items: Array<{ id: string; full_name: string; phone: string; address?: { address_label?: string } }> }>("/citizens/options")
        .then((d) => setCitizenOptions(d.items.map((c) => ({ value: c.id, label: c.full_name, sub: [c.phone, c.address?.address_label].filter(Boolean).join(" · ") }))))
        .catch(() => {})
        .finally(() => setCitizenLoading(false));
    }
  }

  async function submit() {
    if (form.title.trim().length < 3) { setFormError("Murojaat nomi kamida 3 belgi."); return; }
    setBusy(true);
    setFormError("");
    try {
      await api.post("/cases", {
        title: form.title.trim(),
        category: form.category,
        description: form.description,
        priority: form.priority,
        citizen_id: form.citizen_id || undefined,
        target_date: form.target_date || undefined,
      });
      toast.show("success", "Murojaat ro'yxatga olindi.");
      setFormOpen(false);
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
        lede="Har bir murojaat holati, ustuvorligi va bog'langan vazifalar bilan nazorat qilinadi."
        actions={<button className="btn primary" onClick={openForm}><Plus size={16} /> Yangi murojaat</button>}
      />
      <div className="toolbar">
        <select className="select" value={status} onChange={(e) => { setParam({ status: e.target.value || null, page: null }); }} aria-label="Holat filtri">
          <option value="">Holat — barchasi</option>
          {Object.entries(CASE_STATUS).map(([key, val]) => <option key={key} value={key}>{val.label}</option>)}
        </select>
        <div style={{ position: "relative", flex: 1, minWidth: 200, maxWidth: 340 }}>
          <Search size={15} style={{ position: "absolute", left: 12, top: 13, color: "var(--color-text-muted)" }} />
          <input className="input" style={{ paddingLeft: 36 }} placeholder="Qidiruv…" value={q}
            onChange={(e) => setParam({ q: e.target.value || null, page: null })} aria-label="Qidiruv" />
        </div>
      </div>
      {loading && !data && <SkeletonList rows={6} />}
      {data && !loading && (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Murojaat</th><th>Fuqaro</th><th>Toifa</th><th>Holat</th><th>Ustuvorlik</th><th>Ochildi</th><th className="num">Vazifa</th></tr>
              </thead>
              <tbody>
                {data.items.map((row) => {
                  const st = statusBadge(CASE_STATUS, row.status);
                  const pr = statusBadge(PRIORITY, row.priority);
                  return (
                    <tr key={row.id}>
                      <td><Link className="rowlink" href={`/cases/${row.id}`}>{row.title}</Link></td>
                      <td>{row.citizen_name ?? "—"}</td>
                      <td>{row.category}</td>
                      <td><Badge tone={st.tone}>{st.label}</Badge></td>
                      <td><Badge tone={pr.tone}>{pr.label}</Badge></td>
                      <td className="nowrap">{fmtDate(row.opened_at)}</td>
                      <td className="num">{row.task_count}</td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr><td colSpan={7}><Empty title="Murojaat topilmadi" icon={<Inbox size={17} />} /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          {data.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{data.meta.total} ta murojaat · {data.meta.page}/{data.meta.total_pages}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setParam({ page: String(page - 1) })}>‹ Oldingi</button>
                <button className="btn sm" disabled={page >= data.meta.total_pages} onClick={() => setParam({ page: String(page + 1) })}>Keyingi ›</button>
              </span>
            </div>
          )}
        </>
      )}

      <Drawer
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="Yangi murojaat"
        footer={
          <>
            <button className="btn ghost" onClick={() => setFormOpen(false)} disabled={busy}>Bekor qilish</button>
            <button className="btn primary" onClick={() => void submit()} disabled={busy || form.title.trim().length < 3}>
              {busy ? "Saqlanmoqda…" : "Murojaatni ro'yxatga olish"}
            </button>
          </>
        }
      >
        {formError && <div className="alert danger" role="alert">{formError}</div>}
        <Field label="Nomi" required htmlFor="cf-title">
          <input id="cf-title" className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Masalan: Moddiy yordam ajratish masalasi" />
        </Field>
        <div className="grid grid-2">
          <Field label="Toifa" htmlFor="cf-cat">
            <select id="cf-cat" className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Ustuvorlik" htmlFor="cf-pri">
            <select id="cf-pri" className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Fuqaro" htmlFor="cf-citizen" hint="Yozib qidiring — F.I.Sh. yoki telefon">
          <SearchSelect
            id="cf-citizen"
            value={form.citizen_id}
            onChange={(v) => setForm({ ...form, citizen_id: v })}
            options={citizenOptions}
            placeholder="Fuqaro tanlanmagan"
            searchPlaceholder="F.I.Sh. yoki telefon…"
            loading={citizenLoading}
            clearable
          />
        </Field>
        <Field label="Nazorat muddati" htmlFor="cf-date">
          <input id="cf-date" type="date" className="input" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} />
        </Field>
        <Field label="Tavsif" htmlFor="cf-desc">
          <textarea id="cf-desc" className="textarea" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
      </Drawer>
    </>
  );
}

export default function CasesPage() {
  return (
    <Suspense fallback={<SkeletonList rows={6} />}>
      <CasesInner />
    </Suspense>
  );
}
