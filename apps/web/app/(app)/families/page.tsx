"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Home, Plus, Search } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { api, type Paged } from "@/lib/api";

type Mahalla = { id: string; name: string; streets: number; houses: number; citizens: number };
type Street = { id: string; name: string; houses: number; families: number; citizens: number };
type House = { id: string; house_number: string; address_label: string; street: string; families: number; citizens: number };
type Family = {
  id: string; family_type: string; social_status: string; member_count: number;
  head_name?: string | null; address?: { address_label?: string | null } | null;
};

const FAMILIES_TAB = "Oilalar";
const HOUSES_TAB = "Uylar";
const STREETS_TAB = "Ko'chalar";

function FamiliesInner() {
  const searchParams = useSearchParams();
  const toast = useToast();
  const [tab, setTab] = useState<"streets" | "houses" | "families">(STREETS_TAB as never);
  const [mahallas, setMahallas] = useState<Mahalla[]>([]);
  const [streets, setStreets] = useState<Street[]>([]);
  const [houses, setHouses] = useState<Paged<House> | null>(null);
  const [families, setFamilies] = useState<Paged<Family> | null>(null);
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api.get<{ items: Mahalla[] }>("/mahallas").then((d) => setMahallas(d.items)).catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page) });
    if (q) params.set("q", q);
    if (tab === "streets") {
      api.get<{ items: Street[] }>("/streets")
        .then((d) => { setStreets(d.items); setError(""); })
        .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
        .finally(() => setLoading(false));
    } else if (tab === "houses") {
      params.set("page_size", "24");
      api.get<Paged<House>>(`/houses?${params}`)
        .then((d) => { setHouses(d); setError(""); })
        .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
        .finally(() => setLoading(false));
    } else {
      api.get<Paged<Family>>(`/families?${params}`)
        .then((d) => { setFamilies(d); setError(""); })
        .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
        .finally(() => setLoading(false));
    }
  }, [tab, q, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const mahalla = mahallas[0];
  const focusId = searchParams.get("focus");

  useEffect(() => {
    if (focusId) setDetailId(focusId);
  }, [focusId]);

  useEffect(() => {
    if (!detailId) { setDetail(null); return; }
    setDetailLoading(true);
    api
      .get<Record<string, unknown>>(`/families/${detailId}`)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [detailId]);

  const TABS: Array<{ key: "streets" | "houses" | "families"; label: string }> = [
    { key: "streets", label: STREETS_TAB },
    { key: "houses", label: HOUSES_TAB },
    { key: "families", label: FAMILIES_TAB },
  ];
  const TAB_DESC: Record<string, string> = {
    streets: "Mahalla ko'chalari va ulardagi uy, oila, fuqarolar soni.",
    houses: "Uylar ro'yxati — manzil, ko'cha, oilalar va fuqarolar soni.",
    families: "Oilalar ro'yxati — boshliq, tarkib, tur va ijtimoiy holat.",
  };

  return (
    <>
      <PageHead
        kicker="Manzillar ierarxiyasi"
        title="Oilalar va manzillar"
        lede={mahalla ? `${mahalla.name} — ${mahalla.streets} ko'cha, ${mahalla.houses} uy, ${mahalla.citizens} fuqaro.` : "Mahalla, ko'cha, uy va oilalar ierarxiyasi."}
        actions={
          <button className="btn primary" onClick={() => setFormOpen(true)}>
            <Plus size={16} /> Yangi oila
          </button>
        }
      />
      {error && <ErrorState note={error} onRetry={load} />}
      <div className="tabbar" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? "active" : ""}
            onClick={() => { setTab(t.key); setQ(""); setPage(1); }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="text-faint" style={{ fontSize: 13, marginBottom: 12 }}>{TAB_DESC[tab]}</p>

      {tab !== "streets" && (
        <div className="toolbar">
          <div style={{ position: "relative", flex: 1, maxWidth: 360 }}>
            <Search size={15} style={{ position: "absolute", left: 12, top: 13, color: "var(--color-text-muted)" }} />
            <input
              className="input"
              style={{ paddingLeft: 36 }}
              placeholder={tab === "houses" ? "Uy raqami yoki ko'cha…" : "Oila ID, boshliq yoki manzil…"}
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              aria-label="Qidiruv"
            />
          </div>
        </div>
      )}

      {loading && <SkeletonList rows={5} />}

      {!loading && tab === "streets" && (
        <div className="card">
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th>Ko'cha</th><th className="num">Uylar</th><th className="num">Oilalar</th><th className="num">Fuqarolar</th></tr></thead>
              <tbody>
                {streets.map((street) => (
                  <tr key={street.id}>
                    <td><b>{street.name}</b></td>
                    <td className="num">{street.houses}</td>
                    <td className="num">{street.families}</td>
                    <td className="num">{street.citizens}</td>
                  </tr>
                ))}
                {streets.length === 0 && <tr><td colSpan={4}><Empty title="Ko'cha topilmadi" icon={<Home size={17} />} /></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && tab === "houses" && houses && (
        <div className="card">
          <div className="grid grid-2" style={{ padding: 14 }}>
            {houses.items.map((house) => (
              <div key={house.id} className="card card-pad" style={{ boxShadow: "none" }}>
                <h3 style={{ fontSize: 15 }}>{house.address_label}</h3>
                <p className="text-soft mt" style={{ fontSize: 13.5 }}>{house.families} oila · {house.citizens} fuqaro</p>
              </div>
            ))}
            {houses.items.length === 0 && <Empty title="Uy topilmadi" icon={<Home size={17} />} />}
          </div>
          {houses.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{houses.meta.total} ta uy · {houses.meta.page}/{houses.meta.total_pages}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
                <button className="btn sm" disabled={page >= houses.meta.total_pages} onClick={() => setPage(page + 1)}>›</button>
              </span>
            </div>
          )}
        </div>
      )}

      {!loading && tab === "families" && families && (
        <div className="card">
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th>Oila</th><th>Boshliq</th><th>Manzil</th><th className="num">A'zolar</th><th>Tur</th><th>Ijtimoiy holat</th><th aria-label="Amallar" /></tr></thead>
              <tbody>
                {families.items.map((family) => (
                  <tr key={family.id}>
                    <td className="mono">{family.id}</td>
                    <td>{family.head_name ?? "—"}</td>
                    <td>{family.address?.address_label ?? "—"}</td>
                    <td className="num">{family.member_count}</td>
                    <td>{family.family_type}</td>
                    <td>
                      {family.social_status && family.social_status !== "Yo'q" && family.social_status !== "—"
                        ? <Badge tone="warn">{family.social_status}</Badge>
                        : <span className="text-faint">—</span>}
                    </td>
                    <td>
                      <button className="btn sm ghost" onClick={() => setDetailId(family.id)}>Tafsilot</button>
                    </td>
                  </tr>
                ))}
                {families.items.length === 0 && <tr><td colSpan={7}><Empty title="Oila topilmadi" icon={<Home size={17} />} /></td></tr>}
              </tbody>
            </table>
          </div>
          {families.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{families.meta.total} ta oila · {families.meta.page}/{families.meta.total_pages}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Oldingi</button>
                <button className="btn sm" disabled={page >= families.meta.total_pages} onClick={() => setPage(page + 1)}>Keyingi ›</button>
              </span>
            </div>
          )}
        </div>
      )}

      <Drawer open={formOpen} onClose={() => setFormOpen(false)} title="Yangi oila">
        <FamilyForm onSaved={() => { setFormOpen(false); load(); }} />
      </Drawer>

      <Drawer open={Boolean(detailId)} onClose={() => setDetailId(null)} title={`Oila tafsiloti${detail ? "" : ""}`} wide>
        {detailLoading && <SkeletonList rows={3} />}
        {!detailLoading && detail && <FamilyDetail data={detail} />}
        {!detailLoading && !detail && <Empty title="Oila topilmadi" />}
      </Drawer>
    </>
  );
}

function FamilyDetail({ data }: { data: Record<string, unknown> }) {
  const d = data as {
    id?: string; family_type?: string; social_status?: string; notes?: string;
    head_name?: string; member_count?: number;
    address?: { address_label?: string } | null;
    members?: Array<{ id: string; full_name: string; family_role: string; birth_date?: string | null; phone?: string }>;
  };
  return (
    <>
      <dl className="kv mb">
        <dt>Oila</dt><dd className="mono" style={{ fontSize: 12.5 }}>{d.id ?? "—"}</dd>
        <dt>Boshliq</dt><dd>{d.head_name ?? "—"}</dd>
        <dt>Turi</dt><dd>{d.family_type ?? "—"}</dd>
        <dt>Ijtimoiy holat</dt><dd>{d.social_status || "—"}</dd>
        <dt>Manzil</dt><dd>{d.address?.address_label ?? "—"}</dd>
        <dt>A'zolar</dt><dd className="num">{d.member_count ?? d.members?.length ?? 0} nafar</dd>
        {d.notes && (<><dt>Izoh</dt><dd>{d.notes}</dd></>)}
      </dl>
      <h3 style={{ marginBottom: 10 }}>A'zolar</h3>
      <div className="table-wrap">
        <table className="data" style={{ minWidth: 480 }}>
          <thead><tr><th>F.I.Sh.</th><th>O'rni</th><th>Telefon</th></tr></thead>
          <tbody>
            {(d.members ?? []).map((m) => (
              <tr key={m.id}>
                <td><Link className="rowlink" href={`/citizens/${m.id}`}>{m.full_name}</Link></td>
                <td>{m.family_role}</td>
                <td className="nowrap">{m.phone || "—"}</td>
              </tr>
            ))}
            {(d.members ?? []).length === 0 && <tr><td colSpan={3}><Empty title="A'zolar ko'rsatilmagan" /></td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

function FamilyForm({ onSaved }: { onSaved: () => void }) {
  const toast = useToast();
  const [houses, setHouses] = useState<Array<{ value: string; label: string }>>([]);
  const [citizens, setCitizens] = useState<Array<{ value: string; label: string; sub?: string }>>([]);
  const [houseId, setHouseId] = useState("");
  const [headId, setHeadId] = useState("");
  const [familyType, setFamilyType] = useState("To'liq oila");
  const [socialStatus, setSocialStatus] = useState("Yo'q");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<{ items: Paged<House>["items"] }>("/houses?page_size=100")
      .then((d) => setHouses(d.items.map((h) => ({ value: h.id, label: h.address_label }))))
      .catch(() => {});
    api.get<Paged<{ id: string; full_name: string; address?: { address_label?: string } }>>("/citizens?page_size=100")
      .then((d) => setCitizens(d.items.map((c) => ({ value: c.id, label: c.full_name, sub: c.address?.address_label }))))
      .catch(() => {});
  }, []);

  async function submit() {
    setError("");
    if (!houseId) { setError("Uy tanlanishi shart."); return; }
    setBusy(true);
    try {
      await api.post("/families", {
        house_id: houseId,
        family_head_citizen_id: headId || null,
        family_type: familyType,
        social_status: socialStatus,
        notes,
      });
      toast.show("success", "Yangi oila qo'shildi.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Saqlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error && <div className="alert danger" role="alert">{error}</div>}
      <Field label="Uy" required htmlFor="ff-house">
        <select id="ff-house" className="select" value={houseId} onChange={(e) => setHouseId(e.target.value)}>
          <option value="">— tanlang —</option>
          {houses.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
        </select>
      </Field>
      <Field label="Oila boshlig'i (ixtiyoriy)" htmlFor="ff-head">
        <select id="ff-head" className="select" value={headId} onChange={(e) => setHeadId(e.target.value)}>
          <option value="">— tanlanmagan —</option>
          {citizens.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </Field>
      <Field label="Oila turi" htmlFor="ff-type">
        <select id="ff-type" className="select" value={familyType} onChange={(e) => setFamilyType(e.target.value)}>
          {["To'liq oila", "To'liq bo'lmagan oila (ona)", "To'liq bo'lmagan oila (ota)", "Katta oila", "Yashovchilar"].map((t) => <option key={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Ijtimoiy holati" htmlFor="ff-social">
        <select id="ff-social" className="select" value={socialStatus} onChange={(e) => setSocialStatus(e.target.value)}>
          {["Yo'q", "Temir daftar", "Ko'p bolali oila", "Yoshlar daftari", "Kam ta'minlangan oila", "To'liq bo'lmagan oila"].map((t) => <option key={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Izoh" htmlFor="ff-notes">
        <textarea id="ff-notes" className="textarea" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
        <button className="btn ghost" onClick={onSaved} disabled={busy}>Yopish</button>
        <button className="btn primary" onClick={() => void submit()} disabled={busy || !houseId}>
          {busy ? "Saqlanmoqda…" : "Oilani qo'shish"}
        </button>
      </div>
    </>
  );
}

export default function FamiliesPage() {
  return (
    <Suspense fallback={<SkeletonList rows={5} />}>
      <FamiliesInner />
    </Suspense>
  );
}
