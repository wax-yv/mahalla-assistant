"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Plus } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Pager } from "@/components/ui";
import { Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field, SearchSelect } from "@/components/ui/inputs";
import { api, type Paged } from "@/lib/api";
import { PRIORITY, TASK_STATUS, fmtDate, statusBadge } from "@/lib/format";

type TaskRow = {
  id: string; title: string; description: string; status: string; priority: string; category: string;
  due_date: string | null; citizen_id?: string | null; citizen_name?: string | null; assignee?: string | null;
  is_overdue: boolean; evidence_note?: string | null;
};
type Option = { value: string; label: string; sub?: string };

const CATEGORIES = ["Bandlik", "Ijtimoiy yordam", "Kredit va subsidiya", "Ta’lim", "Tibbiy yordam", "Uy-joy", "Hujjatlar", "Oila munosabatlari", "Boshqa"];
const PRIORITIES = [
  { value: "low", label: "Past" }, { value: "normal", label: "Oddiy" },
  { value: "high", label: "Yuqori" }, { value: "urgent", label: "Shoshilinch" },
];

function TasksInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const [data, setData] = useState<Paged<TaskRow> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const page = Number(searchParams.get("page") ?? "1");
  const status = searchParams.get("status") ?? "";
  const timeframe = searchParams.get("timeframe") ?? "";

  const [completing, setCompleting] = useState<TaskRow | null>(null);
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState("");
  const [citizenOptions, setCitizenOptions] = useState<Option[]>([]);
  const [form, setForm] = useState({
    title: "", description: "", category: "Boshqa", priority: "normal", due_date: "", citizen_id: "", assignee: "",
  });

  const setParam = useCallback(
    (patch: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      router.replace(`/tasks?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) params.set("status", status);
    if (timeframe) params.set("timeframe", timeframe);
    api
      .get<Paged<TaskRow>>(`/tasks?${params}`)
      .then((d) => { setData(d); setError(""); })
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
      .finally(() => setLoading(false));
  }, [status, timeframe, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  async function complete() {
    if (!completing) return;
    setBusy(true);
    try {
      await api.post(`/tasks/${completing.id}/complete`, { evidence_note: evidence });
      toast.show("success", "Vazifa bajarilgan deb belgilandi.");
      setCompleting(null);
      setEvidence("");
      load();
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Amal bajarilmadi.");
    } finally {
      setBusy(false);
    }
  }

  function openCreate() {
    setCreateOpen(true);
    setCreateError("");
    if (citizenOptions.length === 0) {
      api
        .get<{ items: Array<{ id: string; full_name: string; address?: { address_label?: string } }> }>("/citizens/options")
        .then((d) => setCitizenOptions(d.items.map((c) => ({ value: c.id, label: c.full_name, sub: c.address?.address_label }))))
        .catch(() => {});
    }
  }

  async function create() {
    if (form.title.trim().length < 3) { setCreateError("Vazifa nomi kamida 3 belgi bo‘lishi kerak."); return; }
    setBusy(true);
    setCreateError("");
    try {
      await api.post("/tasks", {
        title: form.title.trim(),
        description: form.description,
        category: form.category,
        priority: form.priority,
        due_date: form.due_date || null,
        citizen_id: form.citizen_id || undefined,
        assignee: form.assignee || undefined,
      });
      toast.show("success", "Yangi vazifa yaratildi.");
      setCreateOpen(false);
      setForm({ title: "", description: "", category: "Boshqa", priority: "normal", due_date: "", citizen_id: "", assignee: "" });
      load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Saqlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Vazifalar"
        title="Ish rejasi va nazorat"
        lede="Muddati va ustuvorligi bo‘yicha saralangan vazifalar. Bajarilgan vazifa ish yozuvi bilan tasdiqlanadi."
        actions={<button className="btn primary" onClick={openCreate}><Plus size={16} /> Yangi vazifa</button>}
      />
      <div className="toolbar">
        <select className="select" value={status} onChange={(e) => setParam({ status: e.target.value || null, page: null })} aria-label="Holat filtri">
          <option value="">Holat — barchasi</option>
          <option value="new">Yangi</option>
          <option value="in_progress">Jarayonda</option>
          <option value="waiting">Kutilmoqda</option>
          <option value="completed">Bajarildi</option>
        </select>
        <select className="select" value={timeframe} onChange={(e) => setParam({ timeframe: e.target.value || null, page: null })} aria-label="Muddat filtri">
          <option value="">Muddat — barchasi</option>
          <option value="overdue">Muddati o‘tgan</option>
          <option value="today">Bugun</option>
          <option value="week">Shu hafta</option>
        </select>
      </div>
      {loading && !data && <SkeletonList rows={6} />}
      {!loading && error && <ErrorState note={error} onRetry={load} />}
      {data && !loading && !error && (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Vazifa</th><th>Fuqaro</th><th>Muddat</th><th>Holat</th><th>Ustuvorlik</th><th aria-label="Amallar" /></tr>
              </thead>
              <tbody>
                {data.items.map((task) => {
                  const st = statusBadge(TASK_STATUS, task.status);
                  const pr = statusBadge(PRIORITY, task.priority);
                  return (
                    <tr key={task.id}>
                      <td data-label="Vazifa">
                        <b className="fw-600">{task.title}</b>
                        {task.description && <div className="cell-sub">{task.description.slice(0, 90)}</div>}
                      </td>
                      <td data-label="Fuqaro">{task.citizen_name ?? "—"}</td>
                      <td className="nowrap" data-label="Muddat">
                        {fmtDate(task.due_date)}
                        {task.is_overdue && <div className="mt-xs"><Badge tone="danger">Kechikkan</Badge></div>}
                      </td>
                      <td data-label="Holat"><Badge tone={st.tone}>{st.label}</Badge></td>
                      <td data-label="Ustuvorlik"><Badge tone={pr.tone}>{pr.label}</Badge></td>
                      <td data-label="Amallar">
                        {!["completed", "cancelled"].includes(task.status) && (
                          <button className="btn sm" onClick={() => setCompleting(task)}>Bajarildi</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr><td colSpan={6}><Empty title="Vazifa topilmadi" note="Filtrni o‘zgartiring yoki yangi vazifa yarating." art="task" /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager meta={data.meta} onPage={(p) => setParam({ page: String(p) })} />
        </>
      )}

      <Drawer
        open={Boolean(completing)}
        onClose={() => setCompleting(null)}
        title="Vazifani bajarilgan deb belgilash"
        footer={
          <>
            <button className="btn ghost" onClick={() => setCompleting(null)} disabled={busy}>Bekor qilish</button>
            <button className="btn primary" onClick={() => void complete()} disabled={busy || evidence.trim().length < 3}>
              Bajarilgan deb tasdiqlash
            </button>
          </>
        }
      >
        {completing && (
          <>
            <p className="fw-600 mb-sm">{completing.title}</p>
            <p className="text-soft fs-13 mb">
              Tasdiqlash bilan ish yozuvi avtomatik yaratiladi. Dalil izohi majburiy.
            </p>
            <Field label="Dalil izohi" required htmlFor="ev-note" hint="Nima qilindi, natija qanday tasdiqlandi">
              <textarea id="ev-note" className="textarea" rows={3} value={evidence} onChange={(e) => setEvidence(e.target.value)} />
            </Field>
          </>
        )}
      </Drawer>

      <Drawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Yangi vazifa"
        footer={
          <>
            <button className="btn ghost" onClick={() => setCreateOpen(false)} disabled={busy}>Bekor qilish</button>
            <button className="btn primary" onClick={() => void create()} disabled={busy || form.title.trim().length < 3}>
              Vazifani yaratish
            </button>
          </>
        }
      >
        {createError && <div className="alert danger" role="alert">{createError}</div>}
        <Field label="Nomi" required htmlFor="tf-title">
          <input id="tf-title" className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <div className="grid grid-2">
          <Field label="Toifa" htmlFor="tf-cat">
            <select id="tf-cat" className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Ustuvorlik" htmlFor="tf-pri">
            <select id="tf-pri" className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Muddat" htmlFor="tf-due">
          <input id="tf-due" type="date" className="input" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
        </Field>
        <Field label="Fuqaro (ixtiyoriy)" htmlFor="tf-citizen">
          <SearchSelect id="tf-citizen" value={form.citizen_id} onChange={(v) => setForm({ ...form, citizen_id: v })}
            options={citizenOptions} placeholder="Tanlanmagan" searchPlaceholder="F.I.Sh. yozing…" clearable />
        </Field>
        <Field label="Mas’ul (ixtiyoriy)" htmlFor="tf-assignee">
          <input id="tf-assignee" className="input" value={form.assignee} onChange={(e) => setForm({ ...form, assignee: e.target.value })} />
        </Field>
        <Field label="Tavsif" htmlFor="tf-desc">
          <textarea id="tf-desc" className="textarea" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
      </Drawer>
    </>
  );
}

export default function TasksPage() {
  return (
    <Suspense fallback={<SkeletonList rows={6} />}>
      <TasksInner />
    </Suspense>
  );
}
