"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  ArrowRight, Bot, ClipboardList, FileText, HandCoins, Home, Inbox, LayoutDashboard,
  LoaderCircle, Scale, Search, Settings, Users,
} from "@/components/ui/icons";
import { api } from "@/lib/api";

type Group = "navigatsiya" | "fuqarolar" | "murojaatlar" | "oilalar" | "hujjatlar" | "qonun";

type Result = {
  id: string;
  group: Group;
  title: string;
  sub: string;
  href: string;
  icon: React.ReactNode;
};

type NavTarget = { href: string; label: string; icon: React.ReactNode };

const NAV_TARGETS: NavTarget[] = [
  { href: "/dashboard", label: "Boshqaruv paneli", icon: <LayoutDashboard size={15} /> },
  { href: "/citizens", label: "Fuqarolar", icon: <Users size={15} /> },
  { href: "/families", label: "Oilalar va manzillar", icon: <Home size={15} /> },
  { href: "/cases", label: "Murojaatlar", icon: <Inbox size={15} /> },
  { href: "/tasks", label: "Vazifalar", icon: <ClipboardList size={15} /> },
  { href: "/worklogs", label: "Ish yozuvlari", icon: <FileText size={15} /> },
  { href: "/chat", label: "AI assistent", icon: <Bot size={15} /> },
  { href: "/documents", label: "Hujjatlar", icon: <FileText size={15} /> },
  { href: "/reports", label: "Hisobotlar", icon: <FileText size={15} /> },
  { href: "/legislation", label: "Qonunchilik", icon: <Scale size={15} /> },
  { href: "/programs", label: "Kredit va subsidiya", icon: <HandCoins size={15} /> },
  { href: "/admin", label: "Sozlamalar va audit", icon: <Settings size={15} /> },
];

