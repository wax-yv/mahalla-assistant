"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type ReportRow = {
  id: string;
  type: string;
  title: string;
  status: string;
  period_start: string;
  period_end: string;
  summary: string;
  narrative: string;
  created_at: string;
};

const TYPE_LABELS: Record<string, string> = {
  daily: "Kunlik",
  weekly: "Haftalik",
  monthly: "Oylik",
  quarterly: "Choraklik",
  annual: "Yillik",
};

export default function ReportsPage() {
  const [data, setData] = useState<Paged<ReportRow> | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [type, setType] = useState("daily");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<ReportRow | null>(null);

  const load = useCallback(() => {
    api
      .get<Paged<ReportRow>>(`/reports?page=${page}&page_size=12`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [page]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  async function generate() {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const report = await api.post<ReportRow>("/reports", { type });
      setNote(`Hisobot loyihasi yaratildi: ${report.title}`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hisobot yaratilmadi.");
    } finally {
      setBusy(false);
    }
  }

  async function approve(report: ReportRow) {
    setBusy(true);
    try {
      await api.post(`/reports/${report.id}/approve`, { note: "Administrator tasdiqladi" });
      setNote("Hisobot tasdiqlandi.");
      setOpen(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tasdiqlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Hisobotlar"
        title="Hisobotlar markazi"
        lede="Kunlik, haftalik va oylik hisobotlar SQL ko‘rsatkichlari asosida shakllanadi. AI xulosa qismini yozadi, raqamlar bazadan olinadi."
        actions={
          <span style={{ display: "flex", gap: 8 }}>
            <select className="select" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="daily">Kunlik</option>
              <option value="weekly">Haftalik</option>
              <option value="monthly">Oylik</option>
            </select>
            <button className="btn primary" disabled={busy} onClick={generate}>
              Hisobot tayyorlash
            </button>
          </span>
        }
      />
      {error && <ErrorNote message={error} />}
      {note && <div className="alert info">ℹ️ {note}</div>}
      {!data && !error && <Loading />}
      {data && (
        <div className="card">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Hisobot</th>
                  <th>Tur</th>
                  <th>Davr</th>
                  <th>Holat</th>
                  <th>Amallar</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((report) => (
                  <tr key={report.id}>
                    <td>
                      <b>{report.title}</b>
                    </td>
                    <td>{TYPE_LABELS[report.type] ?? report.type}</td>
                    <td className="nowrap">
                      {fmtDate(report.period_start)} — {fmtDate(report.period_end)}
                    </td>
                    <td>
                      <Badge tone={report.status === "approved" ? "ok" : "warn"}>
                        {report.status === "approved" ? "Tasdiqlangan" : "Draft"}
                      </Badge>
                    </td>
                    <td className="nowrap">
                      <button className="btn sm" onClick={() => setOpen(report)}>
                        Ko‘rish
                      </button>{" "}
                      <button className="btn sm" onClick={() => void api.file(`/reports/${report.id}/export?format=docx`, `${report.title}.docx`)}>
                        Word
                      </button>{" "}
                      <button className="btn sm" onClick={() => void api.file(`/reports/${report.id}/export?format=pdf`, `${report.title}.pdf`)}>
                        PDF
                      </button>
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <Empty title="Hisobot yo‘q" icon="▤" note="«Hisobot tayyorlash» tugmasi bilan birinchisini yarating." />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager meta={data.meta} onPage={setPage} />
        </div>
      )}
      {open && (
        <div className="card mb">
          <div className="card-head">
            <h3>{open.title}</h3>
            <Badge tone={open.status === "approved" ? "ok" : "warn"}>
              {open.status === "approved" ? "Tasdiqlangan" : "Draft"}
            </Badge>
          </div>
          <div className="card-pad">
            <div style={{ whiteSpace: "pre-wrap", fontSize: 14.5, lineHeight: 1.7 }}>{open.narrative || open.summary}</div>
            <div className="mt" style={{ display: "flex", gap: 8 }}>
              {open.status !== "approved" && (
                <button className="btn primary" disabled={busy} onClick={() => void approve(open)}>
                  Tasdiqlash
                </button>
              )}
              <button className="btn" onClick={() => setOpen(null)}>
                Yopish
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
