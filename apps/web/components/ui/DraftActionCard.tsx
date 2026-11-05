"use client";

import { useState } from "react";
import { Check, ClipboardList, X } from "@/components/ui/icons";
import { Badge } from "@/components/ui";

const DRAFT_LABELS: Record<string, string> = {
  create_task: "Vazifa yaratish",
  create_case: "Murojaat ochish",
  create_worklog: "Ish yozuvini qo‘shish",
  generate_report: "Hisobot yaratish",
  sync_legislation: "Qonunchilikni sinxronlash",
  save_preference: "Tanlovni saqlash",
  commit_import: "Importni bazaga yozish",
};

/**
 * P0-9: texnik kalitlar (idempotency_key, batch_id, conversation_id, program_id)
 * foydalanuvchiga ko‘rsatilmaydi — ular faqat “Texnik tafsilot” ichida qoladi.
 */
const HIDDEN_FIELDS = new Set(["idempotency_key", "batch_id", "conversation_id", "program_id", "request_id", "trace_id"]);

const FIELD_LABELS: Record<string, string> = {
  title: "Nomi", description: "Tavsif", category: "Toifa", priority: "Ustuvorlik",
  due_date: "Muddat", citizen_id: "Fuqaro", target_date: "Nazorat muddati",
  type: "Turi", period_start: "Davr boshi", period_end: "Davr tugashi",
  query: "So‘rov", url: "Havola", limit: "Soni", organization: "Tashkilot",
  program_name: "Dastur nomi", evidence_note: "Dalil izohi", assignee: "Mas‘ul",
  amount: "Summa", interest_rate: "Stavka", term_months: "Muddat (oy)",
};

const PRIORITY_LABELS: Record<string, string> = {
  low: "Past", normal: "Oddiy", high: "Yuqori", urgent: "Shoshilinch",
};

/** Enum qiymatlarini tabiiy o‘zbekcha yozishga o‘giradi */
const ENUM_LABELS: Record<string, string> = {
  uchrashuv: "Uchrashuv", telefon: "Telefon", tavsiya: "Tavsiya", hujjat: "Hujjat",
  "bajarilgan ish": "Bajarilgan ish", natija: "Natija", vazifa: "Vazifa", murojaat: "Murojaat",
  credit: "Kredit", subsidy: "Subsidiya", benefit: "Ijtimoiy yordam", grant: "Grant",
  daily: "Kunlik", weekly: "Haftalik", monthly: "Oylik", quarterly: "Choraklik", annual: "Yillik",
  new: "Yangi", in_progress: "Jarayonda", waiting: "Kutilmoqda", completed: "Bajarildi",
  cancelled: "Bekor qilingan", open: "Yangi", resolved: "Hal qilindi", closed: "Yopilgan",
  Ishlaydi: "Ishlaydi", Ishsiz: "Ishsiz", Tadbirkor: "Tadbirkor", Pensioner: "Pensioner",
  "O'qiydi": "O‘qiydi", Ishlamaydi: "Ishlamaydi",
};

function humanizeEnum(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return ENUM_LABELS[value] ?? ENUM_LABELS[value.toLowerCase()] ?? null;
}

function humanize(key: string, value: unknown): { label: string; text: string } | null {
  if (value === undefined || value === null || value === "") return null;
  if (HIDDEN_FIELDS.has(key)) return null;
  const label = FIELD_LABELS[key] ?? key;
  let text: string;
  if (key === "priority" && typeof value === "string") {
    text = PRIORITY_LABELS[value] ?? value;
  } else if (typeof value === "boolean") {
    text = value ? "Ha" : "Yo‘q";
  } else if (Array.isArray(value)) {
    text = value.map((v) => humanizeEnum(v) ?? String(v)).join(", ");
  } else {
    const mapped = humanizeEnum(value);
    text = mapped ?? String(value);
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
          <Badge tone="warn" pulse>Tasdiq kutilmoqda</Badge>
        ) : draft.status === "approved" ? (
          <Badge tone="ok">Bajarildi</Badge>
        ) : draft.status === "failed" ? (
          <Badge tone="danger">Xatolik yuz berdi</Badge>
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
      {draft.error && <p className="fs-13 text-danger-ico mb-sm">Xatolik: {draft.error}</p>}
      {draft.status === "pending" ? (
        <div className="row-sm">
          <button className="btn sm primary" onClick={() => onDecide(draft, true)}>
            <Check size={14} /> Tasdiqlash
          </button>
          <button className="btn sm danger" onClick={() => onDecide(draft, false)}>
            <X size={14} /> Rad etish
          </button>
          <button className="btn sm ghost" onClick={() => setShowRaw((v) => !v)} aria-expanded={showRaw}>
            {showRaw ? "Tafsilotni yopish" : "Texnik tafsilot"}
          </button>
        </div>
      ) : null}
      {showRaw && (
        <pre className="mono code-block">
          {JSON.stringify(draft.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

export type DraftActionCardDraft = { id: string; action_type: string; payload: Record<string, unknown>; status: string; error?: string };
