"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Plus, Search } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Pager } from "@/components/ui";
import { Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { Tabs, TabPanel } from "@/components/ui/Tabs";
import { api, type Paged } from "@/lib/api";

type Mahalla = { id: string; name: string; street_count: number; house_count: number; family_count: number; citizen_count: number };
type Street = { id: string; name: string; house_count: number; family_count: number; citizen_count: number };
type House = { id: string; house_number: string; address_label: string; family_count: number; citizen_count: number };
type Family = {
  id: string; family_type: string; social_status: string; member_count: number;
  family_head_name?: string | null; address?: { address_label?: string | null } | null;
};

type TabKey = "streets" | "houses" | "families";

const TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: "streets", label: "Ko‘chalar" },
  { key: "houses", label: "Uylar" },
  { key: "families", label: "Oilalar" },
];

const TAB_DESC: Record<TabKey, string> = {
  streets: "Mahalla ko‘chalari va ulardagi uy, oila hamda fuqarolar soni.",
  houses: "Uylar ro‘yxati — manzil, ko‘cha, oilalar va fuqarolar soni.",
  families: "Oilalar ro‘yxati — boshliq, tarkib, tur va ijtimoiy holat.",
};

const FAMILY_TYPES = ["To‘liq oila", "To‘liq bo‘lmagan oila (ona)", "To‘liq bo‘lmagan oila (ota)", "Katta oila", "Yashovchilar"];
const SOCIAL_STATUSES = ["Yo‘q", "Temir daftar", "Ko‘p bolali oila", "Yoshlar daftari", "Kam ta’minlangan oila", "To‘liq bo‘lmagan oila"];

