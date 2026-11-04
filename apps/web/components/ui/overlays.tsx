"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, Check, Info, X } from "lucide-react";

/* ---------------- Modal ---------------- */
export function Modal({
  open, onClose, title, children, footer, width,
}: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; width?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    ref.current?.querySelector<HTMLElement>("button, input, select, textarea")?.focus();
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={ref} style={width ? { width: `min(${width}px, calc(100vw - 24px))` } : undefined}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Yopish"><X size={17} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </>
  );
}

/* ---------------- Drawer ---------------- */
export function Drawer({
  open, onClose, title, children, footer, wide,
}: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    ref.current?.querySelector<HTMLElement>("button, input, select, textarea")?.focus();
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="drawer" role="dialog" aria-modal="true" aria-label={title} ref={ref} style={wide ? { width: "min(680px, 100vw)" } : undefined}>
        <div className="drawer-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Yopish"><X size={17} /></button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </div>
    </>
  );
}

/* ---------------- ConfirmDialog ---------------- */
export function ConfirmDialog({
  open, onClose, onConfirm, title, message, confirmLabel = "Tasdiqlash", danger = true, busy = false,
}: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: string; message: string;
  confirmLabel?: string; danger?: boolean; busy?: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button className="btn ghost" onClick={onClose} disabled={busy}>Bekor qilish</button>
          <button className={`btn ${danger ? "danger" : "primary"}`} onClick={onConfirm} disabled={busy}>
            {busy ? "Bajarilmoqda…" : confirmLabel}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <span style={{ color: danger ? "var(--color-danger)" : "var(--color-warning)", marginTop: 2, flexShrink: 0 }}>
          <AlertTriangle size={20} />
        </span>
        <p style={{ fontSize: 14 }}>{message}</p>
      </div>
    </Modal>
  );
}

/* ---------------- Toast ---------------- */
type Toast = { id: number; kind: "success" | "error" | "info"; text: string };
const ToastCtx = createContext<{ show: (kind: Toast["kind"], text: string) => void }>({ show: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const show = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev.slice(-3), { id, kind, text }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <div className="toast-host" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === "success" ? <Check size={16} /> : t.kind === "error" ? <AlertTriangle size={16} /> : <Info size={16} />}
            <span style={{ flex: 1 }}>{t.text}</span>
            <button className="icon-btn" onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))} aria-label="Yopish">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

/* ---------------- States ---------------- */
export function SkeletonBlock({ h = 14, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />;
}

export function SkeletonList({ rows = 4, height = 52 }: { rows?: number; height?: number }) {
  return (
    <div className="card" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ padding: "14px 18px", borderBottom: i < rows - 1 ? "1px solid var(--color-border)" : undefined }}>
          <SkeletonBlock h={13} w="38%" />
          <div style={{ height: 6 }} />
          <SkeletonBlock h={11} w="62%" />
        </div>
      ))}
      <div style={{ height: height * 0 }} />
    </div>
  );
}

export function ErrorState({ title = "Xatolik yuz berdi", note, onRetry }: { title?: string; note?: string; onRetry?: () => void }) {
  return (
    <div className="card card-pad empty">
      <div className="icon" style={{ color: "var(--color-danger)", background: "var(--danger-soft)" }}><AlertTriangle size={20} /></div>
      <h3>{title}</h3>
      {note && <p>{note}</p>}
      {onRetry && (
        <div style={{ marginTop: 14 }}>
          <button className="btn" onClick={onRetry}>Qayta urinish</button>
        </div>
      )}
    </div>
  );
}
