"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type Mahalla = { id: string; name: string; streets: number; houses: number; citizens: number };
type Street = { id: string; name: string; houses: number; families: number; citizens: number };
type House = { id: string; house_number: string; address_label: string; street: string; families: number; citizens: number };
type Family = {
  id: string;
  family_type: string;
  social_status: string;
  member_count: number;
  head_name?: string | null;
  address?: { address_label?: string | null } | null;
};

export default function FamiliesPage() {
  const [tab, setTab] = useState<"streets" | "houses" | "families">("streets");
  const [mahallas, setMahallas] = useState<Mahalla[]>([]);
  const [streets, setStreets] = useState<Street[]>([]);
  const [houses, setHouses] = useState<Paged<House> | null>(null);
  const [families, setFamilies] = useState<Paged<Family> | null>(null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<{ items: Mahalla[] }>("/mahallas")
      .then((data) => setMahallas(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  const loadStreets = useCallback(() => {
    api
      .get<{ items: Street[] }>("/streets")
      .then((data) => setStreets(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  const loadHouses = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "24" });
    if (q) params.set("q", q);
    api
      .get<Paged<House>>(`/houses?${params}`)
      .then(setHouses)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [q, page]);

  const loadFamilies = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (q) params.set("q", q);
    api
      .get<Paged<Family>>(`/families?${params}`)
      .then(setFamilies)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [q, page]);

  useEffect(() => {
    setPage(1);
    if (tab === "streets") loadStreets();
    if (tab === "houses") loadHouses();
    if (tab === "families") loadFamilies();
  }, [tab, loadStreets, loadHouses, loadFamilies]);

  useEffect(() => {
    if (tab === "houses") loadHouses();
    if (tab === "families") loadFamilies();
  }, [page, tab, loadHouses, loadFamilies]);

  const mahalla = mahallas[0];

  return (
    <>
      <PageHead
        kicker="Manzillar ierarxiyasi"
        title="Oilalar va manzillar"
        lede={
          mahalla
            ? `${mahalla.name} — ${mahalla.streets} ko‘cha, ${mahalla.houses} uy, ${mahalla.citizens} fuqaro.`
            : "Mahalla, ko‘cha, uy va oilalar ierarxiyasi."
        }
      />
      {error && <ErrorNote message={error} />}
      <div className="tabbar">
        {(
          [
            ["streets", "Ko‘chalar"],
            ["houses", "Uylar"],
            ["families", "Oilalar"],
          ] as const
        ).map(([key, label]) => (
          <Link key={key} href="#" className={tab === key ? "active" : ""} onClick={(e) => { e.preventDefault(); setTab(key); setQ(""); setPage(1); }}>
            {label}
          </Link>
        ))}
      </div>
      {tab !== "streets" && (
        <div className="filters">
          <input
            className="input"
            placeholder={tab === "houses" ? "Uy raqami yoki ko‘cha…" : "Oila ID, boshliq yoki manzil…"}
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
          />
        </div>
      )}

      {tab === "streets" &&
        (streets.length ? (
          <div className="card">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Ko‘cha</th>
                    <th>Uylar</th>
                    <th>Oilalar</th>
                    <th>Fuqarolar</th>
                  </tr>
                </thead>
                <tbody>
                  {streets.map((street) => (
                    <tr key={street.id}>
                      <td>
                        <b>{street.name}</b>
                      </td>
                      <td>{street.houses}</td>
                      <td>{street.families}</td>
                      <td>{street.citizens}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <Loading />
        ))}

      {tab === "houses" &&
        (houses ? (
          <div className="card">
            <div className="grid grid-2" style={{ padding: 14 }}>
              {houses.items.map((house) => (
                <div key={house.id} className="card card-pad" style={{ boxShadow: "none" }}>
                  <h3>{house.address_label}</h3>
                  <p className="text-soft mt">
                    {house.families} oila · {house.citizens} fuqaro
                  </p>
                </div>
              ))}
              {houses.items.length === 0 && <Empty title="Uy topilmadi" />}
            </div>
            <Pager meta={houses.meta} onPage={setPage} />
          </div>
        ) : (
          <Loading />
        ))}

      {tab === "families" &&
        (families ? (
          <div className="card">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Oila</th>
                    <th>Boshliq</th>
                    <th>Manzil</th>
                    <th>A'zolar</th>
                    <th>Tur</th>
                    <th>Ijtimoiy holat</th>
                  </tr>
                </thead>
                <tbody>
                  {families.items.map((family) => (
                    <tr key={family.id}>
                      <td className="mono">{family.id}</td>
                      <td>{family.head_name ?? "—"}</td>
                      <td>{family.address?.address_label ?? "—"}</td>
                      <td>{family.member_count}</td>
                      <td>{family.family_type}</td>
                      <td>
                        {family.social_status && family.social_status !== "Yo'q" ? (
                          <Badge tone="warn">{family.social_status}</Badge>
                        ) : (
                          <span className="text-faint">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {families.items.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <Empty title="Oila topilmadi" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <Pager meta={families.meta} onPage={setPage} />
          </div>
        ) : (
          <Loading />
        ))}
      <p className="text-faint mt" style={{ fontSize: 12.5 }}>
        Ma'lumotlar demo bazadan olingan. Oxirgi sinxronlash: {fmtDate(new Date().toISOString())}
      </p>
    </>
  );
}
