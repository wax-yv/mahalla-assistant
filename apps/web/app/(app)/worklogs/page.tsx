"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type LogRow = {
  id: string;
  type: string;
  title: string;
  description: string;
  occurred_at: string;
  citizen_id?: string | null;
  source: string;
  approval_status: string;
};

const TONES: Record<string, string> = {
  uchrashuv: "brand",
  telefon: "info",
  tavsiya: "muted",
  hujjat: "warn",
  "bajarilgan ish": "ok",
  natija: "ok",
  vazifa: "muted",
  murojaat: "info",
};

export default function WorkLogsPage() {
  const [data, setData] = useState<Paged<LogRow> | null>(null);
  const [error, setError] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    if (type) params.set("type", type);
    api
      .get<Paged<LogRow>>(`/work-logs?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [type, page]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <>
      <PageHead
        kicker="Ish yozuvlari"
        title="Aholi bilan ish tarixi"
        lede="Uchrashuv, telefon aloqa, tavsiya va bajarilgan ishlar yagona jurnalda saqlanadi."
      />
      {error && <ErrorNote message={error} />}
      <div className="filters">
        <select className="select" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
          <option value="">Tur — barchasi</option>
          {["uchrashuv", "telefon", "tavsiya", "hujjat", "bajarilgan ish", "natija", "vazifa", "murojaat"].map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </div>
      {!data && !error && <Loading />}
      {data && (
        <div className="card">
          <div className="card-pad">
            <div className="timeline">
              {data.items.map((log) => (
                <div className="tl-item" key={log.id}>
                  <span className="tl-dot" />
                  <div className="tl-body">
                    <h4>
                      {log.title} <Badge tone={TONES[log.type] ?? "muted"}>{log.type}</Badge>
                    </h4>
                    <div className="when">
                      {fmtDateTime(log.occurred_at)} · {log.source === "seed" ? "demo yozuv" : log.source}
                    </div>
                    {log.description && <div className="desc">{log.description}</div>}
                  </div>
                </div>
              ))}
              {data.items.length === 0 && <Empty title="Yozuv topilmadi" icon="≡" />}
            </div>
          </div>
          <Pager meta={data.meta} onPage={setPage} />
        </div>
      )}
    </>
  );
}
