"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ChevronDown, LifeBuoy, LogOut, MessageCircleQuestion, Settings, UserCog,
} from "@/components/ui/icons";
import { avatar } from "@/lib/avatar";
import { logout, type Me } from "@/lib/auth";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  supervisor: "Nazoratchi",
  agent: "Xodim",
  viewer: "Ko‘ruvchi",
};

export function ProfileMenu({ user }: { user: Me | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const displayName = user?.user.display_name || "Administrator";
  const role = user?.user.role || "admin";
  const av = avatar(user?.user.id ?? displayName, displayName);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        ref.current?.querySelector<HTMLElement>("button")?.focus();
      }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) { setPos(null); return; }
    const trigger = ref.current?.querySelector<HTMLElement>(".user-card");
    const menu = menuRef.current;
    if (!trigger || !menu) return;
    const rect = trigger.getBoundingClientRect();
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    let left = rect.left;
    if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
    let top = rect.top - height - 8;
    if (top < 8) top = Math.min(rect.bottom + 8, window.innerHeight - height - 8);
    setPos({ left, top });
  }, [open]);

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="rel" ref={ref}>
      <button
        className="user-card"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Profil menyusi"
        onClick={() => setOpen((v) => !v)}
      >
        <span className={av.className} aria-hidden="true">{av.text}</span>
        <span className="uc-text">
          <span className="uc-name">{displayName}</span>
          <span className="uc-role">{ROLE_LABELS[role] ?? role}</span>
        </span>
        <ChevronDown size={15} className="uc-chevron" />
      </button>

      {open && (
        <div
          className="menu menu-fixed"
          role="menu"
          aria-label="Profil menyusi"
          ref={menuRef}
          style={{ left: pos?.left ?? 0, top: pos?.top ?? 0 }}
        >
          <div className="menu-head">
            <b>{displayName}</b>
            <span>{ROLE_LABELS[role] ?? role} · {user?.user.username ?? "admin"}</span>
          </div>
          <Link className="menu-item" role="menuitem" href="/chat" onClick={() => setOpen(false)}>
            <MessageCircleQuestion size={15} /> Mening so‘rovlarim
          </Link>
          <Link className="menu-item" role="menuitem" href="/admin" onClick={() => setOpen(false)}>
            <Settings size={15} /> Sozlamalar
          </Link>
          <Link className="menu-item" role="menuitem" href="/worklogs" onClick={() => setOpen(false)}>
            <UserCog size={15} /> Ish yozuvlari
          </Link>
          <a className="menu-item" role="menuitem" href="mailto:support@navbahor-mahalla.uz">
            <LifeBuoy size={15} /> Qo‘llab-quvvatlash
          </a>
          <div className="menu-sep" role="separator" />
          <button className="menu-item danger" role="menuitem" onClick={() => void signOut()}>
            <LogOut size={15} /> Chiqish
          </button>
        </div>
      )}
    </div>
  );
}
