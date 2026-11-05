"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "@/components/ui/icons";

export function applyTheme(theme: "light" | "dark" | "system") {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  localStorage.setItem("mahalla-theme", theme);
}

const ORDER = ["light", "dark", "system"] as const;
const META: Record<(typeof ORDER)[number], { icon: typeof Sun; label: string }> = {
  light: { icon: Sun, label: "Yorug‘" },
  dark: { icon: Moon, label: "Tungi" },
  system: { icon: Monitor, label: "Tizim" },
};

export function ThemeToggle() {
  const [theme, setTheme] = useState<(typeof ORDER)[number]>("system");
  useEffect(() => {
    setTheme((localStorage.getItem("mahalla-theme") as (typeof ORDER)[number]) ?? "system");
  }, []);
  const next = () => {
    const value = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(value);
    applyTheme(value);
  };
  const Icon = META[theme].icon;
  return (
    <button className="btn sm" onClick={next} title={`Mavzu: ${META[theme].label}`} aria-label={`Mavzu: ${META[theme].label}. Almashtirish uchun bosing`}>
      <Icon size={14} />
      <span className="nowrap hide-sm">{META[theme].label}</span>
    </button>
  );
}
