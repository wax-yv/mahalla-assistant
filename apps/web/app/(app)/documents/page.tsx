"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, CheckCircle2, Download, FileSpreadsheet, FileText, Trash2, Upload,
} from "@/components/ui/icons";
import { Badge, Empty, PageHead } from "@/components/ui";
import { ConfirmDialog, Drawer, ErrorState, SkeletonList, useToast } from "@/components/ui/overlays";
import { Field } from "@/components/ui/inputs";
import { api, type Paged } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type DocRow = { id: string; original_name: string; size: number; kind: string; status: string; created_at: string };
type ImportErrorRow = { id: string; row_number: number; column?: string | null; code: string; message: string; severity: string };
type Analysis = {
  batch: { id: string; status: string; mapping: Record<string, string>; summary: Record<string, unknown>; error_count: number; warning_count: number };
  headers: string[]; sheet?: string | null; available_sheets?: string[] | null;
  preview_rows: Record<string, string>[];
  errors: ImportErrorRow[]; warnings: ImportErrorRow[]; can_commit: boolean;
};

const FIELD_LABELS: Record<string, string> = {
  external_id: "Tashqi ID", full_name: "F.I.Sh. (majburiy)", gender: "Jinsi", birth_date: "Tug'ilgan sana",
  phone: "Telefon", mahalla: "Mahalla", street: "Ko'cha", house_number: "Uy raqami",
  family_external_id: "Oila ID", family_role: "Oiladagi o'rni", education: "Ma'lumoti",
  employment_status: "Bandligi", profession: "Kasbi", social_status: "Ijtimoiy holati",
  needs: "Ehtiyoji", notes: "Izoh",
};
const MODULES = ["citizens", "families", "houses", "tasks", "cases"];

function stepperIndex(analysis: Analysis | null, uploading: boolean): number {
  if (uploading) return 1;
  if (!analysis) return 0;
  if (analysis.batch.status === "committed") return 6;
  if (analysis.errors.length > 0) return 5;
  return 4;
}

function Stepper({ step }: { step: number }) {
  const steps = ["Fayl", "Tahlil", "Varaq", "Mapping", "Preview", "Xatolar", "Commit"];
  return (
    <div className="stepper" aria-label="Import bosqichi">
      {steps.map((label, index) => (
        <span key={label} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span className={`step ${index < step ? "done" : index === step ? "current" : ""}`}>
            {index < step ? <CheckCircle2 size={13} /> : <span className="num">{index + 1}</span>}
            {label}
          </span>
          {index < steps.length - 1 && <span className="sep" aria-hidden="true">›</span>}
        </span>
      ))}
    </div>
  );
}

