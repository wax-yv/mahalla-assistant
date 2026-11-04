"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDown, LoaderCircle, Search, X } from "lucide-react";

/* ---------- FormField (label + error + hint) ---------- */
export function Field({
  label, required, error, hint, children, htmlFor,
}: {
  label: string; required?: boolean; error?: string; hint?: string; children: ReactNode; htmlFor?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>
        {label} {required && <span className="req" aria-hidden="true">*</span>}
      </label>
      {children}
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
      {!error && hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

/* ---------- SearchSelect (qidiruvli tanlash — mavjud API bilan) ---------- */
export type Option = { value: string; label: string; sub?: string };

export function SearchSelect({
  value, onChange, options, placeholder = "Tanlang…", searchPlaceholder = "Qidirish…", loading = false, emptyText = "Topilmadi", clearable = false, disabled = false, id,
}: {
  value: string; onChange: (value: string) => void; options: Option[];
  placeholder?: string; searchPlaceholder?: string; loading?: boolean; emptyText?: string;
  clearable?: boolean; disabled?: boolean; id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hl, setHl] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) => o.label.toLowerCase().includes(q) || (o.sub ?? "").toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
    );
  }, [options, query]);

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <button
        id={id}
        type="button"
        className="select"
        style={{ display: "flex", alignItems: "center", gap: 8, textAlign: "left", justifyContent: "space-between" }}
        onClick={() => !disabled && setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: selected ? "inherit" : "var(--color-text-muted)" }}>
          {selected ? selected.label : placeholder}
        </span>
        {loading ? <LoaderCircle size={15} className="spin" /> : <ChevronDown size={15} style={{ flexShrink: 0 }} />}
      </button>
      {selected && clearable && !disabled && (
        <button
          className="icon-btn"
          style={{ position: "absolute", right: 30, top: 5 }}
          aria-label="Tozalash"
          onClick={() => { onChange(""); setQuery(""); }}
        >
          <X size={14} />
        </button>
      )}
      {open && (
        <div role="listbox" style={{ position: "absolute", zIndex: "var(--z-dropdown)", top: "calc(100% + 6px)", left: 0, right: 0, background: "var(--color-surface)", border: "1px solid var(--color-border-strong)", borderRadius: "var(--radius-sm)", boxShadow: "var(--shadow-lg)", overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px", borderBottom: "1px solid var(--color-border)" }}>
            <Search size={15} style={{ color: "var(--color-text-muted)", flexShrink: 0 }} />
            <input
              autoFocus
              value={query}
              onChange={(e) => { setQuery(e.target.value); setHl(0); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setHl((h) => Math.min(h + 1, filtered.length - 1)); }
                if (e.key === "ArrowUp") { e.preventDefault(); setHl((h) => Math.max(0, h - 1)); }
                if (e.key === "Enter" && filtered[hl]) { e.preventDefault(); onChange(filtered[hl].value); setOpen(false); }
                if (e.key === "Escape") setOpen(false);
              }}
              placeholder={searchPlaceholder}
              style={{ border: "none", background: "none", color: "inherit", font: "inherit", outline: "none", width: "100%" }}
            />
          </div>
          <div style={{ maxHeight: 240, overflowY: "auto" }}>
            {filtered.length === 0 && <div style={{ padding: "12px 14px", fontSize: 13, color: "var(--color-text-muted)" }}>{loading ? "Yuklanmoqda…" : emptyText}</div>}
            {filtered.map((o, i) => (
              <button
                key={o.value}
                type="button"
                role="option"
                aria-selected={o.value === value}
                className={`slash-item ${i === hl ? "hl" : ""}`}
                style={{ width: "100%" }}
                onClick={() => { onChange(o.value); setOpen(false); setQuery(""); }}
                onMouseEnter={() => setHl(i)}
              >
                <span style={{ display: "grid" }}>
                  <b style={{ fontWeight: 600 }}>{o.label}</b>
                  {o.sub && <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{o.sub}</span>}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
