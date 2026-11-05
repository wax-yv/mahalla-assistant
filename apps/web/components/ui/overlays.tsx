"use client";

import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { AlertTriangle, Check, Info, X } from "lucide-react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function useFocusTrap(open: boolean, onClose: () => void, ref: RefObject<HTMLElement | null>) {
  const previousRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousRef.current = document.activeElement as HTMLElement | null;

    const node = ref.current;
    const focusables = () =>
      Array.from(node?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
        (el) => el.offsetParent !== null || el === document.activeElement
      );

    const timer = window.setTimeout(() => {
      const list = focusables();
      (list[0] ?? node)?.focus();
    }, 0);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (list.length === 0) {
        e.preventDefault();
        node?.focus();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || !node?.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("keydown", onKey, true);
      previousRef.current?.focus?.();
    };
  }, [open, onClose, ref]);
}

export function Modal({
  open, onClose, title, children, footer, wide,
}: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useFocusTrap(open, onClose, ref);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  if (!open) return null;
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div
        className={`modal${wide ? " modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        tabIndex={-1}
      >
        <div className="modal-head">
          <h3 id={titleId}>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Yopish"><X size={17} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </>
  );
}

export function Drawer({
  open, onClose, title, children, footer, wide,
}: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useFocusTrap(open, onClose, ref);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  if (!open) return null;
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div
        className={`drawer${wide ? " drawer-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        tabIndex={-1}
      >
        <div className="drawer-head">
          <h3 id={titleId}>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Yopish"><X size={17} /></button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </div>
    </>
  );
}

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
      <div className="row-top">
        <span className={danger ? "text-danger-ico" : "text-warn-ico"}>
          <AlertTriangle size={20} />
        </span>
        <p className="fs-14">{message}</p>
      </div>
    </Modal>
  );
}

type Toast = { id: number; kind: "success" | "error" | "info"; text: string };
const ToastCtx = createContext<{ show: (kind: Toast["kind"], text: string) => void }>({ show: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const timers = useRef<Map<number, number>>(new Map());

  const clearTimer = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const show = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev.slice(-3), { id, kind, text }]);
    const timer = window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
      timers.current.delete(id);
    }, kind === "error" ? 7000 : 3500);
    timers.current.set(id, timer);
  }, []);

  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((timer) => window.clearTimeout(timer));
      map.clear();
    };
  }, []);

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <div className="toast-host" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === "success" ? <Check size={16} /> : t.kind === "error" ? <AlertTriangle size={16} /> : <Info size={16} />}
            <span className="toast-text">{t.text}</span>
            <button
              className="icon-btn"
              onClick={() => {
                clearTimer(t.id);
                setItems((prev) => prev.filter((x) => x.id !== t.id));
              }}
              aria-label="Yopish"
            >
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

export function SkeletonBlock({ h = 14, w = "100%", className = "" }: { h?: number; w?: number | string; className?: string }) {
  return <div className={`skeleton ${className}`} style={{ height: h, width: w }} />;
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="card" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skel-row">
          <SkeletonBlock h={13} w="38%" />
          <div className="skel-gap" />
          <SkeletonBlock h={11} w="62%" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonDashboard() {
  return (
    <div aria-hidden="true">
      <div className="grid grid-4 mb">
        {Array.from({ length: 4 }).map((_, i) => (
          <div className="card stat" key={i}>
            <div className="skel-stat">
              <SkeletonBlock h={44} w={44} className="skel-round" />
              <div className="skel-gap" />
              <SkeletonBlock h={11} w="55%" />
              <div className="skel-gap" />
              <SkeletonBlock h={26} w="40%" />
            </div>
          </div>
        ))}
      </div>
      <div className="split s2 mb">
        <SkeletonList rows={4} />
        <SkeletonList rows={3} />
      </div>
      <div className="split s2">
        <SkeletonList rows={5} />
        <SkeletonList rows={5} />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="card" aria-hidden="true">
      <div className="skel-row">
        <SkeletonBlock h={12} w="30%" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skel-row row-sm">
          {Array.from({ length: cols }).map((__, j) => (
            <SkeletonBlock key={j} h={12} w={j === 0 ? "28%" : "14%"} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChat() {
  return (
    <div className="card card-pad skel-chat" aria-hidden="true">
      <SkeletonBlock h={46} w="55%" className="skel-bubble" />
      <SkeletonBlock h={72} w="80%" className="skel-bubble" />
      <SkeletonBlock h={46} w="45%" className="skel-bubble" />
    </div>
  );
}

export function ErrorState({
  title = "Yuklab bo‘lmadi",
  note,
  onRetry,
}: {
  title?: string;
  note?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="card card-pad empty">
      <div className="icon text-danger-ico bg-danger-soft"><AlertTriangle size={20} /></div>
      <h3>{title}</h3>
      {note && <p>{note}</p>}
      <p className="text-faint fs-12_5 mt-xs">
        Internet aloqasini tekshirib, qayta urinishni bosing. Muammo davom etsa, boshqa sahifadan kirib ko‘ring.
      </p>
      {onRetry && (
        <div className="mt">
          <button className="btn" onClick={onRetry}>Qayta urinish</button>
        </div>
      )}
    </div>
  );
}