function FamiliesInner() {
  const searchParams = useSearchParams();
  /* N-12: dashboarddagi "Jami uylar" / "Ko'chalar" kartalari to'g'ri
     bo'limga olib borishi uchun `?tab=` bilan boshlanish mumkin. */
  const initialTab = (searchParams.get("tab") as TabKey | null) ?? "streets";
  const [tab, setTab] = useState<TabKey>(
    initialTab === "houses" || initialTab === "families" ? initialTab : "streets",
  );
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

  /* P1-14: uy kartasi oila ro‘yxatiga havola beradi (`?house_id=` filtri). */
  const houseFilter = searchParams.get("house_id");
  const houseFilterLabel = searchParams.get("house_label") ?? "";

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
      if (houseFilter) params.set("house_id", houseFilter);
      api.get<Paged<Family>>(`/families?${params}`)
        .then((d) => { setFamilies(d); setError(""); })
        .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
        .finally(() => setLoading(false));
    }
  }, [tab, q, page, houseFilter]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const mahalla = mahallas[0];
  const focusId = searchParams.get("focus");

  /* `?house_id=` kiritilganda oilalar bo‘limi va uy filtri avtomatik qo‘llanadi. */
  useEffect(() => {
    if (houseFilter) {
      setTab("families");
      setPage(1);
    }
  }, [houseFilter]);

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

  return (
    <>
      <PageHead
        kicker="Manzillar ierarxiyasi"
        title="Oilalar va manzillar"
        lede={mahalla
          ? `${mahalla.name} — ${mahalla.street_count} ko‘cha, ${mahalla.house_count} uy, ${mahalla.family_count} oila, ${mahalla.citizen_count} fuqaro.`
          : "Mahalla, ko‘cha, uy va oilalar ierarxiyasi."}
        actions={
          <button className="btn primary" onClick={() => setFormOpen(true)}>
            <Plus size={16} /> Yangi oila
          </button>
        }
      />
      {error && <ErrorState note={error} onRetry={load} />}

      <Tabs
        tabs={TABS}
        value={tab}
        onChange={(key) => { setTab(key); setQ(""); setPage(1); }}
        ariaLabel="Manzillar ierarxiyasi bo‘limlari"
      >
      <p className="text-faint fs-13 mb-sm">{TAB_DESC[tab]}</p>

              <TabPanel tabKey="streets">
          {loading ? <SkeletonList rows={5} /> : (
            <div className="card">
              <div className="table-wrap flush">
                <table className="data">
                  <thead><tr><th>Ko‘cha</th><th className="num">Uylar</th><th className="num">Oilalar</th><th className="num">Fuqarolar</th></tr></thead>
                  <tbody>
                    {streets.map((street) => (
                      <tr key={street.id}>
                        <td data-label="Ko‘cha"><b>{street.name}</b></td>
                        <td className="num" data-label="Uylar">{street.house_count}</td>
                        <td className="num" data-label="Oilalar">{street.family_count}</td>
                        <td className="num" data-label="Fuqarolar">{street.citizen_count}</td>
                      </tr>
                    ))}
                    {streets.length === 0 && <tr><td colSpan={4}><Empty title="Ko‘cha topilmadi" note="Mahalla hierarxiyasi hali kiritilmagan." art="document" /></td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </TabPanel>

              <TabPanel tabKey="houses">
          <div className="toolbar">
            <div className="search-field">
              <Search className="search-ico" size={15} />
              <input
                className="input"
                placeholder="Uy raqami yoki ko‘cha…"
                value={q}
                onChange={(e) => { setQ(e.target.value); setPage(1); }}
                aria-label="Uylar bo‘yicha qidiruv"
              />
            </div>
          </div>
          {loading ? <SkeletonList rows={5} /> : houses && (
            <div className="card">
              <div className="grid grid-2 pad-14">
                {houses.items.map((house) => (
                  <Link
                    key={house.id}
                    className="card card-pad card-flat card-link"
                    href={`/families?house_id=${encodeURIComponent(house.id)}&house_label=${encodeURIComponent(house.address_label)}`}
                    aria-label={`${house.address_label} — oila ro‘yxatini ko‘rish`}
                  >
                    <h3 className="fs-15">{house.address_label}</h3>
                    <p className="text-soft mt fs-13_5">{house.family_count} oila · {house.citizen_count} fuqaro</p>
                    <span className="card-link-more">Oila ro‘yxati</span>
                  </Link>
                ))}
                {houses.items.length === 0 && <Empty title="Uy topilmadi" note="Qidiruv shartini o‘zgartirib, qayta urinib ko‘ring." art="search" />}
              </div>
              <Pager meta={houses.meta} onPage={setPage} />
            </div>
          )}
        </TabPanel>

              <TabPanel tabKey="families">
          <div className="toolbar">
            <div className="search-field">
              <Search className="search-ico" size={15} />
              <input
                className="input"
                placeholder="Oila ID, boshliq yoki manzil…"
                value={q}
                onChange={(e) => { setQ(e.target.value); setPage(1); }}
                aria-label="Oilalar bo‘yicha qidiruv"
              />
            </div>
          </div>
          {houseFilter ? (
            <div className="filters">
              <span className="chip-static">
                Uy: {houseFilterLabel || houseFilter}
              </span>
              <Link className="chip-static chip-action" href="/families">
                Filtrni tozalash
              </Link>
            </div>
          ) : null}
          {loading ? <SkeletonList rows={5} /> : families && (
            <div className="card">
              <div className="table-wrap flush">
                <table className="data">
                  <thead><tr><th>Oila</th><th>Boshliq</th><th>Manzil</th><th className="num">A’zolar</th><th>Tur</th><th>Ijtimoiy holat</th><th aria-label="Amallar" /></tr></thead>
                  <tbody>
                    {families.items.map((family) => (
                      <tr key={family.id}>
                        <td className="mono" data-label="Oila">{family.id}</td>
                        <td data-label="Boshliq">{family.family_head_name ?? "—"}</td>
                        <td data-label="Manzil">{family.address?.address_label ?? "—"}</td>
                        <td className="num" data-label="A’zolar">{family.member_count}</td>
                        <td data-label="Tur">{family.family_type}</td>
                        <td data-label="Ijtimoiy holat">
                          {family.social_status && family.social_status !== "Yo‘q" && family.social_status !== "—"
                            ? <Badge tone="warn">{family.social_status}</Badge>
                            : <span className="text-faint">—</span>}
                        </td>
                        <td data-label="Amallar">
                          <button className="btn sm ghost" onClick={() => setDetailId(family.id)}>Tafsilot</button>
                        </td>
                      </tr>
                    ))}
                    {families.items.length === 0 && <tr><td colSpan={7}><Empty title="Oila topilmadi" note="Oilalar bazasi hali to‘ldirilmagan." art="document" /></td></tr>}
                  </tbody>
                </table>
              </div>
              <Pager meta={families.meta} onPage={setPage} />
            </div>
          )}
        </TabPanel>
      </Tabs>

      <Drawer open={formOpen} onClose={() => setFormOpen(false)} title="Yangi oila">
        <FamilyForm onSaved={() => { setFormOpen(false); load(); }} />
      </Drawer>

      <Drawer open={Boolean(detailId)} onClose={() => setDetailId(null)} title="Oila tafsiloti" wide>
        {detailLoading && <SkeletonList rows={3} />}
        {!detailLoading && detail && <FamilyDetail data={detail} />}
        {!detailLoading && !detail && <Empty title="Oila topilmadi" note="Oila o‘chirilgan yoki ID noto‘g‘ri." />}
      </Drawer>
    </>
  );
}

function FamilyDetail({ data }: { data: Record<string, unknown> }) {
  const d = data as {
    id?: string; family_type?: string; social_status?: string; notes?: string;
    family_head_name?: string; member_count?: number;
    address?: { address_label?: string } | null;
    members?: Array<{ id: string; full_name: string; family_role: string; birth_date?: string | null; phone?: string }>;
  };
  return (
    <>
      <dl className="kv mb">
        <dt>Oila</dt><dd className="mono fs-12_5">{d.id ?? "—"}</dd>
        <dt>Boshliq</dt><dd>{d.family_head_name ?? "—"}</dd>
        <dt>Turi</dt><dd>{d.family_type ?? "—"}</dd>
        <dt>Ijtimoiy holat</dt><dd>{d.social_status || "—"}</dd>
        <dt>Manzil</dt><dd>{d.address?.address_label ?? "—"}</dd>
        <dt>A’zolar</dt><dd className="num">{d.member_count ?? d.members?.length ?? 0} nafar</dd>
        {d.notes && (<><dt>Izoh</dt><dd>{d.notes}</dd></>)}
      </dl>
      <h3 className="mb-sm">A’zolar</h3>
      <div className="table-wrap">
        <table className="data min-480">
          <thead><tr><th>F.I.Sh.</th><th>O‘rni</th><th>Telefon</th></tr></thead>
          <tbody>
            {(d.members ?? []).map((m) => (
              <tr key={m.id}>
                <td data-label="F.I.Sh."><Link className="rowlink" href={`/citizens/${m.id}`}>{m.full_name}</Link></td>
                <td data-label="O‘rni">{m.family_role}</td>
                <td className="nowrap" data-label="Telefon">{m.phone || "—"}</td>
              </tr>
            ))}
            {(d.members ?? []).length === 0 && <tr><td colSpan={3}><Empty title="A’zolar ko‘rsatilmagan" note="Bu oilaga a’zo biriktirilmagan." /></td></tr>}
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
  const [familyType, setFamilyType] = useState(FAMILY_TYPES[0]);
  const [socialStatus, setSocialStatus] = useState(SOCIAL_STATUSES[0]);
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
      toast.show("success", "Yangi oila qo‘shildi.");
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
      <Field label="Oila boshlig‘i (ixtiyoriy)" htmlFor="ff-head">
        <select id="ff-head" className="select" value={headId} onChange={(e) => setHeadId(e.target.value)}>
          <option value="">— tanlanmagan —</option>
          {citizens.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </Field>
      <Field label="Oila turi" htmlFor="ff-type">
        <select id="ff-type" className="select" value={familyType} onChange={(e) => setFamilyType(e.target.value)}>
          {FAMILY_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Ijtimoiy holati" htmlFor="ff-social">
        <select id="ff-social" className="select" value={socialStatus} onChange={(e) => setSocialStatus(e.target.value)}>
          {SOCIAL_STATUSES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Izoh" htmlFor="ff-notes">
        <textarea id="ff-notes" className="textarea" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <div className="row-end mt">
        <button className="btn ghost" onClick={onSaved} disabled={busy}>Yopish</button>
        <button className="btn primary" onClick={() => void submit()} disabled={busy || !houseId}>
          {busy ? "Saqlanmoqda…" : "Oilani qo‘shish"}
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
