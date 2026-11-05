"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, Inbox, Phone, Trash2, UserRound } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { ConfirmDialog, Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import { CASE_STATUS, TASK_STATUS, fmtDate, fmtDateTime, statusBadge } from "@/lib/format";
import { CitizenForm, type CitizenFormData } from "@/components/citizens/CitizenForm";

type Detail = {
  id: string; full_name: string; gender: string; birth_date: string | null; age: number | null;
  version: number;
  phone: string; family_role: string; education: string; employment_status: string; profession: string;
  social_status: string; needs: string[]; notes: string; data_source: string; last_verified_at: string | null;
  address: { address_label?: string | null; mahalla?: string | null } | null;
  family: { id: string; family_head_name: string; family_type: string; social_status: string; member_count: number; address?: { address_label?: string } | null } | null;
  data_quality: { score: number; incomplete: number; missing_fields: string[] };
  cases: { id: string; title: string; status: string; priority: string; opened_at: string }[];
  tasks: { id: string; title: string; status: string; due_date: string | null }[];
  work_logs: { id: string; title: string; type: string; occurred_at: string; description: string }[];
  timeline: { id: string; kind: string; title: string; description?: string; occurred_at: string }[];
};

export default function CitizenDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setData(null);
    api
      .get<Detail>(`/citizens/${params.id}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [params.id]);

  useEffect(() => { void load(); }, [load]);

  function toForm(d: Detail): Partial<CitizenFormData> {
    return {
      id: d.id, full_name: d.full_name, gender: d.gender as "Erkak" | "Ayol",
      version: d.version,
      birth_date: d.birth_date ?? "", phone: d.phone ?? "", family_id: d.family?.id ?? "",
      family_role: d.family_role, education: d.education, employment_status: d.employment_status,
      profession: d.profession, social_status: d.social_status, needs: (d.needs ?? []).join(", "),
      notes: d.notes ?? "",
    };
  }

  async function archive() {
    setBusy(true);
    try {
      await api.del(`/citizens/${params.id}`);
      toast.show("success", "Fuqaro arxivlandi.");
      router.push("/citizens");
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Amal bajarilmadi.");
      setBusy(false);
    }
  }

  if (error) return <ErrorState note={error} onRetry={load} />;
  if (!data) return <SkeletonList rows={5} />;

  const st = data.social_status && data.social_status !== "Yo‘q" && data.social_status !== "—";

  return (
    <>
      <nav aria-label="Yo‘l" className="crumbs">
        <Link className="link" href="/citizens">Fuqarolar</Link>
        <ChevronRight size={13} aria-hidden="true" />
        <span className="text-strong">{data.full_name}</span>
      </nav>
      <PageHead
        kicker={`Fuqaro · ${data.id}`}
        title={data.full_name}
        lede={`${data.address?.mahalla ?? ""}${data.address?.address_label ? ` · ${data.address.address_label}` : ""}`}
        actions={
          <>
            <Link className="btn ghost" href="/citizens">← Ro‘yxat</Link>
            <button className="btn" onClick={() => setEditOpen(true)}>
              <UserRound size={15} /> Tahrirlash
            </button>
            <button className="btn danger" onClick={() => setArchiveOpen(true)}>
              <Trash2 size={15} /> Arxivlash
            </button>
          </>
        }
      />

      <div className="split s2r mb">
        <div className="card card-pad">
          <h3 className="mb">Shaxsiy ma’lumotlar</h3>
          <dl className="kv">
            <dt>Jinsi</dt><dd>{data.gender}</dd>
            <dt>Tug‘ilgan sana</dt><dd>{fmtDate(data.birth_date)}{data.age !== null ? ` · ${data.age} yosh` : ""}</dd>
            <dt>Telefon</dt>
            <dd>
              {data.phone ? (
                <a className="rowlink" href={`tel:${data.phone.replace(/\s/g, "")}`}>
                  <Phone size={13} className="ico-inline-sm" />
                  {data.phone}
                </a>
              ) : <span className="text-faint">—</span>}
            </dd>
            <dt>Manzil</dt><dd>{data.address?.address_label ?? "—"}</dd>
            <dt>Oiladagi o‘rni</dt><dd>{data.family_role}</dd>
            <dt>Ma’lumoti</dt><dd>{data.education}</dd>
            <dt>Bandlik</dt><dd>{data.employment_status}{data.profession && data.profession !== "Yo‘q" && data.profession !== "—" ? ` · ${data.profession}` : ""}</dd>
            <dt>Ijtimoiy holat</dt>
            <dd>{st ? <Badge tone="warn">{data.social_status}</Badge> : "—"}</dd>
            {(data.needs ?? []).length > 0 && (
              <>
                <dt>Ehtiyoji</dt>
                <dd className="chip-row">
                  {data.needs.map((need) => <Badge key={need} tone="info">{need}</Badge>)}
                </dd>
              </>
            )}
            <dt>Manba</dt><dd className="mono fs-12_5">{data.data_source || "—"}</dd>
            <dt>Oxirgi tekshiruv</dt><dd>{fmtDateTime(data.last_verified_at)}</dd>
            {data.notes && (<><dt>Izoh</dt><dd>{data.notes}</dd></>)}
          </dl>
        </div>

        <div>
          {data.family && (
            <div className="card card-pad mb">
              <div className="card-head card-head-flush">
                <h3>Oila</h3>
                <Link className="link" href={`/families?focus=${data.family.id}`}>Oila sahifasi →</Link>
              </div>
              <dl className="kv">
                <dt>Oila</dt><dd className="mono fs-12_5">{data.family.id}</dd>
                <dt>Boshlig‘i</dt><dd>{data.family.family_head_name || "—"}</dd>
                <dt>Turi</dt><dd>{data.family.family_type}</dd>
                <dt>A’zolar</dt><dd className="num">{data.family.member_count} nafar</dd>
                <dt>Manzil</dt><dd>{data.family.address?.address_label ?? "—"}</dd>
              </dl>
            </div>
          )}
          <div className="card card-pad">
            <h3 className="mb">Ma’lumot sifati</h3>
            <div className="progress mb"><i style={{ width: `${data.data_quality.score}%` }} /></div>
            <p className="text-soft fs-13_5">
              Sifat: <b>{data.data_quality.score}%</b>
              {data.data_quality.missing_fields.length > 0 && <> · yetishmaydi: {data.data_quality.missing_fields.join(", ")}</>}
            </p>
          </div>
        </div>
      </div>

      <div className="split s2">
        <div className="card">
          <div className="card-head"><h3>Murojaatlar va vazifalar</h3></div>
          <div className="table-wrap flush">
            <table className="data">
              <thead><tr><th>Nomi</th><th>Tur</th><th>Holat</th></tr></thead>
              <tbody>
                {data.cases.map((row) => {
                  const s = statusBadge(CASE_STATUS, row.status);
                  return (
                    <tr key={row.id}>
                      <td data-label="Nomi"><Link className="rowlink" href={`/cases/${row.id}`}>{row.title}</Link></td>
                      <td className="text-faint nowrap" data-label="Tur">Murojaat · {fmtDate(row.opened_at)}</td>
                      <td data-label="Holat"><Badge tone={s.tone}>{s.label}</Badge></td>
                    </tr>
                  );
                })}
                {data.tasks.map((row) => {
                  const s = statusBadge(TASK_STATUS, row.status);
                  return (
                    <tr key={row.id}>
                      <td data-label="Nomi">{row.title}</td>
                      <td className="text-faint nowrap" data-label="Tur">Vazifa · {fmtDate(row.due_date)}</td>
                      <td data-label="Holat"><Badge tone={s.tone}>{s.label}</Badge></td>
                    </tr>
                  );
                })}
                {data.cases.length === 0 && data.tasks.length === 0 && (
                  <tr><td colSpan={3}><Empty title="Murojaat va vazifa yo‘q" note="Bu fuqaro uchun hali ish ochilmagan." art="inbox" /></td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3>Harakatlar tarixi</h3></div>
          <div className="card-pad">
            <div className="timeline">
              {data.timeline.slice(0, 12).map((item) => (
                <div className="tl-item" key={item.id}>
                  <span className="tl-dot" aria-hidden="true" />
                  <div className="tl-body">
                    <h4>{item.title}</h4>
                    <div className="when">{item.kind} · {fmtDateTime(item.occurred_at)}</div>
                    {item.description && <div className="desc">{item.description}</div>}
                  </div>
                </div>
              ))}
              {data.timeline.length === 0 && <Empty title="Tarix bo‘sh" note="Harakatlar tarixi hali shakllanmagan." art="document" />}
            </div>
          </div>
        </div>
      </div>

      <Drawer open={editOpen} onClose={() => setEditOpen(false)} title="Fuqaroni tahrirlash" wide>
        <CitizenForm open={editOpen} onClose={() => setEditOpen(false)} initial={toForm(data)} onSaved={() => load()} />
      </Drawer>
      <ConfirmDialog
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        onConfirm={() => void archive()}
        title="Fuqaroni arxivlash"
        message={`«${data.full_name}» arxivlanadi: ro‘yxatlarda ko‘rinmaydi, ma’lumotlari saqlanadi. Davom etamizmi?`}
        confirmLabel="Arxivlash"
        busy={busy}
      />
    </>
  );
}
