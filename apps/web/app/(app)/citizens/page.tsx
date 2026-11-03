"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { age } from "@/lib/format";

type Citizen = {
  id: string;
  full_name: string;
  gender: string;
  birth_date: string | null;
  age: number | null;
  phone: string;
  family_role: string;
  employment_status: string;
  profession: string;
  social_status: string;
  needs: string[];
  address: { address_label?: string | null } | null;
};

export default function CitizensPage() {
  const [data, setData] = useState<Paged<Citizen> | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [employment, setEmployment] = useState("");
  const [social, setSocial] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (q) params.set("q", q);
    if (employment) params.set("employment_status", employment);
    if (social) params.set("social_status", social);
    api
      .get<Paged<Citizen>>(`/citizens?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [q, employment, social, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <>
      <PageHead
        kicker="Fuqarolar bazasi"
        title="Fuqarolar"
        lede="Navbahor mahallasi aholisi. Qidiruv familiya, ism yoki telefon raqami bo‘yicha ishlaydi."
      />
      {error && <ErrorNote message={error} />}
      <div className="filters">
        <input
          className="input"
          placeholder="F.I.Sh. yoki telefon…"
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setPage(1);
          }}
        />
        <select
          className="select"
          value={employment}
          onChange={(event) => {
            setEmployment(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Bandlik — barchasi</option>
          <option value="Ishlaydi">Ishlaydi</option>
          <option value="Ishsiz">Ishsiz</option>
          <option value="Tadbirkor">Tadbirkor</option>
          <option value="Pensioner">Pensioner</option>
          <option value="O‘qiydi">O‘qiydi</option>
          <option value="Ishlamaydi">Ishlamaydi</option>
        </select>
        <select
          className="select"
          value={social}
          onChange={(event) => {
            setSocial(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Ijtimoiy holat — barchasi</option>
          <option value="Temir daftar">Temir daftar</option>
          <option value="Ko'p bolali oila">Ko‘p bolali oila</option>
          <option value="Yoshlar daftari">Yoshlar daftari</option>
          <option value="Ayollar daftari">Ayollar daftari</option>
          <option value="Kam ta'minlangan oila">Kam ta’minlangan oila</option>
          <option value="Nogironligi bor (I guruh)">Nogironligi bor (I guruh)</option>
          <option value="Nogironligi bor (II guruh)">Nogironligi bor (II guruh)</option>
        </select>
      </div>
      {!data && !error && <Loading />}
      {data && (
        <div className="card">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>F.I.Sh.</th>
                  <th>Yosh</th>
                  <th>Telefon</th>
                  <th>Manzil</th>
                  <th>Bandlik</th>
                  <th>Ijtimoiy holat</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((citizen) => (
                  <tr key={citizen.id}>
                    <td>
                      <Link className="rowlink" href={`/citizens/${citizen.id}`}>
                        {citizen.full_name}
                      </Link>
                      <div className="text-faint mono">{citizen.id}</div>
                    </td>
                    <td>{age(citizen.birth_date)}</td>
                    <td className="nowrap">{citizen.phone || "—"}</td>
                    <td>{citizen.address?.address_label ?? "—"}</td>
                    <td className="nowrap">{citizen.employment_status}</td>
                    <td>
                      {citizen.social_status && citizen.social_status !== "Yo'q" ? (
                        <Badge tone="warn">{citizen.social_status}</Badge>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <Empty title="Fuqaro topilmadi" note="Qidiruv shartlarini o‘zgartirib ko‘ring." />
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
