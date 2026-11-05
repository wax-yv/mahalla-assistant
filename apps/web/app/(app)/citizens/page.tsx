"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Ban, Filter, Phone, Plus, Search, Users, X } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Pager } from "@/components/ui";
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

const EMPLOYMENT = ["Ishlaydi", "Ishsiz", "Tadbirkor", "Pensioner", "O‘qiydi", "Ishlamaydi"];
const SOCIAL = ["Temir daftar", "Ko‘p bolali oila", "Yoshlar daftari", "Ayollar daftari", "Kam ta’minlangan oila", "Nogironligi bor (I guruh)", "Nogironligi bor (II guruh)", "Nogironligi bor (III guruh)"];

function CitizensInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const [data, setData] = useState<Paged<Citizen> | null>(null);
  const [error, setError] = useState("");
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

  const activeFilters = [
    q && { key: "q", label: `Qidiruv: ${q}` },
    employment && { key: "employment_status", label: employment },
    social && { key: "social_status", label: social },
  ].filter(Boolean) as Array<{ key: string; label: string }>;

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
        lede="Navbahor mahallasi aholisi. Qidiruv familiya, ism yoki telefon raqami bo‘yicha ishlaydi."
        actions={
          <button className="btn primary" onClick={() => setFormOpen(true)}>
            <Plus size={16} /> Yangi fuqaro
          </button>
        }
      />

      <div className="toolbar">
        <div className="search-field">
          <Search className="search-ico" size={15} />
          <input
            className="input"
            placeholder="F.I.Sh. yoki telefon…"
            value={q}
            onChange={(e) => setParam({ q: e.target.value || null, page: null })}
            aria-label="Fuqaro qidirish"
          />
          {q && (
            <button className="icon-btn search-clear" onClick={() => setParam({ q: null })} aria-label="Qidiruvni tozalash">
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
            <span key={f.key} className="chip chip-static active">
              <Filter size={12} /> {f.label}
            </span>
          ))}
        </div>
      )}

      {loading && !data && <SkeletonList rows={6} />}
      {!loading && error && <ErrorState note={error} onRetry={load} />}

      {data && !loading && (
        <>
          <p className="text-faint mb fs-12_5">
            Jami <b className="num text-strong">{data.meta.total}</b> fuqaro · {data.meta.page}/{data.meta.total_pages || 1} sahifa
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
                  <th><span className="chip-inline"><Users size={12} /> Ehtiyoj</span></th>
                  <th aria-label="Amallar" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((citizen) => (
                  <tr key={citizen.id}>
                    <td data-label="Fuqaro">
                      <Link className="rowlink" href={`/citizens/${citizen.id}`}>{citizen.full_name}</Link>
                      <div className="cell-sub mono">{citizen.id}</div>
                    </td>
                    <td className="num nowrap" data-label="Yosh">{age(citizen.birth_date)}</td>
                    <td className="nowrap" data-label="Telefon">
                      {citizen.phone ? (
                        <a className="link" href={`tel:${citizen.phone.replace(/\s/g, "")}`} onClick={(e) => e.stopPropagation()}>
                          <Phone size={12} className="ico-inline-sm" />
                          {citizen.phone}
                        </a>
                      ) : <span className="text-faint">—</span>}
                    </td>
                    <td data-label="Manzil">{citizen.address?.address_label ?? <span className="text-faint">—</span>}</td>
                    <td className="nowrap" data-label="Bandlik">{citizen.employment_status}</td>
                    <td data-label="Ijtimoiy holat">
                      {citizen.social_status && citizen.social_status !== "Yo‘q" && citizen.social_status !== "—"
                        ? <Badge tone="warn">{citizen.social_status}</Badge>
                        : <span className="text-faint">—</span>}
                    </td>
                    <td data-label="Ehtiyoj">
                      {citizen.needs.length > 0 ? (
                        <span className="chip-row">
                          {citizen.needs.slice(0, 2).map((need) => <Badge key={need} tone="info">{need}</Badge>)}
                          {citizen.needs.length > 2 && <Badge tone="muted">+{citizen.needs.length - 2}</Badge>}
                        </span>
                      ) : <span className="text-faint">—</span>}
                    </td>
                    <td className="nowrap" data-label="Amallar">
                      <Link className="icon-btn" href={`/citizens/${citizen.id}`} aria-label={`${citizen.full_name} — profil`} title="Profil">
                        <Users size={15} />
                      </Link>
                      <button className="icon-btn danger" onClick={() => setArchiveTarget(citizen)} aria-label={`${citizen.full_name} — arxivlash`} title="Arxivlash">
                        <Ban size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr><td colSpan={8}><Empty title="Mos fuqaro topilmadi" note="Qidiruv yoki filtrlarni o‘zgartirib, qayta urinib ko‘ring." art="search" /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager meta={data.meta} onPage={(p) => setParam({ page: String(p) })} />
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
        message={`«${archiveTarget?.full_name}» arxivlanadi: ro‘yxatlarda ko‘rinmaydi, ma’lumotlari bazada saqlanadi. Davom etamizmi?`}
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
