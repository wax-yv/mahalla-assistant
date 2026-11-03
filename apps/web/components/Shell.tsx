"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { getMe, initAuthRedirect, logout, refreshMe, subscribeMe, type Me } from "@/lib/auth";

const NAV: Array<{ group: string; items: Array<{ href: string; label: string; icon: string }> }> = [
  {
    group: "Boshqaruv",
    items: [
      { href: "/dashboard", label: "Boshqaruv paneli", icon: "◎" },
      { href: "/chat", label: "AI assistent", icon: "✦" },
    ],
  },
  {
    group: "Aholi",
    items: [
      { href: "/citizens", label: "Fuqarolar", icon: "☰" },
      { href: "/families", label: "Oilalar va manzillar", icon: "⌂" },
    ],
  },
  {
    group: "Ish oqimi",
    items: [
      { href: "/cases", label: "Murojaatlar", icon: "❏" },
      { href: "/tasks", label: "Vazifalar", icon: "✓" },
      { href: "/worklogs", label: "Ish yozuvlari", icon: "≡" },
    ],
  },
  {
    group: "Bilim",
    items: [
      { href: "/documents", label: "Hujjatlar", icon: "◫" },
      { href: "/reports", label: "Hisobotlar", icon: "▤" },
      { href: "/legislation", label: "Qonunchilik", icon: "§" },
      { href: "/programs", label: "Kredit va subsidiya", icon: "₴" },
    ],
  },
  {
    group: "Tizim",
    items: [{ href: "/admin", label: "Sozlamalar va audit", icon: "⚙" }],
  },
];

const MOBILE = [
  { href: "/dashboard", label: "Panel", icon: "◎" },
  { href: "/citizens", label: "Fuqarolar", icon: "☰" },
  { href: "/chat", label: "Assistent", icon: "✦" },
  { href: "/tasks", label: "Vazifalar", icon: "✓" },
  { href: "/admin", label: "Sozlamalar", icon: "⚙" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<Me | null>(getMe());

  useEffect(() => {
    initAuthRedirect(() => router.replace("/login"));
    void refreshMe();
    const unsubscribe = subscribeMe(setUser);
    return () => {
      unsubscribe();
    };
  }, [router]);

  const navTo = (href: string) =>
    pathname === href || (href !== "/dashboard" && pathname.startsWith(href));

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">
          <Logo />
        </Link>
        {NAV.map((group) => (
          <div key={group.group}>
            <div className="nav-group">{group.group}</div>
            <nav className="nav">
              {group.items.map((item) => (
                <Link key={item.href} href={item.href} className={navTo(item.href) ? "active" : ""}>
                  <span className="ico" aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        ))}
        <div className="foot">
          <div>{user?.user.display_name ?? "Administrator"}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <ThemeToggle />
            <button className="btn sm" onClick={() => void logout().then(() => router.replace("/login"))}>
              Chiqish
            </button>
          </div>
        </div>
      </aside>
      <div style={{ flex: 1, minWidth: 0 }}>
        <header className="topbar">
          <Link href="/dashboard" className="tbrand">
            <Logo size={30} withText={false} />
            <span>Mahalla Assistant</span>
          </Link>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <ThemeToggle />
            <button
              className="btn sm"
              onClick={() => void logout().then(() => router.replace("/login"))}
            >
              Chiqish
            </button>
          </div>
        </header>
        <main className="page">{children}</main>
      </div>
      <nav className="bottombar" aria-label="Asosiy navigatsiya">
        {MOBILE.map((item) => (
          <Link key={item.href} href={item.href} className={navTo(item.href) ? "active" : ""}>
            <span className="ico" aria-hidden="true">
              {item.icon}
            </span>
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
