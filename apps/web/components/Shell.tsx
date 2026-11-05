"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bot, ClipboardList, FileText, HandCoins, History, Home, Inbox, LayoutDashboard,
  ListChecks, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Scale, Settings, Users, X,
} from "@/components/ui/icons";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Drawer } from "@/components/ui/overlays";
import { getMe, initAuthRedirect, logout, refreshMe, subscribeMe, type Me } from "@/lib/auth";

type NavItem = { href: string; label: string; icon: typeof Home };
type NavGroup = { group: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    group: "Boshqaruv",
    items: [
      { href: "/dashboard", label: "Boshqaruv paneli", icon: LayoutDashboard },
      { href: "/chat", label: "AI assistent", icon: Bot },
      { href: "/agents", label: "Agentlar", icon: ListChecks },
    ],
  },
  {
    group: "Aholi",
    items: [
      { href: "/citizens", label: "Fuqarolar", icon: Users },
      { href: "/families", label: "Oilalar va manzillar", icon: Home },
    ],
  },
  {
    group: "Ish oqimi",
    items: [
      { href: "/cases", label: "Murojaatlar", icon: Inbox },
      { href: "/tasks", label: "Vazifalar", icon: ClipboardList },
      { href: "/worklogs", label: "Ish yozuvlari", icon: History },
    ],
  },
  {
    group: "Bilim",
    items: [
      { href: "/documents", label: "Hujjatlar", icon: FileText },
      { href: "/reports", label: "Hisobotlar", icon: FileText },
      { href: "/legislation", label: "Qonunchilik", icon: Scale },
      { href: "/programs", label: "Kredit va subsidiya", icon: HandCoins },
    ],
  },
  {
    group: "Tizim",
    items: [{ href: "/admin", label: "Sozlamalar va audit", icon: Settings }],
  },
];

const MOBILE_MAIN = [
  { href: "/dashboard", label: "Panel", icon: LayoutDashboard },
  { href: "/citizens", label: "Fuqarolar", icon: Users },
  { href: "/chat", label: "Assistent", icon: Bot },
  { href: "/tasks", label: "Vazifalar", icon: ClipboardList },
];

function isActive(pathname: string, href: string) {
  return pathname === href || (href !== "/dashboard" && pathname.startsWith(href + "/"));
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<Me | null>(getMe());
  const [collapsed, setCollapsed] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    initAuthRedirect(() => router.replace("/login"));
    void refreshMe();
    return subscribeMe(setUser);
  }, [router]);

  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  const currentLabel =
    NAV.flatMap((g) => g.items).find((item) => isActive(pathname, item.href))?.label ?? "Mahalla Assistant";

  function navLink(item: NavItem, collapsedView: boolean) {
    const active = isActive(pathname, item.href);
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        className={active ? "active" : ""}
        title={collapsedView ? item.label : undefined}
        aria-label={item.label}
        aria-current={active ? "page" : undefined}
      >
        <span className="ico" aria-hidden="true">
          <Icon size={18} strokeWidth={1.9} />
        </span>
        {!collapsedView && <span className="lbl">{item.label}</span>}
      </Link>
    );
  }

  const restOfRoutes = NAV.flatMap((g) => g.items).filter(
    (item) => !MOBILE_MAIN.some((m) => m.href === item.href)
  );

  return (
    <div className="shell">
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`} style={{ position: "relative" }}>
        {!collapsed && (
          <button
            className="collapse-btn"
            onClick={() => setCollapsed(true)}
            aria-label="Sahifani yig‘ish"
            title="Sahifani yig‘ish"
          >
            <PanelLeftClose size={14} />
          </button>
        )}
        {collapsed && (
          <button
            className="collapse-btn"
            onClick={() => setCollapsed(false)}
            aria-label="Sahifani ochish"
            title="Sahifani ochish"
            style={{ right: -12 }}
          >
            <PanelLeftOpen size={14} />
          </button>
        )}
        <Link href="/dashboard" className="brand" aria-label="Boshqaruv paneli">
          <Logo collapsed={collapsed} />
        </Link>
        {NAV.map((group) => (
          <div key={group.group}>
            <div className="nav-group">{group.group}</div>
            <nav className="nav" aria-label={group.group}>
              {group.items.map((item) => navLink(item, collapsed))}
            </nav>
          </div>
        ))}
        <div className="foot">
          <div className="who">{user?.user.display_name ?? "Administrator"}</div>
          <div className="actions">
            {!collapsed && <ThemeToggle />}
            <button
              className="btn sm ghost danger"
              onClick={() => void logout().then(() => router.replace("/login"))}
              aria-label="Tizimdan chiqish"
              title="Tizimdan chiqish"
            >
              <LogOut size={15} />
              {!collapsed && <span>Chiqish</span>}
            </button>
          </div>
        </div>
      </aside>

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            <span className="mobile-only tbrand">
              <Logo size={28} withText={false} />
            </span>
            <span className="crumb">
              <span aria-hidden="true">/</span>
              <b>{currentLabel}</b>
            </span>
          </div>
          <div className="tactions">
            <ThemeToggle />
            <button
              className="btn sm mobile-only"
              aria-label="Boshqa bo‘limlar"
              onClick={() => setMoreOpen(true)}
            >
              <Menu size={15} />
              <span>Boshqa</span>
            </button>
            <span className="text-faint nowrap hide-sm" style={{ fontSize: 12.5 }}>
              {user?.user.display_name ?? ""}
            </span>
            <button
              className="icon-btn"
              onClick={() => void logout().then(() => router.replace("/login"))}
              aria-label="Tizimdan chiqish"
              title="Tizimdan chiqish"
            >
              <LogOut size={16} />
            </button>
          </div>
        </header>
        <main className="page">{children}</main>
      </div>

      <nav className="bottombar" aria-label="Asosiy navigatsiya">
        {MOBILE_MAIN.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={isActive(pathname, item.href) ? "active" : ""}
              aria-current={isActive(pathname, item.href) ? "page" : undefined}
            >
              <span className="ico" aria-hidden="true">
                <Icon size={19} strokeWidth={1.9} />
              </span>
              {item.label}
            </Link>
          );
        })}
        <button
          className=""
          style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "inherit" }}
          onClick={() => setMoreOpen(true)}
          aria-label="Boshqa bo‘limlar"
        >
          <span className="ico" aria-hidden="true">
            <Menu size={19} strokeWidth={1.9} />
          </span>
          Boshqa
        </button>
      </nav>

      <Drawer open={moreOpen} onClose={() => setMoreOpen(false)} title="Boshqa bo‘limlar">
        <div className="nav" style={{ display: "grid", gap: 2 }}>
          {restOfRoutes.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  display: "flex", alignItems: "center", gap: 11, padding: "11px 12px",
                  borderRadius: "var(--radius-sm)", fontWeight: 600, fontSize: 14,
                  background: active ? "var(--brand-soft)" : "transparent",
                  color: active ? "var(--brand-strong)" : "var(--color-text-secondary)",
                }}
              >
                <Icon size={18} strokeWidth={1.9} />
                {item.label}
              </Link>
            );
          })}
        </div>
      </Drawer>
    </div>
  );
}
