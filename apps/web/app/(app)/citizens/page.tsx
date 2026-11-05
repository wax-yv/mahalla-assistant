"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Filter, Phone, Plus, Search, Users, X } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { ConfirmDialog, Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { api, type Paged } from "@/lib/api";
import { age } from "@/lib/format";
import { CitizenForm } from "@/components/citizens/CitizenForm";

type Citizen = {
  id: string; full_name: string; gender: string; birth_date: string | null;
  phone: string; family_role: string; employment_status: string; profession: string;
  social_status: string; needs: string[];
  address: { address_label?: string | null } | null;
};

const EMPLOYMENT = ["Ishlaydi", "Ishsiz", "Tadbirkor", "Pensioner", "O'qiydi", "Ishlamaydi"];
const SOCIAL = ["Temir daftar", "Ko'p bolali oila", "Yoshlar daftari", "Ayollar daftari", "Kam ta'minlangan oila", "Nogironligi bor (I guruh)", "Nogironligi bor (II guruh)", "Nogironligi bor (III guruh)"];

function CitizensInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const [data, setData] = useState<Paged<Citizen> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const q = searchParams.get("q") ?? "";
  const employment = searchParams.get("employment_status") ?? "";
  const social = searchParams.get("social_status") ?? "";
  const page = Number(searchParams.get("page") ?? "1");

  const [formOpen, setFormOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<Citizen | null>(null);
  const [archiving, setArchiving] = useState(false);

  const setParam = useCallback(
    (patch: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      router.replace(`/citizens?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (q) params.set("q", q);
    if (employment) params.set("employment_status", employment);
    if (social) params.set("social_status", social);
    api
      .get<Paged<Citizen>>(`/citizens?${params}`)
      .then((d) => { setData(d); setError(""); })
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))
      .finally(() => setLoading(false));
  }, [q, employment, social, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const activeFilters = [q && { key: "q", label: `Qidiruv: ${q}` }, employment && { key: "employment_status", label: employment }, social && { key: "social_status", label: social }].filter(Boolean) as Array<{ key: string; label: string }>;

  async function archive() {
    if (!archiveTarget) return;
    setArchiving(true);
    try {
      await api.del(`/citizens/${archiveTarget.id}`);
      toast.show("success", `${archiveTarget.full_name} arxivlandi.`);
      setArchiveTarget(null);
      load();
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Arxivlash amalga oshmadi.");
    } finally {
      setArchiving(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Fuqarolar bazasi"
        title="Fuqarolar"
        lede="Navbahor mahallasi aholisi. Qidiruv familiya, ism yoki telefon raqami bo'yicha ishlaydi."
        actions={
          <button className="btn primary" onClick={() => setFormOpen(true)}>
            <Plus size={16} /> Yangi fuqaro
          </button>
        }
      />

      <div className="toolbar">
        <div style={{ position: "relative", flex: 1, minWidth: 220, maxWidth: 360 }}>
          <Search size={15} style={{ position: "absolute", left: 12, top: 13, color: "var(--color-text-muted)" }} />
          <input
            className="input"
            style={{ paddingLeft: 36, paddingRight: 36 }}
            placeholder="F.I.Sh. yoki telefon…"
            value={q}
            onChange={(e) => setParam({ q: e.target.value || null, page: null })}
            aria-label="Fuqaro qidirish"
          />
          {busy && <span style={{ position: "absolute", right: 12, top: 13 }} aria-hidden="true" />}
          {q && (
            <button className="icon-btn" style={{ position: "absolute", right: 5, top: 5 }} onClick={() => setParam({ q: null })} aria-label="Qidiruvni tozalash">
              <X size={14} />
            </button>
          )}
        </div>
        <select className="select" value={employment} onChange={(e) => setParam({ employment_status: e.target.value || null, page: null })} aria-label="Bandlik filtri">
          <option value="">Bandlik — barchasi</option>
          {EMPLOYMENT.map((item) => <option key={item}>{item}</option>)}
        </select>
        <select className="select" value={social} onChange={(e) => setParam({ social_status: e.target.value || null, page: null })} aria-label="Ijtimoiy holat filtri">
          <option value="">Ijtimoiy holat — barchasi</option>
          {SOCIAL.map((item) => <option key={item}>{item}</option>)}
        </select>
        {activeFilters.length > 0 && (
          <button className="btn ghost sm" onClick={() => router.replace("/citizens")}>
            <X size={14} /> Filtrlarni tozalash
          </button>
        )}
      </div>

      {activeFilters.length > 0 && (
        <div className="chips">
          {activeFilters.map((f) => (
            <span key={f.key} className="chip active" style={{ cursor: "default" }}>
              <Filter size={12} /> {f.label}
            </span>
          ))}
        </div>
      )}

      {loading && !data && <SkeletonList rows={6} />}
      {!loading && error && <ErrorState note={error} onRetry={load} />}

      {data && !loading && (
        <>
          <p className="text-faint mb" style={{ fontSize: 12.5 }}>
            Jami <b className="num" style={{ color: "var(--color-text)" }}>{data.meta.total}</b> fuqaro · {data.meta.page}/{data.meta.total_pages || 1} sahifa
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Fuqaro</th>
                  <th>Yosh</th>
                  <th>Telefon</th>
                  <th>Manzil</th>
                  <th>Bandlik</th>
                  <th>Ijtimoiy holat</th>
                  <th><span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><Users size={12} /> Ehtiyoj</span></th>
                  <th aria-label="Amallar" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((citizen) => (
                  <tr key={citizen.id}>
                    <td>
                      <Link className="rowlink" href={`/citizens/${citizen.id}`}>{citizen.full_name}</Link>
                      <div className="cell-sub mono">{citizen.id}</div>
                    </td>
                    <td className="num nowrap">{age(citizen.birth_date)}</td>
                    <td className="nowrap">
                      {citizen.phone ? (
                        <a className="rowlink" href={`tel:${citizen.phone.replace(/\s/g, "")}`} style={{ fontWeight: 500 }} onClick={(e) => e.stopPropagation()}>
                          <Phone size={12} style={{ display: "inline", marginRight: 4, verticalAlign: "-1px" }} />
                          {citizen.phone}
                        </a>
                      ) : <span className="text-faint">—</span>}
                    </td>
                    <td>{citizen.address?.address_label ?? <span className="text-faint">—</span>}</td>
                    <td className="nowrap">{citizen.employment_status}</td>
                    <td>
                      {citizen.social_status && citizen.social_status !== "Yo'q" && citizen.social_status !== "—"
                        ? <Badge tone="warn">{citizen.social_status}</Badge>
                        : <span className="text-faint">—</span>}
                    </td>
                    <td>
                      {citizen.needs.length > 0 ? (
                        <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap" }}>
                          {citizen.needs.slice(0, 2).map((need) => <Badge key={need} tone="info">{need}</Badge>)}
                          {citizen.needs.length > 2 && <Badge tone="muted">+{citizen.needs.length - 2}</Badge>}
                        </span>
                      ) : <span className="text-faint">—</span>}
                    </td>
                    <td className="nowrap">
                      <Link className="icon-btn" href={`/citizens/${citizen.id}`} aria-label={`${citizen.full_name} — profil`} title="Profil">
                        <Users size={15} />
                      </Link>
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr><td colSpan={8}><Empty title="Mos fuqaro topilmadi" note="Qidiruv yoki filtrlarni o'zgartirib ko'ring." icon={<Search size={18} />} /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          {data.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{data.meta.total} ta yozuv · {data.meta.page}/{data.meta.total_pages} sahifa</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setParam({ page: String(page - 1) })}>‹ Oldingi</button>
                <button className="btn sm" disabled={page >= data.meta.total_pages} onClick={() => setParam({ page: String(page + 1) })}>Keyingi ›</button>
              </span>
            </div>
          )}
        </>
      )}

      <Drawer open={formOpen} onClose={() => setFormOpen(false)} title="Yangi fuqaro" wide>
        <CitizenForm open={formOpen} onClose={() => setFormOpen(false)} onSaved={() => load()} />
      </Drawer>

      <ConfirmDialog
        open={Boolean(archiveTarget)}
        onClose={() => setArchiveTarget(null)}
        onConfirm={() => void archive()}
        title="Fuqaroni arxivlash"
        message={`«${archiveTarget?.full_name}» arxivlanadi: ro'yxatlarda ko'rinmaydi, ma'lumoti saqlanadi. Davom etamizmi?`}
        confirmLabel="Arxivlash"
        busy={archiving}
      />
    </>
  );
}

export default function CitizensPage() {
  return (
    <Suspense fallback={<SkeletonList rows={6} />}>
      <CitizensInner />
    </Suspense>
  );
}
