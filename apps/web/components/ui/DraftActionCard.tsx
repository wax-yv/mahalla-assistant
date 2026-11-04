"use client";

import { useState } from "react";
import { Check, ClipboardList, X } from "@/components/ui/icons";
import { Badge } from "@/components/ui";

const DRAFT_LABELS: Record<string, string> = {
  create_task: "Vazifa yaratish",
  create_case: "Murojaat ochish",
  create_worklog: "Ish yozuvini qo'shish",
  generate_report: "Hisobot yaratish",
  sync_legislation: "Qonunchilikni sinxronlash",
  save_preference: "Tanlovni saqlash",
  commit_import: "Importni bazaga yozish",
};

const FIELD_LABELS: Record<string, string> = {
  title: "Nomi", description: "Tavsif", category: "Toifa", priority: "Ustuvorlik",
  due_date: "Muddat", citizen_id: "Fuqaro", target_date: "Nazorat muddati",
  type: "Turi", period_start: "Davr boshi", period_end: "Davr tugashi",
  query: "So'rov", url: "Havola", limit: "Soni", organization: "Tashkilot",
  program_id: "Dastur", program_name: "Dastur nomi", batch_id: "Import partiyasi",
  idempotency_key: "Idempotency kalit", conversation_id: "Suhbat",
};

function humanize(key: string, value: unknown): { label: string; text: string } | null {
  if (value === undefined || value === null || value === "") return null;
  const label = FIELD_LABELS[key] ?? key;
  let text: string;
  if (key === "priority" && typeof value === "string") {
    text = ({ low: "Past", normal: "Oddiy", high: "Yuqori", urgent: "Shoshilinch" } as Record<string, string>)[value] ?? value;
  } else if (typeof value === "boolean") {
    text = value ? "Ha" : "Yo'q";
  } else {
    text = String(value);
  }
  return { label, text };
}

export function DraftActionCard({
  draft, onDecide,
}: {
  draft: { id: string; action_type: string; payload: Record<string, unknown>; status: string; error?: string };
  onDecide: (draft: DraftActionCardDraft, approve: boolean) => void;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const fields = Object.entries(draft.payload ?? {})
    .map(([key, value]) => humanize(key, value))
    .filter((v): v is { label: string; text: string } => v !== null);

  return (
    <div className="draft-card">
      <div className="dc-head">
        <span className="dc-title">
          <ClipboardList size={15} />
          {DRAFT_LABELS[draft.action_type] ?? draft.action_type}
        </span>
        {draft.status === "pending" ? (
          <Badge tone="warn">Tasdiq kutmoqda</Badge>
        ) : draft.status === "approved" ? (
          <Badge tone="ok">Bajarildi</Badge>
        ) : draft.status === "failed" ? (
          <Badge tone="danger">Xatolik</Badge>
        ) : (
          <Badge tone="muted">Rad etilgan</Badge>
        )}
      </div>
      {fields.length > 0 && (
        <dl>
          {fields.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.text}</dd>
            </div>
          ))}
        </dl>
      )}
      {draft.error && <p style={{ fontSize: 13, color: "var(--color-danger)", marginBottom: 8 }}>Xatolik: {draft.error}</p>}
      {draft.status === "pending" ? (
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn sm primary" onClick={() => onDecide(draft, true)}>
            <Check size={14} /> Tasdiqlash
          </button>
          <button className="btn sm danger" onClick={() => onDecide(draft, false)}>
            <X size={14} /> Rad etish
          </button>
          <button className="btn sm ghost" onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "Tafsilotni yopish" : "Texnik tafsilot"}
          </button>
        </div>
      ) : null}
      {showRaw && (
        <pre className="mono" style={{ marginTop: 10, background: "var(--color-surface-3)", padding: 10, borderRadius: 8, overflowX: "auto", fontSize: 11.5 }}>
          {JSON.stringify(draft.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

type DraftActionCardDraft = { id: string; action_type: string; payload: Record<string, unknown>; status: string; error?: string };
