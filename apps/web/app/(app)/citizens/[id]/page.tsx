"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { CASE_STATUS, TASK_STATUS, fmtDate, fmtDateTime, statusBadge } from "@/lib/format";

type Detail = {
  id: string;
  full_name: string;
  gender: string;
  birth_date: string | null;
  age: number | null;
  phone: string;
  family_role: string;
  education: string;
  employment_status: string;
  profession: string;
  social_status: string;
  needs: string[];
  notes: string;
  data_source: string;
  last_verified_at: string | null;
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
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<Detail>(`/citizens/${params.id}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [params.id]);

  if (error) return <ErrorNote message={error} />;
  if (!data) return <Loading />;

  return (
    <>
      <PageHead
        kicker={`Fuqaro · ${data.id}`}
        title={data.full_name}
        lede={`${data.address?.mahalla ?? ""}${data.address?.address_label ? ` · ${data.address.address_label}` : ""}`}
        actions={
          <Link className="btn" href="/citizens">
            ← Ro‘yxatga qaytish
          </Link>
        }
      />
      <div className="split s2r mb">
        <div className="card card-pad">
          <h3 className="mb">Pasport ma'lumotlari</h3>
          <dl className="kv">
            <dt>Jinsi</dt>
            <dd>{data.gender}</dd>
            <dt>Tug‘ilgan sana</dt>
            <dd>
              {fmtDate(data.birth_date)} {data.age !== null ? `· ${data.age} yosh` : ""}
            </dd>
            <dt>Telefon</dt>
            <dd>{data.phone || "—"}</dd>
            <dt>Oiladagi o‘rni</dt>
            <dd>{data.family_role}</dd>
            <dt>Ma'lumoti</dt>
            <dd>{data.education}</dd>
            <dt>Bandlik</dt>
            <dd>
              {data.employment_status}
              {data.profession && data.profession !== "Yo'q" ? ` · ${data.profession}` : ""}
            </dd>
            <dt>Ijtimoiy holat</dt>
            <dd>
              {data.social_status && data.social_status !== "Yo'q" ? (
                <Badge tone="warn">{data.social_status}</Badge>
              ) : (
                "—"
              )}
            </dd>
            {data.needs.length > 0 && (
              <>
                <dt>Ehtiyoji</dt>
                <dd>
                  {data.needs.map((need) => (
                    <Badge key={need} tone="info">
                      {need}
                    </Badge>
                  ))}
                </dd>
              </>
            )}
            <dt>Ma'lumot manbasi</dt>
            <dd className="mono">{data.data_source}</dd>
            <dt>Oxirgi tekshiruv</dt>
            <dd>{fmtDateTime(data.last_verified_at)}</dd>
            {data.notes && (
              <>
                <dt>Izoh</dt>
                <dd>{data.notes}</dd>
              </>
            )}
          </dl>
        </div>

        <div>
          {data.family && (
            <div className="card card-pad mb">
              <div className="card-head" style={{ padding: 0, border: "none", marginBottom: 8 }}>
                <h3>Oila</h3>
                <Link className="link" href={`/families?focus=${data.family.id}`}>
                  Oila sahifasi →
                </Link>
              </div>
              <dl className="kv">
                <dt>Oila</dt>
                <dd className="mono">{data.family.id}</dd>
                <dt>Oila boshlig‘i</dt>
                <dd>{data.family.family_head_name}</dd>
                <dt>Turi</dt>
                <dd>{data.family.family_type}</dd>
                <dt>A'zolar</dt>
                <dd>{data.family.member_count} nafar</dd>
                <dt>Manzil</dt>
                <dd>{data.family.address?.address_label ?? "—"}</dd>
              </dl>
            </div>
          )}
          <div className="card card-pad">
            <h3 className="mb">Ma'lumot sifati</h3>
            <div className="progress mb">
              <i style={{ width: `${data.data_quality.score}%` }} />
            </div>
            <p className="text-soft">
              Sifat: <b>{data.data_quality.score}%</b>
              {data.data_quality.missing_fields.length > 0 && (
                <> · to‘ldirilmagan: {data.data_quality.missing_fields.join(", ")}</>
              )}
            </p>
          </div>
        </div>
      </div>

      <div className="split s2">
        <div className="card">
          <div className="card-head">
            <h3>Murojaatlar va vazifalar</h3>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Nomi</th>
                  <th>Tur</th>
                  <th>Holat</th>
                </tr>
              </thead>
              <tbody>
                {data.cases.map((row) => {
                  const status = statusBadge(CASE_STATUS, row.status);
                  return (
                    <tr key={row.id}>
                      <td>{row.title}</td>
                      <td className="text-faint nowrap">Murojaat · {fmtDate(row.opened_at)}</td>
                      <td>
                        <Badge tone={status.tone}>{status.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
                {data.tasks.map((row) => {
                  const status = statusBadge(TASK_STATUS, row.status);
                  return (
                    <tr key={row.id}>
                      <td>{row.title}</td>
                      <td className="text-faint nowrap">Vazifa · {fmtDate(row.due_date)}</td>
                      <td>
                        <Badge tone={status.tone}>{status.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
                {data.cases.length === 0 && data.tasks.length === 0 && (
                  <tr>
                    <td colSpan={3}>
                      <Empty title="Murojaat va vazifa yo‘q" icon="✓" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <h3>Harakatlar tarixi</h3>
          </div>
          <div className="card-pad">
            <div className="timeline">
              {data.timeline.slice(0, 12).map((item) => (
                <div className="tl-item" key={item.id}>
                  <span className="tl-dot" />
                  <div className="tl-body">
                    <h4>{item.title}</h4>
                    <div className="when">
                      {item.kind} · {fmtDateTime(item.occurred_at)}
                    </div>
                    {item.description && <div className="desc">{item.description}</div>}
                  </div>
                </div>
              ))}
              {data.timeline.length === 0 && <Empty title="Tarix bo‘sh" icon="≡" />}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
