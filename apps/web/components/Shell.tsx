"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bot, ChartColumn, ClipboardCheck, Files, HandCoins, History, Home, Inbox,
  LayoutDashboard, LogOut, Menu, MessagesSquare, PanelLeftClose, PanelLeftOpen,
  Scale, Search, Settings, Sparkles, Users,
} from "@/components/ui/icons";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Drawer } from "@/components/ui/overlays";
import { CommandPalette } from "@/components/CommandPalette";
import { NotificationsBell } from "@/components/NotificationsBell";
import { ProfileMenu } from "@/components/ProfileMenu";
import { getMe, initAuthRedirect, logout, refreshMe, subscribeMe, type Me } from "@/lib/auth";

type NavItem = { href: string; label: string; icon: typeof Home };
type NavGroup = { group: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    group: "Boshqaruv",
    items: [
      { href: "/dashboard", label: "Boshqaruv paneli", icon: LayoutDashboard },
      { href: "/chat", label: "AI assistent", icon: Sparkles },
      { href: "/agents", label: "Agentlar", icon: Bot },
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
      { href: "/cases", label: "Murojaatlar", icon: MessagesSquare },
      { href: "/tasks", label: "Vazifalar", icon: ClipboardCheck },
      { href: "/worklogs", label: "Ish yozuvlari", icon: History },
    ],
  },
  {
    group: "Bilim",
    items: [
      { href: "/documents", label: "Hujjatlar", icon: Files },
      { href: "/reports", label: "Hisobotlar", icon: ChartColumn },
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
  { href: "/chat", label: "Assistent", icon: Sparkles },
  { href: "/tasks", label: "Vazifalar", icon: ClipboardCheck },
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
  const [drawerQuery, setDrawerQuery] = useState("");

  useEffect(() => {
    initAuthRedirect(() => router.replace("/login"));
    void refreshMe();
    return subscribeMe(setUser);
  }, [router]);

  useEffect(() => {
    setMoreOpen(false);
    setDrawerQuery("");
  }, [pathname]);

  const currentLabel =
    NAV.flatMap((g) => g.items).find((item) => isActive(pathname, item.href))?.label ?? "Mahalla Assistant";

  function navLink(item: NavItem, collapsedView: boolean) {
    const active = isActive(pathname, item.href);
    const Icon = item.icon;
    const link = (
      <Link
        key={item.href}
        href={item.href}
        className={active ? "active" : ""}
        aria-label={item.label}
        aria-current={active ? "page" : undefined}
      >
        <span className="ico" aria-hidden="true">
          <Icon size={18} strokeWidth={1.9} />
        </span>
        {!collapsedView && <span className="lbl">{item.label}</span>}
      </Link>
    );
    if (!collapsedView) return link;
    return (
      <span className="tooltip-wrap" key={item.href}>
        {link}
        <span className="tooltip" role="presentation">{item.label}</span>
      </span>
    );
  }

  const allRoutes = NAV.flatMap((g) => g.items);
  const restOfRoutes = allRoutes.filter((item) => !MOBILE_MAIN.some((m) => m.href === item.href));
  const filteredRest = drawerQuery.trim()
    ? restOfRoutes.filter((item) => item.label.toLowerCase().includes(drawerQuery.trim().toLowerCase()))
    : restOfRoutes;

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Asosiy kontentga o‘tish</a>

      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <button
          className="collapse-btn"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? "Sahifani ochish" : "Sahifani yig‘ish"}
          title={collapsed ? "Sahifani ochish" : "Sahifani yig‘ish"}
        >
          {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>

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
          <ProfileMenu user={user} />
        </div>
      </aside>

      <div className="shell-main">
        <header className="topbar">
          <div className="tleft">
            <span className="mobile-only tbrand">
              <Logo size={28} withText={false} />
            </span>
            <span className="crumb">
              <span aria-hidden="true">/</span>
              <b>{currentLabel}</b>
            </span>
          </div>

          <button
            className="topbar-search"
            onClick={() => {
              document.dispatchEvent(
                new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true })
              );
            }}
            aria-label="Universal qidiruvni ochish (Ctrl+K)"
          >
            <Search size={15} />
            <span className="ts-label">Qidirish…</span>
            <span className="kbd">Ctrl K</span>
          </button>

          <div className="tactions">
            <NotificationsBell />
            <ThemeToggle />
            <button
              className="icon-btn mobile-only"
              aria-label="Barcha bo‘limlar"
              title="Barcha bo‘limlar"
              onClick={() => setMoreOpen(true)}
            >
              <Menu size={16} />
            </button>
            <span className="text-faint nowrap hide-sm fs-12_5">
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

        <main className="page" id="main" tabIndex={-1}>
          {children}
          <footer className="app-footer no-print">
            <span>© 2026 Navbahor mahallasi</span>
            <span>Ma’lumot himoyalangan</span>
            <span>Versiya {user?.version ?? "1.0"}</span>
            <Link href="/admin">Qo‘llab-quvvatlash</Link>
          </footer>
        </main>
      </div>

      <nav className="bottombar" aria-label="Asosiy navigatsiya">
        {MOBILE_MAIN.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
          return (
            <Link key={item.href} href={item.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
              <span className="ico" aria-hidden="true">
                <Icon size={19} strokeWidth={1.9} />
              </span>
              {item.label}
            </Link>
          );
        })}
        <Link
          href="/bo-limlar"
          className={pathname === "/bo-limlar" ? "active" : ""}
          aria-current={pathname === "/bo-limlar" ? "page" : undefined}
          aria-label="Boshqa bo‘limlar — barcha bo‘limlar katalogi"
        >
          <span className="ico" aria-hidden="true">
            <Menu size={19} strokeWidth={1.9} />
          </span>
          Boshqa
        </Link>
      </nav>

      <Drawer open={moreOpen} onClose={() => setMoreOpen(false)} title="Barcha bo‘limlar">
        <div className="stack-sm mb">
          <div className="search-field w-full">
            <Search size={15} className="search-ico" />
            <input
              className="input"
              placeholder="Bo‘lim nomini yozing…"
              value={drawerQuery}
              onChange={(e) => setDrawerQuery(e.target.value)}
              aria-label="Bo‘limlarni filtrlash"
            />
          </div>
        </div>
        <nav className="nav" aria-label="Barcha bo‘limlar">
          {filteredRest.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "active" : ""}
                aria-current={active ? "page" : undefined}
              >
                <span className="ico" aria-hidden="true">
                  <Icon size={18} strokeWidth={1.9} />
                </span>
                {item.label}
              </Link>
            );
          })}
          {filteredRest.length === 0 && <p className="text-faint fs-13_5">Mos bo‘lim topilmadi.</p>}
        </nav>
        <Link className="btn secondary mt" href="/bo-limlar" onClick={() => setMoreOpen(false)}>
          Barcha bo‘limlar katalogi
        </Link>
      </Drawer>

      <CommandPalette />
    </div>
  );
}
