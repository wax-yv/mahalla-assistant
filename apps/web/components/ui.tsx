"use client";

import type { ReactNode } from "react";
import type { PageMeta } from "@/lib/api";

export function Badge({ tone = "muted", children }: { tone?: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="card stat">
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Empty({ title, note, icon = "🗂️" }: { title: string; note?: string; icon?: string }) {
  return (
    <div className="empty">
      <div className="icon" aria-hidden="true">{icon}</div>
      <h3>{title}</h3>
      {note && <p>{note}</p>}
    </div>
  );
}

export function Loading({ label = "Yuklanmoqda…" }: { label?: string }) {
  return <div className="loading">{label}</div>;
}

export function ErrorNote({ message }: { message: string }) {
  return <div className="alert danger">⚠️ {message}</div>;
}

export function Pager({
  meta,
  onPage,
}: {
  meta?: PageMeta;
  onPage: (page: number) => void;
}) {
  if (!meta || meta.total_pages <= 1) return null;
  return (
    <div className="pager">
      <span>
        {meta.total} ta yozuv · {meta.page}/{meta.total_pages} sahifa
      </span>
      <span style={{ display: "flex", gap: 8 }}>
        <button className="btn sm" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>
          ‹ Oldingi
        </button>
        <button
          className="btn sm"
          disabled={meta.page >= meta.total_pages}
          onClick={() => onPage(meta.page + 1)}
        >
          Keyingi ›
        </button>
      </span>
    </div>
  );
}

export function PageHead({
  kicker,
  title,
  lede,
  actions,
}: {
  kicker: string;
  title: string;
  lede?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <div className="kicker">{kicker}</div>
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {actions && <div className="head-actions">{actions}</div>}
    </div>
  );
}
