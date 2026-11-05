"use client";

import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Download, Plus } from "@/components/ui/icons";
import { Badge, Empty, PageHead, Pager } from "@/components/ui";
import { ConfirmDialog, Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { api, type Paged } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type ReportRow = {
  id: string; type: string; title: string; status: string; period_start: string; period_end: string;
  summary: string; narrative: string; created_at: string;
};

const TYPE_LABELS: Record<string, string> = {
  daily: "Kunlik", weekly: "Haftalik", monthly: "Oylik", quarterly: "Choraklik", annual: "Yillik",
};

export default function ReportsPage() {
  const toast = useToast();
  const [data, setData] = useState<Paged<ReportRow> | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [type, setType] = useState("daily");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<ReportRow | null>(null);
  const [approveOpen, setApproveOpen] = useState<ReportRow | null>(null);
  const [approving, setApproving] = useState(false);

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

  async function approve() {
    if (!approveOpen) return;
    setApproving(true);
    try {
      await api.post(`/reports/${approveOpen.id}/approve`, { note: "Administrator tasdiqladi" });
      toast.show("success", "Hisobot tasdiqlandi.");
      setApproveOpen(null);
      setOpen(null);
      load();
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Tasdiqlash amalga oshmadi.");
    } finally {
      setApproving(false);
    }
  }

  async function exportReport(report: ReportRow, format: "docx" | "pdf") {
    try {
      await api.file(`/reports/${report.id}/export?format=${format}`, `${report.title}.${format}`);
      toast.show("success", `${format.toUpperCase()} fayl yuklab olindi.`);
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "Yuklab olish amalga oshmadi.");
    }
  }

  return (
    <>
      <PageHead
        kicker="Hisobotlar"
        title="Hisobotlar markazi"
        lede="Kunlik, haftalik va oylik hisobotlar bazadagi ko‘rsatkichlar asosida shakllanadi. AI xulosa qismini yozadi, raqamlar bazadan olinadi."
        actions={
          <div className="row-sm">
            <select className="select" value={type} onChange={(e) => setType(e.target.value)} aria-label="Hisobot turi">
              <option value="daily">Kunlik</option>
              <option value="weekly">Haftalik</option>
              <option value="monthly">Oylik</option>
            </select>
            <button className="btn primary" disabled={busy} onClick={() => void generate()}>
              <Plus size={16} /> Hisobot tayyorlash
            </button>
          </div>
        }
      />
      {error && <ErrorState note={error} onRetry={load} />}
      {note && <div className="alert success" role="status">{note}</div>}
      {!data && !error && <SkeletonList rows={4} />}
      {data && (
        <div className="card">
          <div className="table-wrap flush">
            <table className="data">
              <thead><tr><th>Hisobot</th><th>Tur</th><th>Davr</th><th>Holat</th><th>Amallar</th></tr></thead>
              <tbody>
                {data.items.map((report) => (
                  <tr key={report.id}>
                    <td data-label="Hisobot"><b className="fw-600">{report.title}</b></td>
                    <td data-label="Tur">{TYPE_LABELS[report.type] ?? report.type}</td>
                    <td className="nowrap" data-label="Davr">{fmtDate(report.period_start)} — {fmtDate(report.period_end)}</td>
                    <td data-label="Holat">
                      <Badge tone={report.status === "approved" ? "ok" : "warn"}>
                        {report.status === "approved" ? "Tasdiqlangan" : "Draft"}
                      </Badge>
                    </td>
                    <td className="nowrap row-wrap" data-label="Amallar">
                      <button className="btn sm" onClick={() => setOpen(report)}>Ko‘rish</button>
                      <button className="btn sm" onClick={() => void exportReport(report, "docx")} aria-label="Word formatida yuklab olish">
                        <Download size={13} /> Word
                      </button>
                      <button className="btn sm" onClick={() => void exportReport(report, "pdf")} aria-label="PDF formatida yuklab olish">
                        <Download size={13} /> PDF
                      </button>
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr><td colSpan={5}><Empty title="Hisobot yo‘q" note="«Hisobot tayyorlash» tugmasi bilan birinchisini yarating." art="chart" /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager meta={data.meta} onPage={setPage} />
        </div>
      )}

      <Drawer
        open={Boolean(open)}
        onClose={() => setOpen(null)}
        title={open?.title ?? ""}
        wide
        footer={
          <>
            {open?.status !== "approved" && (
              <button className="btn primary" disabled={busy} onClick={() => setApproveOpen(open!)}>
                <Check size={15} /> Tasdiqlash
              </button>
            )}
            <button className="btn ghost" onClick={() => setOpen(null)}>Yopish</button>
          </>
        }
      >
        {open && (
          <>
            <div className="meta-row mb">
              <Badge tone={open.status === "approved" ? "ok" : "warn"}>{open.status === "approved" ? "Tasdiqlangan" : "Draft"}</Badge>
              <span>{TYPE_LABELS[open.type] ?? open.type}</span>
              <span>{fmtDate(open.period_start)} — {fmtDate(open.period_end)}</span>
            </div>
            <div className="narrative">
              <div className="md">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer noopener" /> }}
                >
                  {open.narrative || open.summary}
                </ReactMarkdown>
              </div>
            </div>
          </>
        )}
      </Drawer>

      <ConfirmDialog
        open={Boolean(approveOpen)}
        onClose={() => setApproveOpen(null)}
        onConfirm={() => void approve()}
        title="Hisobotni tasdiqlash"
        message={`«${approveOpen?.title}» rasmiy tasdiqlangan hisobot sifatida belgilanadi. Davom etamizmi?`}
        confirmLabel="Tasdiqlash"
        danger={false}
        busy={approving}
      />
    </>
  );
}
