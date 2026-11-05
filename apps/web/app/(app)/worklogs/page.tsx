"use client";

import { useCallback, useEffect, useState } from "react";
import { History, Plus } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { SearchSelect } from "@/components/ui/inputs";
import { api, type Paged } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type LogRow = {
  id: string; type: string; title: string; description: string; occurred_at: string;
  citizen_id?: string | null; source: string; approval_status: string;
};
type Option = { value: string; label: string; sub?: string };

const TYPES = ["uchrashuv", "telefon", "tavsiya", "hujjat", "bajarilgan ish", "natija", "vazifa", "murojaat"];
const TONES: Record<string, string> = {
  uchrashuv: "brand", telefon: "info", tavsiya: "muted", hujjat: "warn",
  "bajarilgan ish": "ok", natija: "ok", vazifa: "muted", murojaat: "info",
};
const LABELS: Record<string, string> = {
  uchrashuv: "Uchrashuv", telefon: "Telefon", tavsiya: "Tavsiya", hujjat: "Hujjat",
  "bajarilgan ish": "Bajarilgan ish", natija: "Natija", vazifa: "Vazifa", murojaat: "Murojaat",
};

function WorklogsInner() {
  const toast = useToast();
  const [data, setData] = useState<Paged<LogRow> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [citizenOptions, setCitizenOptions] = useState<Option[]>([]);
  const [form, setForm] = useState({
    citizen_id: "", type: "uchrashuv", title: "", description: "", occurred_at: "",
  });

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    if (type) params.set("type", type);
    api
      .get<Paged<LogRow>>(`/work-logs?${params}`)
      .then((d) => { setData(d); setError(""); })
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
      .finally(() => setLoading(false));
  }, [type, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  function openCreate() {
    setCreateOpen(true);
    setFormError("");
    if (citizenOptions.length === 0) {
      api
        .get<{ items: Array<{ id: string; full_name: string; address?: { address_label?: string } }> }>("/citizens/options")
        .then((d) => setCitizenOptions(d.items.map((c) => ({ value: c.id, label: c.full_name, sub: c.address?.address_label }))))
        .catch(() => {});
    }
  }

  async function create() {
    if (form.title.trim().length < 3) { setFormError("Sarlavha kamida 3 belgi."); return; }
    setBusy(true);
    setFormError("");
    try {
      await api.post("/work-logs", {
        citizen_id: form.citizen_id || null,
        type: form.type,
        title: form.title.trim(),
        description: form.description,
        occurred_at: form.occurred_at ? new Date(form.occurred_at).toISOString() : null,
      });
      toast.show("success", "Ish yozuvi qo'shildi.");
      setCreateOpen(false);
      setForm({ citizen_id: "", type: "uchrashuv", title: "", description: "", occurred_at: "" });
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
        kicker="Ish yozuvlari"
        title="Aholi bilan ish tarixi"
        lede="Uchrashuv, telefon aloqa, tavsiya va bajarilgan ishlar yagona jurnalda saqlanadi."
        actions={<button className="btn primary" onClick={openCreate}><Plus size={16} /> Yangi yozuv</button>}
      />
      <div className="toolbar">
        <select className="select" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Tur filtri">
          <option value="">Tur — barchasi</option>
          {TYPES.map((item) => <option key={item} value={item}>{LABELS[item] ?? item}</option>)}
        </select>
      </div>
      {loading && !data && <SkeletonList rows={6} />}
      {!loading && error && <ErrorState note={error} onRetry={load} />}
      {data && !loading && !error && (
        <div className="card">
          <div className="card-pad">
            <div className="timeline">
              {data.items.map((log) => (
                <div className="tl-item" key={log.id}>
                  <span className="tl-dot" />
                  <div className="tl-body">
                    <h4 style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      {log.title} <Badge tone={TONES[log.type] ?? "muted"}>{LABELS[log.type] ?? log.type}</Badge>
                    </h4>
                    <div className="when">
                      {fmtDateTime(log.occurred_at)} · {log.source === "seed" ? "demo yozuv" : log.source}
                      {log.approval_status && log.approval_status !== "confirmed" ? ` · ${log.approval_status}` : ""}
                    </div>
                    {log.description && <div className="desc">{log.description}</div>}
                  </div>
                </div>
              ))}
              {data.items.length === 0 && <Empty title="Yozuv topilmadi" icon={<History size={17} />} />}
            </div>
          </div>
          {data.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{data.meta.total} ta yozuv · {data.meta.page}/{data.meta.total_pages}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Oldingi</button>
                <button className="btn sm" disabled={page >= data.meta.total_pages} onClick={() => setPage(page + 1)}>Keyingi ›</button>
              </span>
            </div>
          )}
        </div>
      )}

      <Drawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Yangi ish yozuvi"
        footer={
          <>
            <button className="btn ghost" onClick={() => setCreateOpen(false)} disabled={busy}>Bekor qilish</button>
            <button className="btn primary" onClick={() => void create()} disabled={busy || form.title.trim().length < 3}>
              Yozuvni qo'shish
            </button>
          </>
        }
      >
        {formError && <div className="alert danger" role="alert">{formError}</div>}
        <Field label="Fuqaro (ixtiyoriy)" htmlFor="wl-citizen">
          <SearchSelect id="wl-citizen" value={form.citizen_id} onChange={(v) => setForm({ ...form, citizen_id: v })}
            options={citizenOptions} placeholder="Tanlanmagan" searchPlaceholder="F.I.Sh. yozing…" clearable />
        </Field>
        <div className="grid grid-2">
          <Field label="Turi" htmlFor="wl-type">
            <select id="wl-type" className="select" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              {TYPES.map((t) => <option key={t} value={t}>{LABELS[t]}</option>)}
            </select>
          </Field>
          <Field label="Sana va vaqt" htmlFor="wl-date" hint="Bo'sh — hozirgi vaqt">
            <input id="wl-date" type="datetime-local" className="input" value={form.occurred_at} onChange={(e) => setForm({ ...form, occurred_at: e.target.value })} />
          </Field>
        </div>
        <Field label="Sarlavha" required htmlFor="wl-title">
          <input id="wl-title" className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <Field label="Tavsif" htmlFor="wl-desc">
          <textarea id="wl-desc" className="textarea" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
      </Drawer>
    </>
  );
}

export default function WorklogsPage() {
  return <WorklogsInner />;
}
