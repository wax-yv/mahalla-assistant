"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowRight, ChevronLeft, ChevronRight, TrendingDown, TrendingUp } from "@/components/ui/icons";
import { EmptyArt, type EmptyArtKind } from "@/components/EmptyArt";
import type { PageMeta } from "@/lib/api";

export function Badge({ tone = "muted", children, pulse }: { tone?: string; children: ReactNode; pulse?: boolean }) {
  return <span className={`badge ${tone}${pulse ? " pulse-dot" : ""}`}>{children}</span>;
}

export type StatIconTone = "teal" | "coral" | "amber" | "sky" | "plum";

/**
 * Premium KPI stat-card (audit 7.3 / P2-3).
 * — 44px gradient ikon
 * — ixtiyoriy trend badge (faqat haqiqiy ma’lumot bo‘lsa)
 * — ixtiyoriy sparkline (7 kun, SVG)
 * — butun karta link (overlay-link)
 */
export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "teal",
  trend,
  sparkline,
  link,
  linkLabel,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  tone?: StatIconTone;
  trend?: { delta: string; up: boolean };
  sparkline?: number[];
  link?: string;
  linkLabel?: string;
}) {
  return (
    <div className="card stat stat-hover">
      <div className="stat-top">
        {icon ? (
          <span className={`stat-icon ${tone}`} aria-hidden="true">
            {icon}
          </span>
        ) : null}
        {trend ? (
          <span className={`stat-trend ${trend.up ? "up" : "down"}`}>
            {trend.up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {trend.delta}
          </span>
        ) : null}
      </div>
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {hint && <span className="hint">{hint}</span>}
      {sparkline && sparkline.length > 1 ? <Sparkline values={sparkline} /> : null}
      {link ? <Link className="overlay-link" href={link} aria-label={linkLabel ?? `${label} — bo‘limga o‘tish`} /> : null}
    </div>
  );
}

/** Mini area sparkline (SVG, kutubxonasiz) */
export function Sparkline({ values, className = "stat-spark" }: { values: number[]; className?: string }) {
  const w = 160;
  const h = 34;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = w / (values.length - 1);
  const points = values.map((v, i) => {
    const x = i * step;
    const y = h - 3 - ((v - min) / span) * (h - 6);
    return [x, y] as const;
  });
  const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;
  return (
    <svg className={className} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={area} fill="var(--brand-soft)" />
      <path d={line} fill="none" stroke="var(--brand-600)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Avvalgi Stat (backward-compatible) — premium StatCard bilan bir xil ko‘rinish */
export function Stat({ label, value, hint, icon, tone = "teal", link }: {
  label: string; value: ReactNode; hint?: string; icon?: ReactNode; tone?: StatIconTone; link?: string;
}) {
  return <StatCard label={label} value={value} hint={hint} icon={icon} tone={tone} link={link} />;
}

export function Empty({
  title,
  note,
  icon,
  art = "search",
}: {
  title: string;
  note?: string;
  icon?: ReactNode;
  art?: EmptyArtKind;
}) {
  return (
    <div className="empty">
      {icon ? <div className="icon" aria-hidden="true">{icon}</div> : <EmptyArt kind={art} />}
      <h3>{title}</h3>
      {note && <p>{note}</p>}
    </div>
  );
}

export function Loading({ label = "Ma’lumotlar yuklanmoqda, iltimos kuting…" }: { label?: string }) {
  return <div className="loading">{label}</div>;
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="alert danger" role="alert">
      <AlertTriangle size={16} />
      <span>{message}</span>
    </div>
  );
}

/** Sahifa raqamlari bilan Pager (audit 4.1) */
export function Pager({ meta, onPage }: { meta?: PageMeta; onPage: (page: number) => void }) {
  if (!meta || meta.total_pages <= 1) return null;
  const page = meta.page;
  const total = meta.total_pages;
  const pages: number[] = [];
  const from = Math.max(1, Math.min(page - 2, total - 4));
  const to = Math.min(total, Math.max(page + 2, 5));
  for (let i = from; i <= to; i += 1) pages.push(i);
  return (
    <div className="pager">
      <span>
        {meta.total} ta yozuv · {page}/{total} sahifa
      </span>
      <div className="pager-pages">
        <button className="btn sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Oldingi sahifa">
          <ChevronLeft size={14} /> Oldingi
        </button>
        {pages.map((p) => (
          <button
            key={p}
            className={`pager-page${p === page ? " current" : ""}`}
            aria-current={p === page ? "page" : undefined}
            aria-label={`${p}-sahifa`}
            onClick={() => onPage(p)}
          >
            {p}
          </button>
        ))}
        <button className="btn sm" disabled={page >= total} onClick={() => onPage(page + 1)} aria-label="Keyingi sahifa">
          Keyingi <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

export function PageHead({ kicker, title, lede, actions }: {
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

/** “Barchasi →” turidagi havolalar uchun yagona komponent */
export function SeeAllLink({ href, children }: { href: string; children?: ReactNode }) {
  return (
    <Link className="link row-sm" href={href}>
      {children ?? "Barchasi"}
      <ArrowRight size={13} />
    </Link>
  );
}
