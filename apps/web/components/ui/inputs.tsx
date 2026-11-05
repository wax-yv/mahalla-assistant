"use client";

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDown, LoaderCircle, Search, X } from "lucide-react";

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

export type Option = { value: string; label: string; sub?: string };

export function SearchSelect({
  value, onChange, options, placeholder = "Tanlang…", searchPlaceholder = "Qidirish…", loading = false, emptyText = "Hech narsa topilmadi", clearable = false, disabled = false, id,
}: {
  value: string; onChange: (value: string) => void; options: Option[];
  placeholder?: string; searchPlaceholder?: string; loading?: boolean; emptyText?: string;
  clearable?: boolean; disabled?: boolean; id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hl, setHl] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (i: number) => `${baseId}-opt-${i}`;
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

  useEffect(() => {
    setHl((h) => Math.min(h, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLElement>(`#${CSS.escape(optionId(hl))}`)?.scrollIntoView({ block: "nearest" });
  }, [hl, open, filtered.length]);

  function commit(index: number) {
    const item = filtered[index];
    if (!item) return;
    onChange(item.value);
    setOpen(false);
    setQuery("");
  }

  return (
    <div ref={boxRef} className="ss">
      <button
        id={id}
        type="button"
        className="select select-pl"
        onClick={() => !disabled && setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        disabled={disabled}
      >
        <span className={selected ? "" : "select-placeholder"}>
          {selected ? selected.label : placeholder}
        </span>
        {loading ? <LoaderCircle size={15} className="spin" /> : <ChevronDown size={15} className="shrink0" />}
      </button>
      {selected && clearable && !disabled && (
        <button
          className="icon-btn ss-clear"
          aria-label="Tozalash"
          onClick={() => { onChange(""); setQuery(""); }}
        >
          <X size={14} />
        </button>
      )}
      {open && (
        <div className="ss-panel">
          <div className="ss-search">
            <Search size={15} className="shrink0 text-faint" />
            <input
              autoFocus
              value={query}
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={filtered.length ? optionId(hl) : undefined}
              aria-label={searchPlaceholder}
              onChange={(e) => { setQuery(e.target.value); setHl(0); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setHl((h) => Math.min(h + 1, filtered.length - 1)); }
                if (e.key === "ArrowUp") { e.preventDefault(); setHl((h) => Math.max(0, h - 1)); }
                if (e.key === "Home" && filtered.length) { e.preventDefault(); setHl(0); }
                if (e.key === "End" && filtered.length) { e.preventDefault(); setHl(filtered.length - 1); }
                if (e.key === "Enter" && filtered[hl]) { e.preventDefault(); commit(hl); }
                if (e.key === "Escape") { e.stopPropagation(); setOpen(false); }
                if (e.key === "Tab") setOpen(false);
              }}
              placeholder={searchPlaceholder}
            />
          </div>
          <div className="ss-list" ref={listRef} id={listId} role="listbox" aria-label={searchPlaceholder}>
            {filtered.length === 0 && (
              <div className="ss-empty">{loading ? "Ma’lumotlar yuklanmoqda, iltimos kunting…" : emptyText}</div>
            )}
            {filtered.map((o, i) => (
              <button
                key={o.value}
                id={optionId(i)}
                type="button"
                role="option"
                aria-selected={o.value === value}
                className={`slash-item ss-option${i === hl ? " hl" : ""}`}
                onClick={() => commit(i)}
                onMouseEnter={() => setHl(i)}
              >
                <span className="ss-option-main">
                  <b className="fw-600">{o.label}</b>
                  {o.sub && <span className="fs-12 text-faint">{o.sub}</span>}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
