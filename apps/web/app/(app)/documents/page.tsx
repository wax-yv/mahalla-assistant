"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, Pager, PageHead } from "@/components/ui";
import { api, type Paged } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type DocRow = { id: string; original_name: string; size: number; kind: string; status: string; created_at: string };
type ImportErrorRow = { id: string; row_number: number; column?: string | null; code: string; message: string; severity: string };
type Analysis = {
  batch: { id: string; status: string; mapping: Record<string, string>; summary: Record<string, unknown>; error_count: number; warning_count: number };
  headers: string[];
  sheet?: string | null;
  available_sheets?: string[] | null;
  preview_rows: Record<string, string>[];
  errors: ImportErrorRow[];
  warnings: ImportErrorRow[];
  can_commit: boolean;
};

const FIELD_LABELS: Record<string, string> = {
  external_id: "Tashqi ID",
  full_name: "F.I.Sh. (majburiy)",
  gender: "Jinsi",
  birth_date: "Tug'ilgan sana",
  phone: "Telefon",
  mahalla: "Mahalla",
  street: "Ko'cha",
  house_number: "Uy raqami",
  family_external_id: "Oila ID",
  family_role: "Oiladagi o'rni",
  education: "Ma'lumoti",
  employment_status: "Bandligi",
  profession: "Kasbi",
  social_status: "Ijtimoiy holati",
  needs: "Ehtiyoji",
  notes: "Izoh",
};