export default function DocumentsPage() {
  const toast = useToast();
  const [docs, setDocs] = useState<Paged<DocRow> | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [page, setPage] = useState(1);
  const [drag, setDrag] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<"all" | "error" | "warning">("all");
  const [commitOpen, setCommitOpen] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocRow | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editableMapping, setEditableMapping] = useState<Record<string, string>>({});
  const [selectedSheet, setSelectedSheet] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");

  const load = useCallback(() => {
    api
      .get<Paged<DocRow>>(`/documents?page=${page}&page_size=15`)
      .then(setDocs)
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [page]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  async function uploadFile(file: File) {
    setBusy(true);
    setUploading(true);
    setError("");
    setNote("");
    setAnalysis(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("analyze", "true");
      const result = await api.upload<{ document: DocRow; analysis?: Analysis }>("/documents", form);
      setAnalysis(result.analysis ?? null);
      setEditableMapping({ ...(result.analysis?.batch.mapping ?? {}) });
      setSelectedSheet(result.analysis?.sheet ?? "");
      setNote(`Fayl yuklandi: ${result.document.original_name}`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yuklash amalga oshmadi.");
    } finally {
      setBusy(false);
      setUploading(false);
    }
  }

  async function reanalyze(sheetOverride?: string) {
    if (!analysis) return;
    setBusy(true);
    try {
      const result = await api.post<Analysis>(`/documents/imports/${analysis.batch.id}/analyze`, {
        mapping: editableMapping,
        sheet: sheetOverride ?? selectedSheet ?? undefined,
      });
      setAnalysis(result);
      setEditableMapping({ ...result.batch.mapping });
      setSelectedSheet(result.sheet ?? "");
      setNote("Mapping yangilandi va qayta tahlil qilindi.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Qayta tahlil amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!analysis) return;
    setCommitting(true);
    try {
      const result = await api.post<{ created: number; updated: number; skipped: number }>(
        `/documents/imports/${analysis.batch.id}/commit`,
        { idempotency_key: `ui-${analysis.batch.id}` }
      );
      setNote(`Import yakunlandi: ${result.created} yangi, ${result.updated} yangilandi, ${result.skipped} o'tkazib yuborildi.`);
      setAnalysis(null);
      setCommitOpen(false);
      if (fileRef.current) fileRef.current.value = "";
      setFileName("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Importni yakunlash amalga oshmadi.");
    } finally {
      setCommitting(false);
    }
  }

  async function rollback() {
    if (!analysis) return;
    setBusy(true);
    try {
      await api.post(`/documents/imports/${analysis.batch.id}/rollback`);
      setNote("Import bekor qilindi.");
      setAnalysis(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bekor qilish amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  async function exportModule(module: string, format: string) {
    await api.file(`/exports/${module}?format=${format}`, `${module}.${format}`);
  }

  async function deleteDoc() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.del(`/documents/${deleteTarget.id}`);
      toast.show("success", `${deleteTarget.original_name} o'chirildi.`);
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast.show("error", err instanceof Error ? err.message : "O'chirish amalga oshmadi.");
    } finally {
      setDeleting(false);
    }
  }

  const allIssues = analysis ? [...analysis.errors, ...analysis.warnings] : [];
  const filteredIssues = allIssues.filter((item) =>
    severityFilter === "all" ? true : item.severity === severityFilter
  );

  return (
    <>
      <PageHead
        kicker="Hujjatlar"
        title="Hujjatlar va ma'lumot almashinuvi"
        lede="Excel, CSV, Word va PDF fayllarini yuklang — ustunlar aniqlanadi, xatolar hisoboti beriladi, tasdiqingiz bilan bazaga yoziladi."
      />
      {error && <div className="alert danger" role="alert">{error}</div>}
      {note && <div className="alert success" role="alert">{note}</div>}

      <Stepper step={stepperIndex(analysis, uploading)} />

      <div className="split s2 mb">
        <div className="card card-pad">
          <h3 className="mb">Hujjat yuklash</h3>
          <div
            className={`dropzone ${drag ? "drag" : ""}`}
            role="button"
            tabIndex={0}
            aria-label="Fayl yuklash maydoni"
            onClick={() => fileRef.current?.click()}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const file = e.dataTransfer.files?.[0];
              if (file) { setFileName(file.name); void uploadFile(file); }
            }}
          >
            <Upload size={22} style={{ color: "var(--color-text-muted)" }} />
            <span className="dz-title">{fileName || "Faylni bu yerga tashlang yoki bosing"}</span>
            <span className="dz-sub">XLSX · CSV · DOCX · PDF — maksimal 4 MB</span>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.csv,.docx,.pdf"
            style={{ display: "none" }}
            aria-label="Fayl tanlash"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) { setFileName(file.name); void uploadFile(file); }
            }}
          />
          {busy && uploading && <p className="loading" style={{ padding: "14px 0 0" }}>Tahlil qilinmoqda…</p>}
        </div>
        <div className="card card-pad">
          <h3 className="mb">Eksport</h3>
          <div className="grid grid-2">
            {MODULES.map((module) => (
              <div key={module} style={{ display: "flex", gap: 6 }}>
                <button className="btn sm" onClick={() => void exportModule(module, "xlsx")}><FileSpreadsheet size={14} /> {module} .xlsx</button>
                <button className="btn sm" onClick={() => void exportModule(module, "csv")}>.csv</button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {analysis && (
        <div className="card mb">
          <div className="card-head">
            <h3>Import tahlili</h3>
            <Badge tone={analysis.can_commit ? "ok" : "warn"}>
              {analysis.can_commit ? "Tasdiqlash mumkin" : `Commit mumkin emas — xatolar: ${analysis.batch.error_count}`}
            </Badge>
          </div>
          <div className="card-pad">
            <div className="field mb">
              <label>Ustun mapping'i — tahrirlab qayta tahlil qilishingiz mumkin</label>
              <div className="grid grid-2">
                {Object.keys(FIELD_LABELS).map((field) => (
                  <div key={field} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ minWidth: 150, fontSize: 13 }} className="text-soft">{FIELD_LABELS[field]}</span>
                    <select
                      className="select" style={{ flex: 1 }}
                      value={editableMapping[field] ?? ""}
                      onChange={(event) =>
                        setEditableMapping((prev) => {
                          const next = { ...prev };
                          if (event.target.value) next[field] = event.target.value;
                          else delete next[field];
                          return next;
                        })
                      }
                    >
                      <option value="">— moslanmagan —</option>
                      {analysis.headers.map((header) => <option key={header} value={header}>{header}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="btn sm" disabled={busy} onClick={() => void reanalyze()}>Qayta tahlil qilish</button>
              </div>
            </div>
            {(analysis.available_sheets?.length ?? 0) > 1 && (
              <Field label={`Excel varaq — faylda ${analysis.available_sheets!.length} ta varaq`} htmlFor="sheet-select">
                <select
                  id="sheet-select" className="select" style={{ maxWidth: 280 }}
                  value={selectedSheet || analysis.sheet || ""}
                  onChange={(event) => { setSelectedSheet(event.target.value); void reanalyze(event.target.value); }}
                >
                  {analysis.available_sheets!.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </Field>
            )}
            <dl className="kv mb">
              <dt>Fayl sarlavhalari</dt><dd>{analysis.headers.join(" · ")}</dd>
              <dt>Qatorlar</dt>
              <dd>Jami: {(analysis.batch.summary as { total_rows?: number })?.total_rows ?? "—"} · yaroqli: {(analysis.batch.summary as { valid_rows?: number })?.valid_rows ?? "—"}</dd>
              <dt>Xatolar</dt><dd className="num">{analysis.batch.error_count}</dd>
              <dt>Ogohlantirishlar</dt><dd className="num">{analysis.batch.warning_count}</dd>
            </dl>

            {analysis.preview_rows.length > 0 && (
              <>
                <h3 style={{ marginBottom: 10 }}>Preview (birinchi {Math.min(10, analysis.preview_rows.length)} qator)</h3>
                <div className="table-wrap mb">
                  <table className="data" style={{ minWidth: 480 }}>
                    <thead>
                      <tr>{Object.keys(analysis.preview_rows[0]).slice(0, 8).map((key) => <th key={key}>{key}</th>)}</tr>
                    </thead>
                    <tbody>
                      {analysis.preview_rows.slice(0, 10).map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          {Object.keys(analysis.preview_rows[0]).slice(0, 8).map((key) => (
                            <td key={key}>{String(row[key] ?? "—").slice(0, 40) || <span className="text-faint">—</span>}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {allIssues.length > 0 && (
              <>
                <div className="chips" role="group" aria-label="Muammo turlari">
                  {Array.from(
                    allIssues.reduce((map, item) => {
                      map.set(item.code, { count: (map.get(item.code)?.count ?? 0) + 1, severity: item.severity });
                      return map;
                    }, new Map<string, { count: number; severity: string }>())
                  )
                    .sort((a, b) => (b[1] as { count: number }).count - (a[1] as { count: number }).count)
                    .map(([code, info]) => (
                      <button
                        key={code as string}
                        className={`chip ${severityFilter !== "all" && (info as { severity: string }).severity !== severityFilter ? "" : "active"}`}
                        onClick={() => setSeverityFilter((info as { severity: string }).severity as "error" | "warning")}
                      >
                        {code} — {(info as { count: number }).count}
                      </button>
                    ))}
                  <button className="chip" onClick={() => setSeverityFilter("all")}>Barchasi</button>
                </div>
                <div className="table-wrap mb">
                  <table className="data">
                    <thead><tr><th>Qator</th><th>Tur</th><th>Kod</th><th>Xabar</th></tr></thead>
                    <tbody>
                      {filteredIssues.slice(0, 12).map((row) => (
                        <tr key={row.id}>
                          <td className="num">{row.row_number}</td>
                          <td>
                            <Badge tone={row.severity === "error" ? "danger" : "warn"}>
                              {row.severity === "error" ? "Xato" : "Ogohlantirish"}
                            </Badge>
                          </td>
                          <td className="mono">{row.code}</td>
                          <td>{row.message}{row.column ? ` (${row.column})` : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {filteredIssues.length > 12 && <p className="text-faint" style={{ fontSize: 12.5 }}>va yana {filteredIssues.length - 12} ta muammo…</p>}
              </>
            )}

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn primary" disabled={!analysis.can_commit || busy} onClick={() => setCommitOpen(true)}>
                Bazaga yozish (tasdiqlash)
              </button>
              {!analysis.can_commit && (
                <span className="text-faint" style={{ fontSize: 12.5, alignSelf: "center" }}>
                  Sabab: {analysis.batch.error_count} ta xato — ularni to'g'irlang yoki faylni qayta yuklang.
                </span>
              )}
              <button className="btn danger" disabled={busy} onClick={() => void rollback()}>Importni bekor qilish</button>
            </div>
          </div>
        </div>
      )}

      {!docs && !error && <SkeletonList rows={4} />}
      {docs && (
        <div className="card">
          <div className="card-head"><h3>Yuklangan hujjatlar</h3></div>
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table className="data">
              <thead><tr><th>Nomi</th><th>Tur</th><th>Hajm</th><th>Holat</th><th>Yuklandi</th><th aria-label="Amallar" /></tr></thead>
              <tbody>
                {docs.items.map((doc) => (
                  <tr key={doc.id}>
                    <td><FileText size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "-2px" }} />{doc.original_name}</td>
                    <td className="mono">{doc.kind}</td>
                    <td className="num">{(doc.size / 1024).toFixed(1)} KB</td>
                    <td><Badge tone={doc.status === "archived" ? "muted" : "ok"}>{doc.status}</Badge></td>
                    <td className="nowrap">{fmtDateTime(doc.created_at)}</td>
                    <td className="nowrap">
                      <a className="icon-btn" href={`/api/v1/documents/${doc.id}/download`} aria-label={`${doc.original_name} yuklab olish`} title="Yuklab olish">
                        <Download size={15} />
                      </a>
                      <button className="icon-btn danger" aria-label={`${doc.original_name} o'chirish`} title="O'chirish" onClick={() => setDeleteTarget(doc)}>
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
                {docs.items.length === 0 && (
                  <tr><td colSpan={6}><Empty title="Hujjat yo'q" note="Birinchi faylni yuklab, aholi bazasini yangilang." icon={<FileText size={18} />} /></td></tr>
                )}
              </tbody>
            </table>
          </div>
          {docs.meta.total_pages > 1 && (
            <div className="pager">
              <span className="num">{docs.meta.total} ta hujjat · {docs.meta.page}/{docs.meta.total_pages}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
                <button className="btn sm" disabled={page >= docs.meta.total_pages} onClick={() => setPage(page + 1)}>›</button>
              </span>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={commitOpen}
        onClose={() => setCommitOpen(false)}
        onConfirm={() => void commit()}
        title="Importni tasdiqlash"
        message={`Tahlil natijasidagi ma'lumotlar bazaga yoziladi (yaroqli qatorlar). Importni keyinchalik bekor qilish imkoni bor. Davom etamizmi?`}
        confirmLabel="Bazaga yozish"
        danger={false}
        busy={committing}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => void deleteDoc()}
        title="Hujjatni o'chirish"
        message={`«${deleteTarget?.original_name}» fayli o'chiriladi. Bu amalni qaytarib bo'lmaydi. Davom etamizmi?`}
        confirmLabel="O'chirish"
        busy={deleting}
      />
    </>
  );
}
