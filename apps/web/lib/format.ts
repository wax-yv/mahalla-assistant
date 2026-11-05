export function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("uz-UZ", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function age(birth?: string | null): string {
  if (!birth) return "—";
  const d = new Date(birth);
  const now = new Date();
  let years = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) years -= 1;
  return `${years} yosh`;
}

export const CASE_STATUS: Record<string, { label: string; tone: string }> = {
  open: { label: "Yangi", tone: "info" },
  in_progress: { label: "Jarayonda", tone: "brand" },
  waiting: { label: "Kutilmoqda", tone: "warn" },
  resolved: { label: "Hal qilindi", tone: "ok" },
  closed: { label: "Yopilgan", tone: "muted" },
  cancelled: { label: "Bekor qilingan", tone: "muted" },
};

export const TASK_STATUS: Record<string, { label: string; tone: string }> = {
  new: { label: "Yangi", tone: "info" },
  in_progress: { label: "Jarayonda", tone: "brand" },
  waiting: { label: "Kutilmoqda", tone: "warn" },
  completed: { label: "Bajarildi", tone: "ok" },
  cancelled: { label: "Bekor qilingan", tone: "muted" },
};

export const PRIORITY: Record<string, { label: string; tone: string }> = {
  low: { label: "Past", tone: "muted" },
  normal: { label: "Oddiy", tone: "info" },
  high: { label: "Yuqori", tone: "warn" },
  urgent: { label: "Shoshilinch", tone: "danger" },
};

export function statusBadge(map: Record<string, { label: string; tone: string }>, key?: string | null) {
  const item = map[key ?? ""] ?? { label: key ?? "—", tone: "muted" };
  return { label: item.label, tone: item.tone };
}
