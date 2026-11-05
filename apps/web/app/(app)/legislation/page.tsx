"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Info, Scale } from "@/components/ui/icons";
import { Badge, Empty, ErrorNote, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type DocRow = {
  id: string;
  title: string;
  number: string;
  doc_type: string;
  legal_status: string;
  retrieved_at: string;
  source_url: string;
  chunk_count?: number;
};
type Status = { documents: number; chunks: number; last_synced_at: string | null; source: string };
type SearchHit = { document: DocRow; chunk: { id: string; article: string; heading: string; content: string }; score: number };

export default function LegislationPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ answer: string; sources: { index: number; title: string; article: string; url: string }[]; warnings: string[] } | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<Status>("/legislation/status").then(setStatus).catch(() => {});
    api
      .get<{ items: DocRow[] }>("/legislation/documents")
      .then((data) => setDocs(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const search = useCallback(() => {
    if (q.trim().length < 2) { setHits(null); return; }
    api
      .get<{ items: SearchHit[] }>(`/legislation/search?q=${encodeURIComponent(q)}`)
      .then((data) => setHits(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, [q]);

  useEffect(() => {
    const timer = setTimeout(search, 350);
    return () => clearTimeout(timer);
  }, [search]);

  async function sync() {
    if (q.trim().length < 2) {
      setError("Sinxronlash uchun kalit so‘z kiriting.");
      return;
    }
    setBusy(true);
    setError("");
    setNote("");
    try {
      const result = await api.post<{ documents: DocRow[] }>("/legislation/sync", { query: q, limit: 2 });
      setNote(`Lex.uz dan ${result.documents.length} ta hujjat yuklab olindi.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sinxronlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    if (question.trim().length < 3) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      setAnswer(await api.post("/legislation/ask", { question, use_ai: true, sync_if_empty: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Savolga javob olinmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Qonunchilik bazasi"
        title="Qonunchilik (Lex.uz)"
        lede={
          status
            ? `${status.documents} hujjat, ${status.chunks} parça. Oxirgi sinxronlash: ${fmtDateTime(status.last_synced_at)}. Manba: lex.uz (jonli).`
            : "Qonunchilik hujjatlari Lex.uz dan jonli yuklanadi."
        }
        actions={
          <button className="btn primary" disabled={busy} onClick={sync}>
            <Scale size={15} /> Lex.uz dan yuklash
          </button>
        }
      />
      {error && <ErrorNote message={error} />}
      {note && (
        <div className="alert info" role="status">
          <Info size={16} />
          <span>{note}</span>
        </div>
      )}

      <div className="card card-pad mb">
        <h3 className="mb">Savol-javob (manbali)</h3>
        <div className="field">
          <label htmlFor="leg-question">Savolingiz</label>
          <textarea
            id="leg-question"
            className="textarea"
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Masalan: Ishsizlik nafaqasi qanday tayinlanadi?"
          />
        </div>
        <button className="btn primary" disabled={busy || question.trim().length < 3} onClick={ask}>
          {busy ? "Manbalar o‘rganilmoqda…" : "Javob olish"}
        </button>
        {answer && (
          <div className="mt">
            <div className="narrative pre-wrap">{answer.answer}</div>
            {answer.sources.length > 0 && (
              <div className="src-list mt">
                {answer.sources.map((source) => (
                  <div key={source.index}>
                    [{source.index}] {source.title} — {source.article || "umumiy qoida"}{" "}
                    <a className="link" href={source.url} target="_blank" rel="noreferrer">
                      Lex.uz da ochish ↗
                    </a>
                  </div>
                ))}
              </div>
            )}
            {answer.warnings.map((warning) => (
              <div key={warning} className="alert warn mt">
                <AlertTriangle size={16} />
                <span>{warning}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card card-pad mb">
        <h3 className="mb">Hujjatlar ichidan qidirish</h3>
        <input className="input" placeholder="Kalit so‘z…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Qonunchilik hujjatlarida qidirish" />
      </div>

      {hits && hits.length > 0 && (
        <div className="card mb">
          <div className="card-head">
            <h3>Qidiruv natijalari</h3>
          </div>
          <div className="card-pad">
            <div className="timeline">
              {hits.map((hit) => (
                <div className="tl-item" key={`${hit.document.id}-${hit.chunk.id}`}>
                  <span className="tl-dot" aria-hidden="true" />
                  <div className="tl-body">
                    <h4>
                      {hit.document.title} {hit.chunk.article && <Badge tone="brand">{hit.chunk.article}</Badge>}
                    </h4>
                    <div className="desc">{hit.chunk.content.slice(0, 260)}…</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-head">
          <h3>Saqlangan hujjatlar</h3>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Hujjat</th>
                <th>Raqami</th>
                <th>Tur</th>
                <th>Holat</th>
                <th>Parça</th>
                <th>Manba</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td data-label="Hujjat">{doc.title.slice(0, 90)}{doc.title.length > 90 ? "…" : ""}</td>
                  <td className="mono" data-label="Raqami">{doc.number || "—"}</td>
                  <td data-label="Tur">{doc.doc_type || "—"}</td>
                  <td data-label="Holat">
                    <Badge tone={doc.legal_status === "amaldagi" ? "ok" : "muted"}>{doc.legal_status}</Badge>
                  </td>
                  <td data-label="Parça">{doc.chunk_count ?? "—"}</td>
                  <td data-label="Manba">
                    <a className="link" href={doc.source_url} target="_blank" rel="noreferrer">
                      Lex.uz ↗
                    </a>
                  </td>
                </tr>
              ))}
              {docs.length === 0 && (
                <tr>
                  <td colSpan={6}>
                    <Empty title="Hujjat yo‘q" note="Kalit so‘z bilan Lex.uz dan yuklab oling." art="document" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
