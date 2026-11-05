"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot, ChartColumn, ClipboardCheck, Files, HandCoins, History, Home, Inbox,
  LayoutDashboard, Scale, Settings, Sparkles, Users,
} from "@/components/ui/icons";
import { PageHead } from "@/components/ui";

const SECTIONS: Array<{ group: string; items: Array<{ href: string; label: string; icon: typeof Home; note: string }> }> = [
  {
    group: "Boshqaruv",
    items: [
      { href: "/dashboard", label: "Boshqaruv paneli", icon: LayoutDashboard, note: "KPI, vazifa nazorati, ma’lumot sifati va oxirgi harakatlar" },
      { href: "/chat", label: "AI assistent", icon: Sparkles, note: "Manbali javob, tayyor buyruqlar va draft amallarni tasdiqlash" },
      { href: "/agents", label: "Agentlar", icon: Bot, note: "Agent holati, model zanjiri, token budjeti va provayderlar" },
    ],
  },
  {
    group: "Aholi",
    items: [
      { href: "/citizens", label: "Fuqarolar", icon: Users, note: "Fuqarolar bazasi, qidiruv, profil va arxivlash" },
      { href: "/families", label: "Oilalar va manzillar", icon: Home, note: "Ko‘chalar, uylar va oilalar ierarxiyasi" },
    ],
  },
  {
    group: "Ish oqimi",
    items: [
      { href: "/cases", label: "Murojaatlar", icon: Inbox, note: "Murojaat holati, ustuvorligi va bog‘langan vazifalar" },
      { href: "/tasks", label: "Vazifalar", icon: ClipboardCheck, note: "Muddat, ustuvorlik va dalil bilan bajarish" },
      { href: "/worklogs", label: "Ish yozuvlari", icon: History, note: "Uchrashuv, telefon, tavsiya va bajarilgan ishlar jurnali" },
    ],
  },
  {
    group: "Bilim",
    items: [
      { href: "/documents", label: "Hujjatlar", icon: Files, note: "Fayl yuklash, ustun mapping’i, xatolar hisoboti va eksport" },
      { href: "/reports", label: "Hisobotlar", icon: ChartColumn, note: "Kunlik, haftalik va oylik hisobotlar, tasdiqlash va eksport" },
      { href: "/legislation", label: "Qonunchilik", icon: Scale, note: "Lex.uz dan jonli sinxronlash va manbali savol-javob" },
      { href: "/programs", label: "Kredit va subsidiya", icon: HandCoins, note: "Davlat dasturlari katalogi va fuqaro mosligini tekshirish" },
    ],
  },
  {
    group: "Tizim",
    items: [
      { href: "/admin", label: "Sozlamalar va audit", icon: Settings, note: "AI konfiguratsiyasi, audit jurnali, sarflar va joblar" },
    ],
  },
];

export default function AllSectionsPage() {
  const pathname = usePathname();
  return (
    <>
      <PageHead
        kicker="Navigatsiya"
        title="Barcha bo‘limlar"
        lede="Tizimdagi barcha bo‘limlar bir ro‘yxatda. Har bir bo‘lim o‘z vazifasini qisqacha izohlaydi."
      />

      <div className="stack-lg">
        {SECTIONS.map((section) => (
          <section key={section.group} className="card card-pad">
            <h3 className="mb">{section.group}</h3>
            <div className="grid grid-2">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`stat-hover card card-flat panel-soft card-pad-sm nav-card${active ? " active" : ""}`}
                    aria-current={active ? "page" : undefined}
                  >
                    <div className="row-top">
                      <span className="stat-icon teal" aria-hidden="true"><Icon size={19} /></span>
                      <span className="min0">
                        <b className="fs-14">{item.label}</b>
                        <span className="text-soft fs-13 block">{item.note}</span>
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
