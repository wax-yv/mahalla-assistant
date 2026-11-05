"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Download, Plus } from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
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

  return (
    <>
      <PageHead
        kicker="Hisobotlar"
        title="Hisobotlar markazi"
        lede="Kunlik, haftalik va oylik hisobotlar SQL ko'rsatkichlari asosida shakllanadi. AI xulosa qismini yozadi, raqamlar bazadan olinadi."
        actions={
          <span style={{ display: "flex", gap: 8 }}>
            <select className="select" value={type} onChange={(e) => setType(e.target.value)} aria-label="Hisobot turi">
              <option value="daily">Kunlik</option>
              <option value="weekly">Haftalik</option>
              <option value="monthly">Oylik</option>
            </select>
            <button className="btn primary" disabled={busy} onClick={() => void generate()}>
              <Plus size={16} /> Hisobot tayyorlash
            </button>
          </span>
        }
      />
      {error && <div className="alert danger" role="alert">{error}</div>}
      {note && <div className="alert success" role="alert">{note}</div>}
      {!data && !error && <SkeletonList rows={4} />}
      {data && (
        <div className="card">
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th>Hisobot</th><th>Tur</th><th>Davr</th><th>Holat</th><th>Amallar</th></tr></thead>
              <tbody>
                {data.items.map((report) => (
                  <tr key={report.id}>
                    <td><b style={{ fontWeight: 600 }}>{report.title}</b></td>
                    <td>{TYPE_LABELS[report.type] ?? report.type}</td>
                    <td className="nowrap">{fmtDate(report.period_start)} — {fmtDate(report.period_end)}</td>
                    <td>
                      <Badge tone={report.status === "approved" ? "ok" : "warn"}>
                        {report.status === "approved" ? "Tasdiqlangan" : "Draft"}
                      </Badge>
                    </td>
                    <td className="nowrap">
                      <button className="btn sm" onClick={() => setOpen(report)}>Ko'rish</button>{" "}
                      <button className="btn sm" onClick={() => void api.file(`/reports/${report.id}/export?format=docx`, `${report.title}.docx`)} aria-label="Word yuklab olish">
                        <Download size={13} /> Word
                      </button>{" "}
                      <button className="btn sm" onClick={() => void api.file(`/reports/${report.id}/export?format=pdf`, `${report.title}.pdf`)} aria-label="PDF yuklab olish">
                        <Download size={13} /> PDF
                      </button>
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr><td colSpan={5}><Empty title="Hisobot yo'q" note="«Hisobot tayyorlash» tugmasi bilan birinchisini yarating." /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          {data.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{data.meta.total} ta hisobot · {data.meta.page}/{data.meta.total_pages}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
                <button className="btn sm" disabled={page >= data.meta.total_pages} onClick={() => setPage(page + 1)}>›</button>
              </span>
            </div>
          )}
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
            <div style={{ fontSize: 14.5, lineHeight: 1.75, whiteSpace: "pre-wrap" }}>{open.narrative || open.summary}</div>
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