const MODULES = ["citizens", "families", "houses", "tasks", "cases"];

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Paged<DocRow> | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [editableMapping, setEditableMapping] = useState<Record<string, string>>({});
  const [selectedSheet, setSelectedSheet] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const fileRef = useRef<HTMLInputElement>(null);

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

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Fayl tanlanmagan.");
      return;
    }
    setBusy(true);
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
    }
  }

  async function reanalyze(sheetOverride?: string) {
    if (!analysis) return;
    setBusy(true);
    setError("");
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
    setBusy(true);
    try {
      const result = await api.post<{ created: number; updated: number; skipped: number }>(
        `/documents/imports/${analysis.batch.id}/commit`,
        { idempotency_key: `ui-${analysis.batch.id}` }
      );
      setNote(`Import yakunlandi: ${result.created} yangi, ${result.updated} yangilandi, ${result.skipped} o'tkazib yuborildi.`);
      setAnalysis(null);
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Importni yakunlash amalga oshmadi.");
    } finally {
      setBusy(false);
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

  return (
    <>
      <PageHead
        kicker="Hujjatlar"
        title="Hujjatlar va ma'lumot almashinuvi"
        lede="Excel, CSV va Word fayllarini yuklang — tizim ustunlarni aniqlab, xatolarni ko‘rsatadi va tasdiqlangandan keyin bazaga yozadi."
      />
      {error && <ErrorNote message={error} />}
      {note && <div className="alert info">ℹ️ {note}</div>}

      <div className="split s2 mb">
        <div className="card card-pad">
          <h3 className="mb">Hujjat yuklash</h3>
          <input ref={fileRef} type="file" accept=".xlsx,.csv,.docx,.pdf" className="input" />
          <div style={{ display: "flex", gap: 8 }} className="mt">
            <button className="btn primary" disabled={busy} onClick={upload}>
              {busy ? "Yuklanmoqda…" : "Yuklash va tahlil qilish"}
            </button>
          </div>
          <p className="text-faint mt" style={{ fontSize: 12.5 }}>
            Maksimal hajm: 4 MB. Qo‘llanadigan formatlar: .xlsx, .csv, .docx, .pdf
          </p>
        </div>
        <div className="card card-pad">
          <h3 className="mb">Eksport</h3>
          <div className="grid grid-2">
            {MODULES.map((module) => (
              <div key={module} style={{ display: "flex", gap: 6 }}>
                <button className="btn sm" onClick={() => void exportModule(module, "xlsx")}>
                  {module} .xlsx
                </button>
                <button className="btn sm" onClick={() => void exportModule(module, "csv")}>
                  .csv
                </button>
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
              {analysis.can_commit ? "Tasdiqlash mumkin" : `Xatolar: ${analysis.batch.error_count}`}
            </Badge>
          </div>
          <div className="card-pad">
            {(analysis.available_sheets?.length ?? 0) > 1 && (
              <div className="field mb">
                <label>Excel varaq — faylda {analysis.available_sheets!.length} ta varaq bor</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <select
                    className="select"
                    style={{ maxWidth: 280 }}
                    value={selectedSheet || analysis.sheet || ""}
                    onChange={(event) => {
                      setSelectedSheet(event.target.value);
                      void reanalyze(event.target.value);
                    }}
                  >
                    {analysis.available_sheets!.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            <div className="field mb">
              <label>Ustun mapping'i — tahrirlab qayta tahlil qilishingiz mumkin</label>
              <div className="grid grid-2">
                {Object.keys(FIELD_LABELS).map((field) => (
                  <div key={field} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ minWidth: 150, fontSize: 13 }} className="text-soft">
                      {FIELD_LABELS[field]}
                    </span>
                    <select
                      className="select"
                      style={{ flex: 1 }}
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
                      {analysis.headers.map((header) => (
                        <option key={header} value={header}>
                          {header}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="btn sm" disabled={busy} onClick={() => void reanalyze()}>
                  Qayta tahlil qilish
                </button>
              </div>
            </div>
            <dl className="kv mb">
              <dt>Fayl sarlavhalari</dt>
              <dd>{analysis.headers.join(" · ")}</dd>
              <dt>Qatorlar</dt>
              <dd>Jami: {(analysis.batch.summary as any)?.total_rows ?? "—"} · yaroqli: {(analysis.batch.summary as any)?.valid_rows ?? "—"}</dd>
              <dt>Xatolar</dt>
              <dd>{analysis.batch.error_count}</dd>
              <dt>Ogohlantirishlar</dt>
              <dd>{analysis.batch.warning_count}</dd>
            </dl>
            {(() => {
              const all = [...analysis.errors, ...analysis.warnings];
              if (all.length === 0) return null;
              const grouped = Array.from(
                all.reduce((map, item) => {
                  map.set(item.code, { count: (map.get(item.code)?.count ?? 0) + 1, severity: item.severity });
                  return map;
                }, new Map<string, { count: number; severity: string }>())
              ).sort((a, b) => (b[1] as { count: number }).count - (a[1] as { count: number }).count);
              return (
                <div className="chips mb">
                  {grouped.map(([code, info]) => (
                    <span key={code as string} className={`badge ${(info as { severity: string }).severity === "error" ? "danger" : "warn"}`}>
                      {code} — {(info as { count: number }).count}
                    </span>
                  ))}
                </div>
              );
            })()}
            {analysis.errors.length > 0 && (
              <div className="table-wrap mb">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Qator</th>
                      <th>Ustun</th>
                      <th>Xatolik</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.errors.slice(0, 8).map((row) => (
                      <tr key={row.id}>
                        <td>{row.row_number}</td>
                        <td className="mono">{row.column ?? "—"}</td>
                        <td>{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {analysis.warnings.length > 0 && (
              <div className="table-wrap mb">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Qator</th>
                      <th>Tur</th>
                      <th>Ogohlantirish</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.warnings.slice(0, 8).map((row) => (
                      <tr key={row.id}>
                        <td>{row.row_number}</td>
                        <td className="mono">{row.code}</td>
                        <td>{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn primary" disabled={!analysis.can_commit || busy} onClick={commit}>
                Bazaga yozish (tasdiqlash)
              </button>
              <button className="btn danger" disabled={busy} onClick={rollback}>
                Importni bekor qilish
              </button>
            </div>
          </div>
        </div>
      )}

      {!docs && !error && <Loading />}
      {docs && (
        <div className="card">
          <div className="card-head">
            <h3>Yuklangan hujjatlar</h3>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Nomi</th>
                  <th>Tur</th>
                  <th>Hajm</th>
                  <th>Holat</th>
                  <th>Yuklandi</th>
                </tr>
              </thead>
              <tbody>
                {docs.items.map((doc) => (
                  <tr key={doc.id}>
                    <td>{doc.original_name}</td>
                    <td className="mono">{doc.kind}</td>
                    <td>{(doc.size / 1024).toFixed(1)} KB</td>
                    <td>
                      <Badge tone={doc.status === "archived" ? "muted" : "ok"}>{doc.status}</Badge>
                    </td>
                    <td className="nowrap">{fmtDateTime(doc.created_at)}</td>
                  </tr>
                ))}
                {docs.items.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <Empty title="Hujjat yo‘q" icon="◫" note="Birinchi Excel faylni yuklab, aholi bazasini yangilang." />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <Pager meta={docs.meta} onPage={setPage} />
        </div>
      )}
    </>
  );
}