const GROUP_LABELS: Record<Group, string> = {
  navigatsiya: "Bo‘limlar",
  fuqarolar: "Fuqarolar",
  murojaatlar: "Murojaatlar",
  oilalar: "Oilalar",
  hujjatlar: "Hujjatlar",
  qonun: "Qonunchilik",
};

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const [hl, setHl] = useState(0);
  const baseId = useId();
  const listId = `${baseId}-results`;
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const node = listRef.current?.closest(".cmdk") as HTMLElement | null;

    const focusables = () =>
      Array.from(
        (node?.querySelectorAll<HTMLElement>(
          'input:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
        ) ?? [])
      ).filter((el) => el.offsetParent !== null);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (list.length === 0) { e.preventDefault(); inputRef.current?.focus(); return; }
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || !node?.contains(active))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault(); first.focus();
      }
    };

    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      previous?.focus?.();
    };
  }, [open, close]);

  const runSearch = useCallback(async (raw: string) => {
    const q = raw.trim();
    const token = ++seq.current;

    if (q.length === 0) {
      setResults([]);
      setLoading(false);
      return;
    }

    const nav: Result[] = NAV_TARGETS
      .filter((t) => t.label.toLowerCase().includes(q.toLowerCase()))
      .slice(0, 4)
      .map((t) => ({ id: `nav-${t.href}`, group: "navigatsiya", title: t.label, sub: "Bo‘limga o‘tish", href: t.href, icon: t.icon }));

    setResults(nav);
    setLoading(true);

    type LawItem = { document: { id: string; title: string; number?: string }; chunk?: { article?: string } };

    const lawsPromise: Promise<{ items: LawItem[] }> =
      q.length >= 2
        ? api.get<{ items: LawItem[] }>(`/legislation/search?q=${encodeURIComponent(q)}&limit=4`)
        : Promise.resolve({ items: [] });

    const [citizens, cases, families, documents, laws] = await Promise.allSettled([
      api.get<{ items: Array<{ id: string; full_name: string; phone?: string; address?: { address_label?: string } | null }> }>(
        `/citizens?q=${encodeURIComponent(q)}&page_size=5`
      ),
      api.get<{ items: Array<{ id: string; title: string; citizen_name?: string | null; status: string }> }>(
        `/cases?q=${encodeURIComponent(q)}&page_size=5`
      ),
      api.get<{ items: Array<{ id: string; family_head_name?: string | null; family_type?: string; address?: { address_label?: string } | null }> }>(
        `/families?q=${encodeURIComponent(q)}&page_size=4`
      ),
      api.get<{ items: Array<{ id: string; original_name: string; kind: string }> }>(
        `/documents?q=${encodeURIComponent(q)}&page_size=4`
      ),
      lawsPromise,
    ]);

    if (token !== seq.current) return;

    const next: Result[] = [...nav];
    if (citizens.status === "fulfilled") {
      for (const c of citizens.value.items) {
        next.push({
          id: `cit-${c.id}`,
          group: "fuqarolar",
          title: c.full_name,
          sub: [c.id, c.address?.address_label].filter(Boolean).join(" · "),
          href: `/citizens/${c.id}`,
          icon: <Users size={15} />,
        });
      }
    }
    if (cases.status === "fulfilled") {
      for (const c of cases.value.items) {
        next.push({
          id: `case-${c.id}`,
          group: "murojaatlar",
          title: c.title,
          sub: [c.id, c.citizen_name].filter(Boolean).join(" · "),
          href: `/cases/${c.id}`,
          icon: <Inbox size={15} />,
        });
      }
    }
    if (families.status === "fulfilled") {
      for (const f of families.value.items) {
        next.push({
          id: `fam-${f.id}`,
          group: "oilalar",
          title: f.family_head_name || f.id,
          sub: [f.id, f.family_type, f.address?.address_label].filter(Boolean).join(" · "),
          href: `/families?focus=${f.id}`,
          icon: <Home size={15} />,
        });
      }
    }
    if (documents.status === "fulfilled") {
      for (const d of documents.value.items) {
        next.push({
          id: `doc-${d.id}`,
          group: "hujjatlar",
          title: d.original_name,
          sub: `Hujjat · ${d.kind}`,
          href: "/documents",
          icon: <FileText size={15} />,
        });
      }
    }
    if (laws.status === "fulfilled") {
      for (const l of laws.value.items) {
        next.push({
          id: `law-${l.document.id}-${l.chunk?.article ?? ""}`,
          group: "qonun",
          title: l.document.title,
          sub: [l.document.number, l.chunk?.article].filter(Boolean).join(" · "),
          href: "/legislation",
          icon: <Scale size={15} />,
        });
      }
    }

    setResults(next);
    setHl(0);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => void runSearch(query), 250);
    return () => window.clearTimeout(timer);
  }, [query, open, runSearch]);

  const grouped = useMemo(() => {
    const map = new Map<Group, Result[]>();
    for (const r of results) {
      const list = map.get(r.group) ?? [];
      list.push(r);
      map.set(r.group, list);
    }
    return Array.from(map.entries());
  }, [results]);

  const flat = useMemo(() => grouped.flatMap(([, list]) => list), [grouped]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLElement>(`#${CSS.escape(`${baseId}-opt-${hl}`)}`)?.scrollIntoView({ block: "nearest" });
  }, [hl, open, baseId, results]);

  function go(result: Result) {
    close();
    router.push(result.href);
  }

  if (!open) return null;

  return (
    <>
      <div className="overlay" onClick={close} />
      <div className="cmdk" role="dialog" aria-modal="true" aria-label="Universal qidiruv">
        <div className="cmdk-input-row">
          <Search size={18} className="shrink0 text-faint" />
          <input
            ref={inputRef}
            value={query}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={flat.length ? `${baseId}-opt-${hl}` : undefined}
            aria-label="Fuqaro, murojaat, oila, hujjat yoki bo‘lim qidiring"
            placeholder="Fuqaro, murojaat, oila, hujjat yoki bo‘lim…"
            onChange={(e) => { setQuery(e.target.value); setHl(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setHl((h) => Math.min(h + 1, flat.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setHl((h) => Math.max(0, h - 1)); }
              if (e.key === "Home" && flat.length) { e.preventDefault(); setHl(0); }
              if (e.key === "End" && flat.length) { e.preventDefault(); setHl(flat.length - 1); }
              if (e.key === "Enter" && flat[hl]) { e.preventDefault(); go(flat[hl]); }
              if (e.key === "Escape") { e.preventDefault(); close(); }
            }}
          />
          {loading ? <LoaderCircle size={16} className="spin text-faint" /> : null}
          <span className="kbd">Esc</span>
        </div>

        <div className="cmdk-results" ref={listRef} id={listId} role="listbox" aria-label="Qidiruv natijalari">
          {flat.length === 0 && !loading ? (
            <div className="ss-empty">
              {query.trim().length === 0
                ? "Qidiruvni boshlash uchun kamida 1 ta harf yozing."
                : "Hech narsa topilmadi. Qidiruvni qisqartirib ko‘ring."}
            </div>
          ) : null}

          {grouped.map(([group, list]) => (
            <div key={group}>
              <div className="cmdk-group-label">{GROUP_LABELS[group]}</div>
              {list.map((item) => {
                const index = flat.indexOf(item);
                return (
                  <button
                    key={item.id}
                    id={`${baseId}-opt-${index}`}
                    type="button"
                    role="option"
                    aria-selected={index === hl}
                    className={`cmdk-item${index === hl ? " hl" : ""}`}
                    onMouseEnter={() => setHl(index)}
                    onClick={() => go(item)}
                  >
                    <span className="ci-ico" aria-hidden="true">{item.icon}</span>
                    <span className="ci-main">
                      <span className="ci-title">{item.title}</span>
                      <span className="ci-sub">{item.sub}</span>
                    </span>
                    <ArrowRight size={14} className="ci-go" />
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="cmdk-foot">
          <span><span className="kbd">↑</span> <span className="kbd">↓</span> tanlash</span>
          <span><span className="kbd">Enter</span> ochish</span>
          <span><span className="kbd">Esc</span> yopish</span>
          <span className="grow" />
          <span>Manbalar: fuqarolar, murojaatlar, oilalar, hujjatlar, qonunchilik</span>
        </div>
      </div>
    </>
  );
}
