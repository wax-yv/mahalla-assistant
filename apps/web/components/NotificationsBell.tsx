"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  AlertTriangle, Bell, CheckCircle2, ClipboardList, Inbox, LoaderCircle, RefreshCw,
} from "@/components/ui/icons";
import { api } from "@/lib/api";

type TaskRow = { id: string; title: string; due_date: string | null; status: string; citizen_name?: string | null };
type CaseRow = { id: string; title: string; status: string; citizen_name?: string | null };
type DashboardQuality = { data_quality: { score: number; incomplete: number } };

type NotifState = {
  overdue: TaskRow[];
  today: TaskRow[];
  openCases: CaseRow[];
  quality: number | null;
  incomplete: number | null;
};

const EMPTY: NotifState = { overdue: [], today: [], openCases: [], quality: null, incomplete: null };

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<NotifState>(EMPTY);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const titleId = `${useId()}-bildirishnoma`;

  const load = useCallback(async () => {
    setLoading(true);
    const [tasks, cases, dashboard] = await Promise.allSettled([
      api.get<{ overdue: TaskRow[]; today: TaskRow[] }>("/dashboard/tasks"),
      api.get<{ items: CaseRow[] }>("/cases?status=open&page_size=5"),
      api.get<DashboardQuality>("/dashboard"),
    ]);
    setState({
      overdue: tasks.status === "fulfilled" ? tasks.value.overdue : [],
      today: tasks.status === "fulfilled" ? tasks.value.today : [],
      openCases: cases.status === "fulfilled" ? cases.value.items : [],
      quality: dashboard.status === "fulfilled" ? dashboard.value.data_quality.score : null,
      incomplete: dashboard.status === "fulfilled" ? dashboard.value.data_quality.incomplete : null,
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 120000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const alertCount = state.overdue.length + state.openCases.length;
  const qualityLow = state.quality !== null && state.quality < 100;

  return (
    <div className="notif" ref={ref}>
      <button
        className="icon-btn"
        aria-label={alertCount > 0 ? `Bildirishnomalar: ${alertCount} ta e’tibor talab qiladi` : "Bildirishnomalar"}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Bildirishnomalar"
        onClick={() => { setOpen((v) => !v); if (!open) void load(); }}
      >
        <Bell size={16} />
        {alertCount > 0 ? <span className="notif-dot">{alertCount > 99 ? "99+" : alertCount}</span> : null}
      </button>

      {open && (
        <div className="notif-panel" role="dialog" aria-labelledby={titleId}>
          <div className="notif-head">
            <h3 id={titleId}>Bildirishnomalar</h3>
            <button className="icon-btn" onClick={() => void load()} aria-label="Yangilash" title="Yangilash">
              {loading ? <LoaderCircle size={14} className="spin" /> : <RefreshCw size={14} />}
            </button>
          </div>

          <div className="notif-list">
            <Link className="notif-group" href="/tasks?timeframe=overdue" onClick={() => setOpen(false)}>
              <span className="ng-ico danger" aria-hidden="true"><AlertTriangle size={15} /></span>
              <span>
                Muddati o‘tgan vazifalar: <b>{state.overdue.length}</b> ta
              </span>
            </Link>

            <Link className="notif-group" href="/tasks?timeframe=today" onClick={() => setOpen(false)}>
              <span className="ng-ico warn" aria-hidden="true"><ClipboardList size={15} /></span>
              <span>
                Bugungi reja: <b>{state.today.length}</b> ta vazifa
              </span>
            </Link>

            <Link className="notif-group" href="/cases?status=open" onClick={() => setOpen(false)}>
              <span className="ng-ico info" aria-hidden="true"><Inbox size={15} /></span>
              <span>
                Ochiq murojaatlar: <b>{state.openCases.length}</b> ta
                {state.openCases.length > 0 ? (
                  <span className="text-faint"> · {state.openCases[0].title}</span>
                ) : null}
              </span>
            </Link>

            {qualityLow ? (
              <Link className="notif-group" href="/documents" onClick={() => setOpen(false)}>
                <span className="ng-ico warn" aria-hidden="true"><CheckCircle2 size={15} /></span>
                <span>
                  Ma’lumot sifati: <b>{state.quality}%</b> · to‘ldirilmagan yozuvlar: <b>{state.incomplete}</b>
                </span>
              </Link>
            ) : null}
          </div>

          <div className="notif-foot">
            Manbalar: vazifalar, murojaatlar va ma’lumot sifati — barchasi joriy bazadan olinadi.
          </div>
        </div>
      )}
    </div>
  );
}
